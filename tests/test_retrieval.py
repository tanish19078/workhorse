import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from workhorse.compare import Options, compare
from workhorse.imports import Submission
from workhorse.packets import export_packet
from workhorse.report import render_html
from workhorse.reviews import init_reviews, load_report, load_reviews, record_review


def edited_pair():
    benchmark = json.loads((Path(__file__).resolve().parents[1] / "examples/benchmark/cases.json").read_text())
    case = next(c for c in benchmark["cases"] if c["id"] == "different-dataflow")
    return [Submission(side, side, "q", "python", side, case[side]) for side in ("left", "right")]


class RetrievalTests(unittest.TestCase):
    def test_edited_copy_retained_without_promoting_to_flag(self):
        report = compare(edited_pair())
        self.assertFalse(report["findings"])
        self.assertEqual(len(report["additional_candidates"]), 1)
        self.assertEqual(report["summary"]["flagged_pairs"], 0)
        finding = report["additional_candidates"][0]
        self.assertEqual(finding["category"], "broad_candidate")
        self.assertEqual(finding["evidence_normalization"], "legacy")
        self.assertIn("Broad retrieval only", finding["cautions"][0])
        self.assertIn("not a review flag", render_html(report))

    def test_broad_pass_can_be_disabled(self):
        self.assertFalse(compare(edited_pair(), Options(broad_retrieval=False))["additional_candidates"])

    def test_declined_python_scope_still_has_visible_retrieval(self):
        a = "f, g = lambda x: x + 1, lambda y: y * 7\n" + "\n".join(f"value += {i}" for i in range(20))
        items = [Submission(side, side, "q", "python", side, a) for side in ("a", "b")]
        report = compare(items)
        self.assertEqual(report["groups"][0]["declined_sources"], 2)
        self.assertEqual(report["submissions"][0]["analysis_status"], "declined")
        self.assertTrue(report["additional_candidates"])
        self.assertIn("Declined analyses", render_html(report))

    def test_shared_total_budget_applies_to_both_passes(self):
        items = edited_pair()
        with self.assertRaisesRegex(ValueError, "budget|limit"):
            compare(items, Options(max_candidates=1))

    def test_broad_packet_keeps_category_and_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report_path = root / "report.json"
            report_path.write_text(json.dumps(compare(edited_pair())))
            workspace = root / "reviews.json"
            init_reviews(report_path, workspace)
            key = next(iter(load_reviews(workspace)["pairs"]))
            record_review(workspace, key, "investigate", "Inspect changed variable references", "synthetic reviewer")
            output = root / "packet.zip"
            export_packet(report_path, workspace, [key], output)
            with zipfile.ZipFile(output) as archive:
                packet = json.loads(archive.read("report.json"))
                self.assertFalse(packet["findings"])
                self.assertEqual(packet["summary"]["additional_candidates"], 1)
                self.assertEqual(packet["additional_candidates"][0]["category"], "broad_candidate")
                (root / "packet-report.json").write_text(json.dumps(packet))
                load_report(root / "packet-report.json")

    def test_category_cannot_be_falsified_on_import(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            report = compare(edited_pair())
            report["additional_candidates"][0]["category"] = "review_flag"
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "explicit broad"):
                load_report(path)

    def test_independent_factorial_is_not_promoted_to_strict_flag(self):
        path = Path(__file__).resolve().parents[1] / "examples/benchmark/cases.json"
        case = next(c for c in json.loads(path.read_text())["cases"] if c["id"] == "independent-factorial")
        items = [Submission(side, side, case["task"], case["language"], side, case[side]) for side in ("left", "right")]
        report = compare(items)
        self.assertFalse(report["findings"])
        self.assertEqual(len(report["additional_candidates"]), 1)

    def test_older_report_without_candidate_fields_still_loads(self):
        source = "\n".join(f"value += {i}" for i in range(20))
        report = compare([Submission(side, side, "q", "python", side, source) for side in ("a", "b")])
        report.pop("additional_candidates")
        report.pop("retrieval_groups")
        report["summary"].pop("additional_candidates")
        report["summary"].pop("broad_candidate_pairs")
        for finding in report["findings"]:
            finding.pop("category")
            finding.pop("evidence_normalization")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.json"
            path.write_text(json.dumps(report))
            self.assertEqual(len(load_report(path)["findings"]), 1)
