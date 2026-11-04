# Verification record

Verified on **3 November 2026**, Windows / PowerShell, Python **3.13.5**, Node **24.14.1**, Vite **7.3.7**, Vitest **4.1.12**, installed Microsoft Edge.

## Actual results

| Check | Result |
|---|---|
| Original backend suite | 16 passed, 1 failed (outdated case-response expectation) |
| Final backend suite in empty `.venv-clean` | **65 passed**, one upstream Starlette/httpx deprecation warning |
| Frontend tests after `npm ci` | **17 passed**, 4 test files |
| Frontend production build | **Passed**, 669 modules; no oversized-chunk warning |
| Live desktop + mobile workflow, dev server | **2 passed** |
| Live desktop + mobile workflow, production build + clean backend environment | **2 passed**, 12.0 seconds total |
| Python dependency consistency | `No broken requirements found` |
| npm dependency audit | **0 vulnerabilities** at verification time |
| Generated root database | Schema **3**, **250 cases**, **150 sessions**, SQLite integrity `ok`, **0 FK violations** |
| Repeat seed command | **0 inserted rows** in every reported table; no duplicate cases |
| Main evaluation | 200 unchanged legacy synthetic cases; adaptive **91% / F1 0.9548**, baseline **78% / F1 0.7214** |
| Evaluation reproducibility | Two independent scratch runs produced identical predictions, evidence scores, confidence, tool order, signals and learning headline metrics |

The final browser workflow actually submitted a complaint, verified a diagnosis/evidence/trace, submitted reviewer feedback, previewed and applied learning, inspected tool priors and the audit log, filtered resolved cases, ran a 25-case evaluation through the UI, and uploaded a CSV whose phone number was redacted. It ran at **1440×1000** and **390×844**, with no page JavaScript errors and no page-level horizontal overflow. Both frontend and backend were real servers; browser tests did not mock their API.

Component tests independently cover intake navigation, metadata failures/retry, pagination/filter reset, error-versus-empty states, evidence/feedback/learning interactions, rule activation, review upload/refresh, evaluation validation/errors and dashboard failures. Hook tests reproduce stale-response races and synchronous loader failures. Transport tests verify filters, structured errors, network failures and multipart uploads. Date tests cover UTC/offset consistency.

Backend regression tests cover exact/app-scoped session matching, ambiguous sessions, unrelated hardware/payment records, telematics identity scoping, weak-category diagnoses, unverified reported codes, surfaced tool failures, corrected false-positive accounting, real recommendation links, distinct-case proposal thresholds, proposal deduplication, concurrent idempotent learning, stale-change rejection, rollback state restoration, activation/revert, idempotent seed/reset, read endpoint schemas, malformed/oversized/partial review imports, complete feedback workflows and evaluation scratch-file protection.

## Exact successful commands used

The recorded commands below were executed in **PowerShell**, not Git Bash. For a `MINGW64` prompt, use the Git Bash instructions in the README: forward-slash Windows interpreter paths and `E2E_CLEAN=1 E2E_PRODUCTION=1 npm.cmd run test:e2e`. The `.venv-clean` directory is an optional second verification environment; regular setup and browser tests use `.venv` by default.

Repository root (a second environment was created specifically to check clean installation):

```powershell
.\.venv\Scripts\python.exe -m venv .venv-clean
.\.venv-clean\Scripts\python.exe -m pip install -r ev_backend\requirements-lock.txt
.\.venv-clean\Scripts\python.exe -m pip check
.\.venv-clean\Scripts\python.exe ev_backend\scripts\seed_database.py --db .tmp\clean-demo.db --seed 42 --per-template 10
.\.venv-clean\Scripts\python.exe ev_backend\scripts\seed_database.py --seed 42 --per-template 10
.\.venv-clean\Scripts\python.exe ev_backend\scripts\seed_database.py --seed 42 --per-template 10
.\.venv-clean\Scripts\python.exe -m uvicorn app.main:app --app-dir ev_backend --host 127.0.0.1 --port 8000
# While the server was running:
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/cases?page_size=1'
```

From `ev_backend/`:

```powershell
..\.venv-clean\Scripts\python.exe -m pytest -q -o addopts= --tb=short
..\.venv\Scripts\python.exe scripts\fit_calibration.py --seed 314159 --per-template 20
..\.venv-clean\Scripts\python.exe scripts\run_evaluation.py --seed 42 --per-template 8 --check-reproducibility
```

From `ev_frontend/`:

```powershell
npm.cmd ci
npm.cmd test
npm.cmd run build
npm.cmd audit --audit-level=low
npm.cmd run test:e2e
$env:E2E_CLEAN = '1'
$env:E2E_PRODUCTION = '1'
npm.cmd run test:e2e
```

`E2E_CLEAN=1` selects `.venv-clean`; `E2E_PRODUCTION=1` selects the already-built Vite preview rather than the development server. Normal `npm.cmd run test:e2e` uses `.venv` and the dev server. Both test modes provision disposable data/report directories and stop their own servers. Ports 8000 and 5173 must be available.

The separate documented Uvicorn CLI startup also returned HTTP 200, `status=ok`, schema version 3, and 250 cases, using the regenerated root database. The verification server was then stopped.

## Artifacts and reproducibility

- `ev_backend/reports/evaluation_report.md`: procedure, headlines, category tables, both confusion matrices, calibration and learning breakdowns, fixture audit and reproducibility result.
- `evaluation_results.json`: machine-readable metrics, learning details, frozen calibration metadata and dataset inconsistencies.
- `evaluation_results.csv` and `evaluation_categories.csv`: headline and class-specific metrics.
- `evaluation_cases.json` and `evaluation_errors.json`: every scored case and detailed failures, including executed tools/signals and tool errors.
- `docs/original-evaluation/`: historical supplied reports preserved before edits.
- `ev_backend/app/config/calibration.json`: measured development fit, never fitted on the seed-42 test set.

Runtimes and generation timestamps naturally vary. Case outcomes and scoring are deterministic for the fixed fixture configuration. The test suite does not refit calibration or overwrite the main reports: its evaluation API test redirects reports to a temporary directory. Browser tests do the same through `EV_REPORT_DIR`.

## Limits and verification caveats

The in-app Browser connector failed during connection setup with an environment metadata error. Verification continued using the installed local Edge browser through the repository's Playwright runner. Desktop and mobile results above are genuine local browser runs, not a claim that the in-app connector worked.

Windows sandbox restrictions blocked access to the installed Python launcher runtime, npm registry access and the frontend compiler's parent-directory reads. Required installation/build/browser commands were rerun with approved execution permissions. The initial evaluator depended on pandas; standard-library CSV writing removed that unnecessary runtime dependency and its compiled-DLL issue. The clean environment successfully generated the final reports without pandas.

The current upstream Starlette TestClient emits one warning recommending its newer HTTP client; all 65 tests still pass. npm also prints maintenance notices for Recharts 2 and a jsdom transitive text-encoding package; the final audit reports no known vulnerabilities. These are maintenance notices, not silently ignored failing checks.

This checkout was supplied without a `.git` directory. Ignore rules now cover databases, environment files, logs, caches, dependencies and build/browser artifacts, but there was no Git index to modify or inspect. The user's local `.env` remains private and ignored; `.env.example` is preserved. The local generated database remains available for the demonstration and is regenerable from the README.

The remaining scientific limitations are documented in `DIAGNOSIS_FINDINGS.md`: unchanged inconsistent fixtures, unresolved payment claims, synthetic template dependence, aggregate calibration and no independent real-world validation. These prevent a defensible claim of **100% diagnostic accuracy or production readiness**, despite successful functional checks for the local academic workflow. Linux/macOS commands are documented but were not executed on those platforms.
