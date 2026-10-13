import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from workhorse.compare import compare
from workhorse.imports import Submission
from workhorse.packets import export_packet
from workhorse.reviews import init_reviews, load_reviews, record_review


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = "\n".join(f"value += {i}" for i in range(25))
        self.report = compare([Submission(i, i, "q", "python", i + ".py", source) for i in ("a", "b", "c")])
        self.report_path = self.root / "report.json"
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        self.workspace = self.root / "reviews.json"
        init_reviews(self.report_path, self.workspace)
        self.key = next(iter(load_reviews(self.workspace)["pairs"]))
        self.output = self.root / "packet.zip"

    def decide(self):
        record_review(self.workspace, self.key, "explained", "<script>template</script>", "reviewer",
                      "allowed shared template")

    def test_export_selects_pair_and_verifies_integrity(self):
        self.decide()
        self.assertEqual(export_packet(self.report_path, self.workspace, [self.key], self.output), 1)
        with zipfile.ZipFile(self.output) as archive:
            report = json.loads(archive.read("report.json"))
            self.assertEqual(len(report["findings"]), 1)
            self.assertEqual(len(report["submissions"]), 2)
            self.assertNotIn(b"<script>template</script>", archive.read("report.html"))
            for line in archive.read("SHA256SUMS").decode().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)

    def test_unreviewed_pair_cannot_be_exported(self):
        with self.assertRaisesRegex(ValueError, "record an explanation"):
            export_packet(self.report_path, self.workspace, [self.key], self.output)

    def test_stale_sources_rejected(self):
        self.decide()
        self.report["submissions"][0]["sha256"] = "0" * 64
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale"):
            export_packet(self.report_path, self.workspace, [self.key], self.output)

    def test_existing_packet_not_overwritten(self):
        self.decide()
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            export_packet(self.report_path, self.workspace, [self.key], self.output)
        self.assertEqual(self.output.read_bytes(), b"existing")
