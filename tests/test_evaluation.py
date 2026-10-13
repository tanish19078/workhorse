import json
from pathlib import Path
import tempfile
import unittest
from workhorse.evaluation import evaluate


class EvaluationTests(unittest.TestCase):
    def test_task_leakage_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            case = dict(id="a", task="one", language="python", left="x=1", right="x=1",
                        label="shared_origin", split="development", provenance="synthetic")
            path = Path(temp) / "cases.json"
            path.write_text(json.dumps({"schema_version": 1, "cases": [case, {**case, "id": "b", "split": "holdout"}]}))
            with self.assertRaisesRegex(ValueError, "both development"):
                evaluate(path)

    def test_metrics_cover_each_labeled_case_once_per_mode(self):
        path = Path(__file__).resolve().parents[1] / "examples/benchmark/cases.json"
        result = evaluate(path)
        self.assertEqual(len(result["results"]), 4)
        for row in result["results"]:
            counts = row["counts"]
            self.assertEqual(len(row["cases"]), sum(counts[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative", "insufficient_cases", "ambiguous_cases")))
        self.assertIn("do not estimate", result["interpretation"])
