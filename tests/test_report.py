import json
from pathlib import Path
import tempfile
import unittest

from workhorse.compare import compare
from workhorse.imports import Submission
from workhorse.report import render_html, write_reports


class ReportTests(unittest.TestCase):
    def report(self):
        source = 'text = "<script>alert(1)</script>"\n' + "\n".join(f"value += {i}" for i in range(20))
        return compare([Submission("a", "<img onerror=x>", "sample", "python", "a.py", source),
                        Submission("b", "second", "sample", "python", "b.py", source)])

    def test_imported_text_escaped(self):
        html = render_html(self.report())
        self.assertNotIn("<img onerror=x>", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_dangerous_link_not_rendered(self):
        report = self.report()
        report["submissions"][0]["url"] = "javascript:alert(1)"
        self.assertNotIn("javascript:", render_html(report))

    def test_overwrite_requires_force(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = self.report()
            write_reports(report, root)
            with self.assertRaisesRegex(ValueError, "already exist"):
                write_reports(report, root)
            write_reports(report, root, True)
            self.assertEqual(json.loads((root / "report.json").read_text())["schema_version"], 1)

    def test_empty_report_explains_no_findings(self):
        self.assertIn("No pairs met", render_html(compare([])))
