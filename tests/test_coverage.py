import unittest

from workhorse.coverage import coverage
from workhorse.imports import Submission


class CoverageTests(unittest.TestCase):
    def test_expected_gaps_not_confused_with_no_platform_submission(self):
        source = Submission("s1", "a", "q1", "python", "s1.py", "print(1)")
        result = coverage([source], tasks=["q1", "q2"], authors=["a", "b"])
        self.assertEqual(len(result["missing_cells"]), 3)
        self.assertEqual(result["cells"][0]["timestamps_missing"], 1)
        self.assertIn("do not prove", result["interpretation"])

    def test_duplicates_and_unexpected_records_reported(self):
        items = [Submission(i, i, "q", "python", i + ".py", "print(1)") for i in ("a", "b")]
        result = coverage(items, authors=["a"])
        self.assertEqual(result["duplicate_source_groups"], [["a", "b"]])
        self.assertEqual(result["unexpected_ids"], ["b"])
