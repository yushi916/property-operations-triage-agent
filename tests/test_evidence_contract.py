import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agent_tools import execute_read_tool
from app.review_actions import save_report_proposal
from app.tools import SQLiteEvidenceTools
from evals.scenarios import create_scenario_database

ROOT = Path(__file__).resolve().parents[1]

CASES = [
    ("伪造报事", "R-999", False, False, "缺少自身证据"),
    ("未查工单", "R-03", False, False, "未核查既有工单"),
    ("查到却漏引", "R-03", True, False, "未引用既有工单 W-02"),
    ("查到且引用", "R-03", True, True, None),
    ("查询为空", "R-02", True, False, None),
]


class EvidenceContractTest(unittest.TestCase):
    def test_submission_boundary(self):
        for label, report_id, lookup, cite_order, error in CASES:
            with self.subTest(case=label), TemporaryDirectory() as folder:
                db_path = Path(folder) / "case.db"
                create_scenario_database(
                    db_path, ROOT / "data" / "demo_case.json", "base"
                )

                trace = []
                with closing(sqlite3.connect(db_path)) as conn:
                    tools = SQLiteEvidenceTools(conn)

                    def read(name, arguments):
                        outcome = execute_read_tool(tools, name, arguments)
                        self.assertTrue(outcome["ok"], outcome)
                        trace.append({
                            "tool": name,
                            "arguments": arguments,
                            "outcome": outcome,
                        })

                    read("get_report", {"report_id": "R-01"})
                    if report_id != "R-999":
                        read("get_report", {"report_id": report_id})
                    if lookup:
                        read(
                            "lookup_report_work_orders",
                            {"report_id": report_id},
                        )

                if lookup and report_id == "R-03":
                    orders = trace[-1]["outcome"]["result"]["evidence"]
                    self.assertEqual(
                        [order["source_id"] for order in orders],
                        ["W-02"],
                    )

                refs = [{
                    "id": "R-01" if report_id == "R-999" else report_id,
                    "version": 1,
                }]
                if cite_order:
                    refs.append({
                        "id": orders[0]["source_id"],
                        "version": orders[0]["source_version"],
                    })

                run = {
                    "status": "proposal",
                    "report_id": "R-01",
                    "trace": trace,
                    "proposal": {
                        "seed_report_id": "R-01",
                        "reports": [{
                            "report_id": report_id,
                            "relation": "hold_separate",
                            "reason": "需核查",
                            "evidence_refs": refs,
                        }],
                        "notices": [],
                        "unknowns": [],
                        "next_actions": ["人工核查"],
                    },
                }

                if error:
                    with self.assertRaisesRegex(ValueError, error):
                        save_report_proposal(db_path, run)
                    expected_count = 0
                else:
                    saved = save_report_proposal(db_path, run)
                    self.assertEqual(saved["state"], "pending")
                    if cite_order:
                        self.assertIn(refs[-1], saved["evidence_refs"])
                    expected_count = 1

                with closing(sqlite3.connect(db_path)) as conn:
                    actual_count = conn.execute(
                        "SELECT COUNT(*) FROM review_proposals"
                    ).fetchone()[0]
                self.assertEqual(actual_count, expected_count)


if __name__ == "__main__":
    unittest.main()
