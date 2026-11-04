"""Monitoring and generation API; public session responses omit truth annotations."""
import json
import os
import threading
from pathlib import Path
from fastapi import APIRouter, Depends, Query
from app.communication.catalog import templates, ROOTS, VERSION
from app.communication.schema import GenerateRequest, CommunicationEvaluationRequest, GenerationResult, SessionPage, SessionDetail
from app.communication.simulator import generate_dataset
from app.communication.storage import persist_dataset, list_sessions
from app.communication.service import session_detail, diagnose_session
from app.communication.evaluation import evaluate_communication, write_communication_reports
from app.routers.deps import get_conn
from app.routers.errors import ApiHTTP
from app.services.tickets import TicketError

router = APIRouter(prefix='/communication', tags=['communication simulation'])
_evaluation_lock = threading.Lock()


def report_directory():
    return Path(os.environ.get('EV_REPORT_DIR') or Path(__file__).resolve().parents[2] / 'reports/live/communication')


@router.get('/templates')
def configuration():
    return {'version': VERSION, 'scenarios': list(ROOTS), 'templates': templates(),
            'protocol_scope': 'OCPP/ISO 15118 inspired semantic simulation; no protocol compliance claim.'}


@router.post('/generate', status_code=201, response_model=GenerationResult)
def generate(req: GenerateRequest, conn=Depends(get_conn)):
    try:
        dataset = generate_dataset(req)
        result = persist_dataset(conn, dataset)
        warnings = [{'session_id': s['session_id'], 'unapplied': s['truth']['unapplied_injections']} for s in dataset['sessions'] if s['truth']['unapplied_injections']]
        return {**result, 'session_ids': [s['session_id'] for s in dataset['sessions']], 'warnings': warnings, 'data_origin': 'simulated'}
    except ValueError as exc:
        raise ApiHTTP(422, 'invalid_simulation', str(exc))


@router.get('/sessions', response_model=SessionPage)
def sessions(conn=Depends(get_conn), run_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return list_sessions(conn, run_id=run_id, page=page, page_size=page_size)


@router.get('/sessions/{session_id}', response_model=SessionDetail)
def detail(session_id: str, conn=Depends(get_conn)):
    try:
        return session_detail(conn, session_id)
    except LookupError as exc:
        raise ApiHTTP(404, 'simulation_session_not_found', str(exc))


@router.post('/sessions/{session_id}/diagnose')
def diagnose(session_id: str, conn=Depends(get_conn)):
    try:
        return diagnose_session(conn, session_id)
    except TicketError as exc:
        raise ApiHTTP(exc.status,exc.code,str(exc))
    except LookupError as exc:
        raise ApiHTTP(404, 'simulation_session_not_found', str(exc))


@router.get('/evaluation')
def evaluation_summary():
    path = report_directory() / 'communication_evaluation.json'
    if not path.exists():
        return {'available': False}
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ApiHTTP(503, 'evaluation_report_unavailable', 'The saved communication evaluation could not be read.')
    return {'available': True, **{k: v for k, v in report.items() if k != 'per_session'}}


@router.post('/evaluation')
def run_evaluation(req: CommunicationEvaluationRequest):
    if not _evaluation_lock.acquire(blocking=False):
        raise ApiHTTP(409, 'evaluation_running', 'A communication evaluation is already running.')
    try:
        report = evaluate_communication(req.seed, req.per_template)
        write_communication_reports(report, report_directory())
        return {k: v for k, v in report.items() if k != 'per_session'}
    finally:
        _evaluation_lock.release()
