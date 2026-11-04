"""Frozen synthetic challenge and matched text/evidence ablation; no score targets."""
import csv
import hashlib
import json
import math
import re
import tempfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

from app.communication.catalog import ROOTS
from app.communication.diagnosis import MultiComponentAgent,confidence_from
from app.communication.evaluation import legacy_prediction,fit_calibration
from app.communication.storage import persist_dataset
from app.evaluation.evaluation import _fresh_conn
from app.models import Complaint
from app.research.dataset import generate_challenge,hash_value
from app.services.tickets import decide,POLICY_FILE


def target(annotation):
    if not annotation['evidence_sufficient']:
        return 'inconclusive'
    return '+'.join(annotation['physical_roots']) or 'none'


def tokens(text):
    return set(re.findall(r'[a-z]{3,}',text.lower()))


class MatchedAgent:
    """Same symptom model in both arms; logs impose a causal evidence gate.

    Multinomial naive Bayes is fitted only on train symptoms. This small model
    is a baseline, not a pretrained language model or a production confidence.
    """
    def __init__(self,training):
        self.documents=Counter();self.counts={};self.vocabulary=set()
        for row in training:
            label=target(row['annotations']);words=tokens(row['complaint'])
            self.documents[label]+=1
            self.counts.setdefault(label,Counter()).update(words);self.vocabulary.update(words)
        self.threshold=.45  # Prespecified; not selected using final test errors.

    def text(self,complaint):
        scores={}
        words=tokens(complaint)&self.vocabulary
        for label,n in self.documents.items():
            denominator=sum(self.counts[label].values())+len(self.vocabulary)
            scores[label]=math.log(n/sum(self.documents.values()))+sum(math.log((self.counts[label][w]+1)/denominator) for w in words)
        best=max(scores,key=scores.get)
        probability=1/sum(math.exp(v-scores[best]) for v in scores.values())
        answered=best!='inconclusive' and probability>=self.threshold
        return {'root_cause':best if answered and '+' not in best else None,
                'predicted_roots':best.split('+') if answered and best!='none' else [],'answered':answered,
                'evidence_strength':probability,'diagnostic_checks':0,'evidence':[],
                'classification':'probable' if answered else 'inconclusive',
                'communication_failure_detected':answered and bool(set(best.split('+')) & {'network_delay','network_loss','network_duplicate','charger_controller_timeout'}),
                'component_type':ROOTS.get(best,(None,None))[1],'category':ROOTS.get(best,(None,None))[0]}

    def predict(self,complaint,observed=None):
        context=self.text(complaint)
        if observed is None:
            return context
        # Same text is supplied as context, but cannot override unavailable or
        # contradictory component evidence in the observation arm.
        out=normalize(observed)
        out['text_context_hypothesis']=context.get('root_cause')
        return out


def normalize(result):
    out=dict(result)
    roots=result.get('supported_root_causes',[])
    if not roots and result.get('root_cause') not in (None,'none'):
        roots=[result['root_cause']]
    out['predicted_roots']=sorted(roots)
    out['answered']=bool(roots) or result.get('root_cause')=='none'
    if len(roots)>1:
        # This is the supported-set output, not a fictional unique primary.
        out['evidence_strength']=sum(e['weight'] for e in result['evidence'] if e.get('root_cause') in roots)/max(1,sum(e.get('root_cause') in roots for e in result['evidence']))
    return out


def decision_label(prediction):
    return ('+'.join(prediction['predicted_roots']) or 'none') if prediction['answered'] else 'inconclusive'


def calibrate(rows):
    return fit_calibration([{'root_cause':decision_label(r['prediction']) if r['prediction']['answered'] else None,
        'evidence_strength':r['prediction']['evidence_strength'],'expected_label':target(r['annotations'])} for r in rows])


def multilabel(rows):
    tp=fp=fn=exact=0
    for row in rows:
        real=set(row['annotations']['physical_roots']);pred=set(row['prediction']['predicted_roots'])
        tp+=len(real&pred);fp+=len(pred-real);fn+=len(real-pred);exact+=real==pred
    precision=tp/(tp+fp) if tp+fp else 0
    recall=tp/(tp+fn) if tp+fn else 0
    per_root={}
    for root in ROOTS:
        if root in ('none','inconclusive'):continue
        root_tp=sum(root in r['annotations']['physical_roots'] and root in r['prediction']['predicted_roots'] for r in rows)
        root_fp=sum(root not in r['annotations']['physical_roots'] and root in r['prediction']['predicted_roots'] for r in rows)
        root_fn=sum(root in r['annotations']['physical_roots'] and root not in r['prediction']['predicted_roots'] for r in rows)
        p=root_tp/(root_tp+root_fp) if root_tp+root_fp else 0
        r=root_tp/(root_tp+root_fn) if root_tp+root_fn else 0
        per_root[root]={'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0,'support':root_tp+root_fn}
    return {'sessions':len(rows),'true_positives':tp,'false_positives':fp,'false_negatives':fn,'classification_report':per_root,
        'macro_f1_ten_roots':sum(v['f1'] for v in per_root.values())/len(per_root),
        'micro_precision':round(precision,6),'micro_recall':round(recall,6),'micro_f1':round(2*precision*recall/(precision+recall),6) if precision+recall else 0,
        'exact_set_accuracy_pct':round(100*exact/len(rows),4) if rows else None}


def metrics(rows):
    percent=lambda n,d:round(100*n/d,4) if d else None
    labels=sorted({target(r['annotations']) for r in rows}|{decision_label(r['prediction']) for r in rows})
    matrix={a:Counter() for a in labels}
    for r in rows:
        matrix[target(r['annotations'])][decision_label(r['prediction'])]+=1
    classes={}
    for label in labels:
        tp=matrix[label][label];support=sum(matrix[label].values());predicted=sum(matrix[t][label] for t in labels)
        p=tp/predicted if predicted else 0;r=tp/support if support else 0
        classes[label]={'precision':round(p,6),'recall':round(r,6),'f1':round(2*p*r/(p+r),6) if p+r else 0,'support':support}
    answered=[r for r in rows if r['prediction']['answered']]
    ambiguous=[r for r in rows if not r['annotations']['evidence_sufficient']]
    observable=[r for r in rows if r['annotations']['evidence_sufficient']]
    correct=lambda r:decision_label(r['prediction'])==target(r['annotations'])
    brier=sum((r['prediction']['confidence']-int(correct(r)))**2 for r in answered)/len(answered) if answered else None
    bins=[];ece=0
    for low,high in ((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.000001)):
        bucket=[r for r in answered if low<=r['prediction']['confidence']<high]
        if bucket:
            conf=sum(r['prediction']['confidence'] for r in bucket)/len(bucket);accuracy=sum(correct(r) for r in bucket)/len(bucket)
            ece+=len(bucket)/len(answered)*abs(conf-accuracy)
            bins.append({'lower':low,'upper':min(high,1),'support':len(bucket),'mean_confidence':conf,'accuracy':accuracy})
    communication={'network_delay','network_loss','network_duplicate','charger_controller_timeout'}
    positive=[r for r in rows if set(r['annotations']['physical_roots'])&communication]
    negative=[r for r in rows if not set(r['annotations']['physical_roots'])&communication]
    localized=[r for r in observable if len(r['annotations']['physical_roots'])==1]
    return {'sessions':len(rows),'accuracy_pct':percent(sum(correct(r) for r in rows),len(rows)),
        'observable_root_accuracy_pct':percent(sum(correct(r) for r in observable),len(observable)),
        'macro_f1':round(sum(v['f1'] for v in classes.values())/len(classes),6),'classification_report':classes,
        'confusion_matrix':{'labels':labels,'rows':[[matrix[t][p] for p in labels] for t in labels],'orientation':'rows=true, columns=predicted'},
        'answered_sessions':len(answered),'answer_coverage_pct':percent(len(answered),len(rows)),
        'accuracy_among_answered_pct':percent(sum(correct(r) for r in answered),len(answered)),
        'ambiguous_sessions':len(ambiguous),'false_assertions_on_ambiguous_pct':percent(sum(r['prediction']['answered'] for r in ambiguous),len(ambiguous)),
        'successful_abstention_pct':percent(sum(not r['prediction']['answered'] for r in ambiguous),len(ambiguous)),
        'avg_diagnostic_checks':round(sum(r['prediction']['diagnostic_checks'] for r in rows)/len(rows),4),
        'communication_positive_sessions':len(positive),'communication_negative_sessions':len(negative),
        'communication_detection_pct':percent(sum(r['prediction'].get('communication_failure_detected',False) for r in positive),len(positive)),
        'communication_false_positive_pct':percent(sum(r['prediction'].get('communication_failure_detected',False) for r in negative),len(negative)),
        'localization_sessions':len(localized),'component_localization_pct':percent(sum(r['prediction'].get('component_type')==ROOTS[r['annotations']['physical_roots'][0]][1] for r in localized),len(localized)),
        'physical_multilabel_all_sessions':multilabel(rows),'observable_multilabel':multilabel(observable),
        'multi_fault_subset':multilabel([r for r in rows if len(r['annotations']['physical_roots'])>1]),
        'calibration':{'target':'Exact decision/set correctness among answered cases; validation-fitted probabilities, not evidence scores',
            'assertions':len(answered),'ece':round(ece,6) if answered else None,'brier':round(brier,6) if brier is not None else None,'bins':bins}}


def freeze_record(model,calibration,manifest):
    root=Path(__file__).resolve().parents[1]
    files=[*sorted(root.rglob('*.py')),*sorted((root/'config').glob('*.json'))]
    return {'frozen_before_final_test_predictions':True,'threshold':model.threshold,
        'text_model':{'training_documents':dict(model.documents),'word_counts':{k:dict(v) for k,v in model.counts.items()}},
        'validation_calibration':calibration,'manifest_sha256':hash_value(manifest),
        'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'exposure':'Authored test configurations were declared before first challenge scoring. The initial frozen report is preserved in research_initial_frozen. After that exposure, ticket intake was made durable before investigation; no diagnostic rules, thresholds, calibration strategy or test labels were tuned. This final rerun is an exposed-test regression, not a fresh blind holdout. Authors know the shared simulator/ontology; legacy benchmarks were previously exposed too.'}


def categorical_report(pairs):
    labels=sorted({str(x) for pair in pairs for x in pair});counts={v:Counter() for v in labels}
    for true,pred in pairs:counts[str(true)][str(pred)]+=1
    per_class={}
    for label in labels:
        tp=counts[label][label];n=sum(counts[label].values());pred=sum(counts[t][label] for t in labels)
        p=tp/pred if pred else 0;r=tp/n if n else 0
        per_class[label]={'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0,'support':n}
    return {'sessions':len(pairs),'accuracy_pct':100*sum(t==p for t,p in pairs)/len(pairs),
        'macro_f1':sum(v['f1'] for v in per_class.values())/len(per_class),'classification_report':per_class,
        'confusion_matrix':{'labels':labels,'rows':[[counts[t][p] for p in labels] for t in labels]}}


def evaluate_research(seed=20261104,repeats=2,development_only=False,freeze_path=None):
    dataset=generate_challenge(seed,repeats)
    partitions={s:[r for r in dataset['rows'] if r['annotations']['split']==s] for s in ('train','validation','test')}
    model=MatchedAgent(partitions['train'])
    methods=('fixed_baseline','current_adaptive','multi_component','text_only','text_plus_observations')
    with tempfile.TemporaryDirectory(prefix='ev-support-research-') as folder:
        conn=_fresh_conn(str(Path(folder)/'research.db'))
        try:
            # Persist one split at a time: final test observations are absent
            # while fitting train/validation artifacts and inspecting dev data.
            def predict_partition(split):
                for row in partitions[split]:persist_dataset(conn,row['dataset'])
                outputs={m:[] for m in methods}
                for row in partitions[split]:
                    s=row['dataset']['sessions'][0];sid=row['session_id']
                    complaint=Complaint(s['app_id'],row['complaint'],session_ref=sid,complaint_ts=s['ended_at'],
                        station_id=s['components']['charger'],user_ref='USR-'+sid,data_origin='simulated')
                    observed=MultiComponentAgent(conn,use_saved_calibration=False).run(sid,complaint=complaint).result
                    predictions={'multi_component':normalize(observed),'text_only':model.predict(row['complaint']),
                                 'text_plus_observations':model.predict(row['complaint'],observed)}
                    for method in ('fixed_baseline','current_adaptive'):
                        predictions[method]=normalize(legacy_prediction(conn,sid,method,complaint_text=row['complaint']))
                    for method,pred in predictions.items():
                        outputs[method].append({'session_id':sid,'complaint':row['complaint'],'annotations':row['annotations'],'prediction':pred})
                return outputs
            validation=predict_partition('validation')
            calibrations={m:calibrate(rows) for m,rows in validation.items()}
            frozen=freeze_record(model,calibrations,dataset['manifests'])
            frozen_hash=hash_value(frozen)
            if freeze_path:
                freeze_path=Path(freeze_path);freeze_path.parent.mkdir(parents=True,exist_ok=True)
                freeze_path.write_text(json.dumps(frozen,indent=2)+'\n',encoding='utf-8')
            if development_only:
                outcomes=validation
            else:
                outcomes=predict_partition('test')
            if hash_value(freeze_record(model,calibrations,dataset['manifests']))!=frozen_hash:
                raise RuntimeError('Frozen code/model/configuration changed during held-out scoring')
            for method,rows in outcomes.items():
                for r in rows:
                    r['prediction']['confidence']=confidence_from(calibrations[method],r['prediction']['evidence_strength']) if r['prediction']['answered'] else None
            support=[]
            session_index={r['session_id']:r for r in dataset['rows']}
            for row in outcomes['multi_component']:
                original=session_index[row['session_id']]
                decision=decide(row['prediction'],original['dataset']['sessions'][0]['events'],row['complaint'])
                expected=row['annotations']['expected_support']
                support.append({'session_id':row['session_id'],'expected':expected,'decision':decision,
                    'classification_correct':decision['classification']==expected['classification'],
                    'priority_correct':decision['priority']==expected['priority'],'routing_correct':decision['assigned_team']==expected['assigned_team'],
                    'escalation_correct':decision['requires_escalation']==row['annotations']['expected_escalation']})
            report={'generated_at':datetime.now(timezone.utc).isoformat(),'benchmark':dataset['version'],'seed':seed,'repeats':repeats,
                'evaluated_partition':'validation_development' if development_only else 'test','split_sizes':{s:len(rows) for s,rows in partitions.items()},
                'manifests':dataset['manifests'],'freeze':frozen,'freeze_sha256':frozen_hash,
                'challenge':{m:metrics(outcomes[m]) for m in methods[:3]},
                'ablation':{m:metrics(outcomes[m]) for m in methods[3:]},
                'support_workflow':{'sessions':len(support),**{key:round(100*sum(r[key] for r in support)/len(support),4) for key in ('classification_correct','priority_correct','routing_correct','escalation_correct')},
                    'classification':categorical_report([(r['expected']['classification'],r['decision']['classification']) for r in support]),
                    'priority':categorical_report([(r['expected']['priority'],r['decision']['priority']) for r in support]),
                    'routing':categorical_report([(r['expected']['assigned_team'],r['decision']['assigned_team']) for r in support]),
                    'escalation':categorical_report([(row['annotations']['expected_escalation'],r['decision']['requires_escalation']) for row,r in zip(outcomes['multi_component'],support)]),
                    'outcomes':support},
                'per_session':outcomes,'limitations':[
                    'All results are synthetic, authored with a shared causal simulator and ontology; no real-world or protocol-compliance validation.',
                    'Scenario configurations, physical startup variants and multi-fault combinations are disjoint; individual mechanisms and software are shared.',
                    'Observation loss is separate from physical faults. Contradictions are deliberate observation corruptions, not physical network loss.',
                    'Multi-component supported-set metrics use independently corroborated hypotheses; a unique-primary result can still be inconclusive for multiple supported roots.',
                    'Single-root legacy outputs score zero exact-set credit for a multi-root target; partial credit appears only in multi-label precision/recall.',
                    'Ablation uses the identical symptom corpus/cases/splits/taxonomy and a train-only naive Bayes context model. The observation arm adds the existing causal evidence gate; this is not a matched-size learned-model comparison.',
                    'Symptoms intentionally overlap between causes. This small authored corpus and conservative text threshold limit what the ablation establishes.',
                    'Confidence target is exact answer/set correctness among assertions, calibrated only on validation. Small supports and pooled bins limit interpretation.',
                    'Support expectations were separately specified in research/dataset.py, not generated by the production routing/priority policy; they remain authored policy expectations, not organizational SLA validation.',
                    'No rules were changed after this frozen test run to hide failures. Previously exposed legacy/current benchmarks remain regression tests.']}
            return report
        finally:
            conn.close()


def write_reports(report,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'research_results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (folder/'partition_manifests.json').write_text(json.dumps(report['manifests'],indent=2)+'\n',encoding='utf-8')
    (folder/'frozen_experiment.json').write_text(json.dumps(report['freeze'],indent=2)+'\n',encoding='utf-8')
    lines=['# Synthetic support challenge and complaint ablation','',f"Partition: {report['evaluated_partition']}; seed {report['seed']}; split sizes {report['split_sizes']}.",'',
        '| Experiment / method | Accuracy % | Macro F1 | Answer coverage % | Accuracy answered % | False assertions on ambiguous % | ECE | Brier |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for experiment in ('challenge','ablation'):
        for method,m in report[experiment].items():
            lines.append(f"| {experiment} / {method} | {m['accuracy_pct']} | {m['macro_f1']} | {m['answer_coverage_pct']} | {m['accuracy_among_answered_pct']} | {m['false_assertions_on_ambiguous_pct']} | {m['calibration']['ece']} | {m['calibration']['brier']} |")
    lines+=['','## Support workflow','', '| Decision | Accuracy % | Macro F1 | Sessions |','|---|---:|---:|---:|']
    for key in ('classification','priority','routing','escalation'):
        m=report['support_workflow'][key]
        lines.append(f"| {key} | {m['accuracy_pct']} | {m['macro_f1']} | {m['sessions']} |")
    lines+=['',
        'Full per-label precision/recall/F1/support, confusion matrices, multi-label metrics, detection/localization denominators, confidence bins, supported sets, failed outcomes and annotations are in research_results.json.',
        '', '## Experimental record','',f"Frozen artifact SHA256: {report['freeze_sha256']}",'',report['freeze']['exposure'],'',
        '## Limitations','',*['- '+v for v in report['limitations']]]
    if report.get('reproducibility'):lines+=['','## Reproducibility','',json.dumps(report['reproducibility'])]
    (folder/'research_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (folder/'research_categories.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['experiment','method','label','precision','recall','f1','support'])
        for experiment in ('challenge','ablation'):
            for method,values in report[experiment].items():
                for label,m in values['classification_report'].items():writer.writerow([experiment,method,label,m['precision'],m['recall'],m['f1'],m['support']])
