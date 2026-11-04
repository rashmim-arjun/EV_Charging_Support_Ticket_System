# Academic review implementation plan

1. Inspect all source, configuration, database schema, tests and reports. Preserve the original evaluation before changes. Establish isolated Python and Node environments.
2. Repair evidence scoping and classification based on reproducible error traces. Add correct classification metrics, confusion matrices, calibration diagnostics, and before/after learning breakdowns. Keep synthetic labels and baseline comparison honest.
3. Repair imports, seed/reset behavior, feedback transactions, learning idempotency and reversal. Exercise critical workflows through the API.
4. Preserve the UI while fixing request races, forms, filters, mobile layout and API integration. Lazy-load routes. Add Vitest/React Testing Library coverage.
5. Run backend tests, frontend tests/build, evaluation and a combined local application smoke test. Document actual results, reproducible setup, architecture and limitations. Ignore local runtime artifacts.

Completion evidence and remaining limitations are recorded in `docs/VERIFICATION.md` once verified. The project is a local academic demo; synthetic benchmark accuracy is not production validation.
