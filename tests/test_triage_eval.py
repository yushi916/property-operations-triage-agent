import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agent_tools import execute_read_tool
from app.tools import SQLiteEvidenceTools
from evals.scenarios import create_scenario_database
from evals.triage_eval import evaluate_public_outage

ROOT = Path(__file__).resolve().parents[1]


class TriageEvalTest(unittest.TestCase):
    def test_r03_order_is_required_for_case_pass(self):
        with TemporaryDirectory() as folder:
            db = Path(folder) / "case.db"
            create_scenario_database(
                db, ROOT / "data" / "demo_case.json", "base"
            )

            trace = []
            with closing(sqlite3.connect(db)) as conn:
                tools = SQLiteEvidenceTools(conn)

                def read(name, arguments):
                    outcome = execute_read_tool(tools, name, arguments)
                    self.assertTrue(outcome["ok"], outcome)
                    return {
                        "tool": name,
                        "arguments": arguments,
                        "outcome": outcome,
                    }

                for report_id in ("R-01", "R-02", "R-03", "R-04"):
                    trace.append(read(
                        "get_report", {"report_id": report_id}
                    ))
                trace.append(read("lookup_notices", {
                    "building": "3栋",
                    "at": "2026-09-28T09:05:00+08:00",
                }))
                for report_id in ("R-02", "R-04"):
                    trace.append(read("lookup_report_work_orders", {
                        "report_id": report_id,
                    }))
                order_call = read("lookup_report_work_orders", {
                    "report_id": "R-03",
                })

            orders = order_call["outcome"]["result"]["evidence"]
            self.assertEqual(
                [row["source_id"] for row in orders], ["W-02"]
            )

            proposal = {
                "seed_report_id": "R-01",
                "reports": [
                    {
                        "report_id": report_id,
                        "relation": relation,
                        "reason": "待核实",
                        "evidence_refs": [
                            {"id": report_id, "version": 1}
                        ],
                    }
                    for report_id, relation in (
                        ("R-02", "possible_same_event"),
                        ("R-03", "hold_separate"),
                        ("R-04", "needs_verification"),
                    )
                ],
                "notices": [{
                    "notice_id": "N-01",
                    "time_relation": "expired",
                    "evidence_refs": [{"id": "N-01", "version": 1}],
                }],
                "unknowns": [
                    {"code": code, "detail": "待核实"}
                    for code in (
                        "fault_cause",
                        "impact_scope",
                        "restoration_time",
                    )
                ],
                "next_actions": [],
            }
            run = {
                "status": "proposal",
                "proposal": proposal,
                "trace": trace,
            }
            gold = ROOT / "evals" / "gold_case.json"

            # 漏查 W-02：不能通过。
            missed = evaluate_public_outage(run, gold)
            self.assertFalse(missed["case_pass"])
            self.assertFalse(
                missed["checks"]["critical_order_examined"]
            )

            # 查到 W-02，但 R-03 的建议没有引用：仍不能通过。
            trace.append(order_call)
            uncited = evaluate_public_outage(run, gold)
            self.assertFalse(uncited["case_pass"])
            self.assertTrue(
                uncited["checks"]["critical_order_examined"]
            )
            self.assertFalse(
                uncited["checks"]["critical_order_cited"]
            )

            # 查到且引用：这个固定案例通过。
            proposal["reports"][1]["evidence_refs"].append({
                "id": orders[0]["source_id"],
                "version": orders[0]["source_version"],
            })
            complete = evaluate_public_outage(run, gold)
            self.assertTrue(complete["case_pass"], complete)
            trace[:] = [
                call for call in trace
                if not (
                    call["tool"] == "lookup_report_work_orders"
                    and call["arguments"].get("report_id") == "R-02"
                )
            ]
            omitted = evaluate_public_outage(run, gold)
            self.assertFalse(omitted["case_pass"])
            self.assertEqual(
                omitted["details"]["missing_report_order_lookups"],
                ["R-02"],
            )


if __name__ == "__main__":
    unittest.main()
