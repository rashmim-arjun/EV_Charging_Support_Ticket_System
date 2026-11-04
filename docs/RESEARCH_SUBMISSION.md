# Support-workflow research methodology, results and limitations

This document describes the synthetic support challenge used to evaluate the ticket workflow
(complaint → correlated logs → diagnosis → classification → priority → routing/escalation).
Code: `ev_backend/app/research/dataset.py` (challenge and expectations) and `experiment.py` (scoring).
Stored reports: `ev_backend/reports/submission/research/` (test), `.../development/` (validation only),
`.../research_initial_frozen/` (first frozen run, kept unchanged).

## Design

- **Partitions.** 32 train, 32 validation and 46 test sessions from separately declared configurations
  (seed 20261104, 2 repeats). Duplicate or equivalent configurations across partitions are rejected, and
  multi-fault combinations may not overlap between partitions.
- **Scenarios.** Single faults, unseen fault combinations, real retries, observation loss, contradictory
  observations, near-concurrent distinct sessions, a reported-safety complaint with no logs, and
  safety-relevant events hidden from the log.
- **Independent expectations.** Each session carries an expected classification, team and priority written in
  `EXPECTATIONS` in `dataset.py`. They are not imported from the production policy
  (`config/support_policy.json`, `services/tickets.py`). Insufficient or contradictory evidence is expected to
  route to `triage`, never to a specialist team.
- **Isolation.** Agents read an allowlisted, read-only observation snapshot; annotations, scenario IDs and split
  labels are not visible to them (enforced by `test_runtime_agents_cannot_read_or_write_annotations` and related tests).
- **Frozen before scoring.** The text model, validation calibration, manifests and source/config hashes are fixed
  before test predictions; the run aborts if they change.
- **Ablation.** Text-only versus text-plus-observations arms use identical complaints, cases and targets.

## Measured test results (46 sessions)

| Decision | Accuracy % | Macro F1 |
|---|---:|---:|
| Classification | 100.0 | 1.0 |
| Priority | 100.0 | 1.0 |
| Routing (assigned team) | 100.0 | 1.0 |
| Escalation | 100.0 | 1.0 |

| Diagnosis method | Accuracy % | Answer coverage % | False assertions on ambiguous % |
|---|---:|---:|---:|
| Fixed baseline | 21.74 | 56.52 | 62.5 |
| Current adaptive | 26.09 | 52.17 | 50.0 |
| Multi-component | 100.0 | 65.22 | 0.0 |
| Text only | 34.78 | 0.0 | 0.0 |
| Text plus observations | 100.0 | 65.22 | 0.0 |

Per-label precision/recall/F1, confusion matrices and every per-session outcome are in `research_results.json`.

## How to read these numbers

The perfect scores are **not** evidence of real-world accuracy. The challenge is synthetic; the simulator, the
ontology, the diagnostic rules and the expectation table share authors and assumptions. The test partition was
exposed in an earlier frozen run, so the stored result is an exposed-test regression rather than a fresh blind
holdout. The text baseline is a small train-only naive Bayes model, not a language-model baseline. Expected teams
and priorities are authored policy expectations, not an organization's validated service levels.

## Safeguards verified by tests

`ev_backend/tests/test_ticket_safeguards.py` adds checks that:

- a confident label with no cited log evidence (or only complaint-derived evidence) is routed to triage with no
  component asserted;
- complaint wording ("I was charged twice") cannot override contrary component logs (a connector fault stays with
  charger maintenance and cites event IDs and timestamps);
- a payment complaint with no logs goes to triage, not payment support;
- in the support challenge, every insufficient-evidence ticket is routed to triage as inconclusive, every expected
  P0/P1 ticket is escalated, and every decision states that delivery is local only;
- a reviewer correction (verified category differs from an asserted system category) is recorded in the audit trail;
- the queue summary counts open work and states the local-only scope.

## Reproduction

```bash
python ev_backend/scripts/run_research.py --development-only --seed 20261104 --repeats 2 --output ev_backend/reports/submission/development --check-reproducibility
python ev_backend/scripts/run_research.py --seed 20261104 --repeats 2 --output ev_backend/reports/submission/research --check-reproducibility
```

Re-running after the audit/queue-summary additions (see `CHANGES.md`) reproduced every challenge, ablation and
support metric exactly; only the frozen source hash differs because `services/tickets.py` changed. The stored
reports were left as generated.
