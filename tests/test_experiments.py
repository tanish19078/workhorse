from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from workhorse.cli import main
from workhorse.compare import Options, compare
from workhorse.experiments import compare_configs
from workhorse.imports import load_manifest


DEMO = Path(__file__).resolve().parents[1] / "examples/demo"


class ConfigurationComparisonTests(unittest.TestCase):
    def test_real_runs_share_provenance_and_keep_unknown_accuracy(self):
        result = compare_configs(DEMO / "manifest.json")
        self.assertEqual(result["possible_cross_author_pairs"], 3)
        self.assertIsNone(result["accuracy"]["false_positive_rate"])
        self.assertIsNone(result["accuracy"]["precision"])
        self.assertIsNone(result["accuracy"]["recall"])
        self.assertEqual(len(result["input_sha256"]), 64)
        self.assertEqual(result, compare_configs(DEMO / "manifest.json"))
        self.assertEqual(result["runs"]["current"]["summary"]["flagged_pairs"], 1)
        self.assertNotIn("excerpt", json.dumps(result))
        self.assertFalse(result["runs"]["no_corpus_filter"]["options"]["corpus_filter"])
        self.assertEqual(result["runs"]["legacy_no_corpus_filter"]["options"]["normalization"], "legacy")

    def test_file_mutations_cannot_change_later_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "export"
            shutil.copytree(DEMO, root)
            original = load_manifest(root / "manifest.json")
            captured = []

            def mutate_after_first(submissions, options, baselines):
                captured.append(tuple(item.source for item in submissions))
                (root / "amber.py").write_text("changed = True\n")
                return compare(submissions, options, baselines)

            with patch("workhorse.experiments.compare", side_effect=mutate_after_first):
                result = compare_configs(root / "manifest.json", baseline=root / "manifest.json")
            self.assertEqual(captured, [tuple(s.source for s in original)] * 3)
            self.assertEqual(result["submissions"], result["baseline_submissions"])
            self.assertNotEqual(result["input_sha256"], compare_configs(root / "manifest.json")["input_sha256"])

    def test_pair_orientation_and_category_transitions(self):
        def report(submissions, options, baselines):
            base = compare(submissions, options, baselines)
            flag = dict(left="sample-001", right="sample-002", task="window-score", language="python",
                        category="review_flag", containment=.8, shared_fingerprints=4)
            lead = {**flag, "left": "sample-002", "right": "sample-001", "category": "broad_candidate"}
            if options.corpus_filter:
                base.update(findings=[], additional_candidates=[lead])
            elif options.normalization == "legacy":
                base.update(findings=[], additional_candidates=[])
            else:
                base.update(findings=[flag], additional_candidates=[])
            return base

        with patch("workhorse.experiments.compare", side_effect=report):
            result = compare_configs(DEMO / "manifest.json")
        self.assertEqual(len(result["pairs"]), 1)
        states = result["pairs"][0]["outcomes"]
        self.assertEqual(states["legacy_no_corpus_filter"], {"category": "not_returned"})
        self.assertEqual(result["transitions_to_current"]["no_corpus_filter"],
                         [{"from": "review_flag", "to": "broad_candidate", "pairs": 1}])

    def test_pair_denominator_excludes_same_author_and_other_groups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = []
            for number, (author, task) in enumerate([("a", "one"), ("a", "one"), ("b", "one"),
                                                    ("c", "two")]):
                path = f"{number}.py"
                (root / path).write_text("print(1)\n")
                rows.append(dict(id=str(number), author=author, task=task, language="python", path=path))
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(rows))
            result = compare_configs(manifest)
            self.assertEqual(result["possible_cross_author_pairs"], 2)
            self.assertEqual(result["runs"]["current"]["groups"][0]["short_sources"], 3)

    def test_candidate_failure_leaves_no_success_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "experiment.json"
            with redirect_stderr(io.StringIO()), patch("workhorse.experiments.compare",
                                                       side_effect=ValueError("Candidate limit exceeded")):
                self.assertEqual(main(["compare-configs", str(DEMO / "manifest.json"),
                                       "--output", str(output)]), 2)
            self.assertFalse(output.exists())

    def test_cli_preserves_existing_output_and_supports_stdout(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["compare-configs", str(DEMO / "manifest.json")]), 0)
        self.assertEqual(json.loads(output.getvalue())["document_type"], "configuration_comparison")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["compare-configs", str(DEMO / "manifest.json"), "--output", str(path)]), 0)
            original = path.read_bytes()
            with redirect_stderr(io.StringIO()), patch("workhorse.cli.compare_configs") as run:
                self.assertEqual(main(["compare-configs", str(DEMO / "manifest.json"), "--output", str(path)]), 2)
                run.assert_not_called()
            self.assertEqual(path.read_bytes(), original)

    def test_invalid_settings_fail_before_loading_sources(self):
        for options in [replace(Options(), threshold=2), replace(Options(), normalization="legacy"),
                        replace(Options(), corpus_filter=False)]:
            with self.subTest(options=options), patch("workhorse.experiments.load_manifest") as read:
                with self.assertRaises(ValueError):
                    compare_configs(Path("missing.json"), options)
                read.assert_not_called()
