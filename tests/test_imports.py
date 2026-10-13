import json
from pathlib import Path
import tempfile
import unittest

from workhorse.imports import load_manifest


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "one.py").write_text("print(1)\n", encoding="utf-8")
        self.row = dict(id="s1", author="a", task="q", language="py", path="one.py")

    def manifest(self, rows):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        return path

    def test_load_and_normalize_language(self):
        item = load_manifest(self.manifest([self.row]))[0]
        self.assertEqual(item.language, "python")
        self.assertEqual(item.source, "print(1)\n")
        self.assertNotIn("source", item.metadata())

    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_manifest(self.manifest([self.row, self.row]))

    def test_absolute_paths_rejected(self):
        with self.assertRaisesRegex(ValueError, "relative"):
            load_manifest(self.manifest([{**self.row, "path": str(self.root / "one.py")}]))

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "secret.py"
            target.write_text("secret", encoding="utf-8")
            (self.root / "escape.py").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "beneath"):
                load_manifest(self.manifest([{**self.row, "path": "escape.py"}]))

    def test_script_url_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTP"):
            load_manifest(self.manifest([{**self.row, "url": "javascript:alert(1)"}]))

    def test_csv_supported(self):
        path = self.root / "manifest.csv"
        path.write_text("id,author,task,language,path\ns1,a,q,python,one.py\n", encoding="utf-8")
        self.assertEqual(load_manifest(path)[0].id, "s1")

    def test_empty_source_rejected(self):
        (self.root / "one.py").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty source"):
            load_manifest(self.manifest([self.row]))

    def test_html_export_rejected(self):
        (self.root / "one.py").write_text('<!DOCTYPE html><html>Performing security verification</html>', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "instead of source"):
            load_manifest(self.manifest([self.row]))

    def test_oversized_source_rejected(self):
        (self.root / "one.py").write_bytes(b"x" * 1_048_577)
        with self.assertRaisesRegex(ValueError, "exceeds 1 MiB"):
            load_manifest(self.manifest([self.row]))
