import json
from pathlib import Path


UNKNOWN_CODES = {
    "故障原因": "fault_cause",
    "完整受影响范围": "impact_scope",
    "预计恢复时间": "restoration_time",
}


def _source_refs(value):
    refs = set()
    if isinstance(value, dict):
        if "source_id" in value and "source_version" in value:
            refs.add((value["source_id"], value["source_version"]))
        for child in value.values():
            refs.update(_source_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_source_refs(child))
    return refs


def evaluate_public_outage(run: dict, gold_path: Path) -> dict:
    gold = json.loads(
        Path(gold_path).read_text(encoding="utf-8")
    )["public_outage"]
    proposal = run.get("proposal")

    if proposal is None:
        return {
            "case_pass": False,
            "checks": {"valid_proposal": False},
            "details": {"run_status": run["status"]},
            "coverage": {},
        }

    expected = {
        report_id: category
        for category in (
            "possible_same_event",
            "hold_separate",
            "needs_verification",
        )
        for report_id in gold[category]
        if report_id != proposal["seed_report_id"]
    }
    reports = proposal["reports"]
    actual = {
        item["report_id"]: item["relation"]
        for item in reports
    }

    read_refs = set()
    for call in run["trace"]:
        if call["outcome"]["ok"]:
            read_refs.update(
                _source_refs(call["outcome"]["result"])
            )

    assessments = reports + proposal["notices"]
    claimed_refs = {
        (ref["id"], ref["version"])
        for item in assessments
        for ref in item["evidence_refs"]
    }
    missing_refs = sorted(claimed_refs - read_refs)

    own_record_cited = all(
        any(
            ref["id"] == item["report_id"]
            for ref in item["evidence_refs"]
        )
        for item in reports
    ) and all(
        any(
            ref["id"] == item["notice_id"]
            for ref in item["evidence_refs"]
        )
        for item in proposal["notices"]
    )

    notice_ok = any(
        item["notice_id"] == gold["stale_notice"]
        and item["time_relation"] == "expired"
        for item in proposal["notices"]
    )

    expected_unknowns = {
        UNKNOWN_CODES[label] for label in gold["unknowns"]
    }
    actual_unknowns = {
        item["code"] for item in proposal["unknowns"]
    }

    held_reports = {
        item["report_id"]
        for item in reports
        if item["relation"] == "hold_separate"
    }
    checked_indoor_orders = {
        call["arguments"].get("report_id")
        for call in run["trace"]
        if call["tool"] == "lookup_report_work_orders"
        and call["outcome"]["ok"]
    }

    report_order_lookups = {
        call["arguments"].get("report_id")
        for call in run["trace"]
        if call["tool"] == "lookup_report_work_orders"
        and call["outcome"]["ok"]
        and call["outcome"]["result"].get("query") == {
            "report_id": call["arguments"].get("report_id")
        }
    }
    missing_report_order_lookups = sorted(
        set(actual) - report_order_lookups
    )
    required_orders = gold.get("critical_report_work_orders", {})
    examined_orders = {
        (call["arguments"].get("report_id"), order["source_id"])
        for call in run["trace"]
        if call["tool"] == "lookup_report_work_orders"
        and call["outcome"]["ok"]
        for order in call["outcome"]["result"]["evidence"]
    }
    cited_orders = {
        (item["report_id"], ref["id"])
        for item in reports
        for ref in item["evidence_refs"]
    }
    missing_examined_orders = sorted(
        (report_id, order_id)
        for report_id, order_id in required_orders.items()
        if (report_id, order_id) not in examined_orders
    )
    missing_cited_orders = sorted(
        (report_id, order_id)
        for report_id, order_id in required_orders.items()
        if (report_id, order_id) not in cited_orders
    )

    checks = {
        "completed_with_proposal": run["status"] == "proposal",
        "classification_matches_gold": (
            actual == expected
            and len(reports) == len(actual)
        ),
        "stale_notice_identified": notice_ok,
        "unknown_categories_complete": (
            expected_unknowns <= actual_unknowns
        ),
        "every_assessment_has_evidence": all(
            bool(item["evidence_refs"])
            for item in assessments
        ),
        "own_record_cited": own_record_cited,
        "all_cited_id_versions_retrieved": not missing_refs,
        "all_assessed_reports_order_checked": not missing_report_order_lookups,
        "critical_order_examined": not missing_examined_orders,
        "critical_order_cited": not missing_cited_orders,
        "no_tool_errors": all(
            call["outcome"]["ok"]
            for call in run["trace"]
        ),
    }

    return {
        "case_pass": all(checks.values()),
        "checks": checks,
        "details": {
            "expected_classification": expected,
            "actual_classification": actual,
            "unretrieved_id_versions": missing_refs,
            "missing_report_order_lookups": missing_report_order_lookups,
            "missing_critical_orders": missing_examined_orders,
            "uncited_critical_orders": missing_cited_orders,
            "missing_unknown_codes": sorted(
                expected_unknowns - actual_unknowns
            ),
        },
        "coverage": {
            "held_reports_without_order_lookup": sorted(
                held_reports - checked_indoor_orders
            ),
        },
    }
