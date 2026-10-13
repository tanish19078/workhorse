import json
import subprocess
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workhorse.moss import prepare, command, import_index, main

URL = 'http://moss.stanford.edu/results/1/2/'
HEADER = '<table><tr><th>File 1</th><th>File 2</th><th>Lines Matched</th></tr>'
ROW = '<tr><td><a href="match0.html">s000001.py (90%)</a></td><td><a href="match0.html">s000002.py (70%)</a></td><td>12</td></tr></table>'


class MossTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'a.py').write_text('print(1)\n')
        (self.root / 'b.py').write_text('print(2)\n')
        self.rows = [{'id': x, 'author': x, 'task': 'q', 'language': 'python', 'path': x + '.py'} for x in ('a', 'b')]
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps(self.rows))
        self.output = self.root / 'stage'
        self.plan = self.output / 'plan.json'
        self.html = self.root / 'index.html'
        self.html.write_text(HEADER + ROW)

    def stage(self):
        return prepare(self.manifest, self.output)

    def test_local_staging_neutral_names_and_no_overwrite(self):
        plan = self.stage()
        self.assertEqual(plan['groups'][0]['files'][0]['file'], 's000001.py')
        self.assertEqual((self.output/'g0001/s000001.py').read_text(), 'print(1)\n')
        with self.assertRaises(FileExistsError):
            self.stage()

    def test_dry_run_does_not_invoke_client(self):
        self.stage()
        client = self.root / 'moss.pl'
        client.write_text('# user-supplied client\n')
        with patch('workhorse.moss.subprocess.run') as run, redirect_stdout(io.StringIO()):
            main(['submit', str(self.plan), '--group', 'g0001', '--client', str(client)])
            run.assert_not_called()

    def test_sources_must_match_staged_hashes(self):
        self.stage()
        (self.output/'g0001/s000001.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            import_index(self.plan, 'g0001', self.html, URL)

    def test_import_keeps_percentages_and_provenance(self):
        self.stage()
        pair = import_index(self.plan, 'g0001', self.html, URL)['pairs'][0]
        self.assertEqual((pair['left'], pair['right']), ('a', 'b'))
        self.assertEqual((pair['left_percent'], pair['right_percent'], pair['matched_lines']), (90,70,12))
        self.assertEqual(len(pair['left_sha256']),64)
        self.assertEqual(pair['category'], 'external_moss_signal')

    def test_unknown_file_bad_percentage_and_external_link_rejected(self):
        self.stage()
        for row in (ROW.replace('s000001','s000999'), ROW.replace('90%','190%'),
                    ROW.replace('match0.html','https://example.com/results/match0.html')):
            self.html.write_text(HEADER+row)
            with self.assertRaises(ValueError):
                import_index(self.plan, 'g0001', self.html, URL)

    def test_duplicate_pair_and_unrecognized_page_rejected(self):
        self.stage()
        for text in (HEADER+ROW+ROW, '<html>Login required</html>'):
            self.html.write_text(text)
            with self.assertRaises(ValueError):
                import_index(self.plan, 'g0001', self.html, URL)

    def test_same_author_excluded_but_not_silently_counted_independent(self):
        self.rows[1]['author'] = 'a'
        self.manifest.write_text(json.dumps(self.rows))
        self.stage()
        report = import_index(self.plan, 'g0001', self.html, URL)
        self.assertFalse(report['pairs'])
        self.assertEqual(report['same_author_excluded'],1)
        client=self.root/'moss.pl'; client.write_text('# client')
        with self.assertRaisesRegex(ValueError, 'authors'):
            command(self.plan,'g0001',client)

    def test_task_specific_and_global_baseline_and_cpp_language(self):
        (self.root/'a.cpp').write_text('int main() {}')
        (self.root/'b.cpp').write_text('int main() {}')
        self.rows += [{'id': x+'cpp', 'author': x, 'task':'r', 'language':'cpp', 'path':x+'.cpp'} for x in ('a','b')]
        self.manifest.write_text(json.dumps(self.rows))
        baselines=self.root/'bases.json'
        baselines.write_text(json.dumps([{'id':'base','author':'instructor','task':'q','language':'python','path':'a.py'}]))
        plan=prepare(self.manifest,self.output,baselines)
        self.assertEqual([len(g['baselines']) for g in plan['groups']],[1,0])
        client=self.root/'moss.pl'; client.write_text('# client')
        argv,folder=command(self.plan,'g0002',client)
        self.assertEqual(argv[2:4],['-l','cc'])
        self.assertEqual(folder.name,'g0002')

    def test_symlink_escape_rejected(self):
        self.stage()
        staged=self.output/'g0001/s000001.py'
        staged.unlink(); staged.symlink_to(self.root/'a.py')
        with self.assertRaisesRegex(ValueError,'escaped'):
            import_index(self.plan,'g0001',self.html,URL)

    def test_empty_valid_index_is_explicit_empty_result(self):
        self.stage(); self.html.write_text(HEADER+'</table>')
        self.assertEqual(import_index(self.plan,'g0001',self.html,URL)['pairs'],[])

    def test_explicit_execution_records_receipt_and_never_uses_shell(self):
        self.stage()
        client=self.root/'moss.pl'; client.write_text('# user client')
        args=['submit',str(self.plan),'--group','g0001','--client',str(client),'--execute']
        with patch('workhorse.moss.subprocess.run',return_value=subprocess.CompletedProcess([],0,URL)) as run, redirect_stdout(io.StringIO()):
            main(args)
            self.assertEqual(run.call_count,1)
            self.assertNotIn('shell',run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs['timeout'],120)
            receipt=json.loads((self.output/'g0001/submission.json').read_text())
            self.assertEqual(receipt['result_url'],URL)
            with self.assertRaises(SystemExit):
                main(args)
            self.assertEqual(run.call_count,1)

    def test_failed_execution_has_no_automatic_retry_or_success_receipt(self):
        self.stage()
        client=self.root/'moss.pl'; client.write_text('# user client')
        with patch('workhorse.moss.subprocess.run',side_effect=subprocess.TimeoutExpired('perl',120)) as run, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(['submit',str(self.plan),'--group','g0001','--client',str(client),'--execute'])
            self.assertEqual(run.call_count,1)
            self.assertFalse((self.output/'g0001/submission.json').exists())

    def test_optional_html_cell_and_row_closing_tags_are_supported(self):
        self.stage()
        self.html.write_text((HEADER+ROW).replace('</td>','').replace('</tr>',''))
        self.assertEqual(len(import_index(self.plan,'g0001',self.html,URL)['pairs']),1)
