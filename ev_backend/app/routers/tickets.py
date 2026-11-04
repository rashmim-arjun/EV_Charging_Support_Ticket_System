from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from app.routers.deps import get_conn
from app.routers.errors import ApiHTTP, investigation_error
from app.services import tickets
from app.schemas import ComplaintSubmit,CaseSubmitResult

router = APIRouter(prefix='/tickets',tags=['support tickets'])

class TicketUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    version: int = Field(ge=1)
    actor: str = Field(min_length=1,max_length=100)
    reason: str = Field(min_length=5,max_length=2000)
    state: Literal['new','investigating','awaiting_evidence','assigned','escalated','resolved','closed'] | None = None
    assigned_team: str | None = None
    supporting_teams: list[str] | None = Field(default=None,max_length=7)
    priority: Literal['P0','P1','P2','P3'] | None = None

@router.get('/policy')
def configuration():
    return {**tickets.policy(),'states':tickets.STATES,'transitions':{k:sorted(v) for k,v in tickets.TRANSITIONS.items()}}

@router.get('/summary')
def queue_summary(conn=Depends(get_conn)):
    return tickets.summary(conn)

@router.get('/intake-context')
def context(session_ref: str | None = Query(None,max_length=100),conn=Depends(get_conn)):
    from app.services.intake import intake_context
    return intake_context(conn,session_ref)

@router.post('',status_code=201,response_model=CaseSubmitResult)
def intake(request: ComplaintSubmit,conn=Depends(get_conn)):
    from app.core.settings import get_app
    from app.services.intake import build_complaint, prepare_intake
    from app.services.case_service import get_case_full
    data = prepare_intake(conn,request.model_dump())
    if get_app(data['app_id']) is None:
        raise ApiHTTP(400,'invalid_app_id','Select a configured app.')
    row=conn.execute('SELECT app_id FROM communication_sessions WHERE session_id=?',(request.session_ref,)).fetchone()
    if row and row['app_id']!=data['app_id']:
        raise ApiHTTP(422,'session_app_mismatch','The selected session belongs to a different app.')
    case_id=tickets.open_ticket(conn,build_complaint(data))
    full=get_case_full(conn,case_id)
    return {'case_summary':full['case'],'case':full}

@router.get('/{case_id}')
def detail(case_id: str,conn=Depends(get_conn)):
    try:
        return tickets.get_ticket(conn,case_id)
    except tickets.TicketError as e:
        raise ApiHTTP(e.status,e.code,str(e))

@router.patch('/{case_id}')
def change(case_id: str,request: TicketUpdate,conn=Depends(get_conn)):
    try:
        return tickets.update(conn,case_id,request.model_dump())
    except tickets.TicketError as e:
        raise ApiHTTP(e.status,e.code,str(e))

@router.post('/{case_id}/investigate')
def investigate(case_id: str,conn=Depends(get_conn)):
    from app.services.intake import build_complaint
    from app.services.diagnosis import diagnose_and_persist
    from app.communication.service import diagnose_session
    from app.services.case_service import get_case_full
    try:
        current = tickets.get_ticket(conn,case_id)
        if current['state'] in ('resolved','closed'):
            raise tickets.TicketError('reopen_required','Reopen the ticket before investigating again.')
        row = dict(conn.execute('SELECT * FROM cases WHERE case_id=?',(case_id,)).fetchone())
        complaint = build_complaint({'app_id':row['app_id'],'complaint_text':row['complaint_text_redacted'],
            'complaint_ts':row['complaint_ts'],'session_ref':row['reported_session_ref'],'station_id':row['reported_station_id'],
            'user_ref':row['user_ref'],'data_origin':row['data_origin'],'reported_error':row['reported_error'],
            'reported_payment_status':row['reported_payment_status']})
        if conn.execute('SELECT 1 FROM communication_sessions WHERE session_id=?',(complaint.session_ref,)).fetchone():
            diagnose_session(conn,complaint.session_ref,complaint=complaint,case_id=case_id)
        else:
            diagnose_and_persist(conn,complaint,case_id=case_id)
        return get_case_full(conn,case_id)
    except tickets.TicketError as e:
        raise ApiHTTP(e.status,e.code,str(e))
    except Exception as exc:
        raise investigation_error(conn, case_id, exc) from exc
