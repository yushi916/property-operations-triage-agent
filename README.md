# Property Operations Triage Agent

A Python prototype for reviewing fictional residential property reports
against notices, work orders, shared assets, and service records. It
produces an evidence-based proposal for a human reviewer. Approval and
internal task creation are separate steps.

**Scope:** Portfolio demonstration with synthetic data. The Agent's
classifications are suggestions, not verified fault diagnoses.

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

The seed case starts with report `R-01`. Programmatic candidate
discovery checks nearby reports and shared-asset coverage. The Agent
then selects evidence tools and proposes relationships for `R-02`,
`R-03`, and `R-04`. The `active_notice`
scenario adds a notice covering 3栋 but does not by itself establish
that a report from 5栋 has the same cause.

The proximity baseline associates reports by building and time window.
In the seed case it identifies `R-02`, incorrectly includes `R-03`,
and does not assess cross-building `R-04`. This is a comparison on one
designed example, not a general accuracy measurement.

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
