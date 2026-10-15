import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workhorse.calibration import sweep, main
from workhorse.compare import compare
from workhorse.evaluation import evaluate

BENCHMARK = Path(__file__).resolve().parents[1]/'examples/benchmark/cases.json'


class CalibrationTests(unittest.TestCase):
    def test_holdout_sources_never_reach_comparison(self):
        cases=json.loads(BENCHMARK.read_text())['cases']
        development={c['task'] for c in cases if c['split']=='development'}
        scored=[]
        def record(submissions,*args,**kwargs):
            scored.extend(s.task for s in submissions)
            return compare(submissions,*args,**kwargs)
        with patch('workhorse.evaluation.compare',side_effect=record):
            result=sweep(BENCHMARK,[0.5,0.75])
        self.assertTrue(scored)
        self.assertLessEqual(set(scored),development)
        self.assertFalse(result['holdout_scored'])
        self.assertTrue(all(c['id']!='renamed-gcd' for r in result['rows'] for c in r['cases']))

    def test_default_threshold_matches_existing_development_metrics(self):
        row=sweep(BENCHMARK,[0.5])['rows'][0]
        expected=next(r for r in evaluate(BENCHMARK)['results'] if r['normalization']=='relationships' and r['split']=='development')
        self.assertEqual(row['strict_counts'],expected['counts'])
        self.assertEqual(row['retrieval_counts'],expected['retrieval_counts'])
        self.assertGreater(row['all_review_pairs'],row['strict_review_pairs'])

    def test_invalid_or_unbounded_grids_rejected(self):
        for thresholds in ([],[0.5,0.5],[float('nan')],[float('inf')],[-1],[1.01],list(range(21))):
            with self.assertRaises(ValueError):
                sweep(BENCHMARK,thresholds)

    def test_no_labeled_negative_cases_rejected(self):
        data=json.loads(BENCHMARK.read_text())
        data['cases']=[c for c in data['cases'] if c['label']=='shared_origin']
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cases.json';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'positive and negative'):
                sweep(path,[0.5])

    def test_cli_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.json';path.write_text('existing')
            with self.assertRaises(SystemExit):
                main([str(BENCHMARK),'--thresholds','0.5','--output',str(path)])
            self.assertEqual(path.read_text(),'existing')

    def test_all_thresholds_use_initial_bytes_when_file_changes(self):
        import hashlib
        from workhorse.evaluation import BenchmarkSnapshot
        original=BENCHMARK.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cases.json';path.write_bytes(original)
            calls=[]
            def change_after_first(snapshot,*args,**kwargs):
                self.assertIsInstance(snapshot,BenchmarkSnapshot)
                calls.append(snapshot)
                path.write_text('{"broken":true}')
                return evaluate(snapshot,*args,**kwargs)
            with patch('workhorse.calibration.evaluate',side_effect=change_after_first):
                result=sweep(path,[0.5,0.75])
            self.assertIs(calls[0],calls[1])
            self.assertEqual(result['benchmark_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(len(result['rows']),2)
