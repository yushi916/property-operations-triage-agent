import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from evals.scenarios import create_scenario_database


ROOT = Path(__file__).resolve().parents[1]


class ToolCall:
    type = "function_call"
    name = "lookup_report_work_orders"
    arguments = {"report_id": "R-02"}
    id = "test-call-1"

    def model_dump(self):
        return {
            "type": self.type,
            "name": self.name,
            "arguments": self.arguments,
            "id": self.id,
        }


class FailOnSecondCall:
    def __init__(self):
        self.interactions = self
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                steps=[ToolCall()], output_text=""
            )
        raise TimeoutError("provider-detail-must-stay-private")


class ModelCallFailureTraceTest(unittest.TestCase):
    def test_api_keeps_prior_trace_without_saving_proposal(self):
        with TemporaryDirectory() as folder:
            db = Path(folder) / "case.db"
            create_scenario_database(
                db, ROOT / "data" / "demo_case.json", "base"
            )
            fake = FailOnSecondCall()

            with patch.dict(os.environ, {
                "PROPERTY_REVIEW_TOKEN": "local-test-token",
                "GEMINI_API_KEY": "test-key",
            }):
                with patch("google.genai.Client", return_value=fake):
                    with TestClient(create_app(db)) as client:
                        response = client.post(
                            "/v1/reviews/report",
                            headers={
                                "X-Review-Token": "local-test-token"
                            },
                            json={"report_id": "R-01"},
                        )

            self.assertEqual(response.status_code, 502, response.text)
            detail = response.json()["detail"]
            self.assertEqual(detail["run_status"], "model_call_failed")
            self.assertEqual(detail["rounds"], 2)
            self.assertEqual(detail["error_type"], "TimeoutError")
            self.assertEqual(fake.calls, 2)
            self.assertTrue(any(
                call.get("origin") == "candidate_discovery"
                for call in detail["trace"]
            ))
            self.assertTrue(any(
                call["tool"] == "lookup_report_work_orders"
                for call in detail["trace"]
            ))
            self.assertNotIn(
                "provider-detail-must-stay-private", response.text
            )

            with closing(sqlite3.connect(db)) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM review_proposals"
                ).fetchone()[0]
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
