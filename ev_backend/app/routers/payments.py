"""Customer proof submission and explicitly separate local reviewer actions."""
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.routers.deps import get_conn
from app.routers.errors import ApiHTTP
from app.services import payments
from app.services.tickets import TicketError

router = APIRouter(prefix='/tickets/{case_id}/payment',tags=['manual payment verification'])


class PaymentReview(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    version: int = Field(ge=0)
    decision: Literal['under_review','verified','rejected']
    reason: str = Field(min_length=5,max_length=2000)


def payment_reviewer(conn=Depends(get_conn), reviewer_id: str | None=Header(None,alias='X-Reviewer-ID')):
    # This selects an existing local demo identity, not a production login.
    try:
        return payments.require_reviewer(conn,reviewer_id)
    except TicketError as exc:
        raise ApiHTTP(exc.status,exc.code,str(exc)) from exc


@router.get('')
def detail(case_id: str,conn=Depends(get_conn)):
    try:
        return payments.get_payment(conn,case_id)
    except TicketError as exc:
        raise ApiHTTP(exc.status,exc.code,str(exc)) from exc


@router.post('/submissions',status_code=201)
async def submit(case_id: str,request: Request,
                 version: Annotated[int,Form(ge=0)],
                 transaction_reference: Annotated[str | None,Form(max_length=100)]=None,
                 proof: Annotated[UploadFile | None,File()]=None,conn=Depends(get_conn)):
    try:
        form = await request.form()
        if set(form)-{'version','transaction_reference','proof'} or any(len(form.getlist(k))!=1 for k in form):
            raise TicketError('invalid_payment_submission',
                'Submit only version, transaction_reference and an optional proof file. Review decisions are not customer fields.',422)
        validated = None
        if proof is not None:
            content = await proof.read(payments.MAX_PROOF_BYTES+1)
            validated = payments.validate_proof(proof.filename,proof.content_type,content)
        return payments.submit(conn,case_id,version,transaction_reference,validated)
    except TicketError as exc:
        raise ApiHTTP(exc.status,exc.code,str(exc)) from exc
    finally:
        if proof is not None:
            await proof.close()


@router.post('/review')
def review(case_id: str,payload: PaymentReview,reviewer=Depends(payment_reviewer),conn=Depends(get_conn)):
    try:
        return payments.review(conn,case_id,payload.version,payload.decision,payload.reason,reviewer['reviewer_id'])
    except TicketError as exc:
        raise ApiHTTP(exc.status,exc.code,str(exc)) from exc


@router.get('/submissions/{submission_id}/proof')
def proof(case_id: str,submission_id: str,reviewer=Depends(payment_reviewer),conn=Depends(get_conn)):
    row = conn.execute('SELECT proof_content,proof_name FROM payment_submissions '
                       'WHERE submission_id=? AND case_id=?',(submission_id,case_id)).fetchone()
    if row is None or row['proof_content'] is None:
        raise ApiHTTP(404,'payment_proof_not_found','No screenshot was uploaded for this submission.')
    return Response(bytes(row['proof_content']),media_type='application/octet-stream',headers={
        'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['proof_name'],safe=''),
        'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})
