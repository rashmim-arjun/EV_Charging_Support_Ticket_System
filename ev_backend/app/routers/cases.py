from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app import models
from app.core.settings import get_app
from app.schemas import (CaseFull, CaseSummary, ComplaintSubmit, PaginatedCases, CaseTrace, CaseSubmitResult, ResolutionSubmit)
from app.routers.deps import get_conn
from app.routers.errors import ApiHTTP, investigation_error
from app.services import case_service, feedback
from app.services.diagnosis import diagnose_and_persist
from app.services.intake import build_complaint, prepare_intake

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=CaseSubmitResult, status_code=201,
             summary="Submit complaint; agent runs synchronously and returns the diagnosis")
def submit_complaint(payload: ComplaintSubmit, conn=Depends(get_conn)):
    data = prepare_intake(conn, payload.model_dump())
    if get_app(data['app_id']) is None:
        raise ApiHTTP(400, "invalid_app_id", f"Unknown app_id '{data['app_id']}'.",
                      {"valid": [a["id"] for a in
                                 __import__("app.core.settings", fromlist=["apps_raw"]).apps_raw()]})
    complaint = build_complaint(data)
    from app.services import tickets
    communication_session = conn.execute('SELECT app_id FROM communication_sessions WHERE session_id=?',(complaint.session_ref,)).fetchone()
    if communication_session and communication_session['app_id'] != complaint.app_id:
        raise ApiHTTP(422,'session_app_mismatch','The selected session belongs to a different app.')
    case_id=tickets.open_ticket(conn,complaint)
    try:
        if communication_session:
            from app.communication.service import diagnose_session
            result = diagnose_session(conn, complaint.session_ref,complaint=complaint,case_id=case_id)
        else:
            result = diagnose_and_persist(conn, complaint,case_id=case_id)
    except ApiHTTP:
        raise
    except tickets.TicketError as exc:
        raise ApiHTTP(exc.status, exc.code, str(exc), {'ticket_id': case_id}) from exc
    except Exception as exc:
        raise investigation_error(conn, case_id, exc) from exc
    full = case_service.get_case_full(conn, result["case_id"])
    return {"case_summary": full["case"], "case": full}


@router.get("/cases", response_model=PaginatedCases)
def list_cases(conn=Depends(get_conn),
               app_id: Optional[str] = None, category: Optional[str] = None,
               status: Optional[str] = None, data_origin: Optional[str] = None,
               ticket_state: Optional[str] = None, assigned_team: Optional[str] = None, priority: Optional[str] = None,
               date_from: Optional[str] = None, date_to: Optional[str] = None,
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    if status and status not in ("open", "diagnosed", "awaiting_review", "resolved"):
        raise ApiHTTP(400, "invalid_status", f"Unknown status '{status}'.")
    if data_origin and data_origin not in ("real_public_review", "simulated", "manual_test"):
        raise ApiHTTP(400, "invalid_data_origin", f"Unknown data_origin '{data_origin}'.")
    return case_service.list_cases(conn, app_id=app_id, category=category, status=status,
                                   data_origin=data_origin, date_from=date_from,
                                   date_to=date_to, ticket_state=ticket_state,assigned_team=assigned_team,priority=priority,page=page, page_size=page_size)


@router.get("/cases/{case_id}", response_model=CaseFull)
def get_case(case_id: str, conn=Depends(get_conn)):
    full = case_service.get_case_full(conn, case_id)
    if full is None:
        raise ApiHTTP(404, "case_not_found", f"Case {case_id} not found.")
    return full


@router.get("/cases/{case_id}/trace", response_model=CaseTrace)
def get_trace(case_id: str, conn=Depends(get_conn),version: int | None=Query(None,ge=1)):
    trace = case_service.get_trace(conn, case_id,version=version)
    if trace is None:
        raise ApiHTTP(404, "case_not_found", f"Case {case_id} not found.")
    return trace


@router.post("/cases/{case_id}/resolution", status_code=201)
def submit_resolution(case_id: str, payload: ResolutionSubmit, conn=Depends(get_conn)):
    """Reviewer verification. Reviewer validated against active reviewers table."""
    try:
        return feedback.create_resolution(conn, case_id, payload.model_dump())
    except feedback.FeedbackError as exc:
        code_map = {"unauthorised_reviewer": 403, "case_not_found": 404,
                    "already_resolved": 409}
        raise ApiHTTP(code_map.get(exc.code, 400), exc.code, exc.message, exc.details)
