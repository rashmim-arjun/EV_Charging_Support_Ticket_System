"""Classification metrics with explicit abstentions and false positives on every row."""
from collections import Counter


def classification_metrics(results, labels):
    labels = list(dict.fromkeys([*labels, 'inconclusive']))
    matrix = {a: {b: 0 for b in labels} for a in labels}
    for row in results:
        pred = row['primary_category'] or 'inconclusive'
        matrix[row['ground_truth']][pred] += 1
    report = {}
    for cat in labels:
        tp = matrix[cat][cat]
        support = sum(matrix[cat].values())
        predicted = sum(matrix[a][cat] for a in labels)
        p = tp / predicted if predicted else 0
        r = tp / support if support else 0
        f1 = 2 * p * r / (p + r) if p + r else 0
        report[cat] = {'precision': round(p, 4), 'recall': round(r, 4), 'f1': round(f1, 4),
                       'support': support, 'predicted': predicted, 'true_positive': tp,
                       'false_positive': predicted - tp, 'false_negative': support - tp}
    cause_labels = [c for c in labels if c != 'inconclusive']
    asserted = [r for r in results if r['primary_category']]
    return {
        'macro_f1': round(sum(report[c]['f1'] for c in cause_labels) / len(cause_labels), 4) if cause_labels else None,
        'macro_f1_with_abstention': round(sum(v['f1'] for v in report.values()) / len(report), 4),
        'classification_report': report,
        'confusion_matrix': {'labels': labels, 'rows': [list(matrix[c].values()) for c in labels],
                             'orientation': 'rows=true label, columns=predicted; inconclusive column includes abstentions'},
        'assertion_coverage_pct': round(100 * len(asserted) / len(results), 2) if results else 0,
        'asserted_accuracy_pct': round(100 * sum(r['primary_category'] == r['ground_truth'] for r in asserted) / len(asserted), 2) if asserted else None,
        'outcome_counts': {
            'correct_root_cause': sum(r['primary_category'] == r['ground_truth'] for r in asserted),
            'wrong_root_cause': sum(r['primary_category'] != r['ground_truth'] and r['ground_truth'] != 'inconclusive' for r in asserted),
            'false_assertion_on_inconclusive': sum(r['ground_truth'] == 'inconclusive' for r in asserted),
            'correct_abstention': sum(r['ground_truth'] == 'inconclusive' and not r['primary_category'] for r in results),
            'abstention_on_labelled_cause': sum(r['ground_truth'] != 'inconclusive' and not r['primary_category'] for r in results),
        },
    }


def error_analysis(results):
    errors = [r for r in results if (r['primary_category'] or 'inconclusive') != r['ground_truth']]
    pairs = Counter((r['ground_truth'], r['primary_category'] or 'inconclusive') for r in errors)
    return {'n_errors': len(errors), 'confusions': [{'true': a, 'predicted': b, 'count': n}
            for (a, b), n in pairs.most_common()], 'cases': errors}


def assertion_calibration(results, field='confidence'):
    rows = [r for r in results if r['primary_category'] is not None and r.get(field) is not None]
    if not rows:
        return {'n_cases': 0, 'ece': None, 'brier': None, 'bins': []}
    bins, ece = [], 0
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0001)]:
        b = [r for r in rows if lo <= r[field] < hi]
        conf = sum(r[field] for r in b) / len(b) if b else None
        acc = sum(r['primary_category'] == r['ground_truth'] for r in b) / len(b) if b else None
        if b:
            ece += len(b) / len(rows) * abs(acc - conf)
        bins.append({'range': f'{lo:.1f}-{min(hi,1):.1f}', 'n': len(b),
                     'mean_confidence': round(conf, 4) if b else None, 'accuracy_pct': round(acc * 100, 2) if b else None})
    brier = sum((r[field] - int(r['primary_category'] == r['ground_truth'])) ** 2 for r in rows) / len(rows)
    return {'n_cases': len(rows), 'ece': round(ece, 4), 'brier': round(brier, 4), 'bins': bins,
            'scope': 'All asserted diagnoses, including false assertions on inconclusive cases; abstentions excluded.'}
