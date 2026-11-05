# Manual payment submission and review

This update adds ticket-level payment verification without changing fault diagnosis, evaluation labels, benchmark scores, research reports or charging simulation. The inspected v6 checkout had no UPI upload API, proof storage table or payment verification form. Its 238 payment observations (`captured`, `failed`, `refund_pending`) were simulated diagnostic input; none were `Paid` and no uploaded proofs existed. There were 285 existing tickets. No claim is made that an automatic proof-to-Paid implementation was found in this checkout.

## State transitions and separation

```text
not_submitted -> submitted -> under_review -> verified
                                  |
                                  v
                               rejected -> submitted (new attempt)
```

Submission is a customer claim. An image or reference cannot establish settlement. Only active local reviewers whose stored role is exactly `payment_reviewer` may start review or make a decision. Verification means a human recorded approval and a reason; no gateway or bank/UPI response is generated. A verified decision cannot be overwritten through this workflow. A rejected submission may be corrected, preserving old references, proof bytes/metadata and review history. Each action must carry the current **payment** version; stale writes return HTTP 409. Payment versions are independent of ticket/diagnosis versions.

Payment review does not change charging diagnosis, ownership, ticket state, knowledge or learning. Ticket resolution/closure is permitted when payment is not submitted, submitted, under review or rejected. Those actions do not change the payment's status. Staff must follow up separately on an outstanding payment review.

## API

All endpoints have prefix `/api/v1/tickets/{case_id}/payment`:

| Method / suffix | Purpose |
| --- | --- |
| `GET` | Current state/version, current and previous submission metadata, reviewer decision and payment audit history. |
| `POST /submissions` | Multipart/urlencoded form: `version`, optional `transaction_reference`, optional uploaded `proof`. Reference or proof is required. Creates `submitted`, never `verified`. Extra/duplicate fields are rejected. |
| `POST /review` | JSON: `version`, `decision` (`under_review`, `verified`, `rejected`), and `reason` (5-2000 trimmed characters). Requires `X-Reviewer-ID` for an active payment reviewer. `reviewer_id`, roles or verification flags cannot be injected through this body. |
| `GET /submissions/{submission_id}/proof` | Download the actual stored screenshot for this ticket; requires a payment reviewer. Downloads use attachment, no-store and nosniff headers. |

Reference syntax is only input validation, not payment validation. Supported proof is PNG/JPEG, maximum 2 MB; the server checks content signatures and declared media type. The file is supporting evidence, not an authenticity-checked image. Proof is stored in SQLite rather than a public upload directory. No original filename is used as a filesystem path. The API exposes metadata to local ticket users; proof bytes require a reviewer identity.

**Identity limitation:** `X-Reviewer-ID` uses the application's existing local identity model, checked against the database. A customer cannot assert a state or role through the submission payload. However this model has no login, session or identity authentication; a person with API access could claim a known authorized reviewer ID. This is a local academic authorization model, not production security. The UI labels it as local identity selection. The seeded reviewer `rev-payment-001` has the dedicated `payment_reviewer` role; existing reviewers' roles and active flags are preserved. Diagnosis reviewers/field engineers do not automatically receive payment-review permission.

## Versioned migration and preservation

Migration v7 runs in the existing atomic, versioned migration mechanism. It adds:

- `payment_submissions`: immutable submission IDs linked to existing ticket IDs; customer reference, server submission time, source, legacy provenance, screenshot bytes and filename/type/size/SHA256.
- `ticket_payments`: separate status, optimistic version, current submission, reviewer, review time and reason. Existing and new tickets start at `not_submitted`, version 0.
- `create_ticket_payment`: inserts the independent payment state for new tickets.
- One dedicated local reviewer when that ID is absent. Existing identities are never reassigned a role.

No pre-v7 table or column is dropped or rewritten. `payment_records`, `charging_sessions`, cases, diagnostic evidence and resolutions remain unchanged. Existing uploaded proof metadata in any additional legacy columns is retained in those original rows; this checkout has no such columns. `ticket_history` remains append-only through the application.

Migration **v8** reconstructs only the two new payment tables, copies every value (including proof bytes and timestamps), recreates their index/trigger and adds case-deletion cascades. This retains the existing deliberate simulated-fixture reset behavior; manual tickets and their submissions survive that reset. A running development backend had already applied v7, so this compatibility correction uses its own version rather than editing an applied migration. A regression test migrates a v7 database with actual proof bytes and review history, asserts all rows are identical after upgrade, and exercises the existing reset. This is not a new automatic cleanup or payment deletion API.

For older claims, case-level reported `Paid`, `verified` or `success`, or linked payment-record `Paid`/`verified` values create a `legacy_claim` submission with **under_review**, version 1, no reviewer and no approval. The original values and linked payment-record IDs are retained as provenance, and an available `charging_sessions.payment_ref` is copied. One `payment_legacy_review_required` history event explains why review is required. The imported time is the migration time, not an invented historical submission time; the UI explicitly says the original time is unknown. Original claim/observation fields remain unchanged for compatibility, and complaint displays label them as unverified customer claims.

Other diagnostic observation states (including synthetic `captured`/`success` session observations) are not interpreted as manual verification and do not change. Unlinked payment observations have no ticket-level verification decision and remain in their original table. Re-running migration is idempotent through its version marker. Migration regression tests also exercise a legacy `Paid` claim with a reference and custom proof metadata, checking that original rows/history survive and nothing becomes verified.

Before migrating an existing database, stop the backend and run this from the project root in Windows Git Bash:

```bash
./.venv/Scripts/python.exe ev_backend/scripts/check_local_database.py --repair
```

That script creates a SQLite backup before applying migrations. Ordinary API startup also applies migrations, so use the backup command first when retaining local data. Backups, proof-containing databases and `.env` files are excluded from Git and the submission package. To roll back a database, retain the backup and restore it together with the corresponding older code while the backend is stopped; do not downgrade a live schema in place.

## User interface

Each ticket has a **Payment verification** panel with status, reference, server submission/import time, screenshot metadata, reviewer identity/time and rejection reason. Customer proof submission and manual review are separate forms. Only a dedicated active payment reviewer appears in the reviewer selector. Reviewer controls expose start, verify and reject actions at the applicable states; the backend enforces the same rules. The panel supports loading, disabled actions while saving, missing-proof/invalid-file errors, retry/reload after stale updates and empty histories. Prior rejected submissions and audit values remain visible.

No payment gateway, independent payment verification, refund execution, email, SMS, push notification or other external notification service is integrated. A screenshot can be misleading or fabricated. The application records a manual reviewer decision; it cannot attest to the underlying transfer.

## Verification

Verified on Windows on 5 November 2026 using the existing installed dependencies. All API/unit tests use disposable databases; browser workflows start FastAPI and the production Vite preview against a disposable seeded database. They do not submit test proofs to the working database.

| Command / check | Actual result |
| --- | --- |
| `./.venv/Scripts/python.exe -m pytest ev_backend/tests -q -o addopts= --tb=short` | **215 passed**, one existing Starlette/httpx deprecation warning, 65.48 seconds. |
| `npm.cmd test` (in `ev_frontend`) | **53 passed** across seven test files. |
| `npm.cmd run build` | Passed; 673 modules transformed. |
| `npm.cmd run build -- --outDir .tmp/communication-preview` | Passed; isolated production preview built. |
| `E2E_ISOLATED=1 E2E_PRODUCTION=1 npm.cmd run test:e2e` | **12 passed**, desktop and mobile, approximately 1.1 minutes. |
| Working database upgrade and preservation check | Schema **8**, SQLite integrity `ok`, zero foreign-key violations; every original row matched the pre-change SQLite backup. |
| Protected source diff | Diagnosis rules, communication logic, generators, labels, evaluation/research code and stored benchmark reports unchanged. |

The first full backend run exposed two reset compatibility failures; the versioned v8 correction resolved them. The final full run above passed, including that compatibility regression. Frontend and browser output also contains existing Node color-environment warnings; no functional build/test failure remains.

The working database retained all **285 cases/tickets, 238 payment observations, 394 ticket-history rows**, and all original diagnosis, resolution, reference and other table rows. One local payment reviewer and migration markers were added. All 285 ticket-level payment states are `not_submitted`: there were no historical `Paid` claims or uploaded proofs in this working database. Historical `Paid` and pre-existing v7 proof preservation were exercised in regression databases, not invented as working data. The pre-change backup is `ev_diagnosis.db.backup-payment-20261105-094814` and is excluded from Git/submission archives.

Payment regressions cover reference-only/screenshot-only submissions, unauthorized/inactive/wrong-role reviewers, body forgery, allowed/invalid transitions, stale versions, rejection reasons, history and proof retention, legacy migration and resolution without payment verification. Desktop/mobile browser tests exercise upload, reload, screenshot download, manual rejection, correction, charging-ticket resolution while under review, and later manual verification.

To repeat from the project root in Windows Git Bash:

```bash
./.venv/Scripts/python.exe -m pytest ev_backend/tests -q -o addopts= --tb=short
cd ev_frontend
npm.cmd test
npm.cmd run build
npm.cmd run build -- --outDir .tmp/communication-preview
E2E_ISOLATED=1 E2E_PRODUCTION=1 npm.cmd run test:e2e
```

## Changed files

| Area | Files |
| --- | --- |
| Payment backend | `ev_backend/app/services/payments.py`, `ev_backend/app/services/payment_migration.py`, `ev_backend/app/routers/payments.py` |
| Migration/router registration | `ev_backend/app/core/db.py`, `ev_backend/app/main.py` |
| Payment UI and transport | `ev_frontend/src/components/PaymentPanel.jsx`, `ev_frontend/src/api.js`, `ev_frontend/src/styles.css` |
| Existing ticket/intake screens | `ev_frontend/src/pages/CaseDetail.jsx`, `ev_frontend/src/pages/NewCase.jsx` |
| Backend regressions | `ev_backend/tests/test_payments.py`, `ev_backend/tests/test_connection_and_schema_repair.py` |
| Frontend/browser regressions | `ev_frontend/src/components/PaymentPanel.test.jsx`, `ev_frontend/src/api.test.js`, `ev_frontend/e2e/payments.spec.js` |
| Documentation | `README.md` (Payment proof and manual verification), `docs/PAYMENT_VERIFICATION.md`, `docs/FINAL_SUBMISSION.md` (link to this later verification record) |

Remaining limitations are the local selectable-identity model, manual assessment of potentially misleading proof, no independent settlement/gateway/bank/UPI verification, and no external refund/notification actions. No dependency additions were needed.
