# Evaluation Report — SIMULATED DATA ONLY (NOT real-world performance)

Generated: 2026-11-04T06:50:08+00:00  
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
| accuracy_pct | 91.0 | 78.0 |
| macro_f1 | 0.9548 | 0.7214 |
| abstention_correct_pct | 75.0 | 75.0 |
| false_confident_pct | 25.0 | 25.0 |
| avg_checks_per_case | 4.83 | 7.6 |
| avg_unnecessary_checks | 0.12 | 1.96 |
| traceability_pct | 100.0 | 100.0 |
| conflict_detection_pct | 100.0 | 100.0 |
| runtime_s | 2.676 | 2.703 |

### Per-category accuracy (%)

| Category | Adaptive | Baseline |
|---|---|---|
| app_crash_or_technical_error | 100.0 | 25.0 |
| charger_availability_mismatch | 87.5 | 87.5 |
| connector_or_charger_hardware_fault | 100.0 | 100.0 |
| customer_support_issue | 100.0 | 25.0 |
| inconclusive | 75.0 | 75.0 |
| incorrect_or_delayed_station_status | 100.0 | 100.0 |
| incorrect_or_incomplete_charging_history | 100.0 | 25.0 |
| network_or_connectivity_issue | 100.0 | 100.0 |
| payment_or_billing_failure | 75.0 | 75.0 |
| session_fails_to_start | 100.0 | 100.0 |
| session_stops_unexpectedly | 100.0 | 100.0 |
| vehicle_charger_communication_issue | 100.0 | 100.0 |
| vehicle_specific_or_telematics_issue | 100.0 | 0.0 |

### Confidence calibration (adaptive agent, labelled cases)

ECE = 0.4498 (lower is better); mean confidence when correct = 0.545, when wrong = 0.0.

| Confidence bin | n | Mean confidence | Accuracy % |
|---|---|---|---|
| 0.0-0.2 | 10 | 0.0 | 80.0 |
| 0.2-0.4 | 0 | None | None |
| 0.4-0.6 | 83 | 0.492 | 100.0 |
| 0.6-0.8 | 75 | 0.661 | 100.0 |
| 0.8-1.0 | 0 | None | None |

### Reviewer-feedback learning experiment (held-out cases)

Train 100 / test 100 cases; 80 verified resolutions applied (161 knowledge changes). Reviewer simulated from synthetic labels; train/test disjoint; single split, so differences of a few points are within noise.

| Metric | Before | After | Delta |
|---|---|---|---|
| accuracy_pct | 91.0 | 91.0 | 0.0 |
| macro_f1 | 0.9637 | 0.9637 | 0.0 |
| abstention_correct_pct | 76.92 | 76.92 | 0.0 |
| false_confident_pct | 23.08 | 23.08 | 0.0 |
| avg_checks_per_case | 4.83 | 3.25 | -1.58 |

The run above shows the adaptive agent ahead on these synthetic cases.

## LIMITATIONS

- Dataset is synthetic data authored by the same developer as the rules; results are optimistic and NOT real-world performance.
- Small scale (~hundreds of cases); percentages carry wide uncertainty.
- Generator templates and diagnosis rules are correlated by design (signals were defined together).
- No real charging-network logs were used anywhere.
- PII redaction is best-effort, not a guarantee.

## Classification metrics and confusion matrices

Macro-F1 averages the 12 cause categories (zero-division = 0). False positives on truly inconclusive cases count. Accuracy additionally rewards correct abstentions, so these metrics can move in opposite directions.
The matrix uses rows=true, columns=predicted; inconclusive includes every abstention. P/R/F1 are fractions. Support is the true-label count.

### adaptive_agent

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| charger_availability_mismatch | 1.0 | 0.875 | 0.9333 | 16 |
| session_fails_to_start | 1.0 | 1.0 | 1.0 | 24 |
| session_stops_unexpectedly | 1.0 | 1.0 | 1.0 | 24 |
| payment_or_billing_failure | 1.0 | 0.75 | 0.8571 | 32 |
| incorrect_or_delayed_station_status | 1.0 | 1.0 | 1.0 | 8 |
| app_crash_or_technical_error | 1.0 | 1.0 | 1.0 | 8 |
| network_or_connectivity_issue | 1.0 | 1.0 | 1.0 | 8 |
| connector_or_charger_hardware_fault | 0.5 | 1.0 | 0.6667 | 8 |
| vehicle_charger_communication_issue | 1.0 | 1.0 | 1.0 | 16 |
| incorrect_or_incomplete_charging_history | 1.0 | 1.0 | 1.0 | 8 |
| customer_support_issue | 1.0 | 1.0 | 1.0 | 8 |
| vehicle_specific_or_telematics_issue | 1.0 | 1.0 | 1.0 | 8 |
| inconclusive | 0.7059 | 0.75 | 0.7273 | 32 |

Matrix label key:
1. charger_availability_mismatch
2. session_fails_to_start
3. session_stops_unexpectedly
4. payment_or_billing_failure
5. incorrect_or_delayed_station_status
6. app_crash_or_technical_error
7. network_or_connectivity_issue
8. connector_or_charger_hardware_fault
9. vehicle_charger_communication_issue
10. incorrect_or_incomplete_charging_history
11. customer_support_issue
12. vehicle_specific_or_telematics_issue
13. inconclusive

| True / Predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| 2 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 |
| 5 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 |
| 10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 |
| 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 |
| 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 |
| 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 24 |

### Assertion calibration: adaptive_agent

Includes false assertions on inconclusive cases; abstentions carry no root-cause probability.
| Score | Assertions | ECE | Brier |
|---|---|---|---|
| heuristic_assertion_calibration | 166 | 0.3817 | 0.1971 |
| assertion_calibration | 166 | 0.0066 | 0.0459 |

### Most frequent errors: adaptive_agent

| True | Predicted | Count |
|---|---|---|
| payment_or_billing_failure | inconclusive | 8 |
| inconclusive | connector_or_charger_hardware_fault | 8 |
| charger_availability_mismatch | inconclusive | 2 |

### fixed_baseline

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| charger_availability_mismatch | 1.0 | 0.875 | 0.9333 | 16 |
| session_fails_to_start | 1.0 | 1.0 | 1.0 | 24 |
| session_stops_unexpectedly | 1.0 | 1.0 | 1.0 | 24 |
| payment_or_billing_failure | 1.0 | 0.75 | 0.8571 | 32 |
| incorrect_or_delayed_station_status | 1.0 | 1.0 | 1.0 | 8 |
| app_crash_or_technical_error | 1.0 | 0.25 | 0.4 | 8 |
| network_or_connectivity_issue | 1.0 | 1.0 | 1.0 | 8 |
| connector_or_charger_hardware_fault | 0.5 | 1.0 | 0.6667 | 8 |
| vehicle_charger_communication_issue | 1.0 | 1.0 | 1.0 | 16 |
| incorrect_or_incomplete_charging_history | 1.0 | 0.25 | 0.4 | 8 |
| customer_support_issue | 1.0 | 0.25 | 0.4 | 8 |
| vehicle_specific_or_telematics_issue | 0 | 0.0 | 0 | 8 |
| inconclusive | 0.4 | 0.75 | 0.5217 | 32 |

Matrix label key:
1. charger_availability_mismatch
2. session_fails_to_start
3. session_stops_unexpectedly
4. payment_or_billing_failure
5. incorrect_or_delayed_station_status
6. app_crash_or_technical_error
7. network_or_connectivity_issue
8. connector_or_charger_hardware_fault
9. vehicle_charger_communication_issue
10. incorrect_or_incomplete_charging_history
11. customer_support_issue
12. vehicle_specific_or_telematics_issue
13. inconclusive

| True / Predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| 2 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 0 | 0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 |
| 5 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 6 |
| 7 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 0 |
| 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 |
| 10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 6 |
| 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 6 |
| 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 |
| 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 24 |

### Assertion calibration: fixed_baseline

Includes false assertions on inconclusive cases; abstentions carry no root-cause probability.
| Score | Assertions | ECE | Brier |
|---|---|---|---|
| heuristic_assertion_calibration | 140 | 0.3376 | 0.1948 |
| assertion_calibration | 140 | 0.0023 | 0.0539 |

### Most frequent errors: fixed_baseline

| True | Predicted | Count |
|---|---|---|
| vehicle_specific_or_telematics_issue | inconclusive | 8 |
| payment_or_billing_failure | inconclusive | 8 |
| inconclusive | connector_or_charger_hardware_fault | 8 |
| app_crash_or_technical_error | inconclusive | 6 |
| incorrect_or_incomplete_charging_history | inconclusive | 6 |
| customer_support_issue | inconclusive | 6 |
| charger_availability_mismatch | inconclusive | 2 |

## Learning outcome breakdown

| Outcome | Before | After |
|---|---|---|
| correct_root_cause | 81 | 81 |
| wrong_root_cause | 0 | 0 |
| false_assertion_on_inconclusive | 3 | 3 |
| correct_abstention | 10 | 10 |
| abstention_on_labelled_cause | 6 | 6 |

### Learning per-category F1

| Category | Before F1 | After F1 | Support |
|---|---|---|---|
| charger_availability_mismatch | 0.9412 | 0.9412 | 9 |
| session_fails_to_start | 1.0 | 1.0 | 11 |
| session_stops_unexpectedly | 1.0 | 1.0 | 16 |
| payment_or_billing_failure | 0.8 | 0.8 | 15 |
| incorrect_or_delayed_station_status | 1.0 | 1.0 | 4 |
| app_crash_or_technical_error | 1.0 | 1.0 | 3 |
| network_or_connectivity_issue | 1.0 | 1.0 | 4 |
| connector_or_charger_hardware_fault | 0.8235 | 0.8235 | 7 |
| vehicle_charger_communication_issue | 1.0 | 1.0 | 9 |
| incorrect_or_incomplete_charging_history | 1.0 | 1.0 | 2 |
| customer_support_issue | 1.0 | 1.0 | 4 |
| vehicle_specific_or_telematics_issue | 1.0 | 1.0 | 3 |
| inconclusive | 0.6897 | 0.6897 | 13 |

Frozen calibration model: {"method": "monotonic evidence-strength bins with Beta(1,1) smoothing", "seed": 314159, "n_per_template": 20, "dataset_size": 500, "scope": "asserted diagnoses only; synthetic development data; no probabilities for abstentions", "bins": [{"upper": 0.2, "successes": 0, "support": 0, "probability": 0.5}, {"upper": 0.4, "successes": 0, "support": 0, "probability": 0.5}, {"upper": 0.6, "successes": 218, "support": 228, "probability": 0.9452}, {"upper": 0.8, "successes": 176, "support": 186, "probability": 0.9452}, {"upper": 1.0, "successes": 0, "support": 0, "probability": 0.9452}]}

The original leading-hypothesis calibration table above diagnoses the heuristic score on labelled causes only. Assertion calibration is the more relevant measure for displayed probabilities. Calibration and test use different scenario seeds but share synthetic template families; this is not independent real-world validation.
Detailed incorrect case IDs, observed signals, executed tools, and tool errors are saved in evaluation_errors.json; full method outcomes are in evaluation_cases.json.

## Dataset consistency audit (cases retained in scores)

All cases remain in the comparison and its denominators. Unsupported labels are not applied as reviewer training feedback.
Unsupported app/category labels: 2.
Inconclusive labels with a specific matched logged fault: 8.
IDs and reasons are recorded in evaluation_results.json under dataset_audit.
Training labels not applied because their category is unsupported: ['SIM-042-0064'].

## Reproducibility check

{"verified": true, "runs": 2, "compared": "all predictions, evidence scores, confidence, tool order, signals and learning headline metrics; runtimes/timestamps excluded"}
