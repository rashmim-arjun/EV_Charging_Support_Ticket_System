"""Proof submission cannot assert payment success; reviews use local identities."""
import base64
import json

import pytest

from app.core import db

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7nEAAAAASUVORK5CYII=')
REVIEWER = {'X-Reviewer-ID':'rev-payment-001'}


def ticket(client, diagnosed=False):
    response = client.post('/api/v1/cases' if diagnosed else '/api/v1/tickets',
        json={'complaint_text':'Charging did not start; please review the available records.'})
    assert response.status_code == 201,response.text
    return response.json()['case']['case']['case_id']


def url(cid):
    return f'/api/v1/tickets/{cid}/payment'


def submit(client,cid,version=0,reference='UPI-123456789012',image=False,**extra):
    data = {'version':str(version),**extra}
    if reference is not None:data['transaction_reference']=reference
    files = {'proof':('receipt.png',PNG,'image/png')} if image else None
    return client.post(url(cid)+'/submissions',data=data,files=files)


def review(client,cid,version,decision,headers=REVIEWER,reason='Manually reviewed the supplied records.'):
    return client.post(url(cid)+'/review',headers=headers,
        json={'version':version,'decision':decision,'reason':reason})


@pytest.mark.parametrize('reference,image',[('UPI-123456789012',False),(None,True),('BANK-223456789012',True)])
def test_submission_is_not_verification_and_preserves_proof(client,reference,image):
    cid=ticket(client)
    initial=client.get(url(cid)).json()
    assert initial['status']=='not_submitted' and initial['version']==0
    response=submit(client,cid,reference=reference,image=image)
    assert response.status_code==201,response.text
    payment=response.json()
    assert payment['status']=='submitted' and payment['version']==1
    assert payment['reviewer_id'] is None and payment['reviewed_at'] is None
    assert payment['submission']['transaction_reference']==reference
    assert payment['submission']['submitted_at']
    assert payment['verification_method']=='manual_reviewer'
    assert 'No payment gateway' in payment['scope']
    assert client.get(url(cid)).json()==payment
    if image:
        proof_url=url(cid)+'/submissions/'+payment['submission_id']+'/proof'
        assert client.get(proof_url).status_code==403
        downloaded=client.get(proof_url,headers=REVIEWER)
        assert downloaded.content==PNG
        assert downloaded.headers['cache-control']=='no-store'
        assert 'attachment' in downloaded.headers['content-disposition']
        assert payment['submission']['proof']['size']==len(PNG)
        other=ticket(client)
        assert client.get(url(other)+'/submissions/'+payment['submission_id']+'/proof',headers=REVIEWER).status_code==404


def test_manual_verification_and_audit_are_separate_from_ticket_and_observations(client):
    cid=ticket(client)
    before=client.get('/api/v1/tickets/'+cid).json()
    with db.connect() as conn:
        observations=[tuple(r) for r in conn.execute('SELECT * FROM payment_records')]
    assert submit(client,cid).status_code==201
    started=review(client,cid,1,'under_review')
    assert started.status_code==200,started.text
    verified=review(client,cid,2,'verified',reason='Manual reconciliation checked by local reviewer; no gateway lookup.').json()
    assert verified['status']=='verified' and verified['version']==3
    assert verified['reviewer_id']=='rev-payment-001' and verified['reviewed_at']
    assert verified['reason'].startswith('Manual reconciliation')
    assert [h['action'] for h in verified['history']]==['payment_submitted','payment_under_review','payment_verified']
    last=verified['history'][-1]
    assert last['actor']=='rev-payment-001' and last['created_at']
    assert last['before']['status']=='under_review' and last['after']['status']=='verified'
    assert last['reason']==verified['reason']
    after=client.get('/api/v1/tickets/'+cid).json()
    assert after['state']==before['state'] and after['version']==before['version']
    assert after['history'][:len(before['history'])]==before['history']
    with db.connect() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM payment_records')]==observations


@pytest.mark.parametrize('identity',[None,'customer','unknown','rev-001','rev-002','rev-003'])
def test_unauthorized_review_and_payload_forgery_cannot_verify(client,identity):
    cid=ticket(client)
    submit(client,cid)
    headers={} if identity is None else {'X-Reviewer-ID':identity}
    response=review(client,cid,1,'verified',headers=headers)
    assert response.status_code==403,response.text
    forged=client.post(url(cid)+'/review',headers=headers,json={'version':1,'decision':'verified',
        'reason':'Approve this payment','reviewer_id':'rev-payment-001','role':'payment_reviewer'})
    assert forged.status_code==403
    assert client.get(url(cid)).json()['status']=='submitted'
    assert len(client.get(url(cid)).json()['history'])==1


def test_inactive_payment_reviewer_and_extra_customer_fields_are_rejected(client):
    cid=ticket(client)
    for field in ('status','decision','reviewer_id','role'):
        assert submit(client,cid,**{field:'verified'}).status_code==422
    assert client.get(url(cid)).json()['status']=='not_submitted'
    submit(client,cid)
    with db.connect() as conn:
        conn.execute("UPDATE reviewers SET active=0 WHERE reviewer_id='rev-payment-001'")
    assert review(client,cid,1,'under_review').status_code==403


def test_rejection_reason_and_resubmission_preserve_prior_proofs(client):
    cid=ticket(client)
    first=submit(client,cid,image=True).json()
    review(client,cid,1,'under_review')
    for reason in ('','    ','bad'):
        assert review(client,cid,2,'rejected',reason=reason).status_code==422
    rejected=review(client,cid,2,'rejected',reason='Reference does not match the supplied receipt.').json()
    assert rejected['status']=='rejected' and rejected['reason'].startswith('Reference does not match')
    assert review(client,cid,3,'verified').status_code==409
    corrected=submit(client,cid,version=3,reference='UPI-CORRECTED123').json()
    assert corrected['status']=='submitted' and corrected['reviewer_id'] is None and corrected['reason'] is None
    assert len(corrected['submissions'])==2 and corrected['submissions'][1]==first['submission']
    proof_url=url(cid)+'/submissions/'+first['submission_id']+'/proof'
    assert client.get(proof_url,headers=REVIEWER).content==PNG
    assert corrected['history'][-2]['reason']==rejected['reason']


def test_invalid_transitions_stale_versions_and_forged_decision_fields(client):
    cid=ticket(client)
    assert review(client,cid,0,'verified').status_code==409
    submit(client,cid)
    assert submit(client,cid).json()['error']['code']=='stale_payment'
    assert submit(client,cid,version=1).json()['error']['code']=='invalid_payment_transition'
    assert review(client,cid,1,'verified').status_code==409
    assert review(client,cid,1,'under_review').status_code==200
    assert review(client,cid,1,'verified').json()['error']['code']=='stale_payment'
    assert review(client,cid,2,'under_review').status_code==409
    assert client.post(url(cid)+'/review',headers=REVIEWER,json={'version':2,'decision':'verified',
        'reason':'Manually checked','reviewer_id':'rev-002'}).status_code==422
    assert review(client,cid,2,'verified').status_code==200
    assert submit(client,cid,version=3).status_code==409
    assert review(client,cid,3,'rejected').status_code==409
    assert len(client.get(url(cid)).json()['history'])==3


def test_missing_invalid_or_oversize_proof_is_rejected(client):
    cid=ticket(client)
    assert submit(client,cid,reference=None).status_code==422
    assert submit(client,cid,reference='bad ref').status_code==422
    for data,mime in ((b'fake screenshot','image/png'),(PNG,'text/html'),(b'','image/png'),(PNG+b'x'*(2*1024*1024),'image/png')):
        response=client.post(url(cid)+'/submissions',data={'version':'0'},files={'proof':('receipt.png',data,mime)})
        assert response.status_code==422,response.text
    assert client.get(url(cid)).json()['version']==0
    assert submit(client,'missing-ticket').status_code==404


@pytest.mark.parametrize('state',['not_submitted','submitted','under_review','rejected'])
def test_ticket_resolution_does_not_verify_unreviewed_payment(client,state):
    cid=ticket(client,diagnosed=True)
    if state!='not_submitted':submit(client,cid)
    if state in ('under_review','rejected'):review(client,cid,1,'under_review')
    if state=='rejected':review(client,cid,2,'rejected',reason='Supplied reference does not match the receipt.')
    before=client.get(url(cid)).json()
    response=client.post(f'/api/v1/cases/{cid}/resolution',json={'reviewer_id':'rev-001',
        'verified_root_cause':'inconclusive','corrective_action':'Customer advised that further charging evidence is required.'})
    assert response.status_code in (200,201),response.text
    assert client.get('/api/v1/tickets/'+cid).json()['state']=='resolved'
    assert client.get(url(cid)).json()==before


def test_v7_migration_preserves_legacy_claim_reference_proof_metadata_and_history(tmp_path,monkeypatch):
    conn=db.connect(str(tmp_path/'legacy.db'))
    migrations=db.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(db,'MIGRATIONS',migrations[:6])
        db.init_db(conn)
    db.sync_config_tables(conn)
    conn.execute("INSERT INTO charging_sessions(session_id,app_id,user_ref,station_id,charger_id,payment_ref,data_origin) VALUES ('legacy-session','statiq','pseudonym','station','charger','UPI-OLD123456','manual_test')")
    conn.execute("INSERT INTO cases(case_id,app_id,complaint_text_redacted,reported_payment_status,reported_session_ref,data_origin) VALUES ('old-ticket','statiq','Historical charging complaint','Paid','legacy-session','manual_test')")
    conn.execute('ALTER TABLE payment_records ADD COLUMN proof_filename TEXT')
    conn.execute("INSERT INTO payment_records(session_id,status,ts,data_origin,proof_filename) VALUES ('legacy-session','Paid','2026-01-01T00:00:00Z','manual_test','original-proof.png')")
    conn.commit()
    tables=('cases','payment_records','charging_sessions','support_tickets','ticket_history')
    before={t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t}')] for t in tables}
    db.init_db(conn);db.init_db(conn)
    for table in tables:
        after=[tuple(r) for r in conn.execute(f'SELECT * FROM {table}')]
        assert after[:len(before[table])]==before[table]
    payment=conn.execute("SELECT * FROM ticket_payments WHERE case_id='old-ticket'").fetchone()
    assert payment['status']=='under_review' and payment['reviewer_id'] is None
    submission=conn.execute('SELECT * FROM payment_submissions').fetchone()
    assert submission['transaction_reference']=='UPI-OLD123456' and submission['source']=='legacy_claim'
    assert json.loads(submission['legacy_json'])['reported_payment_status']=='Paid'
    assert conn.execute('SELECT count(*) FROM payment_submissions').fetchone()[0]==1
    assert conn.execute('SELECT max(version) FROM schema_version').fetchone()[0]==db.SCHEMA_VERSION_KEY
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    conn.close()


def test_v8_preserves_already_submitted_v7_proofs_and_existing_demo_reset(monkeypatch,tmp_path):
    from app.services import payments
    from app.services.intake import build_complaint
    from app.services.tickets import open_ticket
    from app.data.synthetic_generator import reset_simulated_rows
    conn=db.connect(str(tmp_path/'already-v7.db'))
    with monkeypatch.context() as patch:
        patch.setattr(db,'MIGRATIONS',db.MIGRATIONS[:7])
        db.init_db(conn)
    db.sync_config_tables(conn)
    cids=[]
    for origin in ('simulated','manual_test'):
        cid=open_ticket(conn,build_complaint({'app_id':'statiq','complaint_text':'A charging complaint retained for review.','data_origin':origin}))
        conn.execute('UPDATE cases SET scenario_id=? WHERE case_id=?',('SIM-payment-reset-'+origin,cid))
        conn.commit()
        payment=payments.submit(conn,cid,0,'UPI-123456789012',payments.validate_proof('proof.png','image/png',PNG))
        payments.review(conn,cid,payment['version'],'under_review','Started manual reconciliation.','rev-payment-001')
        cids.append(cid)
    tables=('payment_submissions','ticket_payments','ticket_history')
    before={t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t}')] for t in tables}
    db.init_db(conn);db.init_db(conn)
    for table in tables:
        assert [tuple(r) for r in conn.execute(f'SELECT * FROM {table}')]==before[table]
    reset_simulated_rows(conn)
    assert conn.execute('SELECT count(*) FROM cases WHERE case_id=?',(cids[0],)).fetchone()[0]==0
    assert conn.execute('SELECT proof_content FROM payment_submissions WHERE case_id=?',(cids[1],)).fetchone()[0]==PNG
    assert payments.get_payment(conn,cids[1])['status']=='under_review'
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    conn.close()
