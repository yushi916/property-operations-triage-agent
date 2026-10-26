# Decision 0001: Record a report before investigating it

Date: 2026-10-26. Status: implemented on the milestone-1 branch.

## Problem and scope

The existing API investigated only preloaded report IDs. A duty manager needs
to record a new water-service report before asking an Agent to reconcile it
with notices, work orders, and shared assets. Intake must remain available
without a model API key.

This is an internal staff workflow using synthetic records. It ends with a
saved report and receipt, not a repair, notification, or diagnosis.

## Decisions

- Keep the existing `reports` contract and tools. Add `report_intakes` as an
  additive table for request identity, source, occurrence/receipt timestamps,
  the declared risk, and the fixed demo actor. Existing rows have no receipt;
  they are not assigned invented historical risk assessments.
- Require the existing staff demo token for writes. Real user identity and
  protected evidence reads are separate requirements before real data.
- Treat report receipt time as `reported_at`, the existing candidate window
  input. Store optional occurrence time separately; never replace missing
  occurrence time with an invented timestamp.
- Persist urgent/unknown risk submissions before returning human-action
  guidance. Block normal model submission for them. This is based on explicit
  staff declaration, not keyword detection or proof of safety. There is no
  risk-clearance endpoint yet, and no automatic external notification.
- Use one UUID per user submission. Inside one SQLite write transaction,
  check its normalized-payload hash, create the report and receipt together,
  and return the existing report on matching retries. A reused UUID with
  changed content is a conflict. This protects retries of an operation; two
  deliberate submissions with different UUIDs remain distinct reports.
- Use the buildings already in the fixture's reports/asset coverage as the
  temporary allowlist. A maintained building registry is future work.
- Keep SQLite and unittest for this slice. Startup creates the additive
  receipt table for existing initialized demo databases; there is no destructive
  fixture reload. Formal schema migrations/Postgres are a separate milestone.

## Evidence and alternatives

The phase-1 review identified recording, traceability, and urgent human
handling as requirements supported by geographically scoped public property
guidance. Requiring model success before saving a report would lose the
service request during an outage. Combining report intake with approval would
confuse facts supplied by staff with a later recommendation.

Source boundaries: [Zhongshan guidance](https://jsj.zs.gov.cn/attachment/0/544/544445/2538130.pdf),
sections 1.0.2 and 8.4.2, is local guidance (July 2025); the Hong Kong PMSA
[emergency handling directory](https://www.pmsa.org.hk/tc/regulatory-framework/codes-of-conduct)
contains C12/2022 and G12/2022 for licensed Hong Kong property managers.
Neither mandates this UUID scheme, database design, or the three risk labels;
those are application design choices. No national response-time guarantee is
claimed.

The earlier review inspected OpenProperty's work-order CRUD, Atlas CMMS's
request approval service/tests, Dispatch's event history, and LangGraph's
interrupt/retry tests. This slice adds intake without introducing a second
workflow engine; reference rechecks remain scheduled at completion of the
first full review loop and before deployment.

## Deferred limitations

No new UI, live model validation, durable failed Agent attempts, complete
candidate validation, new-record freshness check, repair execution, or
production emergency response is delivered here. The phase-1 findings remain
open and must not be hidden by the passing intake tests.
