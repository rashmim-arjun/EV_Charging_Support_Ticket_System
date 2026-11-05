"""Local manual payment review, independent of diagnosis and ticket resolution."""
import hashlib
import re
import uuid
from pathlib import PurePosixPath

from app.core.transactions import atomic
from app.services.tickets import TicketError, audit

MAX_PROOF_BYTES = 2 * 1024 * 1024
PAYMENT_ROLE = 'payment_reviewer'
SCOPE = ('Manual local reviewer decision only. No payment gateway, bank/UPI lookup, '
         'refund, external notification or independent transaction verification is integrated.')


def require_reviewer(conn, reviewer_id):
    row = conn.execute('SELECT * FROM reviewers WHERE reviewer_id=? AND active=1 AND role=?',
                       (reviewer_id, PAYMENT_ROLE)).fetchone()
    if row is None:
        raise TicketError('payment_reviewer_required',
            'Select an active local reviewer with the payment_reviewer role. Customer submissions cannot verify payments.',403)
    return dict(row)


def _row(conn, case_id):
    row = conn.execute('SELECT * FROM ticket_payments WHERE case_id=?',(case_id,)).fetchone()
    if row is None:
        raise TicketError('ticket_not_found','Support ticket not found.',404)
    return dict(row)


def _metadata(row):
    data = {key: row[key] for key in ('submission_id','transaction_reference','submitted_at','source')}
    data['proof'] = ({'name':row['proof_name'],'content_type':row['proof_type'],
        'size':row['proof_size'],'sha256':row['proof_sha256']} if row['proof_name'] else None)
    return data


def get_payment(conn, case_id):
    from app.services.tickets import get_ticket
    current = _row(conn,case_id)
    submissions = [_metadata(row) for row in conn.execute(
        'SELECT submission_id,transaction_reference,submitted_at,source,proof_name,proof_type,proof_size,proof_sha256 '
        'FROM payment_submissions WHERE case_id=? ORDER BY rowid DESC',(case_id,))]
    current['submission'] = next((s for s in submissions if s['submission_id']==current['submission_id']),None)
    current['submissions'] = submissions
    current['history'] = [h for h in get_ticket(conn,case_id)['history'] if h['action'].startswith('payment_')]
    current['verification_method'] = 'manual_reviewer'
    current['scope'] = SCOPE
    return current


def validate_reference(reference):
    reference = (reference or '').strip()
    if reference and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/\-]{5,99}',reference):
        raise TicketError('invalid_payment_reference',
            'Use a transaction reference of 6-100 letters, digits, dots, slashes, underscores or hyphens.',422)
    return reference or None


def validate_proof(name, content_type, content):
    if not name:
        return None
    if not content or len(content)>MAX_PROOF_BYTES:
        raise TicketError('invalid_payment_proof','Upload a non-empty PNG or JPEG screenshot, at most 2 MB.',422)
    if not ((content_type=='image/png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or
            (content_type=='image/jpeg' and content.startswith(b'\xff\xd8\xff'))):
        raise TicketError('invalid_payment_proof','The screenshot content must match its PNG or JPEG file type.',422)
    name = PurePosixPath(name.replace('\\','/')).name
    name = ''.join(c for c in name if c.isprintable())[:180] or 'payment-proof'
    return (name,content_type,len(content),hashlib.sha256(content).hexdigest(),content)


def _version(current, version):
    if current['version']!=version:
        raise TicketError('stale_payment','Payment information changed. Reload the payment panel before trying again.')


def _audit_value(current):
    return {key:current[key] for key in ('status','version','submission_id','reviewer_id','reviewed_at','reason')}


@atomic
def submit(conn, case_id, version, reference=None, proof=None):
    before = _row(conn,case_id)
    _version(before,version)
    if before['status'] not in ('not_submitted','rejected'):
        raise TicketError('invalid_payment_transition','A new submission is allowed only before submission or after rejection.')
    reference = validate_reference(reference)
    if not reference and not proof:
        raise TicketError('payment_proof_required','Provide a transaction reference or a PNG/JPEG payment screenshot.',422)
    sid = 'PS-'+uuid.uuid4().hex
    conn.execute('INSERT INTO payment_submissions(submission_id,case_id,transaction_reference,source,'
        'proof_name,proof_type,proof_size,proof_sha256,proof_content) VALUES (?,?,?,\'customer\',?,?,?,?,?)',
        (sid,case_id,reference,*(proof or (None,)*5)))
    conn.execute("UPDATE ticket_payments SET status='submitted',version=version+1,submission_id=?,"
        "reviewer_id=NULL,reviewed_at=NULL,reason=NULL,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE case_id=?",
        (sid,case_id))
    after = _row(conn,case_id)
    metadata = _metadata(conn.execute('SELECT * FROM payment_submissions WHERE submission_id=?',(sid,)).fetchone())
    audit(conn,case_id,'payment_submitted','customer','Payment information submitted; not verified.',
          _audit_value(before),{**_audit_value(after),'submission':metadata})
    return get_payment(conn,case_id)


@atomic
def review(conn, case_id, version, decision, reason, reviewer_id):
    reviewer = require_reviewer(conn,reviewer_id)
    before = _row(conn,case_id)
    _version(before,version)
    allowed = {'submitted':{'under_review'},'under_review':{'verified','rejected'}}
    if decision not in allowed.get(before['status'],set()):
        raise TicketError('invalid_payment_transition',
            'Start review of a submitted payment before verifying or rejecting it. Final decisions cannot be overwritten.')
    reason = (reason or '').strip()
    if len(reason)<5 or len(reason)>2000:
        raise TicketError('payment_reason_required','Record a manual review reason of 5-2000 characters.',422)
    conn.execute("UPDATE ticket_payments SET status=?,version=version+1,reviewer_id=?,reason=?,"
        "reviewed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE case_id=?",
        (decision,reviewer['reviewer_id'],reason,case_id))
    after = _row(conn,case_id)
    audit(conn,case_id,'payment_'+decision,reviewer['reviewer_id'],reason,
          _audit_value(before),{**_audit_value(after),'verification_method':'manual_reviewer','reviewer_role':reviewer['role']})
    return get_payment(conn,case_id)
