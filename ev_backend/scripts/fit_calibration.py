"""Fit and freeze monotonic confidence bins on an independent synthetic seed.

Never run this on evaluation seed 42 or 7. All thresholds are set before the
evaluation run. This calibrates synthetic assertions, not real-world confidence.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent.agent import DiagnosticAgent
from app.agent.calibration import CALIBRATION_PATH
from app.data.synthetic_generator import SyntheticDataset
from app.evaluation.evaluation import _fresh_conn
from app.services.intake import build_complaint


def fit(seed=314159, per_template=20):
    if seed in (42, 7):
        raise ValueError('Reserve seeds 42 and 7 for evaluation, not calibration.')
    with tempfile.TemporaryDirectory() as folder:
        conn = _fresh_conn(os.path.join(folder, 'calibration.db'))
        try:
            ds = SyntheticDataset(seed=seed, n_per_template=per_template)
            ds.write(conn)
            bins = [{'upper': x, 'successes': 0, 'support': 0} for x in (.2, .4, .6, .8, 1.0)]
            for item in ds.complaints():
                d = DiagnosticAgent(conn).run(build_complaint(item['payload'])).diagnosis
                if not d.primary_category:
                    continue
                b = next(b for b in bins if d.evidence_strength <= b['upper'])
                b['successes'] += int(d.primary_category == item['ground_truth'])
                b['support'] += 1
            # Pool-adjacent-violators with Beta(1,1) smoothing per bin.
            blocks = []
            for i, b in enumerate(bins):
                blocks.append(([i], b['successes'] + 1, b['support'] + 2))
                while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
                    y, z = blocks[-2:]
                    blocks[-2:] = [(y[0] + z[0], y[1] + z[1], y[2] + z[2])]
            for indices, successes, support in blocks:
                for i in indices:
                    bins[i]['probability'] = round(successes / support, 4)
            model = {'method': 'monotonic evidence-strength bins with Beta(1,1) smoothing',
                     'seed': seed, 'n_per_template': per_template, 'dataset_size': len(ds.cases),
                     'scope': 'asserted diagnoses only; synthetic development data; no probabilities for abstentions',
                     'bins': bins}
            CALIBRATION_PATH.write_text(json.dumps(model, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(model, indent=2))
        finally:
            conn.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, default=314159)
    p.add_argument('--per-template', type=int, default=20)
    args = p.parse_args()
    fit(args.seed, args.per_template)
