"""Failure contracts use three copied NV records, never GPU or hardware."""
import copy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_saved_evidence as verifier

SOURCE = Path(__file__).resolve().parent


class SavedEvidenceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='saved-evidence-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder, _, expected, code, cycles = verifier.PACKS['nv']
        self.patch = patch.dict(verifier.PACKS, {'nv': (folder, 3, expected, code, cycles)}, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for name in verifier.required_files():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'{}')
        pack = self.root / folder
        for name, size in (('inputs_i16.bin', 256), (expected, 2), ('expected_scores_u64.bin', 8)):
            (pack / name).write_bytes((SOURCE / folder / name).read_bytes()[:3 * size])
        self.folder = self.root / 'evidence/board/boot-1'
        self.report_path = self.folder / 'nv-r1.json'
        self.csv_path = self.folder / 'nv-r1.csv.gz'
        self.control_path = self.folder / 'control-fabric.json'
        self.control = verifier.read_json(SOURCE / 'evidence/board/boot-1/control-fabric.json')
        self.control_path.write_text(json.dumps(self.control))
        self.report = verifier.read_json(SOURCE / 'evidence/board/boot-1/nv-r1.json')
        for key in ('validated_records', 'planned_calls', 'attempted_calls', 'completed_calls', 'latency_sample_count'):
            self.report[key] = 3
        self.report['host_call_ns'] = {'p50': 20, 'p99': 30, 'max': 30}
        self.report['host_total_ns'] = {'p50': 25, 'p99': 35, 'max': 35}
        self.report_path.write_text(json.dumps(self.report))
        with gzip.open(SOURCE / 'evidence/board/boot-1/nv-r1.csv.gz', 'rt', newline='') as stream:
            reader = csv.DictReader(stream)
            self.rows = [next(reader) for _ in range(3)]
        for i, row in enumerate(self.rows):
            row.update(completed_before=str(i + 4), completed_after=str(i + 5),
                       host_call_ns=str((i + 1) * 10), host_total_ns=str((i + 1) * 10 + 5))
        self.write_rows(self.rows)
        self.rehash()

    def write_rows(self, rows):
        with gzip.open(self.csv_path, 'wt', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=verifier.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def rehash(self):
        entries = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in self.root.rglob('*') if p.is_file() and p != self.root / 'evidence/manifest.json'}
        (self.root / 'evidence/manifest.json').write_text(json.dumps({
            'schema': 'cudaq_fpga_public_files_v1', 'files': entries}))

    def check_run(self):
        return verifier.check_run(self.root, 'boot-1', 'nv', 1, {'completed': 4})

    def test_valid_compact_copied_receipt(self):
        self.assertGreater(verifier.check_hashes(self.root), 0)
        self.assertEqual(self.check_run(), 3)
        state = {}
        self.assertEqual(verifier.check_control(self.folder, state), 15)
        self.assertEqual(state['completed'], 4)

    def test_both_original_control_receipts(self):
        for boot in ('boot-1', 'boot-2'):
            self.assertEqual(verifier.check_control(SOURCE / 'evidence/board' / boot), 15)

    def test_required_path_cannot_be_replaced_by_unrelated_entries(self):
        manifest_path = self.root / 'evidence/manifest.json'
        manifest = verifier.read_json(manifest_path)
        del manifest['files']['evidence/board/boot-1/nv-r1.csv.gz']
        for i in range(60):
            relative = f'extra-{i}.txt'
            (self.root / relative).write_text('unrelated')
            manifest['files'][relative] = hashlib.sha256(b'unrelated').hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Incomplete manifest'):
            verifier.check_hashes(self.root)

    def test_missing_file(self):
        self.csv_path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing evidence'):
            verifier.check_hashes(self.root)

    def test_corrupt_file(self):
        self.csv_path.write_bytes(self.csv_path.read_bytes() + b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Hash mismatch'):
            verifier.check_hashes(self.root)

    def test_rehashed_truncated_csv(self):
        self.write_rows(self.rows[:-1])
        self.rehash()
        verifier.check_hashes(self.root)
        with self.assertRaisesRegex(ValueError, 'truncated CSV'):
            self.check_run()

    def test_rehashed_invalid_rows(self):
        cases = [
            ('score_hex', '0x0000000077b5a924', 'score mismatch'),  # Preserve low 32 bits; lose high bits.
            ('result_hex', '0x000000000000002a', 'result mismatch'),
            ('completed_after', '8', 'counter delta'),
            ('completed_before', '99', 'counter delta'),
            ('record', '2', 'row order'),
            ('call', '1', 'row order'),
            ('repeat', '1', 'row order'),
            ('status', '18', 'bad completion'),
            ('error', '1', 'bad completion'),
            ('fabric_cycles', '23478', 'CSV cycles'),
            ('host_call_ns', '-1', 'invalid integer'),
            ('host_call_ns', '1.0', 'invalid integer'),
            ('host_call_ns', str(1 << 64), 'out of range'),
            ('host_total_ns', '1', 'host timing'),
        ]
        for key, value, message in cases:
            with self.subTest(key=key, value=value):
                rows = copy.deepcopy(self.rows)
                rows[0][key] = value
                self.write_rows(rows)
                self.rehash()
                verifier.check_hashes(self.root)
                with self.assertRaisesRegex(ValueError, message):
                    self.check_run()

    def test_rehashed_counter_discontinuity_with_valid_deltas(self):
        rows = copy.deepcopy(self.rows)
        rows[1].update(completed_before='90', completed_after='91')
        self.write_rows(rows)
        self.rehash()
        verifier.check_hashes(self.root)
        with self.assertRaisesRegex(ValueError, 'counter discontinuity'):
            self.check_run()

    def test_valid_counter_wrap(self):
        rows = copy.deepcopy(self.rows)
        for i, row in enumerate(rows):
            row.update(completed_before=str((0xffffffff + i) & 0xffffffff),
                       completed_after=str(i))
        self.write_rows(rows)
        self.assertEqual(verifier.check_run(self.root, 'boot-1', 'nv', 1,
                                           {'completed': 0xffffffff}), 3)

    def test_rehashed_wrong_summary_or_integer_type(self):
        for key, value in (('host_call_ns', {'p50': 19, 'p99': 30, 'max': 30}),
                           ('repeat', True), ('last_status', 2)):
            with self.subTest(key=key):
                report = copy.deepcopy(self.report)
                report[key] = value
                self.report_path.write_text(json.dumps(report))
                self.rehash()
                verifier.check_hashes(self.root)
                with self.assertRaises(ValueError):
                    self.check_run()

    def test_quantiles_match_integer_nearest_rank(self):
        self.assertEqual(verifier.timing_summary(list(range(1, 101))), {'p50': 50, 'p99': 99, 'max': 100})
        self.assertEqual(verifier.timing_summary(list(range(1, 102))), {'p50': 51, 'p99': 100, 'max': 101})
        self.assertEqual(verifier.timing_summary([9, 1, 3]), {'p50': 3, 'p99': 9, 'max': 9})

    def test_rehashed_control_failures_with_pass_flags_unchanged(self):
        cases = [('forced_qec_timeout', 'cycles', 2), ('active_nv_abort', 'status', 10),
                 ('idle_abort_preserves_registers', 'cycles', 38), ('clear_after_abort', 'status', 14),
                 ('qec_after_idle_abort', 'score', 1), ('exit_timeout_restoration', 'timeout', 1),
                 ('qec_after_timeout', 'count_after', 8), ('clear_final', 'hardware_snapshot', False)]
        for name, key, value in cases:
            with self.subTest(name=name, key=key):
                control = copy.deepcopy(self.control)
                next(c for c in control['checks'] if c['name'] == name)[key] = value
                self.control_path.write_text(json.dumps(control))
                self.rehash()
                verifier.check_hashes(self.root)
                with self.assertRaises(ValueError):
                    verifier.check_control(self.folder)

    def test_rehashed_reordered_control_checks(self):
        self.control['checks'][3:5] = reversed(self.control['checks'][3:5])
        self.control_path.write_text(json.dumps(self.control))
        self.rehash()
        verifier.check_hashes(self.root)
        with self.assertRaisesRegex(ValueError, 'unordered control'):
            verifier.check_control(self.folder)

    def test_rehashed_truncated_reference(self):
        relative, _, filename, _, _ = verifier.PACKS['nv']
        path = self.root / relative / filename
        path.write_bytes(path.read_bytes()[:-1])
        self.rehash()
        verifier.check_hashes(self.root)
        with self.assertRaisesRegex(ValueError, 'Bad reference length'):
            self.check_run()

    def test_manifest_rejects_parent_symlink(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'receipt').write_text('data')
        (self.root / 'alias').symlink_to(outside, target_is_directory=True)
        manifest_path = self.root / 'evidence/manifest.json'
        manifest = verifier.read_json(manifest_path)
        manifest['files']['alias/receipt'] = hashlib.sha256(b'data').hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Symlink evidence'):
            verifier.check_hashes(self.root)

    def test_duplicate_json_keys_rejected(self):
        self.report_path.write_text('{"repeat":1,"repeat":4}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            verifier.read_json(self.report_path)


if __name__ == '__main__':
    unittest.main()
