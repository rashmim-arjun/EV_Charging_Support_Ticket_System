"""Scenario-group holdout comparison; labels are accessed only by this evaluator."""
import csv
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.agent.agent import DiagnosticAgent
from app.agent.baseline import FixedCheckBaseline
from app.communication.catalog import ROOTS, VERSION
from app.communication.diagnosis import MultiComponentAgent, confidence_from, CALIBRATION_FILE
from app.communication.simulator import generate_dataset, digest
from app.communication.storage import persist_dataset, get_session
from app.communication.schema import GenerateRequest
from app.evaluation.evaluation import _fresh_conn
from app.services import feedback
from app.services.diagnosis import diagnose_and_persist
from app.models import Complaint


def legacy_prediction(conn, session_id, method, complaint_text='Investigate the correlated charging request.'):
    session = get_session(conn, session_id)
    c = Complaint('statiq', complaint_text, session_ref=session_id,
                  complaint_ts=session['ended_at'], station_id=session['components']['charger'], user_ref='USR-' + session_id, data_origin='simulated')
    agent = FixedCheckBaseline(conn) if method == 'fixed_baseline' else DiagnosticAgent(conn)
    run = agent.run(c)
    d = run.diagnosis
    choices = [root for root, (category, _) in ROOTS.items() if category and category == d.primary_category]
    root = choices[0] if len(choices) == 1 else 'unresolved:' + d.primary_category if d.primary_category else None
    signals = {s for step in run.trace for s in step.result.get('signals', [])}
    matching = [e for e in run.state.evidence if e.kind == 'matching' and e.supports_category]
    # A conservative normal adapter uses only existing tool findings. No new
    # communication observations or labels are supplied to these frozen agents.
    if not root and not matching and 'payment_ok' in signals and run.state.matched_session and run.state.matched_session['status'] == 'completed':
        root = 'none'
    components = {ROOTS[r][1] for r in choices}
    return {'session_id': session_id, 'root_cause': root, 'category': d.primary_category,
        'component_type': next(iter(components)) if len(components) == 1 else None,
        'evidence_strength': d.evidence_strength if root != 'none' else .5,
        'diagnostic_checks': sum(s.result.get('status') != 'not_applicable' for s in run.trace),
        'communication_failure_detected': bool(signals & {'heartbeat_lost', 'connection_timeout_events', 'charger_offline_period', 'error_code_E101_START_TIMEOUT'}),
        'transport_failure_detected': bool(signals & {'heartbeat_lost', 'connection_timeout_events', 'charger_offline_period'}),
        'confidence': None, 'evidence': [], 'tool_errors': [s.tool_name for s in run.trace if s.result.get('status') == 'error']}


def fit_calibration(rows):
    bins = [{'upper': upper, 'support': 0, 'correct': 0} for upper in (.5, .75, .9, 1.0)]
    for r in rows:
        if r['root_cause'] is None:
            continue
        b = next(b for b in bins if r['evidence_strength'] <= b['upper'])
        b['support'] += 1
        b['correct'] += int(r['root_cause'] == r['expected_label'])
    blocks = []
    for i, b in enumerate(bins):
        blocks.append(([i], b['correct'] + 1, b['support'] + 2))
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            a, b = blocks[-2:]
            blocks[-2:] = [(a[0] + b[0], a[1] + b[1], a[2] + b[2])]
    for indices, correct, total in blocks:
        for i in indices:
            bins[i]['probability'] = round(correct / total, 6)
    return {'method': 'monotonic bins with Beta(1,1) smoothing; fitted on validation decisions only', 'bins': bins}


def score(rows):
    known = list(ROOTS)
    labels = known + sorted({r['root_cause'] for r in rows if r['root_cause'] and r['root_cause'] not in known})
    matrix = {a: Counter() for a in known}
    for r in rows:
        matrix[r['expected_label']][r['root_cause'] or 'inconclusive'] += 1
    classes = {}
    for c in labels:
        support = sum(matrix.get(c, {}).values())
        tp = matrix.get(c, {}).get(c, 0)
        predicted = sum(v.get(c, 0) for v in matrix.values())
        p, recall = tp / predicted if predicted else 0, tp / support if support else 0
        classes[c] = {'precision': round(p, 4), 'recall': round(recall, 4),
                      'f1': round(2 * p * recall / (p + recall), 4) if p + recall else 0, 'support': support}
    faults = [r for r in rows if r['expected_label'] not in ('none', 'inconclusive')]
    observable = [r for r in rows if r['expected_label'] != 'inconclusive']
    communication_labels = {'charger_controller_timeout', 'network_delay', 'network_loss', 'network_duplicate'}
    comm = [r for r in rows if r['expected_label'] in communication_labels]
    non_comm = [r for r in rows if r['expected_label'] not in communication_labels]
    transport_cases = [r for r in rows if r['expected_label'].startswith('network_')]
    asserted = [r for r in rows if r['root_cause'] is not None]
    inconclusive = [r for r in rows if r['expected_label'] == 'inconclusive']
    def pct(n, group):
        return round(100 * n / len(group), 2) if group else None
    calibration_bins, ece, brier = [], 0, 0
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.00001)]:
        b = [r for r in asserted if r.get('confidence') is not None and lo <= r['confidence'] < hi]
        confidence = sum(r['confidence'] for r in b) / len(b) if b else None
        accuracy = sum(r['root_cause'] == r['expected_label'] for r in b) / len(b) if b else None
        if b:
            ece += len(b) / len(asserted) * abs(confidence - accuracy)
            brier += sum((r['confidence'] - int(r['root_cause'] == r['expected_label'])) ** 2 for r in b) / len(asserted)
        calibration_bins.append({'range': [lo, min(hi, 1)], 'support': len(b), 'mean_confidence': confidence, 'accuracy': accuracy})
    cause_labels = [c for c in known if c not in ('none', 'inconclusive')]
    return {'sessions': len(rows),
        'decision_accuracy_pct': pct(sum((r['root_cause'] or 'inconclusive') == r['expected_label'] for r in rows), rows),
        'root_cause_accuracy_pct': pct(sum(r['root_cause'] == r['expected_label'] for r in observable), observable),
        'category_accuracy_pct': pct(sum((r['category'] or ('none' if r['root_cause'] == 'none' else 'inconclusive')) ==
            (ROOTS.get(r['expected_label'], (None, None))[0] or r['expected_label']) for r in rows), rows),
        'macro_f1': round(sum(classes[c]['f1'] for c in cause_labels) / len(cause_labels), 4),
        'classification_report': classes,
        'confusion_matrix': {'labels': labels, 'rows': [[matrix.get(c, {}).get(p, 0) for p in labels] for c in labels], 'orientation': 'rows=true, columns=predicted'},
        'communication_failure_detection_pct': pct(sum(r['communication_failure_detected'] for r in comm), comm),
        'transport_failure_detection_pct': pct(sum(r['transport_failure_detected'] for r in transport_cases), transport_cases),
        'communication_false_positive_pct': pct(sum(r['communication_failure_detected'] for r in non_comm), non_comm),
        'component_localization_accuracy_pct': pct(sum(r['component_type'] == ROOTS[r['expected_label']][1] for r in faults), faults),
        'false_confident_on_inconclusive_pct': pct(sum(r['root_cause'] is not None for r in inconclusive), inconclusive),
        'avg_checks_per_session': round(sum(r['diagnostic_checks'] for r in rows) / len(rows), 3),
        'calibration': {'ece': round(ece, 6) if asserted else None, 'brier': round(brier, 6) if asserted else None,
                        'asserted_sessions': len(asserted), 'bins': calibration_bins},
        'tool_errors': sum(len(r.get('tool_errors', [])) for r in rows)}


def evaluate_communication(seed=42, per_template=4):
    cfg = GenerateRequest(seed=seed, per_template=per_template, split='all')
    with tempfile.TemporaryDirectory(prefix='ev-communication-eval-') as folder:
        conn = _fresh_conn(str(Path(folder) / 'evaluation.db'))
        try:
            data = generate_dataset(cfg)
            persist_dataset(conn, data)
            split_rows = {split: [s for s in data['sessions'] if s['truth']['split'] == split] for split in ('train', 'validation', 'test')}
            template_groups = {k: sorted({s['truth']['template_id'] for s in rows}) for k, rows in split_rows.items()}
            configs = {k: {digest([s['truth']['expected_label'], s['truth']['fault_configuration']]) for s in rows} for k, rows in split_rows.items()}
            for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]:
                if set(template_groups[a]) & set(template_groups[b]) or configs[a] & configs[b]:
                    raise ValueError('Scenario template or fault configuration leaked between splits')
            predictions, models = {}, {}

            def annotated(prediction, s):
                # Annotation happens only after the agent returns, and is never
                # passed back to its feature extractor or diagnostic state.
                return {**prediction, 'expected_label': s['truth']['expected_label'], 'template_id': s['truth']['template_id']}

            # Freeze both existing agents before any reviewer training changes.
            for method in ('fixed_baseline', 'current_adaptive'):
                validation = [annotated(legacy_prediction(conn, s['session_id'], method), s) for s in split_rows['validation']]
                models[method] = fit_calibration(validation)
                predictions[method] = [annotated(legacy_prediction(conn, s['session_id'], method), s) for s in split_rows['test']]
            conn.execute("INSERT INTO reviewers(reviewer_id,name,role,active) VALUES ('mc-eval','Simulated training reviewer','diagnosis_reviewer',1)")
            conn.commit()
            training_changes, reviewed = 0, 0
            for s in split_rows['train']:
                truth = s['truth']['expected_label']
                category = ROOTS[truth][0]
                if not category:
                    continue
                outcome = MultiComponentAgent(conn, use_saved_calibration=False).run(s['session_id'])
                stored = diagnose_and_persist(conn, outcome.agent_run.state.complaint, agent_run=outcome.agent_run)
                resolution = feedback.create_resolution(conn, stored['case_id'], {'reviewer_id': 'mc-eval', 'verified_root_cause': category,
                    'corrective_action': 'Simulated reviewer verifies training scenario annotations'})
                update = feedback.apply_verified_outcome(conn, resolution['resolution_id'])
                training_changes += len(update['changes'])
                reviewed += 1
            agent = MultiComponentAgent(conn, use_saved_calibration=False)
            validation = [annotated(agent.run(s['session_id']).result, s) for s in split_rows['validation']]
            models['multi_component'] = fit_calibration(validation)
            predictions['multi_component'] = [annotated(agent.run(s['session_id']).result, s) for s in split_rows['test']]
            for method, rows in predictions.items():
                for r in rows:
                    r['confidence'] = confidence_from(models[method], r['evidence_strength']) if r['root_cause'] is not None else None
            return {'generated_at': datetime.now(timezone.utc).isoformat(), 'simulator_version': VERSION, 'seed': seed,
                'per_template': per_template, 'dataset_size': len(data['sessions']), 'split_sizes': {k: len(v) for k, v in split_rows.items()},
                'split_templates': template_groups, 'split_configuration_hashes': {k: sorted(v) for k, v in configs.items()},
                'training': {'verified_resolutions': reviewed, 'knowledge_changes': training_changes, 'test_labels_used': False},
                'calibration_models': models, 'metrics': {m: score(rows) for m, rows in predictions.items()}, 'per_session': predictions,
                'limitations': [
                    'Synthetic mechanisms and diagnostic rules were authored together. Template/configuration holdout is not independent real-world validation.',
                    'Each split has a distinct startup path, fault trigger/operation and configuration band; the causal simulator and root-cause ontology are shared.',
                    'Legacy agents receive factual projections into their original tables. The multi-component agent has richer transport/component evidence; this is a capability comparison, not a pure scheduling ablation.',
                    'Legacy category outputs with several possible mechanisms are explicitly unresolved at exact-root level; category accuracy is reported separately.',
                    'Root-cause accuracy excludes unobservable sessions; decision accuracy additionally scores correct abstentions. Component localization is evaluated on fault sessions only.',
                    'Validation calibrates decision correctness for each method. No test outcomes fit weights or probabilities. Small supports can produce unstable calibration.',
                    'Reviewer learning operates on existing failure categories, not newly trained fine-grained root-cause models.',
                    'OCPP/ISO 15118 inspired event names are semantic simulations, without wire encoding, network interoperability or protocol compliance testing.']}
        finally:
            conn.close()


def write_communication_reports(report, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'communication_evaluation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    keys = ['root_cause_accuracy_pct', 'decision_accuracy_pct', 'category_accuracy_pct', 'macro_f1', 'avg_checks_per_session',
            'communication_failure_detection_pct', 'transport_failure_detection_pct', 'communication_false_positive_pct', 'component_localization_accuracy_pct', 'false_confident_on_inconclusive_pct']
    lines = ['# Multi-component communication evaluation', '', f"Seed {report['seed']}; {report['dataset_size']} sessions; split sizes {report['split_sizes']}.",
             '', '| Metric | Fixed baseline | Current adaptive | Multi-component |', '|---|---|---|---|']
    methods = ['fixed_baseline', 'current_adaptive', 'multi_component']
    lines += ['| ' + key + ' | ' + ' | '.join(str(report['metrics'][m][key]) for m in methods) + ' |' for key in keys]
    lines += ['', 'Root-cause accuracy includes observable normal/fault sessions. Decision accuracy includes inconclusive cases. Macro-F1 averages the ten fault mechanisms.',
              'Communication failure detection covers dropped, delayed and duplicate delivery plus missing controller responses; transport detection covers the three network mechanisms only.',
              'Detailed per-category precision/recall/F1/support, confusion matrices, confidence bins, split manifests and every prediction are in the JSON report.',
              '', '## Test calibration (probabilities fitted on validation only)', '', '| Method | ECE | Brier | Assertions |', '|---|---|---|---|']
    for m in methods:
        c = report['metrics'][m]['calibration']
        lines.append(f"| {m} | {c['ece']} | {c['brier']} | {c['asserted_sessions']} |")
    for m in methods:
        lines += ['', f'## Per-category metrics: {m}', '', '| Category | Precision | Recall | F1 | Support |', '|---|---|---|---|---|']
        lines += [f"| {c} | {v['precision']} | {v['recall']} | {v['f1']} | {v['support']} |" for c, v in report['metrics'][m]['classification_report'].items()]
    lines += ['', '## Methodology and limitations', '', *['- ' + x for x in report['limitations']]]
    if report.get('reproducibility'):
        lines += ['', '## Reproducibility', '', json.dumps(report['reproducibility'])]
    (folder / 'communication_evaluation.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with (folder / 'communication_categories.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['method', 'category', 'precision', 'recall', 'f1', 'support'])
        writer.writeheader()
        for m in methods:
            for c, values in report['metrics'][m]['classification_report'].items():
                writer.writerow({'method': m, 'category': c, **values})
    return [str(folder / name) for name in ('communication_evaluation.json', 'communication_evaluation.md', 'communication_categories.csv')]
