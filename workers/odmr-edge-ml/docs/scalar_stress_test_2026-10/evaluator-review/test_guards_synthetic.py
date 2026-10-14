#!/usr/bin/env python3
"""Synthetic guard checks. Never imports the evaluator or loads scientific data."""
import ast
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / 'evaluate_stress.py'
EXPECTED = 'db0922faff51bcaea18bb40300773e3adeae73cab32c2462c9430c35b8fa3c6a'
source_bytes = SOURCE.read_bytes()
source_hash = hashlib.sha256(source_bytes).hexdigest()
assert source_hash == EXPECTED, 'Evaluator changed after review'
tree = ast.parse(source_bytes)
names = {'sha', 'source_paths', 'bound_paths', 'verify_frozen_sources', 'verify_partition', 'candidates'}
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
assert {n.name for n in functions} == names
results = []
def check(name, fn):
    fn()
    results.append({'test': name, 'status': 'passed'})
def refusal(fn, message):
    try:
        fn()
    except RuntimeError as error:
        assert str(error) == message, (str(error), message)
        return
    raise AssertionError('Expected refusal: ' + message)

with tempfile.TemporaryDirectory(prefix='scalar-guard-') as tmp:
    root = Path(tmp)
    fake_evaluator = root / 'evaluator.py'
    fake_evaluator.write_bytes(source_bytes)
    ns = {'Path': Path, 'hashlib': hashlib, 'json': json, '__file__': str(fake_evaluator),
          'ARMS': ('B_full_residual', 'C_direct'), 'SEEDS': (42, 20261014, 20261015)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), ns)
    a = SimpleNamespace(**{name: root / name for name in
        ('work', 'repo', 'experiment', 'calibration', 'data', 'protocol', 'freeze')})
    for name in ('work', 'repo', 'experiment', 'calibration', 'data'):
        getattr(a, name).mkdir()
    for p in ns['source_paths'](a):
        p.parent.mkdir(parents=True, exist_ok=True)
        if p != fake_evaluator:
            p.write_text('synthetic source fixture\n')
    frozen = {'bound_paths': ns['bound_paths'](a),
              'source_hashes': {str(p): ns['sha'](p) for p in ns['source_paths'](a)}}
    check('unchanged_paths_and_sources_accepted', lambda: ns['verify_frozen_sources'](a, frozen))
    def changed_path():
        altered = copy.copy(a)
        altered.work = root / 'different-work'
        refusal(lambda: ns['verify_frozen_sources'](altered, frozen),
                'CLI paths differ from frozen paths')
    check('changed_work_path_refused', changed_path)
    def changed_source():
        p = a.work / 's2b/prior_aware_scalar.py'
        original = p.read_bytes()
        p.write_bytes(original + b'# altered\n')
        try:
            refusal(lambda: ns['verify_frozen_sources'](a, frozen),
                    'Frozen imported source set or hash changed')
        finally:
            p.write_bytes(original)
    check('changed_imported_source_refused', changed_source)
    def changed_source_set():
        altered = copy.deepcopy(frozen)
        altered['source_hashes'].pop(str(a.work / 's2b/prior_aware_scalar.py'))
        refusal(lambda: ns['verify_frozen_sources'](a, altered),
                'Frozen imported source set or hash changed')
    check('changed_imported_source_set_refused', changed_source_set)
    def existing_receipt():
        p = a.work / 'FINAL_ACCESS.json'
        p.write_text('{"status":"in_progress"}')
        try:
            refusal(lambda: ns['verify_frozen_sources'](a, frozen),
                    'Final partition already consumed')
        finally:
            p.unlink()
    check('existing_final_receipt_refused', existing_receipt)
    partition = root / 'synthetic_partition'
    partition.mkdir()
    payload = partition / 'fake.npz'
    payload.write_bytes(b'SYNTHETIC NON-NPZ BYTES; never decoded')
    manifest = partition / 'manifest.json'
    manifest.write_text(json.dumps({'single_orientation': True,
        'cells': {'synthetic': {'file': payload.name, 'sha256': ns['sha'](payload)}}}))
    expected_manifest = ns['sha'](manifest)
    payload.chmod(0o444)
    manifest.chmod(0o444)
    partition.chmod(0o555)
    original_sha = ns['sha']
    def metadata_only():
        calls = []
        def recording_sha(path):
            path = Path(path)
            calls.append(path.name)
            if path.suffix == '.npz':
                raise AssertionError('Metadata-only path read an NPZ payload')
            return original_sha(path)
        ns['sha'] = recording_sha
        try:
            ns['verify_partition'](partition, expected_manifest, check_payload=False)
        finally:
            ns['sha'] = original_sha
        assert calls == ['manifest.json'], calls
        results.append({'evidence': 'metadata_only_hash_calls', 'paths': calls})
    try:
        check('metadata_only_verification_never_hashes_npz', metadata_only)
        def payload_check():
            calls = []
            def recording_sha(path):
                calls.append(Path(path).name)
                return original_sha(path)
            ns['sha'] = recording_sha
            try:
                ns['verify_partition'](partition, expected_manifest, check_payload=True)
            finally:
                ns['sha'] = original_sha
            assert 'fake.npz' in calls, calls
        check('payload_verification_hashes_npz_when_enabled', payload_check)
    finally:
        partition.chmod(0o755)
        payload.chmod(0o644)
        manifest.chmod(0o644)

    # Synthetic checkpoint/export fixtures exercise identity checks as byte hashes only.
    choices, exports, repairs = [], [], {'models': {}}
    (a.experiment / 'run-1').mkdir()
    (a.experiment / 'evaluation').mkdir()
    (a.calibration / 'run-1').mkdir()
    for arm in ns['ARMS']:
        for seed in ns['SEEDS']:
            name = f'{arm}_seed{seed}'
            cp = root / (name + '.pt')
            cp.write_bytes(b'NOT A REAL CHECKPOINT')
            choices.append({'arm': arm, 'seed': seed, 'checkpoint': str(cp),
                            'checkpoint_sha256': ns['sha'](cp)})
            export = a.experiment / 'evaluation' / (name + '.tflite')
            export.write_bytes(('NOT A MODEL: ' + name).encode())
            exports.append({'name': name, 'sha256': ns['sha'](export)})
            if arm == 'B_full_residual':
                repairs['models'][name] = {'new_export': str(export),
                                          'new_export_sha256': ns['sha'](export)}
    (a.experiment / 'run-1/FROZEN_CHOICES.json').write_text(json.dumps({'choices': choices}))
    (a.experiment / 'evaluation/exports.json').write_text(json.dumps(exports))
    (a.calibration / 'run-1/results.json').write_text(json.dumps(repairs))
    def accepted_candidates():
        assert len(ns['candidates'](a)) == 6
    check('synthetic_original_candidate_hashes_accepted', accepted_candidates)
    def altered_direct_export():
        p = a.experiment / 'evaluation/C_direct_seed42.tflite'
        p.write_bytes(b'REPLACED SYNTHETIC EXPORT')
        refusal(lambda: ns['candidates'](a), 'Original direct export hash changed')
    check('changed_direct_export_refused', altered_direct_export)

    # Execute only the exact scalar guard statement extracted from run(); no model load.
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    sigma_guard = next(n for n in ast.walk(run) if isinstance(n, ast.If)
                       and isinstance(n.body[0], ast.Raise)
                       and 'Sigma below FP32 preprocessing clamp' in ast.unparse(n))
    sigma_code = compile(ast.Module(body=[sigma_guard], type_ignores=[]), str(SOURCE), 'exec')
    def sigma_low():
        refusal(lambda: exec(sigma_code, {'ckpt': {'state_dict': {'sigma': 0.09}}}),
                'Sigma below FP32 preprocessing clamp')
    check('sigma_below_fp32_clamp_refused', sigma_low)
    check('sigma_at_fp32_clamp_accepted',
          lambda: exec(sigma_code, {'ckpt': {'state_dict': {'sigma': 0.1}}}))
    # Verify the repaired guards are called before any imports or payload verification.
    run_calls = [n for n in ast.walk(run) if isinstance(n, ast.Call)]
    guard_line = next(n.lineno for n in run_calls if isinstance(n.func, ast.Name)
                      and n.func.id == 'verify_frozen_sources')
    first_module_line = min(n.lineno for n in run_calls if isinstance(n.func, ast.Name)
                            and n.func.id == 'module')
    payload_line = next(n.lineno for n in run_calls if isinstance(n.func, ast.Name)
                        and n.func.id == 'verify_partition'
                        and any(k.arg == 'check_payload' and isinstance(k.value, ast.Constant)
                                and k.value.value is True for k in n.keywords))
    receipt_line = next(n.lineno for n in run_calls if isinstance(n.func, ast.Attribute)
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == 'access'
                        and n.func.attr == 'open')
    def guard_order():
        assert guard_line < first_module_line
        assert receipt_line < payload_line
    check('guard_and_receipt_precede_import_and_payload_paths', guard_order)

evidence = {'evaluator_sha256': source_hash, 'passed': sum(r.get('status') == 'passed' for r in results),
    'results': results, 'method': 'AST-extracted actual guard functions with temporary synthetic byte fixtures',
    'real_datasets_opened': False, 'real_checkpoints_loaded': False, 'models_scored': False,
    'evaluator_edited': False}
(BASE / 'guard-test-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
review = {'evaluator_sha256': source_hash, 'date': '2026-10-14',
    'status': 'previous material review findings resolved in inspected revision',
    'tests_passed': evidence['passed'], 'evidence': 'guard-test-evidence.json',
    'resolved': [
        {'id': 'R1', 'lines': [87,122,147,149], 'fix': 'Metadata-only preflight; exclusive receipt precedes first payload hash.'},
        {'id': 'R2', 'lines': [60,69,90,120,235,236], 'fix': 'Resolved CLI roots are frozen; actual source map and existing receipt are checked before imports.'},
        {'id': 'R3', 'lines': [33,45,46], 'fix': 'Direct export hash is checked against original exports receipt.'},
        {'id': 'R4', 'lines': [138], 'fix': 'Checkpoint sigma below FP32 minimum is rejected before data access.'}],
    'limits': ['No end-to-end model/data evaluation.', 'Synthetic candidate receipts cannot establish real artifact provenance.',
               'Sigma guard rejects values below 0.1; it does not explicitly reject NaN. No real checkpoint values were inspected.']}
(BASE / 'review-updated.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps(evidence, indent=2))
