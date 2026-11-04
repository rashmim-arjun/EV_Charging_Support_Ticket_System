# Changed and added files

This distribution has no Git metadata. The list below records implementation changes and intentional deliverables; runtime dependencies, caches, logs, local environment files, build outputs and scratch databases are excluded.

## Project and documentation

- `.gitignore` — ignore generated databases/WAL files, Python/Node caches, environments, logs, builds and browser outputs; preserve `.env.example`.
- `README.md` — installation, startup, seeding, test/build/browser commands, academic demonstration, measured results, Mermaid architecture and scope.
- `docs/IMPLEMENTATION_PLAN.md` — prioritized implementation plan.
- `docs/DIAGNOSIS_FINDINGS.md` — five weak categories, root causes, calibration, learning analysis and remaining case-level limitations.
- `docs/VERIFICATION.md` — exact successful commands, actual results, environment and verification limits.
- `docs/CHANGES.md` — this inventory.
- `docs/original-evaluation/evaluation_report.md`, `evaluation_results.json`, `evaluation_results.csv` — preserved supplied reports, unchanged in content.
- `examples/reviews.csv`, `examples/reviews.json` — valid manual-test review imports.

## Backend

- `ev_backend/requirements.txt`, `requirements-lock.txt` — tested direct pins and reproducible transitive dependency set; no pandas requirement.
- `ev_backend/app/main.py` — evaluation is a required router rather than silently omitted after an import failure.
- `ev_backend/app/models.py` — evidence/signal associations, supported hypothesis ranking, calibrated confidence.
- `ev_backend/app/schemas.py` — concrete submission, diagnosis, activation and evaluation contracts.
- `ev_backend/app/redaction.py` — preserve diagnostic fault codes while redacting vehicle registrations.
- `ev_backend/app/core/db.py` — ordered schema migrations for confidence/hypothesis fields, unique resolutions, indexes and seed metadata.
- `ev_backend/app/core/transactions.py` — serialized atomic workflows with nested savepoints.
- `ev_backend/app/agent/agent.py` — surface failed checks as missing evidence and unresolved work.
- `ev_backend/app/agent/policy.py` — evidence binding, focused tool selection, supported competing hypotheses, abstention/conflict handling and separate calibration.
- `ev_backend/app/agent/baseline.py` — accurate documentation of the fixed-order shared budget.
- `ev_backend/app/agent/calibration.py` — load the frozen synthetic probability model.
- `ev_backend/app/config/calibration.json` — actual fit on independent development seed 314159.
- `ev_backend/app/agent/tools/scope.py` — UTC parsing and incident-scoped event lookup.
- `ev_backend/app/agent/tools/session_lookup.py` — exact/app-scoped lookup and explicit ambiguity.
- `ev_backend/app/agent/tools/station_status_check.py` — incident-time source snapshots and availability/status interpretation.
- `ev_backend/app/agent/tools/app_error_check.py` — scoped app telemetry and explicit support escalation signals.
- `ev_backend/app/agent/tools/telematics_check.py` — filter by user/time before limiting records.
- `ev_backend/app/agent/tools/history_check.py` — scope to the matched session or incident window.
- `ev_backend/app/agent/tools/payment_check.py` — scoped payments and deterministic incident-relative overdue refunds.
- `ev_backend/app/agent/tools/error_code_check.py` — distinguish reported-only codes from logged faults.
- `ev_backend/app/agent/tools/connectivity_check.py`, `connector_check.py`, `timeline_check.py` — remove unrelated-session evidence.
- `ev_backend/app/agent/tools/similar_cases_check.py` — use verified resolutions rather than synthetic ground-truth fields.
- `ev_backend/app/services/diagnosis.py` — persist calibration/hypothesis, link real evidence IDs into recommendations and support actual-run evaluation persistence.
- `ev_backend/app/services/case_service.py` — filter/count latest diagnoses without duplicate cases.
- `ev_backend/app/services/feedback.py` — evidence-bound learning, reviewer category validation, distinct-case proposals, concurrent idempotency, safe reversal, activation and atomic rollback.
- `ev_backend/app/services/metrics.py` — count recurring chargers using matched sessions and distinct diagnosed cases.
- `ev_backend/app/data/synthetic_generator.py` — redacted storage, idempotent insert counts, seed-configuration guard and safe reset; benchmark templates/labels unchanged.
- `ev_backend/app/routers/cases.py`, `knowledge.py`, `reviews.py`, `metrics_rt.py`, `evaluation.py` — correct contracts, audited activation, bounded/atomic redacted imports and explicit failures.
- `ev_backend/app/evaluation/evaluation.py` — real persistence checks, corrected metrics integration, exact stop-policy replay, safe scratch databases and detailed learning reports.
- `ev_backend/app/evaluation/metrics.py` — complete class metrics/confusion matrices and assertion calibration including inconclusive false positives.
- `ev_backend/app/evaluation/dataset_audit.py` — flag fixture inconsistencies without changing scoring denominators.
- `ev_backend/app/evaluation/report_details.py` — extended Markdown/JSON/CSV artifacts.
- `ev_backend/scripts/run_evaluation.py` — reproducibility check and report generation.
- `ev_backend/scripts/fit_calibration.py` — independent development fitting.
- `ev_backend/scripts/inspect_failures.py` — reproducible scenario replay for diagnosis investigation.
- `ev_backend/scripts/smoke_server.py` — disposable backend for browser workflows.
- `ev_backend/tests/conftest.py`, `test_api.py`, `test_feedback.py` — fixtures and corrected contract/reversal assertions.
- `ev_backend/tests/test_api_workflows.py`, `test_regressions.py` — critical API, evidence, learning, import, seed and evaluation regressions.

## Frontend

- `ev_frontend/package.json`, `package-lock.json` — patched compatible tooling/router, test dependencies and scripts.
- `ev_frontend/vite.config.js` — Vitest setup and separate vendor/chart chunks.
- `ev_frontend/playwright.config.js` — dev/production and clean-environment desktop/mobile runs.
- `ev_frontend/e2e/workflow.spec.js` — complete live user workflow with error/overflow checks.
- `ev_frontend/src/App.jsx` — lazy routes, loading/error boundary and accessible mobile navigation.
- `ev_frontend/src/api.js` — audited activation and explicit invalid-response handling.
- `ev_frontend/src/hooks.js` — stale-request/unmount protection, synchronous failures and retry.
- `ev_frontend/src/format.js` — consistent UTC handling for naive and offset timestamps.
- `ev_frontend/src/components/ui.jsx` — accessible alerts and accurate provenance banner.
- `ev_frontend/src/pages/Cases.jsx` — metadata errors, keyboard links and correct error/empty handling.
- `ev_frontend/src/pages/NewCase.jsx` — recoverable metadata loading failures.
- `ev_frontend/src/pages/CaseDetail.jsx` — separate score/confidence, unverified hypotheses and per-case review state.
- `ev_frontend/src/pages/Knowledge.jsx` — audited rule activation/deactivation, visible failures and non-revertible audit entries.
- `ev_frontend/src/pages/Evaluation.jsx` — validated run options, class metrics and both confusion matrices.
- `ev_frontend/src/pages/Reviews.jsx` — upload validation, filter/pagination and loading/error/empty behavior.
- `ev_frontend/src/styles.css` — working mobile navigation, aligned grids and contained overflow.
- `ev_frontend/src/test/setup.js`, `hooks.test.jsx`, `api.test.js`, `format.test.js`, `pages/pages.test.jsx` — 17 verified frontend tests.

## Intentional generated outputs

`ev_backend/reports/evaluation_report.md`, `evaluation_results.json`, `evaluation_results.csv`, `evaluation_categories.csv`, `evaluation_cases.json` and `evaluation_errors.json` were regenerated from actual runs. The root `ev_diagnosis.db` was migrated and seeded locally for the review (250 cases); it remains ignored and regenerable. No local `.env` contents or runtime environment directories were added to the source deliverables.

## Multi-component communication extension (2026-11-04)

New backend files:

- `ev_backend/app/communication/__init__.py`, `catalog.py`, `schema.py`: shared event contract, scenario catalog and validated configuration/response schemas.
- `ev_backend/app/communication/simulator.py`: deterministic causal lifecycle, physical energy model, fault injection and separate actual-cause annotations.
- `ev_backend/app/communication/correlation.py`: request/response reconstruction, missing/delayed/duplicate/conflicting observations and component health.
- `ev_backend/app/communication/migration.py`, `storage.py`: migration 004, observation/truth separation, idempotent persistence and factual legacy projections.
- `ev_backend/app/communication/diagnosis.py`, `service.py`: correlated checks, explicit abstention, evidence, calibration and atomic bridge to reviewer cases.
- `ev_backend/app/communication/evaluation.py`: frozen legacy comparison, train feedback, validation-only calibration, template/configuration holdout and measured reports.
- `ev_backend/app/routers/communication.py`: generation, monitoring, diagnosis and scratch evaluation endpoints.
- `ev_backend/scripts/generate_communication.py`, `evaluate_communication.py`: generation/export and reproducible comparison CLIs.
- `ev_backend/app/config/communication_calibration.json`: actual validation-fitted confidence model.
- `ev_backend/tests/test_communication_simulator.py`, `test_communication_api.py`: 40 new regressions; full backend suite now 105 tests.

Modified backend files:

- `ev_backend/app/core/db.py`: schema version 4 and migration registration.
- `ev_backend/app/data/seed_rules.py`: add missing multi-component evidence rules without overwriting learned state.
- `ev_backend/app/data/synthetic_generator.py`: legacy reset preserves communication observations/projections.
- `ev_backend/app/services/diagnosis.py`: optional same-transaction persistence callback for linked communication cases.
- `ev_backend/app/main.py`: register the communication router.
- `ev_backend/scripts/smoke_server.py`: configurable isolated QA ports/CORS, retaining disposable databases.

Frontend files:

- New `ev_frontend/src/pages/Communication.jsx`, `Communication.test.jsx`: monitoring/generation, historical health, timeline, message flow, anomalies, evidence, review links and six component tests.
- New `ev_frontend/e2e/communication.spec.js`: real full-stack desktop/mobile communication workflows.
- Modified `ev_frontend/src/App.jsx`, `src/api.js`, `src/styles.css`: lazy route/navigation, request wrappers and responsive communication views.
- Modified `ev_frontend/playwright.config.js`: optional isolated ports/production artifact while retaining existing defaults and clean-environment testing.

Documentation and intentional artifacts:

- Updated `README.md`, this inventory and `docs/COMMUNICATION_IMPLEMENTATION_PLAN.md`.
- New `docs/COMMUNICATION_PLATFORM.md`, `COMMUNICATION_VERIFICATION.md`, `examples/communication_config.json`.
- New generated `ev_backend/reports/communication_evaluation.json`, `communication_evaluation.md`, `communication_categories.csv`.
- Existing six legacy benchmark reports regenerated unchanged in scored accuracy/F1; new communication data added locally (12 sessions) without resetting 250 existing cases.

The existing `.gitignore` already covers the new runtime artifacts; no additional ignore patterns or dependencies were necessary. Earlier sections document the preceding implementation; this section records the communication extension.

## Contradictory-message correction (2026-11-04 follow-up)

- Modified `ev_backend/app/communication/correlation.py`: validate message content/identity, contradictory transport outcomes, reply contracts/contents, rejection versus lifecycle outcomes and authoritative facts; keep request/revision context; preserve accepted retries; expose conflicting flows and uncertain health.
- Modified `ev_backend/app/communication/diagnosis.py`: central blocking-conflict policy, inconclusive/zero strength/no confidence, exact conflict event references, and persisted conflicting evidence/check traces.
- Added `ev_backend/tests/test_communication_contradictions.py`: 27 regressions including real API/case persistence and controls for valid retries, repeated facts and new revisions. Total backend suite: 132 passed.
- Modified `ev_frontend/src/pages/Communication.jsx`, `Communication.test.jsx`: red conflicting flows/evidence, inconclusive presentation and navigable conflict evidence; total frontend suite: 24 passed.
- Updated README, communication architecture/plan/verification; added `docs/CONTRADICTORY_MESSAGE_FIX.md`.
- Regenerated communication calibration/reports and legacy reports from actual repeated evaluations; scored benchmark labels/denominators and headline metrics unchanged.

## Support-ticket workflow completion (2026-11-04)

- `ev_backend/app/services/tickets.py`: resolution audit now records the system classification before review and
  whether the reviewer corrected it (an earlier abstention is not counted as a wrong prediction); new `summary()`
  queue overview.
- `ev_backend/app/routers/tickets.py`: `GET /api/v1/tickets/summary`.
- `ev_backend/tests/test_ticket_safeguards.py`: 6 tests covering unsupported confident labels, complaint wording versus
  logs, no-log payment complaints, insufficient-evidence routing and escalation in the challenge, reviewer-correction
  audit and the queue summary. Backend suite: 162 passed.
- `ev_frontend/src/components/TicketPanel.jsx`: shows cited event IDs and timestamps, affected components, human-review
  flag, policy version and requested missing evidence.
- `ev_frontend/src/pages/Dashboard.jsx`, `src/api.js`: ticket queue card (escalated, awaiting evidence, triage,
  overrides, open by priority).
- Frontend tests updated/added; suite: 30 passed.
- Added `docs/RESEARCH_SUBMISSION.md` and `docs/FINAL_SUBMISSION.md`, which the README already linked but did not exist.
