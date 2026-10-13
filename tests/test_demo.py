from pathlib import Path
import unittest

from workhorse.compare import compare
from workhorse.imports import load_manifest


class DemoTests(unittest.TestCase):
    def test_only_renamed_pair_flagged(self):
        path = Path(__file__).resolve().parents[1] / "examples/demo/manifest.json"
        findings = compare(load_manifest(path))["findings"]
        self.assertEqual([(f["left"], f["right"]) for f in findings], [("sample-001", "sample-002")])
