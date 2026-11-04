# Multi-component communication evaluation

Seed 42; 144 sessions; split sizes {'train': 48, 'validation': 48, 'test': 48}.

| Metric | Fixed baseline | Current adaptive | Multi-component |
|---|---|---|---|
| root_cause_accuracy_pct | 18.18 | 18.18 | 100.0 |
| decision_accuracy_pct | 25.0 | 25.0 | 100.0 |
| category_accuracy_pct | 33.33 | 33.33 | 100.0 |
| macro_f1 | 0.1 | 0.1 | 1.0 |
| avg_checks_per_session | 8.0 | 6.833 | 5.083 |
| communication_failure_detection_pct | 75.0 | 75.0 | 100.0 |
| transport_failure_detection_pct | 66.67 | 66.67 | 100.0 |
| communication_false_positive_pct | 0.0 | 0.0 | 0.0 |
| component_localization_accuracy_pct | 10.0 | 10.0 | 100.0 |
| false_confident_on_inconclusive_pct | 0.0 | 0.0 | 0.0 |

Root-cause accuracy includes observable normal/fault sessions. Decision accuracy includes inconclusive cases. Macro-F1 averages the ten fault mechanisms.
Communication failure detection covers dropped, delayed and duplicate delivery plus missing controller responses; transport detection covers the three network mechanisms only.
Detailed per-category precision/recall/F1/support, confusion matrices, confidence bins, split manifests and every prediction are in the JSON report.

## Test calibration (probabilities fitted on validation only)

| Method | ECE | Brier | Assertions |
|---|---|---|---|
| fixed_baseline | 0.02381 | 0.222789 | 24 |
| current_adaptive | 0.02381 | 0.222789 | 24 |
| multi_component | 0.041667 | 0.001736 | 44 |

## Per-category metrics: fixed_baseline

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| none | 0.3333 | 1.0 | 0.5 | 4 |
| charger_controller_timeout | 0 | 0.0 | 0 | 4 |
| vehicle_bms_fault | 0 | 0.0 | 0 | 4 |
| authorization_conflict | 0 | 0.0 | 0 | 4 |
| payment_conflict | 0 | 0.0 | 0 | 4 |
| connector_fault | 1.0 | 1.0 | 1.0 | 4 |
| network_delay | 0 | 0.0 | 0 | 4 |
| network_loss | 0 | 0.0 | 0 | 4 |
| network_duplicate | 0 | 0.0 | 0 | 4 |
| stale_availability | 0 | 0.0 | 0 | 4 |
| metering_mismatch | 0 | 0.0 | 0 | 4 |
| inconclusive | 0.1667 | 1.0 | 0.2857 | 4 |
| unresolved:session_fails_to_start | 0.0 | 0 | 0 | 0 |

## Per-category metrics: current_adaptive

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| none | 0.3333 | 1.0 | 0.5 | 4 |
| charger_controller_timeout | 0 | 0.0 | 0 | 4 |
| vehicle_bms_fault | 0 | 0.0 | 0 | 4 |
| authorization_conflict | 0 | 0.0 | 0 | 4 |
| payment_conflict | 0 | 0.0 | 0 | 4 |
| connector_fault | 1.0 | 1.0 | 1.0 | 4 |
| network_delay | 0 | 0.0 | 0 | 4 |
| network_loss | 0 | 0.0 | 0 | 4 |
| network_duplicate | 0 | 0.0 | 0 | 4 |
| stale_availability | 0 | 0.0 | 0 | 4 |
| metering_mismatch | 0 | 0.0 | 0 | 4 |
| inconclusive | 0.1667 | 1.0 | 0.2857 | 4 |
| unresolved:session_fails_to_start | 0.0 | 0 | 0 | 0 |

## Per-category metrics: multi_component

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| none | 1.0 | 1.0 | 1.0 | 4 |
| charger_controller_timeout | 1.0 | 1.0 | 1.0 | 4 |
| vehicle_bms_fault | 1.0 | 1.0 | 1.0 | 4 |
| authorization_conflict | 1.0 | 1.0 | 1.0 | 4 |
| payment_conflict | 1.0 | 1.0 | 1.0 | 4 |
| connector_fault | 1.0 | 1.0 | 1.0 | 4 |
| network_delay | 1.0 | 1.0 | 1.0 | 4 |
| network_loss | 1.0 | 1.0 | 1.0 | 4 |
| network_duplicate | 1.0 | 1.0 | 1.0 | 4 |
| stale_availability | 1.0 | 1.0 | 1.0 | 4 |
| metering_mismatch | 1.0 | 1.0 | 1.0 | 4 |
| inconclusive | 1.0 | 1.0 | 1.0 | 4 |

## Methodology and limitations

- Synthetic mechanisms and diagnostic rules were authored together. Template/configuration holdout is not independent real-world validation.
- Each split has a distinct startup path, fault trigger/operation and configuration band; the causal simulator and root-cause ontology are shared.
- Legacy agents receive factual projections into their original tables. The multi-component agent has richer transport/component evidence; this is a capability comparison, not a pure scheduling ablation.
- Legacy category outputs with several possible mechanisms are explicitly unresolved at exact-root level; category accuracy is reported separately.
- Root-cause accuracy excludes unobservable sessions; decision accuracy additionally scores correct abstentions. Component localization is evaluated on fault sessions only.
- Validation calibrates decision correctness for each method. No test outcomes fit weights or probabilities. Small supports can produce unstable calibration.
- Reviewer learning operates on existing failure categories, not newly trained fine-grained root-cause models.
- OCPP/ISO 15118 inspired event names are semantic simulations, without wire encoding, network interoperability or protocol compliance testing.

## Reproducibility

{"verified": true, "runs": 2, "scope": "all reported metrics and validation probability models"}
