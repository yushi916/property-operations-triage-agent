# Project delivery status

Updated: 2026-10-27. This tracks verified project behavior, not a person's
independent proficiency. Private learning notes are maintained separately.

## Goal

An accurately described portfolio application for a residential duty manager:
record a report, reconcile operational evidence with an Agent, let a human
revise/approve/return the recommendation, and preserve the outcome and history.
All public demo data is synthetic. Approval creates an internal verification
task; it does not certify a fault cause or completed repair.

## Current milestones

| Milestone | State | Evidence / next boundary |
| --- | --- | --- |
| Phase-1 business/source/code review | Completed | Current base `cd1b3ab` checked; existing 15 tests, two scenarios, recorded runs; additional validation gaps reproduced |
| M1 staff report intake | Locally verified; branch review and user-local acceptance pending | [Validation](milestone-1-validation.md); 24 tests, baseline comparison, rollback/concurrency and process-restart checks |
| M2 evidence validation | Next | Candidate coverage, computed notice times, empty/new query results; preserve existing review behavior |
| M3 durable attempts and return/re-run linkage | Planned | Persist failed runs and their trace; explicit new attempt, bounded calls; do not claim mid-run resume |
| M4 full review-loop UI | Planned | Jinja2/HTML/fetch over verified API; manual decisions with evidence/history; compare baseline and failure cases |
| M5 database migration and deployment | Planned | Postgres/Alembic as separate change, identity/access decisions, persistent state, restart and deployment verification |

## Decisions kept in scope

Runtime compatibility is tracked [separately](runtime-compatibility.md).
The Windows walkthrough uses confirmed Anaconda Python 3.12.15; requirements
installation and dependency checking are complete by user report, while local
application acceptance is still pending. CI now also configures Linux/Python
3.12 and Windows/Python 3.12 coverage in addition to Linux/Python 3.11. Only a
successful job is validation; configuring a matrix is not a passing result.

Keep FastAPI, Python, existing read-only evidence tools, SQLite for the first
slice, versioned review, transactions, recorded replay and unittest. Initial
business focus is water-service reports; time/shared-asset proximity is only
a lead, not a diagnosis. [Decision 0001](decisions/0001-report-intake.md) explains
the intake design and its limits.

Defer multi-agent/reflection frameworks, S3, React rewrites, complex queues,
real maintenance dispatch, completed-repair verification and external notices
until a concrete use case and failure evidence justify them.

## Open findings

- Missing candidates/unknowns can still pass proposal submission checks.
- Proposal notice time classification is not fully validated at save time.
- Newly added related work orders are not covered by cited-row version checks.
- Failed Agent attempts lack durable, queryable records.
- A shared demo token/fixed actor is not individual authentication; evidence
  reads remain public for synthetic demo data.
- No current live-model classification, production emergency response or
  deployed application is claimed by the passing offline suite.

## Working and review policy

Implement a useful small slice, validate it with a business case and relevant
failure behavior, document the remaining limits, then perform a short
maintainer walkthrough at key milestones. Missing knowledge narrows the
explanation; it does not halt independent project work. Do not add an exercise
for every function or infer proficiency from AI-generated implementation.

Revisit selected open-source implementations after the first full review loop,
and again before deployment. Each revisit must answer an implementation or
deployment decision; it is not an open-ended feature survey.
