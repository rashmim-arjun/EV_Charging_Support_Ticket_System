# Contradictory-message handling correction

Implemented and verified on 2026-11-04 after review found the previous completion claim overstated conflict coverage.

## Reproduced defects

Five initial regression cases failed against the previous implementation. A received message could change its operation, source, target or response acceptance while retaining its message ID without being recognized as conflicting. A normal message with an added transport drop record was treated as network loss despite an observed receive. The former could preserve a normal diagnosis; the latter could produce a probable network root cause from incompatible records.

The previous checks covered some clock, identity, state and app/backend inconsistencies but did not compare complete message contents or conflicting transport outcomes. A latest-record comparison also failed to establish whether authoritative records agreed on the same business fact.

## Resulting behavior

| Observations | Behavior |
|---|---|
| Same message ID, different operation/body/endpoints | `message_content_conflict`; conflicting flow |
| Same message ID, different correlation IDs | `message_correlation_conflict` |
| Sender/receiver actor contradicts declared endpoint | Identity conflict |
| Same message dropped and delivered/received | `transport_outcome_conflict`; no automatic network-loss attribution |
| Replies disagree on the contents for one request | `response_conflict`; neither reply silently wins |
| Reply operation/endpoints/correlation/reply_to contradict request | `response_contract_conflict` |
| Rejected startup/payment request followed by success without an accepted retry | `response_state_conflict` |
| Same source asserts conflicting terminal authorization/payment facts, status revision, invoice or meter sample | `authoritative_fact_conflict` |
| Different request identities, identical reobservations, later status revisions | Not treated as an integrity conflict |
| Rejection followed by an observed accepted retry with a distinct request identity | Can reconcile the earlier rejection |
| Valid stale app/backend disagreement with intact provenance | Existing scenario diagnosis remains available |

Blocking observation conflicts force **inconclusive**, `root_cause=null`, no localized component, `evidence_strength=0`, and `confidence=null`. Independently supported fault hypotheses remain visible as candidates, but do not override unreliable observations. Conflicting event IDs are returned with descriptions/unresolved questions and persisted into the linked case and completion check trace. Ground truth remains outside diagnostic inputs.

Flows with incompatible observations are marked `conflicting` and displayed red. Integrity-conflict evidence uses the existing red conflicting-evidence style rather than green matching evidence. Component cards for the conflicting observation sources show unknown health and `conflicting_observations`; this avoids presenting a contradictory transport claim as an established broken network connection. It does not identify which logger is faulty.

## Actual verification

- **27 new backend regressions**, including reversed ingestion order, an independent real fault alongside a contradiction, missing reply identity, full API result persistence and reviewer-case evidence persistence.
- **132 total backend tests passed** in `.venv-clean`, with the existing upstream Starlette/httpx warning.
- **24 frontend tests passed**, including conflict color, absent confidence and evidence navigation.
- Normal and isolated frontend production builds passed.
- **Four real production browser workflows passed**, original and communication paths on desktop/mobile, using the separate backend environment and scratch database.
- Both benchmark pipelines passed their independent repeated-run reproducibility checks. Legacy adaptive accuracy remains **91%**; the existing communication benchmark remains **100% on its 48 authored held-out scenarios**. Those benchmark denominators were not expanded or relabeled: the contradictory-observation coverage is explicitly the new regression suite, not a claim that the original benchmark covered all contradictions.

Actual PowerShell commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest ev_backend\tests\test_communication_contradictions.py -q -o addopts= --tb=short
.\.venv-clean\Scripts\python.exe -m pytest ev_backend\tests -q -o addopts= --tb=short
.\.venv\Scripts\python.exe ev_backend\scripts\run_evaluation.py --seed 42 --per-template 8 --check-reproducibility
.\.venv\Scripts\python.exe ev_backend\scripts\evaluate_communication.py --seed 42 --per-template 4 --install-calibration --check-reproducibility
```

From `ev_frontend/`:

```powershell
npm.cmd test
npm.cmd run build
$env:VITE_API_BASE='http://localhost:8010/api/v1'
npm.cmd run build -- --outDir .tmp/communication-preview
$env:E2E_CLEAN='1'
$env:E2E_ISOLATED='1'
$env:E2E_PRODUCTION='1'
npm.cmd run test:e2e
```

## Boundaries

The schema lacks transport-attempt IDs. A drop followed by receipt under a reused message ID could represent an unrecorded retry; the system conservatively abstains rather than fabricating that explanation. To represent a verified retry, use a distinct request/message identity and observed acceptance. Explicit business IDs and revisions distinguish separate facts; absent identities limit what can be resolved. These checks cover the documented semantic simulator, not every possible real OCPP/ISO 15118 message or arbitrary payment state machine.

Restart the backend after upgrading and rerun diagnosis on previously analyzed sessions. Historical persisted results are preserved; they are not retroactively rewritten. Real hardware, protocol compliance and independent validation remain outside the verified scope.
