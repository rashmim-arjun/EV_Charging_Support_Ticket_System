"""Run separate synthetic challenge/ablation/support experiments; preserve history."""
import argparse,json,logging,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.research.experiment import evaluate_research,write_reports
from app.research.dataset import hash_value

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,default=20261104)
    p.add_argument('--repeats',type=int,default=2,choices=range(1,6))
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'reports/submission/research')
    p.add_argument('--development-only',action='store_true')
    p.add_argument('--check-reproducibility',action='store_true')
    p.add_argument('--export-dataset',type=Path)
    args=p.parse_args();logging.getLogger('app').setLevel(logging.WARNING)
    report=evaluate_research(args.seed,args.repeats,args.development_only,freeze_path=args.output/'frozen_experiment.json')
    if args.check_reproducibility:
        repeated=evaluate_research(args.seed,args.repeats,args.development_only)
        for key in ('challenge','ablation','support_workflow','freeze_sha256'):
            if report[key]!=repeated[key]:raise RuntimeError('Research results differ: '+key)
        report['reproducibility']={'verified':True,'runs':2,'scope':'all metrics, support outcomes, frozen model and source hashes'}
    write_reports(report,args.output)
    if args.export_dataset:
        from app.research.dataset import generate_challenge
        args.export_dataset.parent.mkdir(parents=True,exist_ok=True)
        args.export_dataset.write_text(json.dumps(generate_challenge(args.seed,args.repeats),indent=2)+'\n',encoding='utf-8')
    for experiment in ('challenge','ablation'):
        print(experiment,json.dumps({m:{k:v[k] for k in ('accuracy_pct','macro_f1','answer_coverage_pct','false_assertions_on_ambiguous_pct')} for m,v in report[experiment].items()}))
    print('support',json.dumps({k:v for k,v in report['support_workflow'].items() if isinstance(v,(int,float,str))}))
    print('Reports:',args.output)

if __name__=='__main__':main()
