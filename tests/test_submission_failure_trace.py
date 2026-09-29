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
HEADERS = {"X-Review-Token": "test-token"}
TRACE = [{
    "tool": "get_report",
    "arguments": {"report_id": "R-01"},
    "outcome": {"ok": True, "result": {"source_id": "R-01"}},
}]


class SubmissionFailureTraceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "case.db"
        create_scenario_database(
            self.db_path, ROOT / "data" / "demo_case.json", "base"
        )

    def submit(self, run, save_error=None):
        environment = {
            "PROPERTY_REVIEW_TOKEN": "test-token",
            "GEMINI_API_KEY": "test-key",
        }
        with patch.dict(os.environ, environment), \
             patch("google.genai.Client"), \
             patch("app.agent.investigate_report", return_value=run):
            with TestClient(create_app(self.db_path)) as client:
                if save_error is None:
                    response = client.post(
                        "/v1/reviews/report",
                        headers=HEADERS,
                        json={"report_id": "R-01"},
                    )
                else:
                    with patch(
                        "app.review_actions.save_report_proposal",
                        side_effect=ValueError(save_error),
                    ):
                        response = client.post(
                            "/v1/reviews/report",
                            headers=HEADERS,
                            json={"report_id": "R-01"},
                        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            proposals = conn.execute(
                "SELECT COUNT(*) FROM review_proposals"
            ).fetchone()[0]
        self.assertEqual(proposals, 0)
        return response

    def test_invalid_output_preserves_trace(self):
        response = self.submit({
            "status": "invalid_output",
            "report_id": "R-01",
            "rounds": 2,
            "trace": TRACE,
            "validation_error": "结构化输出不合格",
        })
        self.assertEqual(response.status_code, 502, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["run_status"], "invalid_output")
        self.assertEqual(detail["rounds"], 2)
        self.assertEqual(detail["trace"], TRACE)
        self.assertEqual(detail["validation_error"], "结构化输出不合格")

    def test_submission_rejection_preserves_trace(self):
        response = self.submit(
            {
                "status": "proposal",
                "report_id": "R-01",
                "rounds": 2,
                "trace": TRACE,
                "proposal": {},
            },
            save_error="证据版本已变化",
        )
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["message"], "证据版本已变化")
        self.assertEqual(detail["run_status"], "proposal")
        self.assertEqual(detail["trace"], TRACE)


if __name__ == "__main__":
    unittest.main()
