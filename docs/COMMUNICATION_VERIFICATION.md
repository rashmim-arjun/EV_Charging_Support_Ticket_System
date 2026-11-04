# Communication extension verification

Verified locally on **2026-11-04**, Windows PowerShell, Python 3.13.5, Node 24.14.1, Vite 7.3.7, Vitest 4.1.12 and Microsoft Edge. Commands below are the actual PowerShell commands; Git Bash equivalents are in the README.

## Results

| Check | Actual outcome |
|---|---|
| Full backend suite, separate `.venv-clean` environment | **132 passed**; one upstream Starlette/httpx deprecation warning |
| Frontend unit/component suite | **24 passed**, five files |
| Production build | **Passed**, 670 modules; communication route lazy chunk 15.43 kB (5.00 kB gzip) |
| Production browser suite | **4 passed**: original and communication workflows at desktop/mobile sizes |
| Production browser suite using `.venv-clean` | **4 passed**, 21.9 seconds, fresh scratch database after the contradictory-message fix |
| Python requirements | No broken requirements found |
| npm audit, low threshold | **0 vulnerabilities** at verification time |
| Legacy benchmark | 200 unchanged cases; adaptive **91% / macro-F1 0.9548**, fixed **78% / 0.7214** |
| Communication benchmark | 144 generated; **48 train / 48 validation / 48 test**, four examples per family per split |
| New agent communication results | Root accuracy **100%**, decision accuracy **100%**, ten-fault macro-F1 **1.0** |
| New agent localization / communication detection | **100% / 100%** on modeled fault cases |
| New agent checks / test calibration | **5.083** mean checks; ECE **0.041667**, Brier **0.001736**, 44 assertions |
| Reproducibility | Both evaluation CLIs passed independent repeated scratch runs |
| Working database | **250 original cases**, **12 communication sessions**, integrity **ok**, **0 FK violations** |
| Configured custom dataset CLI | Persisted/exported a delayed-payment session into a separate scratch database |

The new-agent score describes authored synthetic mechanisms, not real equipment or independent clinical-style validation. Legacy methods on the communication benchmark have 18.18% exact-root accuracy, 33.33% broad category accuracy and 0.1 ten-fault macro-F1. They receive the existing table projection and have a coarser taxonomy; these scores do not contradict their separate original benchmark. See the full [methodology and limitations](COMMUNICATION_PLATFORM.md) and [generated report](../ev_backend/reports/communication_evaluation.md).

## Exact verification commands

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest ev_backend\tests -q -o addopts= --tb=short
.\.venv-clean\Scripts\python.exe -m pytest ev_backend\tests -q -o addopts= --tb=short
.\.venv-clean\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe ev_backend\scripts\run_evaluation.py --seed 42 --per-template 8 --check-reproducibility
.\.venv\Scripts\python.exe ev_backend\scripts\evaluate_communication.py --seed 42 --per-template 4 --install-calibration --check-reproducibility
.\.venv\Scripts\python.exe ev_backend\scripts\generate_communication.py --seed 42 --split test --per-template 1
.\.venv\Scripts\python.exe ev_backend\scripts\generate_communication.py --config examples\communication_config.json --db .tmp\communication-custom-verified.db --export .tmp\communication-custom-verified.json
```

The normal environment's earlier full run passed 101 tests before the custom-annotation and contradiction regressions were added; the final complete 132-test suite was verified in `.venv-clean`. No new dependencies were required by the extension. `.venv-clean` was installed from the lockfile during the previous verification; it was reused, not newly downloaded during this run.

From `ev_frontend/`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd audit --audit-level=low

# Separate production artifact with the isolated API URL:
$env:VITE_API_BASE='http://localhost:8010/api/v1'
npm.cmd run build -- --outDir .tmp/communication-preview
Remove-Item Env:VITE_API_BASE
$env:E2E_ISOLATED='1'
$env:E2E_PRODUCTION='1'
npm.cmd run test:e2e
$env:E2E_CLEAN='1'
npm.cmd run test:e2e
```

Commands were issued in fresh tool shells as appropriate; API URL overrides applied only to the isolated preview build. The normal `dist/` build uses the default API on port 8000. The browser runner starts real FastAPI and Vite preview processes on 8010/5174 with a fresh database/report directory. A pre-existing user server on 8000 was left running. The new observation stream, typed API responses and feedback persistence were exercised against those real servers.

The follow-up contradictory-message fix added 27 backend regressions and one frontend regression. Full backend/frontend tests, normal and isolated production builds, all four browser workflows, and both repeated evaluation pipelines were rerun. See [the fix record](CONTRADICTORY_MESSAGE_FIX.md) for behavior and coverage. The final clock/orphan-flow consistency and missing response-identity checks were verified by the complete backend suite and repeated communication evaluation; they do not change the UI or standard generated events.

Read-only database validation used:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('ev_diagnosis.db'); print('integrity:',c.execute('pragma integrity_check').fetchone()[0]); print('FK violations:',len(c.execute('pragma foreign_key_check').fetchall())); print('MC sessions:',c.execute('select count(*) from communication_sessions').fetchone()[0]); print('legacy cases:',c.execute('select count(*) from cases').fetchone()[0])"
```

## Coverage and observed fixes

Backend tests cover successful lifecycle/energy reconciliation, every scenario on all three split variants, drop/delay/duplicate/stale/timeout behavior, missing deliveries/responses, insufficient/conflicting evidence, event provenance and ordering, health degradation, ground-truth independence, idempotent persistence/FKs, legacy reset preservation, reviewer learning/deactivation, API contracts/validation/404s, atomic rollback and deterministic evaluation partitioning. Custom-annotation tests verify actual fired causes, sub-deadline delays, multiple causes and an injection that prevents the requested fault profile.

Frontend tests cover generation, session events, health, correlation selection, evidence navigation, diagnosis links and errors. Browser tests exercise drop diagnosis, timeline/flow/anomaly views, reviewer feedback and applied learning, normal and incomplete-observation sessions, and the three-method evaluation. Original browser tests continue to cover complaint submission, persisted evidence/trace, resolution/learning, cases, evaluation and CSV review import. Both sizes assert no page-level horizontal overflow or uncaught page errors. Saved desktop/mobile communication screenshots were visually inspected.

Testing found a real UI defect where switching sessions retained an unsuitable tab; it now resets to the timeline. The final audit found custom annotated exports could retain a requested profile that never fired; annotations now record actual injected mechanisms. A report layout issue mixing confidence rows into category tables was also corrected and reports regenerated. No legacy labels or scoring denominators were changed.

The in-app browser connector could not initialize because its runtime rejected a missing `sandboxPolicy` field. Repository Playwright with installed Edge provided the verified fallback. Frontend compiler/build/browser commands required execution outside the restricted filesystem sandbox to read dependencies; they completed successfully. This is an environment constraint, not an unresolved application failure.

## Remaining limits

There is no live charger/car/app ingestion, hardware validation, OCPP/ISO compliance, production authentication or independent expert-labeled validation dataset. The simulator has authored fault coverage, single-process transport and simplified energy modeling; custom combinations are exploratory and excluded from the standard single-mechanism benchmark. Confidence fitting and four examples per held-out family do not establish real-world calibration. Existing legacy fixture inconsistencies remain documented and scored.

Runtime databases, exports under `.tmp/`, local environments, browser screenshots/traces, logs, caches, dependencies and build outputs are ignored. Intentional evaluation reports and the validation calibration artifact are retained. The workspace does not contain usable local Git metadata, so a tracked-file diff could not be verified; the changed-file inventory is documented in [CHANGES.md](CHANGES.md).
