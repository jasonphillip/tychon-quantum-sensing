"""Bounded manifest validation tests using temporary saved-file fixtures."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from show_evidence import main


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='evidence-viewer-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'saved.json').write_text('{"count": 512}\n')
        self.manifest = {'files': {'saved.json': hashlib.sha256((self.root/'saved.json').read_bytes()).hexdigest()},
                         'facts': [{'label': 'Quantum probabilities', 'value': 512,
                                    'scope': 'Synthetic saved results; no live measurement.',
                                    'evidence': ['saved.json']}]}

    def invoke(self, manifest=None):
        (self.root/'manifest.json').write_text(json.dumps(self.manifest if manifest is None else manifest))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['--root', str(self.root), '--manifest', 'manifest.json'])
        return code, out.getvalue(), err.getvalue()

    def assert_rejected(self, result):
        code, out, err = result
        self.assertEqual(code, 1)
        self.assertEqual(out, '')  # No partial or unchecked facts are shown.
        self.assertIn('Evidence verification failed:', err)

    def test_valid_saved_evidence_prints_value_scope_and_limit(self):
        code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ''))
        self.assertIn('Quantum probabilities: 512', out)
        self.assertIn('Scope: Synthetic saved results', out)
        self.assertIn('No live hardware or performance checks', out)

    def test_missing_and_corrupt_bytes_fail_before_any_facts(self):
        (self.root/'saved.json').write_text('modified')
        self.assert_rejected(self.invoke())
        (self.root/'saved.json').unlink()
        self.assert_rejected(self.invoke())

    def test_path_escapes_and_symlink_escape_rejected(self):
        for name in ['../outside.json', '/etc/passwd', 'C:/outside.json', 'a\\outside.json']:
            with self.subTest(name=name):
                bad = {'files': {name: '0'*64}, 'facts': self.manifest['facts']}
                self.assert_rejected(self.invoke(bad))
        with tempfile.TemporaryDirectory(prefix='outside-evidence-') as outside:
            other = Path(outside)/'outside.json'
            other.write_text('outside')
            (self.root/'escaped.json').symlink_to(other)
            bad = {'files': {'escaped.json': hashlib.sha256(other.read_bytes()).hexdigest()},
                   'facts': [{'label':'Outside','value':1,'scope':'Saved','evidence':['escaped.json']}]}
            self.assert_rejected(self.invoke(bad))

    def test_unlisted_fact_evidence_rejected(self):
        self.manifest['facts'][0]['evidence'] = ['unlisted.json']
        self.assert_rejected(self.invoke())

    def test_empty_or_invalid_manifest_contracts_rejected(self):
        for bad in [[], {}, {'files': {}, 'facts': self.manifest['facts']},
                    {'files': self.manifest['files'], 'facts': []},
                    {'files': {'saved.json':'invalid'}, 'facts': self.manifest['facts']},
                    {'files': self.manifest['files'], 'facts':[{'label':'Count','value':1,'scope':'','evidence':['saved.json']}]},
                    {'files': self.manifest['files'], 'facts':[{'label':'Count','value':1,'scope':'Saved','evidence':[]}]}]:
            with self.subTest(bad=bad): self.assert_rejected(self.invoke(bad))

    def test_duplicate_keys_nonfinite_and_manifest_escape_rejected(self):
        for content in ['{"files":{},"files":{},"facts":[]}',
                        '{"files":{},"facts":[NaN]}']:
            (self.root/'manifest.json').write_text(content)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(['--root',str(self.root),'--manifest','manifest.json'])
            self.assert_rejected((code,out.getvalue(),err.getvalue()))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code=main(['--root',str(self.root),'--manifest','../manifest.json'])
        self.assert_rejected((code,out.getvalue(),err.getvalue()))


if __name__ == '__main__': unittest.main()
