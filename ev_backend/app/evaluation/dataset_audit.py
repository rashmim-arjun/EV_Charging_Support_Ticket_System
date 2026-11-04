"""Report fixture inconsistencies without changing labels or excluding scored cases."""
from app.core.settings import applicable_categories


def audit_dataset(dataset):
    unsupported, contradictory = [], []
    sessions = {s['scenario_id']: s for s in dataset.sessions}
    for case in dataset.cases:
        gt = case['ground_truth']
        if gt != 'inconclusive' and gt not in applicable_categories(case['app_id']):
            unsupported.append({'scenario_id': case['scenario_id'], 'app_id': case['app_id'], 'label': gt})
        session = sessions.get(case['scenario_id'])
        if gt == 'inconclusive' and session and session.get('error_code'):
            contradictory.append({'scenario_id': case['scenario_id'], 'label': gt,
                                  'logged_error': session['error_code'], 'reason': 'A labelled-inconclusive fixture supplies a matched session with a specific logged fault.'})
    return {'unsupported_app_labels': unsupported, 'inconclusive_with_logged_fault': contradictory,
            'policy': 'All cases remain in the comparison and its denominators. Unsupported labels are not applied as reviewer training feedback.'}
