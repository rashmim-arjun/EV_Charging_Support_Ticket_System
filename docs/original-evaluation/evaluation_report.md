# Evaluation Report — SIMULATED DATA ONLY (NOT real-world performance)

Generated: 2026-10-28T05:17:08  
Dataset size: **200 labelled synthetic cases** (seed=42, 8 variants/template)  
Data origin: **simulated** — fabricated by design.

## Procedure
Both methods ran on the identical labelled synthetic case set inside a fresh temporary SQLite DB seeded only with the static rule set (no learned weights, no cross-run leakage). Ground truth was withheld from agent inputs.

## Metric definitions
- accuracy: primary category equals ground truth; for true-'inconclusive' cases, a correct abstention (no asserted category) counts as correct.
- macro_f1: mean per-category F1 over the 12 problem categories.
- abstention_correct_pct: truly-inconclusive cases returned as inconclusive/requires_further_investigation.
- false_confident_pct: truly-inconclusive cases answered confirmed/probable.
- avg_checks_per_case: executed diagnostic tools per case (not_applicable skips excluded).
- avg_unnecessary_checks: checks run after the evidence prefix already supported the final classification (see evaluation.py docstring).
- traceability_pct: diagnoses whose supporting-evidence ids all resolve to stored evidence items.
- conflict_detection_pct: planted-conflict cases where conflicting evidence was recorded.

## Results (computed from this run — nothing hardcoded)

| Metric | Adaptive agent | Fixed baseline |
|---|---|---|
| n_cases | 200 | 200 |
| accuracy_pct | 53.0 | 23.5 |
| macro_f1 | 0.5255 | 0.1476 |
| abstention_correct_pct | 59.38 | 65.62 |
| false_confident_pct | 40.62 | 34.38 |
| avg_checks_per_case | 5.37 | 7.71 |
| avg_unnecessary_checks | 0.14 | 0.69 |
| traceability_pct | 100.0 | 100.0 |
| conflict_detection_pct | 100.0 | 100.0 |
| runtime_s | 0.459 | 0.268 |

### Per-category accuracy (%)

| Category | Adaptive | Baseline |
|---|---|---|
| app_crash_or_technical_error | 100.0 | 25.0 |
| charger_availability_mismatch | 0.0 | 0.0 |
| connector_or_charger_hardware_fault | 100.0 | 100.0 |
| customer_support_issue | 0.0 | 0.0 |
| inconclusive | 59.4 | 65.6 |
| incorrect_or_delayed_station_status | 62.5 | 0.0 |
| incorrect_or_incomplete_charging_history | 0.0 | 0.0 |
| network_or_connectivity_issue | 62.5 | 0.0 |
| payment_or_billing_failure | 50.0 | 0.0 |
| session_fails_to_start | 100.0 | 66.7 |
| session_stops_unexpectedly | 16.7 | 0.0 |
| vehicle_charger_communication_issue | 100.0 | 0.0 |
| vehicle_specific_or_telematics_issue | 12.5 | 0.0 |

### Confidence calibration (adaptive agent, labelled cases)

ECE = 0.2651 (lower is better); mean confidence when correct = 0.493, when wrong = 0.376.

| Confidence bin | n | Mean confidence | Accuracy % |
|---|---|---|---|
| 0.0-0.2 | 10 | 0.0 | 80.0 |
| 0.2-0.4 | 48 | 0.334 | 43.8 |
| 0.4-0.6 | 65 | 0.509 | 84.6 |
| 0.6-0.8 | 45 | 0.631 | 84.4 |
| 0.8-1.0 | 0 | None | None |

### Reviewer-feedback learning experiment (held-out cases)

Train 100 / test 100 cases; 81 verified resolutions applied (741 knowledge changes). Reviewer simulated from synthetic labels; train/test disjoint; single split, so differences of a few points are within noise.

| Metric | Before | After | Delta |
|---|---|---|---|
| accuracy_pct | 49.0 | 57.0 | 8.0 |
| macro_f1 | 0.4939 | 0.4319 | -0.062 |
| abstention_correct_pct | 53.85 | 92.31 | 38.46 |
| false_confident_pct | 46.15 | 7.69 | -38.46 |
| avg_checks_per_case | 5.56 | 4.26 | -1.3 |

The run above shows the adaptive agent ahead on these synthetic cases.

## LIMITATIONS

- Dataset is synthetic data authored by the same developer as the rules; results are optimistic and NOT real-world performance.
- Small scale (~hundreds of cases); percentages carry wide uncertainty.
- Generator templates and diagnosis rules are correlated by design (signals were defined together).
- No real charging-network logs were used anywhere.
- PII redaction is best-effort, not a guarantee.
