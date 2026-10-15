import io
import json
from pathlib import Path
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from workhorse.io_utils import read_bounded
from workhorse.reviews import read_json


class BoundedReadTests(unittest.TestCase):
    def test_small_report_does_not_allocate_the_full_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'report.json';path.write_text(json.dumps({'schema_version':1}))
            tracemalloc.start()
            try:
                self.assertEqual(read_json(path)['schema_version'],1)
                _,peak=tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertLess(peak,1024*1024)

    def test_exact_limit_and_over_limit_across_chunks(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input';raw=b'x'*70000;path.write_bytes(raw)
            self.assertEqual(read_bounded(path,70000,'too large'),raw)
            with self.assertRaisesRegex(ValueError,'too large'):
                read_bounded(path,69999,'too large')

    def test_enforces_limit_from_stream_without_trusting_stat(self):
        with patch.object(Path,'open',return_value=io.BytesIO(b'x'*100)):
            with self.assertRaisesRegex(ValueError,'too large'):
                read_bounded(Path('growing'),50,'too large')
