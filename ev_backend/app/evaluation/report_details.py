"""Extended audit tables and machine-readable error analysis from measured runs."""
import csv
import json
from pathlib import Path


def detail_lines(report):
    lines = ['', '## Classification metrics and confusion matrices', '',
             'Macro-F1 averages the 12 cause categories (zero-division = 0). False positives on truly inconclusive cases count. Accuracy additionally rewards correct abstentions, so these metrics can move in opposite directions.',
             'The matrix uses rows=true, columns=predicted; inconclusive includes every abstention. P/R/F1 are fractions. Support is the true-label count.']
    for method, metrics in report['metrics'].items():
        lines += ['', f'### {method}', '', '| Category | Precision | Recall | F1 | Support |', '|---|---|---|---|---|']
        for c, x in metrics['classification_report'].items():
            lines.append(f"| {c} | {x['precision']} | {x['recall']} | {x['f1']} | {x['support']} |")
        matrix = metrics['confusion_matrix']
        lines += ['', 'Matrix label key:']
        lines.extend(f'{i + 1}. {c}' for i, c in enumerate(matrix['labels']))
        lines += ['', '| True / Predicted | ' + ' | '.join(str(i + 1) for i in range(len(matrix['labels']))) + ' |',
                  '|---|' + '---|' * len(matrix['labels'])]
        lines.extend('| ' + str(i + 1) + ' | ' + ' | '.join(map(str, row)) + ' |' for i, row in enumerate(matrix['rows']))
        lines += ['', '### Assertion calibration: ' + method, '',
                  'Includes false assertions on inconclusive cases; abstentions carry no root-cause probability.',
                  '| Score | Assertions | ECE | Brier |', '|---|---|---|---|']
        for key in ['heuristic_assertion_calibration', 'assertion_calibration']:
            cal = metrics[key]
            lines.append(f"| {key} | {cal['n_cases']} | {cal['ece']} | {cal['brier']} |")
        lines += ['', '### Most frequent errors: ' + method, '', '| True | Predicted | Count |', '|---|---|---|']
        for x in metrics['error_analysis']['confusions']:
            lines.append(f"| {x['true']} | {x['predicted']} | {x['count']} |")
    le = report['learning_experiment']
    lines += ['', '## Learning outcome breakdown', '', '| Outcome | Before | After |', '|---|---|---|']
    for key, val in le['before_details']['outcome_counts'].items():
        lines.append(f"| {key} | {val} | {le['after_details']['outcome_counts'][key]} |")
    lines += ['', '### Learning per-category F1', '', '| Category | Before F1 | After F1 | Support |', '|---|---|---|---|']
    for key, val in le['before_details']['classification_report'].items():
        lines.append(f"| {key} | {val['f1']} | {le['after_details']['classification_report'][key]['f1']} | {val['support']} |")
    lines += ['', 'Frozen calibration model: ' + json.dumps(report.get('calibration_model')), '',
              'The original leading-hypothesis calibration table above diagnoses the heuristic score on labelled causes only. Assertion calibration is the more relevant measure for displayed probabilities. Calibration and test use different scenario seeds but share synthetic template families; this is not independent real-world validation.',
              'Detailed incorrect case IDs, observed signals, executed tools, and tool errors are saved in evaluation_errors.json; full method outcomes are in evaluation_cases.json.']
    audit = report.get('dataset_audit', {})
    lines += ['', '## Dataset consistency audit (cases retained in scores)', '',
              audit.get('policy', ''),
              f"Unsupported app/category labels: {len(audit.get('unsupported_app_labels', []))}.",
              f"Inconclusive labels with a specific matched logged fault: {len(audit.get('inconclusive_with_logged_fault', []))}.",
              'IDs and reasons are recorded in evaluation_results.json under dataset_audit.',
              f"Training labels not applied because their category is unsupported: {le.get('train_invalid_label_cases', [])}."]
    if report.get('reproducibility'):
        lines += ['', '## Reproducibility check', '', json.dumps(report['reproducibility'])]
    return lines


def write_detail_files(report, directory):
    folder = Path(directory)
    paths = []
    for name, data in [('evaluation_errors.json', {m: v['error_analysis'] for m, v in report['metrics'].items()}),
                       ('evaluation_cases.json', report['per_case'])]:
        path = folder / name
        path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        paths.append(str(path))
    path = folder / 'evaluation_categories.csv'
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['method', 'category', 'precision', 'recall', 'f1', 'support', 'predicted', 'true_positive', 'false_positive', 'false_negative'])
        writer.writeheader()
        for method, metrics in report['metrics'].items():
            for category, values in metrics['classification_report'].items():
                writer.writerow({'method': method, 'category': category, **values})
    paths.append(str(path))
    return paths
