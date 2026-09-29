import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from evals.run_demo import main


FAKE_RUN = {
    "status": "invalid_output",
    "report_id": "R-01",
    "rounds": 2,
    "trace": [{
        "tool": "get_report",
        "arguments": {"report_id": "R-01"},
        "outcome": {"ok": True, "result": {}},
    }],
    "validation_error": "结构化输出不合格",
}


class DemoFailureTest(unittest.TestCase):
    def test_cli_emits_trace_and_exits_nonzero(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), (
            patch("google.genai.Client")
        ), (
            patch("app.agent.investigate_report", return_value=FAKE_RUN)
        ), (
            patch("sys.argv", [
                "run_demo", "--scenario", "base", "--with-model"
            ])
        ), redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                main()

        self.assertEqual(raised.exception.code, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(
            result["submission_failure"]["run_status"],
            "invalid_output",
        )
        self.assertEqual(
            result["submission_failure"]["validation_error"],
            "结构化输出不合格",
        )
        self.assertEqual(result["model_tool_calls"], ["get_report"])
        self.assertEqual(len(result["trace"]), 1)
        self.assertFalse(result["evaluation"]["case_pass"])


if __name__ == "__main__":
    unittest.main()
