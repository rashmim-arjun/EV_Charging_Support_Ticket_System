# Multi-component simulation implementation plan

1. Inspect the existing agent, schema, generators, evaluation, API/UI contracts and tests. Keep the legacy workflow and benchmark intact.
2. Add a versioned event schema and deterministic state-machine simulator. Generate coordinated app, CSMS, charger/connector, vehicle/BMS, payment and transport events with causal message IDs and explicit fault injection.
3. Persist observations separately from ground truth. Reconstruct request/response flows and detect missing, delayed, duplicate and contradictory observations without reading labels.
4. Add a multi-component diagnostic agent and bridge to existing case persistence and reviewer learning. Retain the existing fixed and adaptive agents for comparison.
5. Evaluate on disjoint train/validation/test scenario templates and fault configurations, with calibration fitted on validation only. Report real outcomes and limitations.
6. Add a monitoring dashboard for generation, session selection, health, timeline, flow, anomalies and evidence. Verify legacy/new backend, frontend, browser and build workflows; document commands and measured results.

The simulator is protocol-inspired and does not implement or certify OCPP/ISO 15118 conformance. Ground-truth annotations are never diagnosis inputs.

## Completion evidence (2026-11-04)

All six implementation stages are implemented for the local synthetic platform. Migration 004, the communication package/router/CLIs, lazy monitoring route and regression suites are saved in this repository. Follow-up verification after fixing contradictory messages: 132 backend tests, 24 frontend tests, four production desktop/mobile browser workflows, production build and both reproducible evaluation pipelines passed. See [verification commands/results](COMMUNICATION_VERIFICATION.md), [contradiction regressions](CONTRADICTORY_MESSAGE_FIX.md), [architecture/methodology/limitations](COMMUNICATION_PLATFORM.md) and [changed files](CHANGES.md). Real device ingestion and protocol compliance remain explicitly outside the implemented scope.
