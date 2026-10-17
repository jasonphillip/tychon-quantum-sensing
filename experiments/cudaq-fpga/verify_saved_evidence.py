#!/usr/bin/env python3
"""Verify published FPGA replay bytes and arithmetic. No hardware, GPU, or training."""
import argparse
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path
import struct

PACKS = {
    'readout': ('readout/stress_v2/artifacts/frozen_v2/board_replay', 10240, 'expected_scores_i64.bin', 'Q', 85),
    'nv': ('nv/artifacts/stress_frozen_v2/board_vectors', 2061, 'expected_indices_u16.bin', 'H', 23479),
    'qec': ('qec/noisy_rounds/artifacts/frozen_v1/board_vectors', 4864, 'expected_corrections_u32.bin', 'I', 4),
}
COLUMNS = 'call,repeat,record,expected_hex,result_hex,expected_score_hex,score_hex,match,status,error,completed_before,completed_after,fabric_cycles,host_total_ns,host_call_ns'.split(',')
CONTROL_ORDER = ('identity_before_writes', 'initial_idle', 'clear_initial', 'timeout_one_readback',
    'forced_qec_timeout', 'restore_timeout_before_success', 'clear_after_timeout', 'qec_after_timeout',
    'clear_after_success', 'active_nv_abort', 'idle_abort_preserves_registers', 'clear_after_abort',
    'qec_after_idle_abort', 'clear_final', 'exit_timeout_restoration')
CONTROL_NAMES = set(CONTROL_ORDER)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def uint(value, bits=64):
    return type(value) is int and 0 <= value < (1 << bits)


def required_files():
    paths = {'evidence/SOURCE_MAP.json', 'evidence/summary.json', 'evidence/build/summary.json',
             'evidence/board/coldboot-state.json', 'evidence/board/post-program-v250.json',
             'evidence/board/coldboot-v250.json'}
    for boot in ('boot-1', 'boot-2'):
        prefix = 'evidence/board/' + boot + '/'
        paths.update(prefix + name for name in ('acceptance.json', 'control-fabric.json'))
        for core in PACKS:
            for repeat in (1, 4):
                paths.update(prefix + f'{core}-r{repeat}' + suffix for suffix in ('.json', '.csv.gz'))
    for core, (folder, _, expected, _, _) in PACKS.items():
        names = {expected, 'manifest.json', 'inputs_u8.bin' if core == 'qec' else 'inputs_i16.bin'}
        if core == 'nv':
            names.add('expected_scores_u64.bin')
        if core == 'readout':
            names.update(('labels_u8.bin', 'records.json'))
        paths.update(folder + '/' + name for name in names)
    return paths


def check_hashes(root):
    manifest = read_json(root / 'evidence/manifest.json')
    require(manifest['schema'] == 'cudaq_fpga_public_files_v1', 'Unknown manifest')
    entries = manifest['files']
    require(isinstance(entries, dict), 'Invalid manifest files')
    missing = required_files() - entries.keys()
    require(not missing, 'Incomplete manifest: ' + ', '.join(sorted(missing)))
    for relative, expected in entries.items():
        rel = Path(relative)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == relative,
                'Invalid manifest path')
        require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected), 'Invalid digest')
        path = root / rel
        require(not any((root / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)),
                'Symlink evidence: ' + relative)
        require(path.is_file(), 'Missing evidence: ' + relative)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Hash mismatch: ' + relative)
    return len(entries)


def timing_summary(values):
    require(bool(values), 'Empty timing samples')
    ordered = sorted(values)
    n = len(ordered)
    return {'p50': ordered[(n * 50 + 99) // 100 - 1],
            'p99': ordered[(n * 99 + 99) // 100 - 1], 'max': ordered[-1]}


def csv_values(row, stem):
    require(set(row) == set(COLUMNS) and all(isinstance(v, str) for v in row.values()),
            stem + ': malformed CSV')
    values = {}
    for key, value in row.items():
        pattern = r'0x[0-9a-f]{16}' if key.endswith('_hex') else r'(0|[1-9][0-9]*)'
        require(re.fullmatch(pattern, value) is not None, stem + ': invalid integer: ' + key)
        values[key] = int(value, 16 if key.endswith('_hex') else 10)
        require(uint(values[key]), stem + ': integer out of range: ' + key)
    return values


def references(root, core):
    relative, count, filename, code, _ = PACKS[core]
    folder = root / relative
    data = (folder / filename).read_bytes()
    require(len(data) == count * struct.calcsize(code), 'Bad reference length: ' + core)
    values = [v[0] for v in struct.iter_unpack('<' + code, data)]
    scores = [0] * count
    if core == 'nv':
        data = (folder / 'expected_scores_u64.bin').read_bytes()
        require(len(data) == count * 8, 'Bad NV score length')
        scores = [v[0] for v in struct.iter_unpack('<Q', data)]
    inputs = folder / ('inputs_u8.bin' if core == 'qec' else 'inputs_i16.bin')
    require(inputs.stat().st_size == count * (1 if core == 'qec' else 256), 'Bad input length')
    return values, scores


def check_run(root, boot, core, repeat, counters=None):
    folder = root / 'evidence/board' / boot
    stem = f'{core}-r{repeat}'
    report = read_json(folder / (stem + '.json'))
    _, count, _, _, cycles = PACKS[core]
    total = count * repeat
    numeric = ('exit_code', 'span', 'validated_records', 'repeat', 'planned_calls', 'attempted_calls',
               'completed_calls', 'mismatches', 'host_timeout_ms', 'fabric_timeout_cycles', 'last_status',
               'last_error', 'fabric_cycles_min', 'fabric_cycles_max', 'latency_sample_count')
    require(all(uint(report[k]) for k in numeric), stem + ': invalid JSON integer')
    for key in ('host_total_ns', 'host_call_ns'):
        require(set(report[key]) == {'p50', 'p99', 'max'} and all(uint(v) for v in report[key].values()),
                stem + ': invalid timing summary')
    require(report['schema'] == 'quantum_demo_replay_v1' and report['mode'] == 'fabric_mmio', stem + ': wrong mode')
    require(report['hardware_opened'] is True and report['identity_verified'] is True, stem + ': missing identity')
    require(report['id'] == '0x51465047' and report['abi'] == '0x00010000', stem + ': wrong identity')
    require(report['base'] == '0x60040000' and report['span'] == 4096, stem + ': wrong address scope')
    require(report['core'] == core and report['repeat'] == repeat and report['validated_records'] == count, stem + ': wrong records')
    require(all(report[k] == total for k in ('planned_calls', 'attempted_calls', 'completed_calls', 'latency_sample_count')), stem + ': incomplete calls')
    require(all(report[k] == 0 for k in ('exit_code', 'mismatches', 'last_error')), stem + ': replay error')
    require(report['host_timeout_ms'] == 100 and report['fabric_timeout_cycles'] == 1000000, stem + ': wrong deadlines')
    require(report['fabric_cycles_min'] == report['fabric_cycles_max'] == cycles, stem + ': cycle mismatch')
    expected, expected_scores = references(root, core)
    timing = {'host_total_ns': [], 'host_call_ns': []}
    rows, previous = 0, counters.get('completed') if counters is not None else None
    last_status = None
    with gzip.open(folder / (stem + '.csv.gz'), 'rt', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == COLUMNS, stem + ': wrong CSV columns')
        for row in reader:
            value = csv_values(row, stem)
            require(rows < total and value['call'] == rows and value['repeat'] == rows // count and value['record'] == rows % count, stem + ': row order/count')
            index = rows % count
            require(value['expected_hex'] == value['result_hex'] == expected[index], stem + ': full-width result mismatch')
            require(value['expected_score_hex'] == value['score_hex'] == expected_scores[index], stem + ': full-width score mismatch')
            require(value['match'] == 1 and value['error'] == 0 and value['status'] in (2, 10), stem + ': bad completion')
            before, after = value['completed_before'], value['completed_after']
            require(0 <= before <= 0xffffffff and 0 <= after <= 0xffffffff and (after - before) & 0xffffffff == 1, stem + ': counter delta')
            require(previous is None or before == previous, stem + ': counter discontinuity')
            previous = after
            last_status = value['status']
            require(value['fabric_cycles'] == cycles, stem + ': CSV cycles')
            require(0 < value['host_call_ns'] < 100000000 and value['host_total_ns'] >= value['host_call_ns'], stem + ': host timing')
            for key in timing:
                timing[key].append(value[key])
            rows += 1
    require(rows == total, stem + ': truncated CSV')
    require(report['last_status'] == last_status, stem + ': last status mismatch')
    for key, values in timing.items():
        require(timing_summary(values) == report[key], stem + ': timing summary mismatch')
    if counters is not None:
        counters['completed'] = previous
    return rows


def check_control(folder, counters=None):
    report = read_json(folder / 'control-fabric.json')
    require(report['schema'] == 'quantum_demo_control_v1' and report['mode'] == 'fabric_mmio', 'Control schema/mode')
    require(all(uint(report[k]) for k in ('exit_code', 'span', 'deadline_ms', 'id', 'abi', 'original_timeout')),
            'Control integer schema')
    require(report['exit_code'] == 0 and report['base'] == '0x60040000' and report['span'] == 4096
            and report['deadline_ms'] == 100, 'Control failure/address/deadline')
    require(all(report[k] is True for k in ('hardware_opened', 'identity_verified', 'timeout_restored',
                                          'register_writes', 'start_written')), 'Control identity/restoration')
    require(report['id'] == 0x51465047 and report['abi'] == 0x10000 and report['original_timeout'] == 1000000,
            'Control identity/timeout mismatch')
    checks = report['checks']
    require(isinstance(checks, list) and [c['name'] for c in checks] == list(CONTROL_ORDER)
            and all(c['pass'] is True for c in checks), 'Incomplete or unordered control checks')
    require(checks[0]['hardware_snapshot'] is False, 'Invalid identity snapshot')
    previous = None
    active = {'forced_qec_timeout': (1, 1), 'qec_after_timeout': (0, 4),
              'active_nv_abort': (2, None), 'qec_after_idle_abort': (0, 4)}
    for c in checks[1:]:
        name = c['name']
        require(c['hardware_snapshot'] is True, 'Missing control snapshot')
        require(all(uint(c[k], 64 if k in ('result', 'score') else 32) for k in
                    ('status', 'error', 'cycles', 'count_before', 'count_after', 'count_delta', 'result', 'score', 'timeout')),
                'Invalid control integer')
        require(c['status'] <= 15 and c['status'] & 1 == 0 and c['result'] == c['score'] == 0,
                'Invalid control state/output')
        delta = (c['count_after'] - c['count_before']) & 0xffffffff
        require(c['count_delta'] == delta == (1 if name in active else 0), 'Control counter delta')
        require(previous is None or c['count_before'] == previous['count_after'], 'Control counter discontinuity')
        want_timeout = 1 if name in ('timeout_one_readback', 'forced_qec_timeout') else report['original_timeout']
        require(c['timeout'] == want_timeout, 'Control timeout restoration/readback')
        if name in active:
            error, cycles = active[name]
            require(c['error'] == error and c['status'] & 7 == (6 if error else 2), 'Invalid recovery control result')
            require(c['cycles'] == cycles if cycles is not None else 0 < c['cycles'] < report['original_timeout'],
                    'Invalid control cycles')
        elif name.startswith('clear_'):
            require(c['error'] == 0 and c['status'] == (previous['status'] & 8)
                    and c['cycles'] == previous['cycles'], 'Invalid CLEAR preservation')
        elif previous is not None:
            require(all(c[k] == previous[k] for k in ('status', 'error', 'cycles', 'result', 'score')),
                    'Invalid idle/timeout preservation')
        previous = c
    if counters is not None:
        counters['completed'] = previous['count_after']
    return len(checks)


def verify(root):
    files = check_hashes(root)
    total, controls = 0, 0
    commands = {'readout-parse', 'nv-parse', 'qec-parse', 'control-parse', 'control-fabric'} | {f'{c}-r{r}' for c in PACKS for r in (1, 4)}
    for boot in ('boot-1', 'boot-2'):
        folder = root / 'evidence/board' / boot
        acceptance = read_json(folder / 'acceptance.json')
        require(acceptance['schema'] == 'quantum_board_acceptance_v1' and acceptance['mode'] == 'fabric_acceptance'
                and acceptance['status'] == 'PASS' and acceptance['fabric_started'] is True, 'Acceptance failure')
        entries = acceptance['commands']
        ordered_commands = [f'{core}-parse' for core in PACKS] + ['control-parse', 'control-fabric']
        ordered_commands += [f'{core}-r{repeat}' for repeat in (1, 4) for core in PACKS]
        require(len(entries) == len(commands) and [c['name'] for c in entries] == ordered_commands,
                'Missing or unordered acceptance command')
        require(all(type(c['returncode']) is int and c['returncode'] == 0 and c['accepted'] is True for c in entries), 'Failed command receipt')
        counters = {}
        controls += check_control(folder, counters)
        for repeat in (1, 4):
            for core in PACKS:
                total += check_run(root, boot, core, repeat, counters)
    require(total == 171650 and controls == 30, 'Incorrect aggregate totals')
    for name in ('post-program-v250.json', 'coldboot-v250.json'):
        report = read_json(root / 'evidence/board' / name)
        require(type(report['exit_code']) is int and report['exit_code'] == 0 and 'RESULT: INFERENCE COMPLETED' in report['output'] and 'error_val=0' in report['output'], 'V250 regression failed')
    return {'status': 'PASS', 'files_hashed': files, 'exact_replay_calls': total, 'frozen_records': 17165,
            'passes_per_record': 10, 'control_checks': controls, 'v250_regressions': 2,
            'scope': 'Saved evidence verification only. No new hardware execution or scientific validation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError, EOFError, csv.Error) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
