# Diagnosis investigation and measured limitations

## Preserved baseline

The unmodified backend test run had 16 passes and one API-contract failure. Re-running the original evaluator reproduced 53% adaptive accuracy, 23.5% baseline accuracy, 0.5255 historical adaptive macro-F1 and 40.62% false-confident answers on truly inconclusive cases (seed 42, eight variants/template, 200 cases). Its reports are preserved under `docs/original-evaluation/`.

The synthetic templates, wording pools, labels and comparison denominators were not rewritten to raise the score. Database writing now redacts stored text and records seed/template-count metadata; agent evidence interpretation changed. The regenerated main comparison still includes every legacy fixture, including inconsistent ones.

## Five weakest diagnostic categories

| Category | Historical accuracy | Revised accuracy | Actual cause and repair |
|---|---:|---:|---|
| Charger availability mismatch | 0% | 87.5% | Unbounded status history selected unrelated dates, and overlapping availability/status observations competed as independent votes. The tool now compares the latest incident-time snapshots from the same charger and distinguishes the requested availability question from a stale-status question. Two remaining labels are inapplicable to their configured companion app. |
| Customer support issue | 0% | 100% | Legacy support escalation telemetry was stored as `app_error`; no diagnostic tool emitted a support signal. The app-telemetry tool now recognizes the explicit no-response marker as support evidence rather than an app crash. |
| Incorrect/incomplete history | 0% | 100% | History audits could span unrelated sessions, tool ordering exhausted the budget before the relevant check, and an unsupported billing keyword reduced confidence in verified history evidence. Checks are scoped and prioritized, and unsupported alternatives no longer compete with logged evidence. |
| Vehicle telematics | 12.5% | 100% | The latest ten app events were selected before user filtering, excluding the relevant user's records. App-wide evidence also contaminated other complaints. Identity/time filtering now occurs before any display limit. |
| Unexpected session stops | 16.7% | 100% | Charger-wide events from other sessions inflated hardware/connectivity alternatives. A generic reported hardware code could be treated as a verified fault. Checks now use the exact matched session; reported-only codes are neutral observations; a lifecycle symptom and its corroborating mechanism are compatible contributing findings. |

Additional repairs include exact app-scoped session references (no wildcard match), explicit ambiguity instead of choosing an arbitrary abnormal session, scoped payments, incident-relative refund age, correct evidence-to-signal linkage, surfaced failed checks, and preservation of error codes during PII redaction. Selection remains bounded and adaptive; keywords guide which question to test, while matching source evidence is required for an assertion.

## Classification and calibration

The original confidence formula used a heuristic evidence score as a probability. It penalized missing unrelated sources and keyword-only alternative hypotheses. The revised evidence score uses positive logged support, competing supported hypotheses, source corroboration and explicit conflicts. Confirmed diagnoses still need multiple tools and no conflicts. The probable threshold is unchanged at 0.45; it was not lowered to force predictions.

The UI distinguishes **evidence score** from **synthetic calibrated confidence**. `fit_calibration.py` fits monotonic probability bins with Beta(1,1) smoothing on seed 314159 (500 development cases), independently of the seed-42 comparison. Evaluation rejects reuse of the calibration seed. Abstentions assert no category and carry no root-cause probability.

On the 166 seed-42 assertions, heuristic ECE is 0.3817, calibrated ECE 0.0066 and calibrated Brier score 0.0459. These calculations include false assertions on truly inconclusive cases. The older leading-hypothesis calibration table is retained and explicitly distinguished; it measures a different population and is not directly comparable.

The fitted nonempty probability bins pool to one probability, 0.9452. This is an aggregate estimate with limited discrimination, not evidence that individual cases are confidently ranked. It must be recalibrated and independently evaluated if rules or deployment data change. Sharing synthetic template families between development and test is an explicit limitation.

## Why learning accuracy rose while macro-F1 fell

The historical experiment reported accuracy 49% → 57%, macro-F1 0.4939 → 0.4319, and correct abstention 53.85% → 92.31%. Accuracy counts correct inconclusive decisions; cause macro-F1 averages only the 12 diagnostic categories. Becoming more conservative can add correct abstentions while losing recall in less frequent cause categories. Those metrics need not move together.

The original learning implementation also reduced all observed off-label rules, including incidental symptoms, and updated priors from signals without requiring matching evidence. That can suppress valid secondary patterns and promote abstention. New-rule counts used tool-check rows instead of distinct verified cases. In addition, the old F1 scorer omitted false positives on inconclusive cases, and the old traceability metric accepted an empty support-ID list without checking persistence.

The revised learner updates only observed matching signals, reinforces verified primary/contributing categories, and restricts negative updates to a wrong asserted primary category. Unrelated alternative findings are not automatically punished. Priors follow the same evidence boundary. Rule proposals count distinct verified cases, remain inactive pending explicit approval and do not duplicate an existing proposal. Apply, reviewer resolution, revert, activation and rollback use serialized transactions/savepoints. Learning is idempotent even for concurrent apply requests. Revert restores prior observation counts and rejects overwriting newer changes to the same target.

The new report stores full before/after per-category metrics, confusion matrices, outcome counts and changed predictions. On the current seed-42 split, accuracy stays **91%**, macro-F1 stays **0.9637**, and mean checks fall **4.83 → 3.25**. There are 100 train and 100 test cases. The comparison never applies learning; this separate experiment does. Unsupported training labels are listed rather than applied as fictitious reviewer verification. This result demonstrates efficiency and mechanism correctness, not a general learning accuracy gain. The original reports do not contain enough per-case detail to attribute their F1 decline to an exact historical set of predictions; the explanation of that run is limited to its aggregate results and implementation defects.

## Remaining errors (18 of 200 main comparison cases)

- **Two unsupported labels:** `SIM-042-0060` and `SIM-042-0064` label public charger availability as the root cause for Bajaj Chetak, whose configured category set excludes public station availability. The agent abstains. The labels were retained.
- **Eight contradictory inconclusive labels:** `SIM-042-0161` through `SIM-042-0168` are labelled inconclusive, but supply matched sessions with logged `HW210` faults and hardware events. The agent asserts hardware fault. These account for all eight remaining false-confident cases (25% of the 32 inconclusive fixtures). The labels/evidence were retained and flagged by the dataset audit.
- **Eight payment-conflict cases:** `SIM-042-0137` through `SIM-042-0144` are labelled billing failure, but supply only failed/declined attempts and a customer deduction claim with no independent capture confirmation. The agent records the conflict and abstains pending reconciliation. Assigning a verified billing root cause would overstate the available evidence.

All 200 cases remain in the reported accuracy, confusion matrices and category support. An improved future benchmark should resolve these inconsistencies with independent domain review, version the corrected fixtures and separately report results on both versions. That is a proposed improvement, not an implemented score adjustment.

## Limits of the academic claim

Synthetic rules and templates were authored together. Case-disjoint learning and seed-disjoint calibration do not constitute template-disjoint or independent real-world validation. The fixed baseline shares the repaired tools and classifier and uses a fixed order with the same eight-step budget, so it also benefits from correctness fixes. The adaptive advantage here primarily measures investigation order and stopping efficiency.

No real charging logs, live gateway reconciliation, actual support-ticket system or authenticated reviewer identity are present. The small regex redactor is best-effort. Calibration, performance numbers, source integrations and security properties should not be presented as production validation. Functional completion for an academic demo does not mean 100% diagnostic accuracy.
