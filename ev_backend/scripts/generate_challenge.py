"""Generate the separately annotated support challenge without running evaluation."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.research.dataset import generate_challenge

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=20261104)
    parser.add_argument('--repeats',type=int,default=2,choices=range(1,6))
    parser.add_argument('--output',type=Path,default=Path('.tmp/support-challenge.json'))
    args=parser.parse_args()
    data=generate_challenge(args.seed,args.repeats)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print('Annotated synthetic challenge:',args.output,len(data['rows']),'sessions')
