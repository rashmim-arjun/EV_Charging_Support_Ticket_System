# Final submission record - 5 November 2026

This is an academic local prototype for evidence-based EV charging support. The application preserves the React/Vite frontend, FastAPI backend, SQLite schema and existing ticket records.

The later payment workflow update is documented in [manual payment verification](PAYMENT_VERIFICATION.md). The verification counts below describe the earlier UI/diagnosis submission; payment regression results are recorded separately there after execution.

## Verification before the payment workflow update

Verified on Windows with Python 3.13.5, Node.js 24.14.1 and Microsoft Edge. Both the working source and a separately extracted source ZIP were checked. The clean copy used its own new `.venv` and new `node_modules`; dependencies were installed from `ev_backend/requirements-lock.txt` and `ev_frontend/package-lock.json`, using available package caches. It did not reuse the original installed dependency directories or working database.

| Check in the clean extraction | Result |
| --- | --- |
| Backend dependency installation | Passed |
| `python -m pip check` | No broken requirements |
| `python -m pytest ev_backend/tests -q -o addopts= --tb=short` | **195 passed** |
| `npm.cmd ci` | Installed all 202 packages |
| `npm.cmd test` | **42 passed** |
| `npm.cmd run build` | Passed |
| `E2E_ISOLATED=1 npm.cmd run test:e2e` | **10 passed** on desktop and mobile |
| `seed_demo_tickets.py` in the clean copy | 24 simulated tickets; integrity `ok`; zero foreign-key violations |
| Source ZIP manifest | Every included file matched its SHA256 digest |

The Playwright runner started FastAPI and Vite from the extracted project with a disposable database. Tests exercised real HTTP requests, ticket persistence and reload, component logs, normal and inconclusive outcomes, urgent safety triage, ownership changes, investigation versions, reviewer resolution, closure, learning, evaluation, and CSV import without a provider column. Viewports were 1440 x 1000 and 390 x 844.

The installed Starlette test client emits a deprecation warning about its httpx integration. Tests pass; no runtime dependency failure was found. npm also reports dependency deprecation notices for Recharts 2 and whatwg-encoding. Major dependency migrations were kept outside this final polish pass.

## Corrections and UI changes

- Reported burning/burnt smells now trigger precautionary **P0** safety triage, without asserting an unverified component fault. Normal completion logs do not automatically clear a reported hazard.
- Normal charging is displayed consistently as **No fault established** in communication monitoring, the ticket queue, dashboard and ticket details. Current session evidence and the matching investigation are required. Historic diagnostic grades remain in SQLite; the additive API `diagnosis.outcome` distinguishes no-fault completion from inconclusive fault investigation.
- Normal results receive an appropriate no-corrective-work recommendation. Obsolete generic missing-log advice is not shown as current advice for an already corroborated healthy session. Administrative no-fault/inconclusive reviews do not appear as red incorrect fault predictions.
- Ticket details begin with a concise reason, supporting evidence, recommended next action and responsible team. Operator controls, assignment evidence and belief details are expandable.
- Main navigation and queue labels consistently say **Support tickets**. Provider selectors/columns are absent from customer intake, the queue, review import and recent-ticket views. Existing API provider metadata remains compatible.
- Mobile navigation collapses behind **Menu**; ticket lists use readable cards. The dashboard links **View all tickets** and explains its six-record recent list.
- Dashboard accuracy is explicitly limited to reviewed **simulated** tickets. It is not a real-world reliability measure.
- BMS, payment and network cards show actual event counts, latest timestamps, direct log links and explicit missing-record explanations. A lone health check is distinguished from activity logs.

## Demo data and preservation

The final read-only check found 285 existing tickets, including the 24 recently added support examples. Before/after snapshots confirmed that cases, diagnoses, resolutions, ticket history, support tickets, evidence and checks were unchanged by API verification. SQLite integrity was `ok`, with zero foreign-key violations. The demo generator is additive and idempotent; it preserves existing tickets and does not apply learning. Fixture resolutions are explicitly labelled `[SIMULATED OUTCOME]` and use a dedicated fictional reviewer disabled after generation. No actual repair, payment, refund or customer notification occurs.

The submission excludes the working database. Running the demo generator in a fresh extraction produces 24 recent tickets spanning new, assigned, investigating, awaiting-evidence, escalated, resolved and closed states, including P0-P3 priorities and timestamped component observations. The older bulk benchmark generator remains available separately.

## Running the submission

Extract the ZIP, open Git Bash in its root and run:

```bash
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r ev_backend/requirements-lock.txt
./.venv/Scripts/python.exe ev_backend/scripts/seed_demo_tickets.py
(cd ev_frontend && npm.cmd ci)
```

In terminal 1, from that root:

```bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir ev_backend --host 127.0.0.1 --port 8000 --reload
```

In terminal 2, from the same root:

```bash
cd ev_frontend
npm.cmd run dev -- --host localhost --strictPort
```

Open **http://localhost:5173**. No external AI key is required. The frontend proxies `/api` to the local backend. Additional configuration and optional legacy demos are documented in the root README.

## Package contents and boundaries

The final ZIP is `submission/EV_Support_Submission.zip`. It contains application source, pinned dependency files, tests, configuration templates, examples, documentation, intentional research reports, these screenshots and a SHA256 source manifest. Its adjacent `.sha256` file identifies the delivered archive.

Local databases and backups, real `.env` files, private keys, installed dependencies, environments, caches, runtime reports, logs, browser traces and Git metadata are excluded. A regression test checks those exclusions. The final archive contains the same application, tests and configuration verified in the clean candidate; final verification documentation and screenshots were added afterward and the final source manifest was checked again.

## Screenshots from isolated browser tests

- [Desktop investigation summary](screenshots/desktop-investigation-summary.png)
- [Mobile investigation summary](screenshots/mobile-investigation-summary.png)
- [Mobile support-ticket queue](screenshots/mobile-support-tickets.png)

These screenshots show disposable synthetic browser-test data, not private customer records.

## Known scope and limitations

- Component records are generated by one causal simulator with a shared event clock. Independent physical-device logging, live charging-network integration and wire-level OCPP/ISO 15118 compliance are future work.
- The diagnostic agent uses bounded local rules and correlated observations. Missing or contradictory data can remain inconclusive; a short complaint alone cannot establish a charging fault.
- Research scores are synthetic and share authored assumptions. Historical frozen reports remain unchanged; their source hashes and dates describe those earlier runs. The current browser/API tests reran the small communication evaluation, not a new independent real-world trial.
- Reviewer identities are local demo identities, not authenticated production users. Assignments and escalation are local audit records; external dispatch, email and payment actions are not implemented.
- Published on 5 November 2026 to the private [rashmim-arjun/EV_Charging_Support_Ticket_System](https://github.com/rashmim-arjun/EV_Charging_Support_Ticket_System) repository on branch `main`. The authenticated account and matching local/remote commit were verified. Repository access requires an authorized GitHub account.
