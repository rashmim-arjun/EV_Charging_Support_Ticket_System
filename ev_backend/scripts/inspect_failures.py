"""Replay selected synthetic scenarios and print observed evidence (debugging aid)."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent.agent import DiagnosticAgent
from app.data.synthetic_generator import SyntheticDataset
from app.evaluation.evaluation import _fresh_conn
from app.services.intake import build_complaint


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('indices', type=int, nargs='+')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--per-template', type=int, default=8)
    a = p.parse_args()
    conn = _fresh_conn(':memory:')
    try:
        ds = SyntheticDataset(a.seed, a.per_template)
        ds.write(conn)
        for index in a.indices:
            item = ds.complaints()[index - 1]
            run = DiagnosticAgent(conn).run(build_complaint(item['payload']))
            print('\n', item['scenario_id'], item['payload'], 'label=', item['ground_truth'])
            print(run.diagnosis.to_dict(), run.state.beliefs)
            for e in run.state.evidence:
                print(e.kind, e.supports_category, e.signal_key, e.weight, e.description)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
