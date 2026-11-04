import copy
import sqlite3
import pytest
from app.research.dataset import generate_challenge,configurations,validate_partitions
from app.research.experiment import evaluate_research,target,MatchedAgent
from app.communication.correlation import correlate
from app.communication.diagnosis import MultiComponentAgent
from app.communication.storage import persist_dataset
from app.agent.agent import DiagnosticAgent
from app.agent.baseline import FixedCheckBaseline
from app.models import Complaint


def test_challenge_generation_and_semantic_partition_checks():
    data=generate_challenge(repeats=1)
    assert data==generate_challenge(repeats=1)
    with pytest.raises(ValueError,match='equivalent'):
        validate_partitions(configurations()+[copy.deepcopy(configurations()[0])])
    specs=configurations();copied=copy.deepcopy(specs[0]);copied['split']='test';copied['configuration_id']='renamed'
    with pytest.raises(ValueError):validate_partitions(specs+[copied])
    for row in data['rows']:
        assert all(root not in row['complaint'] for root in row['annotations']['physical_roots'])
        assert row['annotations']['observation_completeness']<=1
    combined=[r for r in data['rows'] if len(r['annotations']['physical_roots'])>1]
    assert combined and all(r['annotations']['evidence_sufficient'] for r in combined)
    assert all('+' in target(r['annotations']) for r in combined)


def test_missing_observations_are_not_network_faults_in_development(conn):
    data=generate_challenge(repeats=1)
    rows=[r for r in data['rows'] if r['annotations']['split']!='test' and r['annotations']['evidence_status']=='incomplete']
    for row in rows:
        persist_dataset(conn,row['dataset'])
        result=MultiComponentAgent(conn).run(row['session_id']).result
        assert result['classification']=='inconclusive' and result['confidence'] is None
        assert not result['transport_failure_detected']
        assert not result['communication_failure_detected']


def test_attempt_persistence_and_session_boundaries(conn):
    data=generate_challenge(repeats=1)
    row=next(r for r in data['rows'] if r['annotations']['split']=='train' and r['dataset']['config']['injections'] and r['dataset']['config']['injections'][0]['kind']=='retry')
    persist_dataset(conn,row['dataset'])
    assert conn.execute('SELECT COUNT(*) FROM communication_events WHERE attempt_id IS NOT NULL').fetchone()[0]>=4
    other=next(r for r in data['rows'] if r['annotations']['split']=='validation')
    with pytest.raises(ValueError,match='one session'):
        correlate(row['dataset']['sessions'][0]['events']+other['dataset']['sessions'][0]['events'])


def test_all_agents_strip_annotation_complaint_fields_and_ignore_truth_mutations(conn):
    data=generate_challenge(repeats=1);row=data['rows'][0];persist_dataset(conn,row['dataset'])
    c=Complaint('statiq',row['complaint'],session_ref=row['session_id'],data_origin='simulated',ground_truth_category='network_or_connectivity_issue',scenario_id='privileged-template')
    for cls in (DiagnosticAgent,FixedCheckBaseline):
        run=cls(conn).run(c)
        assert run.state.complaint.ground_truth_category is None and run.state.complaint.scenario_id is None
        before=run.diagnosis.to_dict()
        conn.execute("UPDATE communication_truth SET annotations_json='{}',split='poison',template_id='poison'");conn.commit()
        assert cls(conn).run(c).diagnosis.to_dict()==before


def test_validation_only_experiment_is_reproducible_and_uses_matched_cases():
    a=evaluate_research(repeats=1,development_only=True);b=evaluate_research(repeats=1,development_only=True)
    assert a['challenge']==b['challenge'] and a['freeze_sha256']==b['freeze_sha256']
    assert a['evaluated_partition']=='validation_development'
    left=a['per_session']['text_only'];right=a['per_session']['text_plus_observations']
    assert [(r['session_id'],r['complaint'],r['annotations']) for r in left]==[(r['session_id'],r['complaint'],r['annotations']) for r in right]
    assert a['freeze']['frozen_before_final_test_predictions']
    assert not any(r['annotations']['split']=='test' for rows in a['per_session'].values() for r in rows)
    for result in a['challenge'].values():
        assert sum(sum(r) for r in result['confusion_matrix']['rows'])==result['sessions']
