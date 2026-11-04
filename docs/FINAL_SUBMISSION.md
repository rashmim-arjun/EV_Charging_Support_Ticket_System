# Final submission record

Scope: the EV charging support-ticket application (React/Vite frontend, FastAPI backend, SQLite).
Workflow: customer complaint → ticket → correlated component logs → evidence-supported diagnosis →
classification → priority → routing/escalation → verified resolution → learning from verified outcomes only.

## Verification performed for the latest changes

Environment: Linux, Python 3.12.3, Node 22.23.4, dependencies from `requirements.txt` / `package-lock.json`.

| Check | Result |
|---|---|
| `pytest ev_backend/tests` | 162 passed |
| `vitest run` (frontend) | 30 passed |
| `vite build` | succeeded |
| `run_research.py` re-run | challenge, ablation and support metrics identical to stored reports |

Not re-run in this environment: Playwright browser tests (`npm run test:e2e`), `npm audit`, and the legacy and
communication evaluation scripts. The earlier Windows verification recorded in `VERIFICATION.md` and
`COMMUNICATION_VERIFICATION.md` was not repeated.

## Requirement coverage

| Requirement | Where it lives |
|---|---|
| 1. Ticket intake and tracking | `services/tickets.py` (`open_ticket`, `get_ticket`), tables `support_tickets`, `ticket_history`; existing case IDs are ticket IDs |
| 2. Investigate logs before deciding | `communication/diagnosis.py`, `communication/correlation.py`; complaint text never substitutes for logs (`test_ticket_safeguards.py`) |
| 3. Evidence-supported diagnosis | Diagnosis cites event IDs/timestamps; contradictions or gaps give inconclusive plus requested evidence |
| 4. Classification and priority | `tickets.decide`; P0 reported safety, P1 observed safety, financial impact or interrupted charging, P2 standard, P3 no fault |
| 5. Routing and escalation | `config/support_policy.json`; supporting teams listed, triage queue for unsupported cases, human overrides with reasons |
| 6. Lifecycle and feedback | Seven states with enforced transitions, audit history, versioned diagnoses; learning only from reviewer-verified resolutions |
| 7. Frontend | New complaint, Cases queue, Case detail with ticket panel, evidence, verification, communication log links, dashboard queue |
| 8. Evaluation | `research/` experiment plus `test_ticket_safeguards.py` negative tests |

"Sending to a team" means a local assignment and audit record. No email, notification or external ticket is sent,
and the interface and API say so.

## Known limitations

- All benchmark results are synthetic and authored with shared assumptions; 100% scores on the authored challenge
  do not predict real-world performance.
- Reviewer identities are local demo identities; there is no authentication.
- Team mappings and priority rules are configurable initial mappings, not a real organization's structure.
- The stored research reports predate the audit and queue-summary additions; their frozen source hash therefore no
  longer matches the current code, though regenerated metrics are identical.
