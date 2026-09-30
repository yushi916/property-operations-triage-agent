# Property Operations Triage Agent

[![Offline checks](https://github.com/yushi916/property-operations-triage-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/yushi916/property-operations-triage-agent/actions/workflows/ci.yml)

A Python prototype for reviewing fictional residential property reports
against notices, work orders, shared assets, and service records. It
produces an evidence-based proposal for a human reviewer. Approval and
internal task creation are separate steps.

**Scope:** Portfolio demonstration with synthetic data. The Agent's
classifications are suggestions, not verified fault diagnoses.

## Verification at a glance

| Check | What it verifies | Boundary |
| --- | --- | --- |
| Offline unit tests | Candidate discovery, evidence validation, review versions, audit behavior, and failure traces | No live model call |
| Two no-model scenarios | Fixed fixture results for the baseline, plan conflict, and notices | Does not assess Agent classification |
| Recorded-run replay | Proposal and tool-trace checks for two designed cases | Replays saved runs; not a general accuracy estimate |

GitHub Actions runs these checks on Python 3.11 without a Gemini API key.

## What the demo shows

- Cross-record investigation using read-only evidence tools.
- Separate labels for a possible shared event, an unrelated report,
  and a report requiring verification.
- A review queue with evidence versions, decision history, and a guard
  against approving a proposal after its evidence changes.
- A plan-versus-execution record conflict.
- A simple same-building, 30-minute rule baseline for comparison.
- A reproducible scenario runner and a small, case-specific evaluation.

## Setup

Use Python 3.11 or a compatible version. From the repository root:

```bash
python -m venv .venv
```

Activate the environment:

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Then install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Run without a model or API key

The scenario runner and tests use temporary databases. The replay
command reads saved traces. None alter `data/property.db`:

```bash
python -m evals.run_demo --scenario base
python -m evals.run_demo --scenario active_notice
python -m evals.replay_recorded
python -m unittest discover -s tests -v
```

To create a persistent database from the synthetic fixture:

```bash
python -m evals.init_demo_db --output data/property.db
```

The initialization command refuses to overwrite an existing file.
Choose a different `--output` path if `data/property.db` already exists.

## Run the Agent scenario

Set `GEMINI_API_KEY` in your local environment. Do not commit the key
or paste it into a notebook output. Then run:

```bash
python -m evals.run_demo --scenario base --with-model
```

The runner creates a fresh temporary database, calls the Agent through
the FastAPI review endpoint, reads back the saved proposal and trace,
and checks the result against `evals/gold_case.json`. You can also run
`--scenario active_notice --with-model`. Model output can vary; a
failed check should be inspected rather than rerun until it passes.

## Start the API

First create `data/property.db` with the initialization command above
if it does not already exist. Set a private `PROPERTY_REVIEW_TOKEN` in
your local environment, then start:

```bash
uvicorn app.main:app --reload
```

FastAPI's interactive documentation is at
`http://127.0.0.1:8000/docs`. The review endpoints are under
`/v1/reviews`; send the token in the `X-Review-Token` header.
Submitting a report for Agent investigation also requires
`GEMINI_API_KEY`.


## Reviewer correction and recorded runs

`POST /v1/reviews/{proposal_id}/revisions` lets an authenticated reviewer
change the classification and explanation of reports already in a pending
proposal. The request includes `expected_version`, an audit reason, and
the changed report IDs, relations, and explanations. The endpoint cannot
add reports or alter evidence references.

A correction advances the pending proposal from version 1 to version 2.
`GET /v1/reviews/{proposal_id}` exposes `revisions` with before/after
snapshots. Approval with the old version is rejected; approval with
version 2 checks evidence versions and creates one internal task.
The shared demo token records the fixed actor `demo_manager`, not a
verified personal identity.

The API and scenario runner report `candidate_discovery_calls` separately
from `model_tool_calls`. One run per scenario is stored under
`evals/recorded_runs/`. These two designed cases are examples, not a
business accuracy measurement.

## Example investigation

The synthetic case starts with `R-01`: a 3栋 resident reports a water
outage at 09:05. Deterministic candidate discovery finds nearby
same-building reports and a 5栋 report through shared asset `A-01`.
The [recorded base run](evals/recorded_runs/base_2026-09-29.json)
shows the Agent selecting read-only evidence tools and proposing:

| Report | Recorded relation | Evidence and remaining boundary |
| --- | --- | --- |
| `R-02` | `possible_same_event` | Another 3栋 whole-home outage close in time; the cause is not confirmed |
| `R-03` | `hold_separate` | A local kitchen-tap report with its own open work order `W-02` |
| `R-04` | `needs_verification` | 5栋 shares asset `A-01`, and `W-03` investigates pressure; a common cause is not established |

The base run marks notice `N-01` as expired. The
[active-notice run](evals/recorded_runs/active_notice_2026-09-29.json)
adds active notice `N-02` for 3栋; that notice alone does not explain
the 5栋 report. These are two designed examples, not an accuracy estimate.

The same-building, 30-minute baseline includes `R-03` and misses
cross-building `R-04` in this fixture. The proposal remains pending
until a reviewer decides; approval can create an internal task, not
a confirmed repair or resident notification.

## Why structured evidence tools?

This version queries structured reports, notices, assets, and work
orders by ID, time, location, and version. Exact record and version
checks support the review workflow; the project does not use a vector
store. The earlier portfolio projects use RAG for policy documents,
while this case centers on reconciling operational records.

## Project layout

| Path | Purpose |
| --- | --- |
| `app/agent.py`, `app/agent_tools.py` | Agent investigation and tool access |
| `app/candidates.py` | Deterministic candidate discovery |
| `app/tools.py`, `app/db.py` | SQLite evidence and synthetic data |
| `app/review_api.py`, `app/review_store.py`, `app/review_actions.py` | Review API, persistence, and decisions |
| `app/review.py`, `app/tasks.py` | Plan review and internal tasks |
| `app/baseline.py` | Simple proximity rule |
| `data/demo_case.json` | Synthetic source records |
| `evals/` | Scenario construction, runner, and case checks |
| `tests/` | Offline review workflow tests |

Local `.db` files and `.env` files are excluded by `.gitignore`.
