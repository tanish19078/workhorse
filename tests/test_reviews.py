import json
from pathlib import Path
import tempfile
import unittest

from workhorse.compare import compare
from workhorse.imports import Submission
from workhorse.reviews import init_reviews, load_reviews, pair_key, record_review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = "\n".join(f"value += {i}" for i in range(25))
        self.report = compare([Submission(i, i, "q", "python", i + ".py", source) for i in ("a", "b")])
        self.report_path = self.root / "report.json"
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        self.workspace = self.root / "reviews.json"
        init_reviews(self.report_path, self.workspace)
        self.key = next(iter(load_reviews(self.workspace)["pairs"]))

    def test_notes_preserve_history_and_separate_scores(self):
        record_review(self.workspace, self.key, "investigate", "unusual shared constants", "reviewer")
        record_review(self.workspace, self.key, "explained", "allowed template confirmed", "reviewer",
                      "shared template predates the task")
        item = load_reviews(self.workspace)["pairs"][self.key]
        self.assertEqual(item["status"], "explained")
        self.assertEqual(len(item["history"]), 2)
        self.assertIn("template", item["contrary_evidence"])
        self.assertEqual(json.loads(self.report_path.read_text()), self.report)

    def test_workspace_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            init_reviews(self.report_path, self.workspace)

    def test_pair_identity_includes_hashes_and_is_symmetric(self):
        a, b = self.report["submissions"]
        self.assertEqual(pair_key(a, b), pair_key(b, a))
        self.assertNotEqual(pair_key(a, b), pair_key({**a, "sha256": "changed"}, b))

    def test_explanation_required(self):
        with self.assertRaisesRegex(ValueError, "require a note"):
            record_review(self.workspace, self.key, "explained", "", "reviewer")

    def test_unknown_pair_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown pair"):
            record_review(self.workspace, "missing", "investigate", "check", "reviewer")

    def test_malformed_report_rejected(self):
        self.report["findings"][0]["left"] = "missing"
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown submission"):
            init_reviews(self.report_path, self.root / "new.json")

    def test_malformed_span_rejected(self):
        self.report["findings"][0]["evidence"][0]["left"]["end_line"] = -1
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "line range"):
            init_reviews(self.report_path, self.root / "new.json")

    def test_inconsistent_summary_rejected(self):
        self.report["summary"]["submissions"] = 200
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match"):
            init_reviews(self.report_path, self.root / "new.json")

    def test_invalid_optional_signals_rejected(self):
        self.report["findings"][0]["signals"]["raw_containment"] = "bad"
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "signal score"):
            init_reviews(self.report_path, self.root / "new.json")
