# EV Charging Support Ticket System — Comparison and Completion Review

Date: 4 November 2026

## Inputs compared

- **DP-main (5).zip**: original application plus Windows Python and Node dependency folders, transient test files, and an SQLite database containing 250 pre-existing cases.
- **DP-main-completed.zip**: streamlined source package with ticket safeguards, ticket-centric frontend updates, and additional tests, but without the original SQLite database.
- **Final combined ZIP**: starts from the completed source, incorporates the safety and lifecycle fixes below, includes the original case database after SQLite integrity checks, and omits installed dependencies and temporary logs.

The comparison found that the two ZIPs share almost all application source files. The completed source version had eight changed shared code/documentation files and a new negative-test suite. The original ZIP's much larger size was primarily bundled environments and node modules, not additional product source.

## Objective checklist

| Required capability | Final implementation | Where to inspect |
|---|---|---|
| 1. Ticket intake and tracking | Implemented: case ID is ticket ID; complaint/session links, state, priority, ownership, timestamps and history. Preserved original 250 cases. | `services/tickets.py`, `routers/tickets.py`, `core/db.py`, `ev_diagnosis.db` |
| 2. Cross-component investigation | Implemented for configured synthetic/available records: app, backend/CSMS, charger, BMS, payment and network event timelines. Complaint text is not enough to justify a component assignment. | `communication/diagnosis.py`, `communication/correlation.py`, `communication/storage.py` |
| 3. Evidence-supported diagnosis | Implemented: matching component events, IDs, timestamps, unresolved questions and contradictory observations. Added event-reference checks and validation of older database evidence sources; insufficient or mismatched evidence abstains. | `services/tickets.py`, `components/TicketPanel.jsx` |
| 4. Classification and priority | Implemented: policy-based category, P0–P3 priority, safety/customer interruption/financial impact and uncertainty-driven triage explanations. | `config/support_policy.json`, `services/tickets.py` |
| 5. Team routing and escalation | Implemented as **local internal** ownership; primary/supporting teams, triage queue, configurable mappings, reasoned manual overrides, explicit escalation history. No external dispatch is implied. | `services/tickets.py`, `routers/tickets.py` |
| 6. Lifecycle and reviewer feedback | Implemented: new/investigating/awaiting evidence/assigned/escalated/resolved/closed, audit history, reviewer resolution and gated learning. Fixed reopen/closure version checks and retained urgent escalations across failed or repeated investigation. | `services/feedback.py`, `services/tickets.py`, `tests/test_ticket_workflow_hardening.py` |
| 7. Frontend workflow | Implemented: complaint intake, queue filters, ticket panel, log link, evidence, priority, reassignment, escalation, reviewer-verified resolution and existing communication pages. | `ev_frontend/src/pages`, `ev_frontend/src/components/TicketPanel.jsx` |
| 8. Support evaluation | Implemented: independent synthetic scenario expectations score classification, priority, route and escalation, plus negative tests for forged/missing evidence. | `research/dataset.py`, `research/experiment.py`, `reports/submission/research` |

## Concrete additions over DP-main-completed

1. **Evidence integrity:** a specialist assignment from communication events requires root-matching references to real observed event IDs; a claimed healthy session requires positive completion and captured-payment records. Legacy event references are resolved against case-linked SQLite tables before being trusted. Downstream symptoms and contradictions are exposed separately.
2. **Consistent human overrides:** updated assignment/priority, supporting teams, escalation flags and explanation stay synchronized in stored ticket decision JSON. Re-submitting unchanged fields no longer falsely sets manual override flags. A no-op patch is rejected.
3. **Auditable escalation:** an explicit human escalation receives an `escalated` history entry in addition to the human override record. Automated investigations also retain their audit reasoning.
4. **Correct lifecycle:** reopening a resolved ticket updates the case status, a re-investigation cannot be closed based on an outdated previous resolution, and existing urgent escalation remains active until changed by a human. Failed investigation does not silently remove an urgent case from the escalation queue.
5. **Ticket-first interface:** existing application shell retains all current pages while identifying the product as a support ticket application, with clearer ticket evidence, symptom and timestamp information.
6. **Original data preserved:** copied `ev_diagnosis.db` from the original ZIP instead of throwing away the existing 250 ticket/case records. The main `cases` and `support_tickets` rows remain linked 1-to-1.
7. **Regression coverage:** added a focused backend suite for unsupported references, manual override persistence, escalation safety and re-verification on reopen.

## Verification executed

- Backend unit/integration tests: **166 passed** (`PYTHONPATH=ev_backend pytest -q ev_backend/tests -o addopts=`).
- Parsed **22** frontend `.js` / `.jsx` files with the Babel parser; no syntax errors.
- SQLite original database: `PRAGMA integrity_check = ok`; `foreign_key_check = 0 violations`; schema version 5; **250 cases and 250 support tickets** before/after app initialization.
- Held-out synthetic support challenge, seed 20261104, 2 repeats: **46** evaluated sessions; classification, priority, routing and escalation each matched the authored expectations for all 46 sessions. Repeated run produced identical research metrics and frozen hashes. Detailed per-session outcomes are in `ev_backend/reports/submission/research`.
- Existing frontend unit tests, browser E2E tests and Vite build **were not rerun in this Linux workspace**: the original archive's `node_modules` contains Windows-specific native optional packages, not the Linux Rollup package required here. Use `npm ci`, `npm test`, `npm run build` and `npm run test:e2e` on a properly provisioned machine to verify browser behavior. Do not interpret JSX parsing as equivalent to running the frontend.

## Boundaries and unresolved external work

- All 46 challenge samples are **synthetic authored EV sessions**, not independent real-world charger data. High synthetic scores do not establish field accuracy, generalization, cybersecurity assurance or SLA suitability.
- The application does not provide authenticated operational role permissions, live production component log ingestion, real-time charging provider integration, external helpdesk dispatch, email sending or notification delivery. Its assignments and escalations are **local database records only**.
- The team names in `support_policy.json` are configurable demo owner mappings. Real deployment requires authorization, staff/team validation, and live log source agreements.
- The included database retains original user-supplied records; make backups before replacing it. Installed Python/Node packages are deliberately excluded from the final ZIP to avoid machine-specific binaries.

## Running the application

Follow the existing `README.md`. On a clean machine, install Python backend dependencies from `ev_backend/requirements-lock.txt` and the frontend with `npm ci`. Start the FastAPI server and Vite frontend as documented. The bundled SQLite database already has 250 original case records; running the optional synthetic seeder will add further demo records and is not required just to inspect those existing tickets.
