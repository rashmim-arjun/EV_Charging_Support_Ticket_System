# Connection and diagnosis repair — 4 November 2026

## Reproduced causes

The existing SQLite database had 255 cases and claimed schema version 5, but `case_checks`, `case_evidence`, and `resolutions` lacked `diagnosis_version`. It also retained the old unique resolution index on `case_id`. The migration runner trusted the version marker, so restarting skipped those missing changes. On a disposable copy of that file, `POST /api/v1/cases` saved the complaint then returned HTTP 503; running the diagnosis directly exposed `sqlite3.OperationalError: table case_evidence has no column named diagnosis_version`. Existing backend logs also contained `no such column: diagnosis_version` on case-detail and trace reads.

The frontend used an absolute `http://localhost:8000/api/v1` URL without a Vite proxy. Backend CORS allowed only `http://localhost:5173`; a preflight from `http://127.0.0.1:5173` reproduced HTTP 400. In addition, unhandled server errors were returned outside normal CORS middleware, making them unreadable to cross-origin browser requests. The generic frontend fetch error obscured these failures. The backend's IPv4 bind address also differed from the hostname in the browser URL; the proxy now uses the explicit matching IPv4 address.

Both synchronous diagnosis routes caught exceptions without logging their causes. No external AI integration, missing API key, or missing runtime package caused the diagnosis failure. `pip check` and `npm ls --depth=0` passed.

## Repair

- The default browser API base is `/api/v1`. Vite dev and preview forward `/api` to `http://127.0.0.1:8000`. Set `EV_API_TARGET` to change that target; an explicit `VITE_API_BASE` remains supported. Trailing slashes are normalized. A disconnected backend returns HTTP 502 with actionable JSON. Vite stops if its port is occupied.
- Both local frontend origins are allowed for direct API access. `EV_CORS_ORIGINS` supports a comma-separated override. Internal-error responses also retain CORS headers for allowed origins.
- Additive migration 6 repairs missing version columns and the resolution index. It handles both the inconsistent shipped database and a correct v5 database. Schema changes and migration version records commit atomically, with rollback on failure. Existing ticket IDs, records, and functionality are retained.
- Diagnosis exceptions are logged with ticket IDs and tracebacks. Responses distinguish a busy database, schema mismatch, and other investigation failures, retain the ticket ID, and explain recovery. Intake remains durable.
- The local observation snapshot can safely be finalized by a different FastAPI worker thread, preventing SQLite cleanup warnings.
- No AI key is required. The existing local diagnostic agents remain the working offline mechanism. Available observations support diagnoses; missing observations produce inconclusive results, unresolved questions, and recommended checks. An engine exception remains an explicit failure, never a fabricated diagnosis.

The working database now has schema version 6, all 255 cases, `PRAGMA integrity_check = ok`, and zero foreign-key violations. A SQLite backup is retained beside it as `ev_diagnosis.db.backup-20261104-140739-643820`. Browser tests use a separate disposable database.

## Changed files

| File | Purpose |
| --- | --- |
| `ev_backend/app/core/db.py` | Repair migration 6; atomic migrations |
| `ev_backend/app/core/settings.py` | Environment override for CORS origins |
| `ev_backend/app/core/observations.py` | Thread-safe snapshot cleanup |
| `ev_backend/app/config/settings.json` | Both default local CORS origins |
| `ev_backend/app/main.py` | Readable CORS responses on internal failures |
| `ev_backend/app/routers/errors.py` | Logged, actionable investigation errors |
| `ev_backend/app/routers/cases.py` | Use shared investigation error handling |
| `ev_backend/app/routers/tickets.py` | Same handling for investigation retries |
| `ev_backend/.env.example` | Document backend variables and local diagnosis |
| `ev_backend/scripts/check_local_database.py` | Read-only inspection; optional backup and migration |
| `ev_backend/tests/test_connection_and_schema_repair.py` | Schema, transaction, CORS, missing-key, and failure regressions |
| `ev_frontend/src/api.js` | Relative API base and meaningful transport errors |
| `ev_frontend/src/api.test.js` | Proxy, outage, and invalid-response tests |
| `ev_frontend/vite.config.js` | Dev/preview API proxy and outage response |
| `ev_frontend/.env.example` | Document proxy and direct API configuration |
| `ev_frontend/playwright.config.js` | Browser tests exercise the default proxy |
| `ev_frontend/e2e/connection.spec.js` | Save, diagnose without logs, display, reload |
| `README.md` | Correct Windows Git Bash paths, setup, environment, migration instructions |
| `.gitignore` | Exclude database backups and disposable reproduction copy |
| `docs/CONNECTION_AND_DIAGNOSIS_FIX.md` | Findings, changed-file list, verification |

## Verification

- Backend full suite: 174 tests passed. Includes reproducing the shipped v5 schema drift, preserving records, diagnosis/reinvestigation, transactional rollback, both local CORS origins, custom origins, readable HTTP 500 responses, unavailable API keys, and durable failures.
- Frontend: all 34 unit tests passed; production build succeeded; all installed top-level packages resolved.
- Playwright with Microsoft Edge: all 8 tests passed on desktop and mobile. The runner started FastAPI and Vite against a disposable SQLite database. Covered complaint submission, persisted diagnosis and reload, missing-evidence results, evidence/trace display, correlated-session diagnosis, investigation/reinvestigation, ownership, reviewer resolution, learning, closure, evaluation, and imports.
- Live Vite dev and production-preview proxies targeting an unused backend port returned HTTP 502, code `backend_unavailable`, and startup/retry instructions. Production preview also served the built UI successfully.
- The only backend test warning was the installed Starlette test client's deprecation of its `httpx` integration; no dependency change was required.
- The in-app Browser connection was unavailable, so browser verification used the project's Playwright runner. Windows sandbox permissions blocked Vite configuration reads; frontend tests/build and the browser run succeeded with approved access outside that sandbox.

Exact Windows Git Bash install/start commands are in the root README under **Git Bash on Windows (MINGW64)**. Start commands use `DP-main/.venv/Scripts/python.exe` explicitly; stop an older instance before starting a replacement on the same port. No reseed or database reset is required. For static production deployment, configure `/api` forwarding at the hosting server or build with an explicit API URL and configure CORS.
