from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, File, UploadFile, Query

from app.core.settings import get_app
from app.redaction import redact_pii
from app.routers.deps import get_conn
from app.routers.errors import ApiHTTP
from app.schemas import ReviewImportResult, ReviewOut

router = APIRouter(prefix="/reviews", tags=["reviews"])

MAX_BYTES = 2 * 1024 * 1024  # 2 MB upload cap


def _insert_review(conn, row: dict, errors: list) -> int:
    if not isinstance(row, dict) or any(row.get(k) is not None and not isinstance(row[k], str)
                                         for k in ('app_id', 'text', 'original_text', 'data_origin', 'source', 'source_ref', 'review_date', 'problem_category')):
        errors.append('row skipped (expected an object with text fields)')
        return 0
    app_id = (row.get("app_id") or "").strip() or 'ev_support'
    text = (row.get("text") or row.get("original_text") or "").strip()
    origin = (row.get("data_origin") or "").strip()
    if not text:
        errors.append("row skipped (empty text)")
        return 0
    if get_app(app_id) is None:
        errors.append(f"row skipped (unknown app_id '{app_id}')")
        return 0
    if origin not in ("real_public_review", "simulated", "manual_test"):
        errors.append(f"row skipped (invalid data_origin '{origin}')")
        return 0
    from app.core.settings import category_ids
    if row.get('problem_category') and row['problem_category'] not in category_ids():
        errors.append('row skipped (unknown problem_category)')
        return 0
    conn.execute(
        "INSERT INTO reviews(app_id, source, source_ref, review_date, original_text,"
        " redacted_text, problem_category, data_origin) VALUES (?,?,?,?,?,?,?,?)",
        (app_id, (row.get("source") or "user_import").strip(), row.get("source_ref"),
         row.get("review_date"), redact_pii(text), redact_pii(text),
         row.get("problem_category"), origin))
    return 1


@router.post("/import", response_model=ReviewImportResult, summary="Import legally collected reviews (CSV or JSON)")
async def import_reviews(file: UploadFile = File(...), conn=Depends(get_conn)):
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ApiHTTP(400, "upload_too_large", "Upload exceeds 2 MB limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiHTTP(400, "encoding_error", "File must be UTF-8 text (CSV or JSON).")
    imported = skipped = 0
    errors: list[str] = []
    try:
        conn.execute('BEGIN IMMEDIATE')
        if file.filename and file.filename.endswith(".json") or text.lstrip().startswith(("[", "{")):
            data = json.loads(text)
            rows = data if isinstance(data, list) else data.get("reviews", [])
            if not isinstance(rows, list) or (isinstance(data, dict) and 'reviews' not in data):
                raise ApiHTTP(400, 'bad_json', 'JSON must be an array or an object with a reviews array.')
            for r in rows:
                n = _insert_review(conn, r, errors)
                imported += n
                skipped += 1 - n
        else:
            reader = csv.DictReader(io.StringIO(text))
            required = {"text", "data_origin"}
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                raise ApiHTTP(400, "bad_csv",
                              "CSV must have at least columns: text, data_origin "
                              "(optional: source, source_ref, review_date, problem_category)")
            for r in reader:
                n = _insert_review(conn, r, errors)
                imported += n
                skipped += 1 - n
        conn.commit()
    except ApiHTTP:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise ApiHTTP(400, "parse_error", "Could not import upload; no rows were saved.")
    return {"imported": imported, "skipped": skipped, "errors": errors[:50]}


@router.get("", response_model=list[ReviewOut])
def list_reviews(conn=Depends(get_conn), app_id: str | None = None,
                 data_origin: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    q, params = ["SELECT * FROM reviews WHERE 1=1"], []
    if app_id:
        q.append("AND app_id=?"); params.append(app_id)
    if data_origin:
        q.append("AND data_origin=?"); params.append(data_origin)
    q.append("ORDER BY review_id DESC LIMIT ? OFFSET ?"); params.extend([limit, offset])
    return [dict(r) for r in conn.execute(" ".join(q), tuple(params)).fetchall()]
