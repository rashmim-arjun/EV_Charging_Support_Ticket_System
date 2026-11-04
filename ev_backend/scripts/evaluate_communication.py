"""Run the three-agent scenario/configuration holdout evaluation."""
import argparse
import json
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.communication.evaluation import evaluate_communication, write_communication_reports
from app.communication.diagnosis import CALIBRATION_FILE
from app.core.logging_setup import setup_logging


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--per-template', type=int, default=4)
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'reports/submission/communication')
    p.add_argument('--install-calibration', action='store_true', help='Install only the validation-fitted model for dashboard diagnosis')
    p.add_argument('--check-reproducibility', action='store_true')
    args = p.parse_args()
    setup_logging()
    logging.getLogger('app').setLevel(logging.WARNING)
    report = evaluate_communication(args.seed, args.per_template)
    if args.check_reproducibility:
        repeated = evaluate_communication(args.seed, args.per_template)
        if report['metrics'] != repeated['metrics'] or report['calibration_models'] != repeated['calibration_models']:
            raise RuntimeError('Communication evaluation was not reproducible')
        report['reproducibility'] = {'verified': True, 'runs': 2, 'scope': 'all reported metrics and validation probability models'}
    for path in write_communication_reports(report, args.output):
        print(path)
    for method, values in report['metrics'].items():
        print(method, json.dumps({k: values[k] for k in ('root_cause_accuracy_pct', 'decision_accuracy_pct', 'macro_f1', 'communication_failure_detection_pct', 'component_localization_accuracy_pct', 'avg_checks_per_session')}))
    if args.install_calibration:
        model = {**report['calibration_models']['multi_component'], 'seed': args.seed, 'simulator_version': report['simulator_version'],
                 'validation_templates': report['split_templates']['validation'], 'scope': 'Synthetic validation decisions only; no test labels used.'}
        CALIBRATION_FILE.write_text(json.dumps(model, indent=2) + '\n', encoding='utf-8')
        print('Installed validation-fitted calibration:', CALIBRATION_FILE)


if __name__ == '__main__':
    main()
