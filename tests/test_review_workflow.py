import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from evals.scenarios import create_scenario_database


ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-Review-Token": "local-test-token"}
PLAN = {
    "plan_id": "P-01",
    "order_id": "W-01",
    "inspection_id": "I-01",
}


class ReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "case.db"

        create_scenario_database(
            self.db_path, ROOT / "data" / "demo_case.json", "base"
        )

        environment = patch.dict(
            os.environ, {"PROPERTY_REVIEW_TOKEN": "local-test-token"}
        )
        environment.start()
        self.addCleanup(environment.stop)

        self.client = TestClient(create_app(self.db_path))

    def test_review_endpoint_requires_token(self):
        response = self.client.get("/v1/reviews")
        self.assertEqual(response.status_code, 401, response.text)

        response = self.client.get("/v1/reviews", headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)

    def test_stale_evidence_blocks_approval_without_creating_task(self):
        first = self.client.post(
            "/v1/reviews/plan", headers=HEADERS, json=PLAN
        )
        self.assertEqual(first.status_code, 201, first.text)

        duplicate = self.client.post(
            "/v1/reviews/plan", headers=HEADERS, json=PLAN
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        with closing(sqlite3.connect(self.db_path)) as conn:
            proposal_id = conn.execute(
                """SELECT id FROM review_proposals
                   WHERE kind = 'plan_review'
                     AND case_ref = 'P-01'
                     AND state = 'pending'"""
            ).fetchone()[0]
            conn.execute(
                "UPDATE inspections SET version = version + 1 "
                "WHERE id = 'I-01'"
            )
            conn.commit()

        approval = self.client.post(
            f"/v1/reviews/{proposal_id}/decision",
            headers=HEADERS,
            json={
                "decision": "approved",
                "expected_version": 1,
                "reason": "测试旧证据不可批准",
            },
        )
        self.assertEqual(approval.status_code, 409, approval.text)

        with closing(sqlite3.connect(self.db_path)) as conn:
            state = conn.execute(
                "SELECT state, version FROM review_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            task_count = conn.execute(
                "SELECT COUNT(*) FROM internal_tasks"
            ).fetchone()[0]

        self.assertEqual(state, ("pending", 1))
        self.assertEqual(task_count, 0)


    def test_missing_default_db_returns_503_without_creating_file(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "not_initialized.db"
            with patch("app.main.DEFAULT_DB", missing):
                with TestClient(create_app()) as client:
                    report = client.get("/v1/reports/R-01")
                    reviews = client.get(
                        "/v1/reviews", headers=HEADERS
                    )

            self.assertEqual(report.status_code, 503, report.text)
            self.assertEqual(reviews.status_code, 503, reviews.text)
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
