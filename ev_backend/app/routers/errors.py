"""Shared error-raising helpers so every router returns the same shape."""
from __future__ import annotations

from fastapi import HTTPException
import sqlite3

from app.core.logging_setup import get_logger


class ApiHTTP(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        super().__init__(status_code=status_code,
                         detail={"code": code, "message": message, "details": details})


def investigation_error(conn, case_id: str, exc: Exception) -> ApiHTTP:
    """Retain intake, log the cause, and return actionable, non-sensitive details."""
    from app.services import tickets
    log = get_logger('app.investigation')
    log.error('Investigation failed for ticket %s', case_id,
              exc_info=(type(exc), exc, exc.__traceback__))
    reason = 'investigation_error'
    action = 'Retry investigation from the saved ticket. If it fails again, request human review and check ev_backend/logs/ev_backend.log.'
    if isinstance(exc, sqlite3.OperationalError):
        if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
            reason = 'database_busy'
            action = 'The database is busy. Close other database writers, then retry investigation from the saved ticket.'
        elif 'no such' in str(exc).lower() or 'no column' in str(exc).lower():
            reason = 'database_schema_mismatch'
            action = 'The database schema needs an upgrade. Restart the updated backend to apply migrations, then retry investigation from the saved ticket.'
    try:
        tickets.investigation_failed(conn, case_id)
    except Exception:
        log.exception('Could not record failed-investigation status for ticket %s', case_id)
    return ApiHTTP(503, 'diagnosis_failed', f'Ticket {case_id} was saved, but investigation failed. {action}',
                   {'ticket_id': case_id, 'reason': reason, 'action': action})
