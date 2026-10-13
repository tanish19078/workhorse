from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from workhorse.cli import main
from workhorse.reviews import load_reviews


class CliTests(unittest.TestCase):
    def test_folder_to_review_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = "\n".join(f"value += {i}" for i in range(25))
            for author in ("one", "two"):
                folder = root / "task" / author
                folder.mkdir(parents=True)
                (folder / "solution.py").write_text(source, encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["index", str(root)]), 0)
                self.assertEqual(main(["validate", str(root / "manifest.json")]), 0)
                self.assertEqual(main(["review", str(root / "manifest.json"), "--output", str(root / "report")]), 0)
            report = json.loads((root / "report/report.json").read_text())
            self.assertEqual(report["summary"]["flagged_pairs"], 1)
            self.assertTrue((root / "report/report.html").is_file())
            with redirect_stdout(io.StringIO()):
                report_path = root / "report/report.json"
                workspace = root / "reviews.json"
                self.assertEqual(main(["review-init", str(report_path), "--output", str(workspace)]), 0)
                key = next(iter(load_reviews(workspace)["pairs"]))
                self.assertEqual(main(["review-note", str(workspace), key, "--status", "explained",
                                       "--reviewer", "example", "--note", "synthetic fixture"]), 0)
                self.assertEqual(main(["packet", str(report_path), str(workspace), "--pair", key,
                                       "--output", str(root / "packet.zip")]), 0)
            self.assertTrue((root / "packet.zip").is_file())

    def test_coverage_command(self):
        manifest = Path(__file__).resolve().parents[1] / "examples/demo/manifest.json"
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["coverage", str(manifest), "--task", "unimported"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(len(report["missing_cells"]), 3)

    def test_invalid_manifest_returns_error(self):
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(["validate", "/nonexistent-workhorse-test/manifest.json"]), 2)
            self.assertIn("workhorse:", error.getvalue())

    def test_index_preserves_existing_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "manifest.json"
            manifest.write_text("existing", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["index", str(root)]), 2)
            self.assertEqual(manifest.read_text(), "existing")
