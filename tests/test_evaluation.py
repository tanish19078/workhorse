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

    def test_edited_origin_retrieved_without_changing_strict_flag_metric(self):
        path = Path(__file__).resolve().parents[1] / "examples/benchmark/cases.json"
        row = next(r for r in evaluate(path)["results"] if r["normalization"] == "relationships" and r["split"] == "development")
        case = next(c for c in row["cases"] if c["id"] == "different-dataflow")
        self.assertFalse(case["flagged"])
        self.assertTrue(case["retrieved"])
        self.assertEqual(case["retrieval_category"], "broad_candidate")
        self.assertGreater(row["retrieval_recall"], row["recall"])

    def test_identical_source_cannot_cross_tasks_to_hide_leakage(self):
        with tempfile.TemporaryDirectory() as temp:
            case = dict(id='a', task='one', language='python', left='x=1', right='x=2',
                        label='shared_origin', split='development', provenance='synthetic')
            path = Path(temp)/'cases.json'
            path.write_text(json.dumps({'schema_version':1, 'cases':[case,
                {**case,'id':'b','task':'two','split':'holdout','left':' x=1\r\n','right':'y=4'}]}))
            with self.assertRaisesRegex(ValueError,'Identical source'):
                evaluate(path)

    def test_declared_source_family_cannot_cross_splits(self):
        with tempfile.TemporaryDirectory() as temp:
            case = dict(id='a',task='one',language='python',left='x=1',right='x=2',
                        label='shared_origin',split='development',provenance='synthetic',source_family='ancestor')
            path=Path(temp)/'cases.json'
            path.write_text(json.dumps({'schema_version':1,'cases':[case,
                {**case,'id':'b','task':'two','split':'holdout','left':'z=3','right':'w=4'}]}))
            with self.assertRaisesRegex(ValueError,'Source family'):
                evaluate(path)

    def test_evaluation_digest_uses_scored_bytes_after_input_changes(self):
        import hashlib
        from unittest.mock import patch
        from workhorse.compare import compare
        original=(Path(__file__).resolve().parents[1]/'examples/benchmark/cases.json').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cases.json';path.write_bytes(original)
            def change_during_comparison(*args,**kwargs):
                path.write_bytes(b'changed after snapshot')
                return compare(*args,**kwargs)
            with patch('workhorse.evaluation.compare',side_effect=change_during_comparison):
                result=evaluate(path)
            self.assertEqual(result['benchmark_sha256'],hashlib.sha256(original).hexdigest())
