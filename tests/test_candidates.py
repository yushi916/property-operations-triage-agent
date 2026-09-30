import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from app.candidates import discover_report_candidates
from app.tools import SQLiteEvidenceTools
from evals.scenarios import create_scenario_database

ROOT = Path(__file__).resolve().parents[1]


class CandidateDiscoveryTest(unittest.TestCase):
    def test_shared_asset_finds_cross_building_report(self):
        with TemporaryDirectory() as folder:
            db = Path(folder) / "case.db"
            create_scenario_database(
                db, ROOT / "data" / "demo_case.json", "base"
            )
            with closing(sqlite3.connect(db)) as conn:
                result = discover_report_candidates(
                    SQLiteEvidenceTools(conn), "R-01"
                )

        candidates = {
            row["evidence"]["source_id"]: row
            for row in result["candidates"]
        }
        self.assertEqual(set(candidates), {"R-02", "R-03", "R-04"})
        self.assertEqual(candidates["R-04"]["paths"], [{
            "kind": "shared_asset",
            "asset_id": "A-01",
        }])
        self.assertIn(
            "find_reports_for_asset",
            [call["tool"] for call in result["trace"]],
        )
        self.assertTrue(all(
            call["outcome"]["ok"] for call in result["trace"]
        ))

    def test_excludes_unrelated_and_out_of_window_reports(self):
        with TemporaryDirectory() as folder:
            db = Path(folder) / "case.db"
            create_scenario_database(
                db, ROOT / "data" / "demo_case.json", "base"
            )
            with closing(sqlite3.connect(db)) as conn:
                with conn:
                    conn.executemany("""
                        INSERT INTO reports
                            (id, reported_at, building, text, version)
                        VALUES (?, ?, ?, ?, ?)
                    """, [
                        ("R-05", "2026-09-28T09:12:00+08:00",
                         "8栋", "同时发生但无共同设备", 1),
                        ("R-06", "2026-09-28T10:05:00+08:00",
                         "3栋", "同楼栋但超过时间窗", 1),
                        ("R-07", "2026-09-28T10:05:00+08:00",
                         "5栋", "共用设备但超过时间窗", 1),
                    ])
                result = discover_report_candidates(
                    SQLiteEvidenceTools(conn), "R-01"
                )

        found = {
            item["evidence"]["source_id"]
            for item in result["candidates"]
        }
        self.assertEqual(found, {"R-02", "R-03", "R-04"})

    def test_agent_receives_discovered_candidates(self):
        from types import SimpleNamespace
        from app.agent import investigate_report

        class FakeClient:
            def __init__(self):
                self.interactions = self
                self.sent_input = None

            def create(self, **kwargs):
                self.sent_input = kwargs["input"]
                return SimpleNamespace(steps=[], output_text="")

        with TemporaryDirectory() as folder:
            db = Path(folder) / "case.db"
            create_scenario_database(
                db, ROOT / "data" / "demo_case.json", "base"
            )
            fake = FakeClient()
            run = investigate_report(
                fake, db, "R-01",
                max_rounds=1, max_tool_calls=14,
            )

        self.assertEqual(run["status"], "invalid_output")
        self.assertIn(
            "R-04", fake.sent_input[0]["content"][0]["text"]
        )
        self.assertTrue(any(
            call["tool"] == "find_reports_for_asset"
            and call.get("origin") == "candidate_discovery"
            for call in run["trace"]
        ))

    def test_discovery_does_not_use_model_tool_budget(self):
        from types import SimpleNamespace
        from app.agent import investigate_report

        class ToolCall:
            type = "function_call"
            name = "lookup_report_work_orders"
            arguments = {"report_id": "R-01"}
            id = "test-call-1"

            def model_dump(self):
                return {
                    "type": self.type,
                    "name": self.name,
                    "arguments": self.arguments,
                    "id": self.id,
                }

        class FakeClient:
            def __init__(self):
                self.interactions = self
                self.rounds = 0

            def create(self, **kwargs):
                self.rounds += 1
                steps = [ToolCall()] if self.rounds == 1 else []
                return SimpleNamespace(steps=steps, output_text="")

        with TemporaryDirectory() as folder:
            db = Path(folder) / "case.db"
            create_scenario_database(
                db, ROOT / "data" / "demo_case.json", "base"
            )
            run = investigate_report(
                FakeClient(), db, "R-01",
                max_rounds=2, max_tool_calls=1,
            )

        model_calls = [
            call for call in run["trace"]
            if call.get("origin") != "candidate_discovery"
        ]
        self.assertEqual(run["status"], "invalid_output")
        self.assertEqual(
            [call["tool"] for call in model_calls],
            ["lookup_report_work_orders"],
        )


if __name__ == "__main__":
    unittest.main()
