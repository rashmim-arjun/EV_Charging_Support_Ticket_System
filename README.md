# EV Charging Customer Support and Escalation System

**AI-powered customer ticket management for EV charging, with evidence-supported diagnosis and escalation.**

Charging complaints can involve an app, station, vehicle, network or payment record. This project helps support staff investigate those records together: create a ticket, inspect the evidence behind a diagnosis, assign responsibility and track a human-reviewed resolution.

The AI is a **local, rule-based diagnostic agent** with adaptive tool selection and reviewer-feedback updates. No external LLM or AI API key is required. Charging demonstrations and benchmarks are simulated; this is a local academic prototype.

[Features](#features) · [Workflow](#workflow) · [Architecture](#architecture) · [Quick start](#quick-start) · [Demo](#demo) · [Evaluation](#evaluation) · [Documentation](#documentation) · [Limitations](#limitations)

## Features

- **Support tickets:** save complaints, investigate immediately or later, filter the queue and track resolution and closure.
- **Evidence-supported diagnosis:** correlate session records, timestamps and component messages; inspect supporting evidence, conflicts and agent traces. Insufficient evidence can remain inconclusive.
- **Ownership and escalation:** recommend priority and an internal owner; audit staff reassignment, escalation and decision reasons.
- **Human review and learning:** record reviewer-verified resolutions, then optionally preview and apply bounded, reversible updates to rules and tool priorities.
- **Communication monitoring:** generate simulated app, CSMS, charger, connector, vehicle, BMS, payment and network events; explore timelines, message flows and component observations.
- **Manual payment review:** submit a reference or screenshot for review. Submission never establishes payment success; local payment reviewers record approval or rejection with a reason.

Dashboard summaries, CSV/JSON review import with best-effort PII redaction, and evaluation pages support the workflow. Complaints, reviews and charging observations carry `data_origin` labels.

## Workflow

1. **Capture:** create a complaint, optionally linked to a session. The case ID is also the support ticket ID.
2. **Investigate:** correlate available records and inspect the diagnosis, supporting evidence and unanswered questions. Results can indicate a fault, corroborated normal completion or insufficient/conflicting evidence.
3. **Triage:** review the proposed priority and owner; request evidence, reassign or escalate with an audited reason.
4. **Resolve:** record a reviewer resolution before closing the ticket. Learning is optional; payment review stays separate from ticket resolution.

## Architecture

```text
React UI -> FastAPI REST API (/api/v1) -> ticket / diagnosis / review services
                                                 |
                                    SQLite records and audit history
```

| Layer | Implementation |
| --- | --- |
| Frontend | React, Vite, React Router and Recharts in `ev_frontend/` |
| Backend | Python, FastAPI and Pydantic in `ev_backend/app/` |
| Diagnosis | Local adaptive diagnostic tools and a cross-component evidence agent |
| Persistence | SQLite, foreign keys, versioned migrations and audit history |
| Verification | pytest, Vitest/Testing Library and Playwright desktop/mobile workflows |

Vite proxies the frontend's `/api` requests to FastAPI at `http://127.0.0.1:8000` during development and preview.

## Quick start

### Prerequisites

- Git and repository access.
- Python **3.13**, Node.js **24** and npm. The recorded Windows setup used Python 3.13.5 and Node 24.14.1.
- Internet access for dependency installation. Browser tests use Microsoft Edge on Windows or Playwright Chromium elsewhere.

Windows commands below use **Git Bash**. Linux/macOS equivalents are provided but were not verified by the recorded Windows runs.

### Install

Clone and enter the repository root, where this README and both application folders live:

```bash
git clone https://github.com/rashmim-arjun/EV_Charging_Support_Ticket_System.git
cd EV_Charging_Support_Ticket_System
```

Create and activate a virtual environment using your platform's block.

**Windows / Git Bash:**

```bash
py -3.13 -m venv .venv
source .venv/Scripts/activate
```

**Linux / macOS (Python 3.13 installed):**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

Install the pinned dependencies in that activated terminal:

```bash
python -m pip install -r ev_backend/requirements-lock.txt
npm --prefix ev_frontend ci
```

### Run

Start FastAPI from the repository root in the activated terminal:

```bash
python -m uvicorn app.main:app --app-dir ev_backend --host 127.0.0.1 --port 8000 --reload
```

In a second terminal, from the same repository root, start the frontend:

```bash
npm --prefix ev_frontend run dev -- --host localhost --strictPort
```

Open [the application](http://localhost:5173), [API documentation](http://127.0.0.1:8000/docs) or [API health](http://127.0.0.1:8000/api/v1/health).

Startup creates or migrates `ev_diagnosis.db` in the repository root; no database server is needed. For an existing installation, back up before upgrading using the [inspection/backup script](ev_backend/scripts/check_local_database.py); see [migration details](docs/PAYMENT_VERIFICATION.md#versioned-migration-and-preservation). Databases and proof uploads are excluded from Git.

No `.env` file is needed for defaults. Optional database/CORS and proxy settings are documented in the [backend](ev_backend/.env.example) and [frontend](ev_frontend/.env.example) templates. Backend `.env` loading is opt-in.

## Demo

After starting the backend, optionally add **24 explicitly simulated support tickets** with correlated logs and varied lifecycle states. Run this from the repository root in another terminal with the virtual environment activated:

```bash
python ev_backend/scripts/seed_demo_tickets.py
```

Refresh **Support tickets** to explore the queue, or create an example:

1. In **Communication monitoring**, choose a fault scenario and select **Generate sessions**.
2. Inspect its logs, then follow **Open support ticket for this session**.
3. Describe the issue and select **Run diagnosis**. Review the evidence, priority and responsible team.
4. Manage ownership/escalation in **Support ticket management**, then record a reviewer resolution before closing. **Verify & learn** offers optional learning updates.

Choose **Successful charging** for a normal example. Complaints without usable logs can produce an evidence request. See the [communication guide](docs/COMMUNICATION_PLATFORM.md) and the separate [payment review workflow](docs/PAYMENT_VERIFICATION.md).

## Evaluation

These are **committed synthetic benchmark results**, not field performance. The tasks and denominators differ.

| Benchmark | Selected result | Source |
| --- | --- | --- |
| Legacy diagnosis: 200 synthetic cases, seed 42 | Adaptive accuracy **91%**; fixed baseline **78%** | [Evaluation report](ev_backend/reports/evaluation_report.md) |
| Communication: 48 simulated test sessions, following separate 48-session train and validation partitions | Multi-component decision accuracy **100%**; fixed baseline **25%**, including correct inconclusive decisions | [Communication report](ev_backend/reports/communication_evaluation.md) |

Generators, rules and diagnostic categories share authored assumptions; known legacy fixture inconsistencies remain. The multi-component agent receives richer observations than legacy baselines. These scores do **not** establish real-world accuracy. The separate support research challenge is an exposed-test regression, not a fresh blind holdout; see its [methodology and caveats](docs/RESEARCH_SUBMISSION.md).

Latest recorded functional verification (5 November 2026): **215 backend, 53 frontend and 12 desktop/mobile browser tests passed**, plus production builds. These test counts are separate from diagnostic accuracy; [commands and scope](docs/PAYMENT_VERIFICATION.md#verification) are documented.

## Documentation

| Topic | Guide |
| --- | --- |
| Payment proof, manual review and migrations | [Payment verification](docs/PAYMENT_VERIFICATION.md) |
| Simulation, schema, API and communication evaluation | [Communication platform](docs/COMMUNICATION_PLATFORM.md) |
| Database inspection and earlier connection/schema fixes | [Maintenance script](ev_backend/scripts/check_local_database.py) · [Connection and diagnosis notes](docs/CONNECTION_AND_DIAGNOSIS_FIX.md) |
| Testing and builds | [Latest verification](docs/PAYMENT_VERIFICATION.md#verification) · [Earlier clean-install record](docs/VERIFICATION.md) |
| Evaluation interpretation | [Diagnosis findings](docs/DIAGNOSIS_FINDINGS.md) |
| Research methodology | [Support-workflow research](docs/RESEARCH_SUBMISSION.md) |
| Final submission verification | [Submission record before the payment update](docs/FINAL_SUBMISSION.md) |

## Limitations

- Events come from a coordinated simulator, not independent physical-device logs or live chargers. OCPP/ISO 15118 inspiration is not protocol compliance.
- Reviewer IDs are selectable local identities, not authenticated logins. API users can impersonate a known reviewer; this is not production access control.
- Payment approval is manual. Screenshots/references do not independently prove settlement; no bank/UPI lookup, gateway or refund execution is integrated.
- Assignment and escalation are local records. No external ticket dispatch, email, SMS or push notification is sent.
- Evidence availability and synthetic calibration limit conclusions. There is no independent real-world validation; human review remains necessary.
