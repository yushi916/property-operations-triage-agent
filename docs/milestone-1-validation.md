# Milestone 1: staff intake validation

Date: 2026-10-26. Base commit: `cd1b3aba32f9df94865d65610403c25dda3e31ae`.
All cases use synthetic data. Checks were performed with an AI coding
assistant; the results do not establish the maintainer's independent mastery.

## Verified behavior

`tests/test_report_intake.py` adds nine tests covering:

1. Authenticated report creation, receipt/occurrence distinction, reading after
   reconstructing the app, and no model call or proposal during intake.
2. Matching retry returns the same report; changed content with the same UUID
   returns a conflict without adding a row.
3. Concurrent retries produce one report and responses `201`/`200`.
4. Invalid building, blank/long description, missing timezone, invalid/future
   occurrence time, invalid UUID/risk, and extra fields do not write records.
5. Urgent and unknown risk are saved and block normal model investigation.
6. A forced receipt-write failure rolls back the report insert as well.
7. Missing/wrongly configured authentication and missing database fail clearly;
   a missing database is not silently created.
8. Original synthetic reports remain readable without invented intake data.
9. New intake can feed the existing candidate discovery and simple baseline.

The ninth test freezes receipt time at 2026-09-28 09:15 +08:00 so it can use
the existing historical fixture. The same-building/time baseline returns
R-01/R-02/R-03. Shared-asset discovery additionally finds R-04 in 5栋.
These are candidate-coverage checks, not proof that all reports share a cause,
and not an LLM accuracy measurement.

## Commands and results

```text
python -m unittest discover -s tests -v
24 tests: OK

python -m evals.run_demo --scenario base
offline_checks: all true

python -m evals.run_demo --scenario active_notice
offline_checks: all true

python -m evals.replay_recorded
base / active_notice: case_pass=true
```

The initial intake tests were run against the unchanged base and failed due
to the missing endpoint/receipt behavior. The successful results above were
obtained after implementation, rather than assumed from reading the code.

Local validation: Linux, Python 3.12.14, repository-pinned direct dependencies.
The resolved Starlette version emits a TestClient/httpx deprecation warning;
the checks pass. Windows and the PR's Python 3.11 CI are reported separately.
No real model API, external message, or production database was used.

A separate Uvicorn process was also exercised over actual localhost HTTP:
create `201`, identical retry `200`, changed-payload reuse `409`, model submission
without a key `503`, and reading the same receipt after terminating and
restarting the server process `200`. The report and receipt survived unchanged.

## Not yet verified or delivered

Live model behavior, all phase-1 evidence validation gaps, persistent failed
runs, end-to-end report-to-decision workflow for new submissions, browser UI,
Windows execution, deployment, and production reliability remain unverified.
The staff risk declaration is not a guarantee that dangerous text is detected.

## Maintainer walkthrough

Only after the branch is available locally, start the API and use `/docs`.
Submit the README example once, repeat it unchanged, then change only `text`
while keeping `request_id`. Expected statuses: `201`, `200`, `409`.
Read the report by ID after restarting the server. This is an actual project
acceptance step, not a separate exercise for every function.

At this milestone, discuss one question: why are both occurrence time and
server receipt time useful? Record the answer in the private progress notes;
do not infer understanding from the assistant's passing tests.
