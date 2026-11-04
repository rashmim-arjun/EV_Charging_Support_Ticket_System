"""Critical evidence, transaction, seed and evaluation regression coverage."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest

from app.agent.agent import DiagnosticAgent
from app.agent.tools import TOOL_REGISTRY, session_lookup, payment_check, connector_check, telematics_check
from app.core import db
from app.data.synthetic_generator import SyntheticDataset, reset_simulated_rows
from app.evaluation.evaluation import _score, evaluate, evaluate_learning
from app.models import CaseState, Complaint, CheckResult
from app.redaction import contains_pii
from app.redaction import redact_pii
from app.services import feedback as fb
from app.services.diagnosis import diagnose_and_persist
from app.services.intake import build_complaint
from tests.conftest import template_of


def persist(conn, dataset, template='T11'):
    item = next(i for i in dataset.complaints() if template_of(i, dataset) == template)
    out = diagnose_and_persist(conn, build_complaint(item['payload']))
    res = fb.create_resolution(conn, out['case_id'], {'reviewer_id': 'rev-test',
        'verified_root_cause': item['ground_truth'], 'verified_contributing': [item['secondary']] if item['secondary'] else [],
        'corrective_action': 'Verified against logs'})
    return out, res


def test_database_seed_idempotent_redacted_and_reset(conn):
    ds = SyntheticDataset(42, 2)
    inserted = ds.write(conn)
    assert inserted['events'] > 0
    tables = ['cases', 'charging_sessions', 'session_events', 'payment_records', 'charger_status_log']
    counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
    inserted_again = ds.write(conn)
    assert all(v == 0 for v in inserted_again.values())
    assert counts == {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
    with pytest.raises(ValueError, match='different per-template count'):
        SyntheticDataset(42, 3).write(conn)
    assert not any(contains_pii(r[0]) for r in conn.execute('SELECT complaint_text_redacted FROM cases'))
    db.init_db(conn)
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    reset_simulated_rows(conn)
    assert all(conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] == 0 for t in tables)


def test_session_reference_is_exact_and_app_scoped(conn, dataset):
    s = dataset.sessions[0]
    for ref, app in [(s['session_id'][:-1], s['app_id']), (s['session_id'], 'unknown')]:
        state = CaseState(Complaint(app_id=app, text_redacted='Charging never started', session_ref=ref), [])
        session_lookup.run(conn, state)
        assert state.matched_session is None


def test_session_lookup_does_not_guess_between_candidates(conn, dataset):
    s = dataset.sessions[0]
    copy = dict(s, session_id='another', scenario_id='another')
    cols = list(copy)
    conn.execute(f"INSERT INTO charging_sessions({','.join(cols)},data_origin) VALUES ({','.join('?' for _ in cols)},'simulated')", tuple(copy.values()))
    conn.commit()
    state = CaseState(Complaint(app_id=s['app_id'], text_redacted='Charging failed at station', user_ref=s['user_ref'], station_id=s['station_id']), [])
    r = session_lookup.run(conn, state)
    assert 'ambiguous_sessions' in r.signals
    assert state.matched_session is None


def test_unrelated_hardware_events_are_ignored(conn, dataset):
    s = next(s for s in dataset.sessions if s['status'] == 'completed')
    state = CaseState(Complaint(app_id=s['app_id'], text_redacted='Charging failure'), [], matched_session=s)
    conn.execute("INSERT INTO session_events(charger_id,event_ts,event_type,detail,data_origin) VALUES (?,?,'connector_fault','another session','manual_test')", (s['charger_id'], s['start_ts']))
    conn.commit()
    assert 'connector_fault_event' not in connector_check.run(conn, state).signals


def test_payment_from_other_app_or_time_cannot_prove_deduction(conn, dataset):
    p = dataset.payments[0]
    state = CaseState(Complaint(app_id='other', user_ref=p['user_ref'], complaint_ts=p['ts'],
        text_redacted='Money deducted but no charge', reported_payment_status='deducted'), [])
    assert 'payment_captured_without_session' not in payment_check.run(conn, state).signals


def test_telematics_filters_identity_before_limit(conn, dataset):
    item = next(i for i in dataset.complaints() if template_of(i, dataset) == 'T16')
    state = CaseState(build_complaint(item['payload']), ['vehicle_specific_or_telematics_issue'])
    for i in range(20):
        conn.execute("INSERT INTO session_events(charger_id,event_ts,event_type,detail,data_origin) VALUES ('app:bajaj_chetak',?,'soc_not_updating',?,'manual_test')",
                     (item['payload']['complaint_ts'], f'USR-other-{i}'))
    conn.commit()
    result = telematics_check.run(conn, state)
    assert 'soc_not_updating' in result.signals
    assert len(result.findings['events']) == 2


@pytest.mark.parametrize('template', ['T03', 'T04', 'T14', 'T15', 'T16'])
def test_weak_category_regressions_use_logged_evidence(conn, dataset, template):
    for item in dataset.complaints():
        if template_of(item, dataset) != template:
            continue
        run = DiagnosticAgent(conn).run(build_complaint(item['payload']))
        assert run.diagnosis.primary_category == item['ground_truth']
        assert any(e.supports_category == item['ground_truth'] and e.source_ref for e in run.state.evidence)


def test_reported_error_without_logs_is_not_verified(conn):
    run = DiagnosticAgent(conn).run(Complaint('statiq', 'Hardware fault reported', reported_error='HW210'))
    assert run.diagnosis.primary_category is None
    assert run.diagnosis.confidence is None


def test_redaction_preserves_diagnostic_codes():
    redacted = redact_pii('HS301 HW210 APP500 E101 registration MH12AB1234 phone 9812345678')
    assert 'HS301 HW210 APP500 E101' in redacted
    assert 'MH12AB1234' not in redacted and '9812345678' not in redacted


def test_proposals_count_distinct_verified_cases_and_do_not_duplicate(conn):
    def case(i, checks):
        cid = f'proposal-{i}'
        conn.execute("INSERT INTO cases(case_id,app_id,complaint_text_redacted,data_origin) VALUES (?,'statiq','Support request unresolved','manual_test')", (cid,))
        result = json.dumps({'signals': ['unseen_signal'], 'evidence_items': [{'kind': 'matching', 'signal_key': 'unseen_signal'}]})
        for j in range(checks):
            conn.execute("INSERT INTO case_checks(case_id,step_no,tool_name,selection_reason,candidate_scores_json,result_json) VALUES (?,?,'app_error_check','test','[]',?)", (cid,j,result))
        res = conn.execute("INSERT INTO resolutions(case_id,reviewer_id,verified_root_cause,corrective_action) VALUES (?,'rev-test','customer_support_issue','Verified ticket')", (cid,)).lastrowid
        conn.commit()
        return res
    first = case(1, 3)
    assert not [ch for ch in fb.compute_updates(conn, first) if ch['change_type'] == 'create']
    second = case(2, 1)
    case(3, 1)
    fb.apply_verified_outcome(conn, first)
    rules = conn.execute("SELECT * FROM knowledge_rules WHERE signal_key='unseen_signal'").fetchall()
    assert len(rules) == 1 and not rules[0]['active']
    fb.apply_verified_outcome(conn, second)
    assert conn.execute("SELECT COUNT(*) FROM knowledge_rules WHERE signal_key='unseen_signal'").fetchone()[0] == 1


def test_tool_failure_is_visible_and_agent_survives(conn, monkeypatch):
    def broken(*_):
        raise RuntimeError('test source unavailable')
    monkeypatch.setattr(TOOL_REGISTRY['app_error_check'], 'fn', broken)
    run = DiagnosticAgent(conn).run(Complaint('statiq', 'App crashes repeatedly'))
    assert any('app_error_check' in q for q in run.diagnosis.unresolved_questions)
    assert run.diagnosis.primary_category is None


def test_metric_counts_false_positives_on_inconclusive():
    def row(gt, pred):
        return dict(ground_truth=gt, primary_category=pred, classification='probable', leading_hypothesis=pred,
                    evidence_strength=.7, checks_run=1, traceable=True)
    m = _score([row('a', 'a'), row('inconclusive', 'a'), row('b', None)], ['a', 'b'])
    assert m['classification_report']['a']['precision'] == .5
    assert m['classification_report']['a']['false_positive'] == 1
    assert sum(map(sum, m['confusion_matrix']['rows'])) == 3
    assert m['macro_f1'] == pytest.approx(.3333)


def test_recommendation_links_are_real(conn, dataset):
    out, _ = persist(conn, dataset)
    evidence = {r[0] for r in conn.execute('SELECT id FROM case_evidence WHERE case_id=?', (out['case_id'],))}
    recs = conn.execute('SELECT linked_evidence_ids_json FROM recommendations WHERE case_id=?', (out['case_id'],)).fetchall()
    assert any(json.loads(r[0]) for r in recs)
    assert all(set(json.loads(r[0])) <= evidence for r in recs)


def test_recurring_chargers_count_cases_not_evidence_items(conn, dataset):
    from app.services.metrics import recurring_problems
    item = next(i for i in dataset.complaints() if template_of(i, dataset) == 'T11')
    for _ in range(2):
        diagnose_and_persist(conn, build_complaint(item['payload']))
    rows = recurring_problems(conn)['recurring_chargers']
    assert rows and rows[0]['count'] == 2
    assert rows[0]['category'] == 'network_or_connectivity_issue'


def test_older_change_cannot_erase_newer_learning(conn, dataset):
    _, a = persist(conn, dataset)
    fb.apply_verified_outcome(conn, a['resolution_id'])
    old = next(c for c in fb.list_changes(conn) if c['change_type'] == 'update')
    _, b = persist(conn, dataset)
    fb.apply_verified_outcome(conn, b['resolution_id'])
    with pytest.raises(fb.FeedbackError, match='newer changes'):
        fb.revert_change(conn, old['change_id'])
    assert not conn.in_transaction


def test_learning_apply_is_concurrently_idempotent(conn, dataset):
    _, res = persist(conn, dataset)
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    def apply():
        c = db.connect(path)
        try:
            return fb.apply_verified_outcome(c, res['resolution_id'])
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: apply(), range(2)))
    assert sum(r['applied'] for r in results) == 1
    assert sum(r['already_applied'] for r in results) == 1


def test_rollback_restores_weights_priors_and_observation_counts(conn, dataset):
    _, first = persist(conn, dataset)
    fb.apply_verified_outcome(conn, first['resolution_id'])
    anchor = conn.execute('SELECT MAX(change_id) FROM knowledge_changes').fetchone()[0]
    weights = [tuple(r) for r in conn.execute('SELECT rule_id,weight,active FROM knowledge_rules ORDER BY rule_id')]
    priors = [tuple(r) for r in conn.execute('SELECT tool_name,category,usefulness_score,n_observations FROM tool_priors ORDER BY tool_name,category')]
    _, second = persist(conn, dataset)
    fb.apply_verified_outcome(conn, second['resolution_id'])
    assert fb.rollback_to(conn, anchor, 'test restore')['rolled_back_changes'] > 0
    assert weights == [tuple(r) for r in conn.execute('SELECT rule_id,weight,active FROM knowledge_rules ORDER BY rule_id')]
    assert priors == [tuple(r) for r in conn.execute('SELECT tool_name,category,usefulness_score,n_observations FROM tool_priors ORDER BY tool_name,category')]


def test_activation_is_auditable_and_reversible(conn):
    fb.set_rule_active(conn, 1, False, 'reviewer test')
    change = fb.list_changes(conn)[0]
    assert conn.execute('SELECT active FROM knowledge_rules WHERE rule_id=1').fetchone()[0] == 0
    fb.revert_change(conn, change['change_id'])
    assert conn.execute('SELECT active FROM knowledge_rules WHERE rule_id=1').fetchone()[0] == 1


def test_evaluation_never_overwrites_an_existing_database(tmp_path):
    path = tmp_path / 'precious.db'
    path.write_bytes(b'preserve this file')
    with pytest.raises(FileExistsError):
        evaluate(42, 1, str(path))
    assert path.read_bytes() == b'preserve this file'
