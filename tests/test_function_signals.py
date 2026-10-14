import json
from pathlib import Path
import tempfile
import unittest

from workhorse.compare import compare
from workhorse.function_signals import analyze, functions
from workhorse.imports import load_manifest

SOURCE = '''def score(values):
    total = 0
    for index, value in enumerate(values):
        if value > 7:
            total += value * (index + 3)
        else:
            total -= value * 2
    return total
'''


class FunctionSignalTests(unittest.TestCase):
    def test_helper_insertion_and_renaming_keep_exact_function_evidence(self):
        renamed=SOURCE.replace('score','measure').replace('values','items').replace('total','answer').replace('index','position').replace('value','entry')
        a,_=functions(SOURCE)
        b,_=functions('def helper(x):\n    return x + 1\n\n'+renamed)
        self.assertEqual(a[0]['tokens'],b[0]['tokens'])
        self.assertEqual(b[0]['start_line'],4)

    def test_changed_variable_relationship_is_not_equal(self):
        a,_=functions(SOURCE)
        b,_=functions(SOURCE.replace('value * (index + 3)','index * (value + 3)'))
        self.assertNotEqual(a[0]['tokens'],b[0]['tokens'])

    def test_contextual_functions_are_declined(self):
        for source in ('@cache\n'+SOURCE, SOURCE.replace('values):','values=shared):',1),
                       SOURCE.replace('total = 0','global total\n    total = 0'),
                       SOURCE.replace('values):','values: list):',1)):
            accepted,declined=functions(source)
            self.assertFalse(accepted)
            self.assertEqual(len(declined),1)

    def test_function_evidence_provenance_categories_and_allowed_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'a.py').write_text(SOURCE)
            (root/'b.py').write_text('def helper(x):\n    return x+1\n\n'+SOURCE)
            manifest=root/'manifest.json'
            rows=[{'id':x,'author':x,'task':'q','language':'python','path':x+'.py'} for x in ('a','b')]
            manifest.write_text(json.dumps(rows))
            report=root/'report.json'
            original=compare(load_manifest(manifest))
            report.write_text(json.dumps(original))
            result=analyze(manifest,report)
            self.assertEqual(len(result['pairs']),1)
            category=(original['findings']+original['additional_candidates'])[0]['category']
            self.assertEqual(result['pairs'][0]['category'],category)
            baseline=root/'base.json'
            baseline.write_text(json.dumps([{**rows[0],'id':'base','author':'instructor'}]))
            self.assertFalse(analyze(manifest,report,baseline)['pairs'])
            (root/'a.py').write_text(SOURCE+'# change\n')
            with self.assertRaisesRegex(ValueError,'provenance'):
                analyze(manifest,report)

    def test_external_api_names_and_short_functions_remain_distinct(self):
        a,_=functions(SOURCE.replace('enumerate','custom_api'))
        b,_=functions(SOURCE.replace('enumerate','other_api'))
        self.assertNotEqual(a[0]['tokens'],b[0]['tokens'])
        self.assertIn('custom_api',a[0]['external_names'])
        self.assertFalse(functions('def tiny(x):\n    return x\n')[0])

    def test_duplicate_match_count_does_not_materialize_cartesian_product(self):
        from unittest.mock import patch
        import tracemalloc
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('a','b'):
                (root/(name+'.py')).write_text(SOURCE)
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps([{'id':x,'author':x,'task':'q','language':'python','path':x+'.py'} for x in ('a','b')]))
            report=root/'report.json';report.write_text(json.dumps(compare(load_manifest(manifest))))
            fragment=functions(SOURCE)[0][0]
            with patch('workhorse.function_signals.functions',return_value=([fragment]*400,[])):
                tracemalloc.start()
                try:
                    result=analyze(manifest,report)
                    _,peak=tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
            self.assertEqual(result['pairs'][0]['total_matches'],160000)
            self.assertEqual(len(result['pairs'][0]['matches']),5)
            # Report loading itself reserves a bounded 50 MiB read buffer.
            self.assertLess(peak,80*1024*1024)
