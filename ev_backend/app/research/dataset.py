"""Declared challenge configurations. Annotations are never agent inputs."""
import copy
import hashlib
import json
from datetime import datetime,timedelta

from app.communication.simulator import generate_dataset
from app.communication.catalog import ROOTS

VERSION='support-challenge-v1'
SPLITS=('train','validation','test')
# Independently written business expectations, deliberately not imported from
# the production routing policy. These are reviewable synthetic policy oracles.
EXPECTATIONS={
 'none':('no_fault_established','triage','P3'),
 'charger_controller_timeout':('session_fails_to_start','charger_maintenance','P2'),
 'vehicle_bms_fault':('vehicle_specific_or_telematics_issue','vehicle_specialists','P1'),
 'authorization_conflict':('session_fails_to_start','application_support','P2'),
 'payment_conflict':('payment_or_billing_failure','payment_support','P2'),
 'connector_fault':('connector_or_charger_hardware_fault','charger_maintenance','P1'),
 'network_delay':('network_or_connectivity_issue','network_operations','P2'),
 'network_loss':('network_or_connectivity_issue','network_operations','P2'),
 'network_duplicate':('network_or_connectivity_issue','network_operations','P2'),
 'stale_availability':('charger_availability_mismatch','csms_engineering','P2'),
 'metering_mismatch':('payment_or_billing_failure','csms_engineering','P2'),
}


def hash_value(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def configurations():
    result=[]
    for index,split in enumerate(SPLITS):
        for root in EXPECTATIONS:
            result.append(dict(split=split,profile=root,mode='complete',injections=[],expected_roots=[] if root=='none' else [root],sufficient=True))
        op=['Authorize','SessionSetupReq','PaymentCapture'][index]
        result.append(dict(split=split,profile='none',mode='complete',injections=[dict(kind='retry',operation=op,delay_ms=3700+index*2100)],expected_roots=['network_loss'],sufficient=True))
        result.append(dict(split=split,profile='none',mode=['missing_sender','missing_receiver','missing_response'][index],
            operation=['SetChargingProfile','RequestStartTransaction','MeterValues'][index],injections=[],expected_roots=[],sufficient=False))
        result.append(dict(split=split,profile=['vehicle_bms_fault','payment_conflict','connector_fault'][index],mode='complete',
            injections=[dict(kind='duplicate',operation=['Authorize','MeterValues','PaymentHold'][index])],
            expected_roots=sorted([['vehicle_bms_fault','payment_conflict','connector_fault'][index],'network_duplicate']),sufficient=True))
        result.append(dict(split=split,profile='none',mode=['contradictory_drop','contradictory_status','contradictory_reply'][index],injections=[],expected_roots=[],sufficient=False))
        result.append(dict(split=split,profile='inconclusive',mode='complete',injections=[],expected_roots=[],sufficient=False))
    result.extend([
        dict(split='test',profile='metering_mismatch',mode='complete',injections=[dict(kind='duplicate',operation='Authorize')],expected_roots=['metering_mismatch','network_duplicate'],sufficient=True),
        dict(split='test',profile='none',mode='missing_sender',operation='PaymentCapture',injections=[],expected_roots=[],sufficient=False),
        dict(split='test',profile='none',mode='missing_receiver',operation='SessionSetupReq',injections=[],expected_roots=[],sufficient=False),
        dict(split='test',profile='network_loss',mode='hidden_loss',injections=[],expected_roots=['network_loss'],sufficient=False),
        dict(split='test',profile='vehicle_bms_fault',mode='safety_gap',injections=[],expected_roots=['vehicle_bms_fault'],sufficient=False),
        dict(split='test',profile='none',mode='nearby_session',injections=[],expected_roots=[],sufficient=True),
        dict(split='test',profile='inconclusive',mode='reported_safety',injections=[],expected_roots=[],sufficient=False),
    ])
    for item in result:
        # Variant is a real different startup path, meter schedule and trigger,
        # not just a renamed ID. The shared causal engine remains a limitation.
        item['physical_variant']=SPLITS.index(item['split'])
        item['configuration_id']='CFG-'+hash_value(item)[:16]
    return result


def semantic_fingerprint(spec):
    return hash_value({k:v for k,v in spec.items() if k not in ('split','configuration_id','expected_roots','sufficient')})


def validate_partitions(specs):
    seen={}
    for spec in specs:
        fingerprint=semantic_fingerprint(spec)
        if fingerprint in seen:
            raise ValueError('Duplicate or equivalent challenge configuration across manifests')
        seen[fingerprint]=spec['split']
    combinations={s:{tuple(c['expected_roots']) for c in specs if c['split']==s and len(c['expected_roots'])>1} for s in SPLITS}
    if any(combinations[a]&combinations[b] for a,b in [('train','test'),('validation','test'),('train','validation')]):
        raise ValueError('Multi-fault combinations overlap between partitions')
    return {s:[c for c in specs if c['split']==s] for s in SPLITS}


def complaint_for(session,split):
    """Visible symptoms from physical/app observations, never internal root labels."""
    events=session['events']
    payment=next((e for e in events if e['event_type']=='payment.displayed'),None)
    status=session['truth']['physical_status']
    if any(e['event_type']=='connector.occupied' for e in events):
        phrases=['The map showed a free charger, but another car was already plugged in when I arrived.',
                 'I followed the app to a free connector and found it already in use by someone else.',
                 'Your map said this point was available, but a different car was using it. Please check.']
    elif session['truth']['physical_energy_kwh'] and status in ('stopped','failed'):
        phrases=['Charging began and then ended before my target. Please check my visit.',
                 'The car received some charge but the session ended early. Can support investigate?',
                 'I returned to find the charge had stopped short of my target. What happened?']
    elif status=='completed' and payment:
        phrases=['My car finished charging, but I would like support to check this visit and its receipt.',
                 'The charging visit finished. Please review the session record and payment.',
                 'Charging ended and the app displayed a receipt. Could you check that everything agrees?']
    elif status=='completed':
        phrases=['Charging ended but the final receipt is unclear. Please check what happened.',
                 'My charging finished, and I am still waiting for the final account update.',
                 'The car got its charge but the app has not clearly confirmed the final bill.']
    else:
        phrases=['I connected the car and tried to start, but I could not get a charge.',
                 'The session would not begin after I plugged in. Please investigate my visit.',
                 'I tried charging at the station, but the car received no energy. Can you help?']
    return phrases[SPLITS.index(split)]


def generate_challenge(seed=20261104,repeats=2):
    specs=configurations();manifests=validate_partitions(specs);rows=[]
    for spec in specs:
        for index in range(repeats):
            sub_seed=int(hash_value([seed,spec['configuration_id'],index])[:7],16)
            data=generate_dataset(dict(seed=sub_seed,split=spec['split'],per_template=1,scenarios=[spec['profile']],injections=spec['injections']))
            session=data['sessions'][0];truth=session['truth']
            actual=sorted(r for r in truth['root_causes'] if r and r!='none')
            if actual!=spec['expected_roots']:
                raise ValueError(f"Fired physical causes differ from predeclared expectation: {spec['configuration_id']}: {actual}")
            full=copy.deepcopy(session['events']);mode=spec['mode']
            if mode.startswith('missing_'):
                op=spec['operation']
                if mode=='missing_response':
                    op+='.response'
                    session['events']=[e for e in full if e['payload'].get('operation')!=op]
                else:
                    kind='message.sent' if mode=='missing_sender' else 'message.received'
                    session['events']=[e for e in full if not (e['event_type']==kind and e['payload'].get('operation')==op)]
            elif mode=='hidden_loss':
                session['events']=[e for e in full if e['event_type'] not in ('transport.dropped','request.timeout')]
            elif mode=='safety_gap':
                session['events']=[e for e in full if not (e['event_type']=='message.received' and e['payload'].get('operation')=='PowerDeliveryStop')]
            elif mode.startswith('contradictory_'):
                if mode=='contradictory_reply':
                    received=next(e for e in session['events'] if e['event_type']=='message.received' and e['payload'].get('accepted'))
                    received['payload']['accepted']=False
                else:
                    kind='transport.delivered' if mode=='contradictory_drop' else 'charger.status'
                    original=next(e for e in full if e['event_type']==kind)
                    extra=copy.deepcopy(original)
                    extra['event_id']=session['session_id']+'-OBS-'+hash_value(spec['configuration_id'])[:8]
                    extra['sequence']=max(e['sequence'] for e in full)+1
                    if mode=='contradictory_drop':
                        extra.update(event_type='transport.dropped',status='lost',severity='error')
                    else:
                        extra.update(status='occupied')
                    session['events'].append(extra)
            if mode=='nearby_session':
                # The deliberate near-twin pair shares wall time and semantic
                # contents but retains entirely independent opaque identities.
                offset=timedelta(milliseconds=index)
                base=datetime(2026,10,14,12,0,0,tzinfo=datetime.fromisoformat(session['started_at']).tzinfo)
                delta=base-datetime.fromisoformat(session['started_at'])+offset
                for e in session['events']:
                    e['timestamp']=(datetime.fromisoformat(e['timestamp'])+delta).isoformat()
                session['started_at']=(base+offset).isoformat()
            session['ended_at']=max(e['timestamp'] for e in session['events'])
            evidence_status='sufficient' if spec['sufficient'] else 'contradictory' if mode.startswith('contradictory') else 'incomplete'
            public_complaint=complaint_for(session,spec['split'])
            if mode=='reported_safety':
                public_complaint='I saw smoke beside the connector and need someone to review my charging visit urgently.'
            safety_visible=any(e['event_type'] in ('bms.fault','connector.fault') for e in session['events'])
            if not spec['sufficient'] or len(actual)>1:
                expected=('inconclusive','triage','P1' if safety_visible else 'P2')
            else:
                expected=EXPECTATIONS[actual[0] if actual else 'none']
            if mode=='reported_safety':
                expected=('inconclusive','triage','P0')
            annotations={'configuration_id':spec['configuration_id'],'split':spec['split'],'physical_roots':actual,
                'physical_status':truth['physical_status'],'physical_energy_kwh':truth['physical_energy_kwh'],
                'affected_components':truth['affected_components'],'configured_injections':spec['injections'],
                'observation_completeness':min(len({e['event_id'] for e in session['events']} & {e['event_id'] for e in full})/len(truth['expected_events']),1),'evidence_status':evidence_status,
                'evidence_sufficient':spec['sufficient'],'expected_support':dict(zip(('classification','assigned_team','priority'),expected)),
                'expected_escalation':expected[2] in ('P0','P1'),'semantic_fingerprint':semantic_fingerprint(spec)}
            rows.append({'dataset':data,'session_id':session['session_id'],'complaint':public_complaint,'annotations':annotations})
    return {'version':VERSION,'seed':seed,'repeats':repeats,'manifests':manifests,'rows':rows}
