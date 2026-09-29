import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent_tools import execute_read_tool
from app.main import create_app
from app.review_actions import save_report_proposal
from app.tools import SQLiteEvidenceTools
from evals.scenarios import create_scenario_database

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-Review-Token": "local-test-token"}
REVISION = {
    "expected_version": 1,
    "reason": "审核员认为关联证据仍需现场核实",
    "changes": [{
        "report_id": "R-02",
        "relation": "needs_verification",
        "reason": "现场确认影响范围前暂缓判断",
    }],
}


class ReviewRevisionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "case.db"
        create_scenario_database(
            self.db, ROOT / "data" / "demo_case.json", "base"
        )

        trace = []
        with closing(sqlite3.connect(self.db)) as conn:
            tools = SQLiteEvidenceTools(conn)
            for name, arguments in (
                ("get_report", {"report_id": "R-01"}),
                ("get_report", {"report_id": "R-02"}),
                ("lookup_report_work_orders", {"report_id": "R-02"}),
            ):
                outcome = execute_read_tool(tools, name, arguments)
                self.assertTrue(outcome["ok"], outcome)
                trace.append({
                    "tool": name,
                    "arguments": arguments,
                    "outcome": outcome,
                })

        self.run = {
            "status": "proposal",
            "report_id": "R-01",
            "trace": trace,
            "proposal": {
                "seed_report_id": "R-01",
                "reports": [{
                    "report_id": "R-02",
                    "relation": "possible_same_event",
                    "reason": "时间地点接近，仍待审核",
                    "evidence_refs": [{"id": "R-02", "version": 1}],
                }],
                "notices": [],
                "unknowns": [],
                "next_actions": [],
            },
        }
        self.saved = save_report_proposal(self.db, self.run)
        self.url = f"/v1/reviews/{self.saved['id']}"

        environment = patch.dict(
            os.environ,
            {"PROPERTY_REVIEW_TOKEN": "local-test-token"},
        )
        environment.start()
        self.addCleanup(environment.stop)

        self.client = TestClient(create_app(self.db))
        self.addCleanup(self.client.close)

    def test_revision_audit_and_versioned_approval(self):
        before = self.client.get(
            self.url, headers=HEADERS
        ).json()

        no_token = self.client.post(
            self.url + "/revisions", json=REVISION
        )
        self.assertEqual(no_token.status_code, 401)

        injected = self.client.post(
            self.url + "/revisions",
            headers=HEADERS,
            json={
                **REVISION,
                "changes": [{
                    **REVISION["changes"][0],
                    "evidence_refs": [
                        {"id": "W-999", "version": 1}
                    ],
                }],
            },
        )
        self.assertEqual(injected.status_code, 422)

        revised = self.client.post(
            self.url + "/revisions",
            headers=HEADERS,
            json=REVISION,
        )
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["version"], 2)

        duplicate = self.client.post(
            self.url + "/revisions",
            headers=HEADERS,
            json=REVISION,
        )
        self.assertEqual(duplicate.status_code, 409)

        detail = self.client.get(
            self.url, headers=HEADERS
        ).json()
        self.assertEqual((detail["state"], detail["version"]),
                         ("pending", 2))
        self.assertEqual(len(detail["revisions"]), 1)
        audit = detail["revisions"][0]
        self.assertEqual(
            (audit["from_version"], audit["to_version"]),
            (1, 2),
        )
        self.assertEqual(audit["actor"], "demo_manager")
        self.assertEqual(
            audit["before"]["reports"][0]["relation"],
            "possible_same_event",
        )
        self.assertEqual(
            audit["after"]["reports"][0]["relation"],
            "needs_verification",
        )
        self.assertEqual(detail["trace"], self.run["trace"])
        self.assertEqual(
            detail["evidence_refs"], before["evidence_refs"]
        )

        old_approval = self.client.post(
            self.url + "/decision",
            headers=HEADERS,
            json={
                "decision": "approved",
                "expected_version": 1,
                "reason": "旧版不应批准",
            },
        )
        self.assertEqual(old_approval.status_code, 409)

        approved = self.client.post(
            self.url + "/decision",
            headers=HEADERS,
            json={
                "decision": "approved",
                "expected_version": 2,
                "reason": "批准修正后的待核实建议",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        final = self.client.get(
            self.url, headers=HEADERS
        ).json()
        self.assertEqual(
            (final["state"], final["version"]),
            ("approved", 3),
        )
        self.assertEqual(len(final["tasks"]), 1)
        self.assertEqual(len(final["revisions"]), 1)

    def test_stale_evidence_rolls_back_revision(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "UPDATE reports SET version = version + 1 "
                "WHERE id = 'R-02'"
            )
            conn.commit()

        response = self.client.post(
            self.url + "/revisions",
            headers=HEADERS,
            json=REVISION,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("版本已变化", response.text)

        detail = self.client.get(
            self.url, headers=HEADERS
        ).json()
        self.assertEqual(
            (detail["state"], detail["version"]),
            ("pending", 1),
        )
        self.assertEqual(detail["revisions"], [])


if __name__ == "__main__":
    unittest.main()
