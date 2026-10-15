from contextlib import redirect_stdout, redirect_stderr
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workhorse.compare import compare
from workhorse.function_signals import analyze, functions, main
from workhorse.imports import load_manifest
from workhorse.report import render_html

SOURCE = '''def score(values):
    total = 0
    for index, value in enumerate(values):
        if value > 7:
            total += value * (index + 3)
        else:
            total -= value * 2
    return total
'''


class FunctionReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest=self.root/'manifest.json';self.report=self.root/'report.json'
        self.manifest.write_text(json.dumps([{'id':x,'author':x,'task':'q','language':'python','path':x+'.py'} for x in ('a','b')]))

    def prepare(self, source=SOURCE):
        for x in ('a','b'): (self.root/(x+'.py')).write_text(source)
        self.report.write_text(json.dumps(compare(load_manifest(self.manifest))))
        return analyze(self.manifest,self.report,include_report=True)

    def test_combined_report_has_source_excerpts_and_retains_category(self):
        evidence,report=self.prepare()
        html=render_html(report,function_evidence=evidence)
        self.assertIn('Function supporting evidence',html)
        self.assertIn('total += value * (index + 3)',html)
        self.assertIn('Original pair category retained',html)
        self.assertIn('External names: enumerate',html)
        self.assertIn('Review flag',html)

    def test_function_source_is_escaped_and_large_excerpt_labeled(self):
        source=SOURCE.replace('total = 0','message = "<script>alert(1)</script>"\n    total = 0')
        evidence,report=self.prepare(source)
        html=render_html(report,function_evidence=evidence)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)
        evidence,report=self.prepare(SOURCE.replace('total = 0','#'+'x'*7000+'\n    total = 0'))
        self.assertEqual(len(evidence['pairs'][0]['matches'][0]['left']['excerpt']),6000)
        self.assertIn('Function excerpt truncated',render_html(report,function_evidence=evidence))

    def test_changed_review_or_promoted_category_rejected(self):
        evidence,report=self.prepare()
        changed=copy.deepcopy(report);changed['submissions'][0]['author']='changed'
        with self.assertRaisesRegex(ValueError,'provenance'):
            render_html(changed,function_evidence=evidence)
        evidence['pairs'][0]['category']='broad_candidate'
        with self.assertRaisesRegex(ValueError,'category'):
            render_html(report,function_evidence=evidence)

    def test_declined_functions_are_visible_in_combined_report(self):
        evidence,report=self.prepare('@cache\n'+SOURCE)
        html=render_html(report,function_evidence=evidence)
        self.assertIn('contextual declarations',html)
        self.assertIn('No eligible exact function match',html)

    def test_report_snapshot_survives_file_replacement_during_analysis(self):
        self.prepare()
        raw=self.report.read_bytes()
        def replace_file(*args,**kwargs):
            self.report.write_bytes(b'replaced during analysis')
            return functions(*args,**kwargs)
        with patch('workhorse.function_signals.functions',side_effect=replace_file):
            evidence,report=analyze(self.manifest,self.report,include_report=True)
        self.assertEqual(evidence['report_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertIn('Function supporting evidence',render_html(report,function_evidence=evidence))

    def test_cli_writes_combined_html_and_preserves_original_report(self):
        self.prepare();raw=self.report.read_bytes()
        output=self.root/'functions.json';html=self.root/'combined.html'
        with redirect_stdout(io.StringIO()):
            main([str(self.manifest),str(self.report),'--output',str(output),'--html',str(html)])
        self.assertEqual(self.report.read_bytes(),raw)
        self.assertIn('Function supporting evidence',html.read_text())
        self.assertEqual(json.loads(output.read_text())['report_sha256'],hashlib.sha256(raw).hexdigest())

    def test_existing_html_blocks_both_outputs_before_write(self):
        self.prepare();html=self.root/'existing.html';html.write_text('preserve')
        output=self.root/'new.json'
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main([str(self.manifest),str(self.report),'--output',str(output),'--html',str(html)])
        self.assertFalse(output.exists())
        self.assertEqual(html.read_text(),'preserve')
