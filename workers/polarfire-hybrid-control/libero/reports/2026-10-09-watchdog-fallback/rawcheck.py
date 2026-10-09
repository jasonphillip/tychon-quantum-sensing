#!/usr/bin/env python3
"""Verdict numbers for docs/watchdog_fallback_test_plan.md from the raw run logs (control + observer CSVs).
Usage: rawcheck.py <run-dir-with-*-control.csv-and-*-observer.csv>
Trip time = observer's first timeout rise after the control tool's last normal-phase row (that row's
timestamp follows the inference completion by tens of microseconds, so trip times read slightly low).
Fallback = first update where post_clamp_out stops changing while u_ai still moves; recovery = next change."""
import csv, glob, re, statistics as st, sys
S = sys.argv[1]
FORCED = {}
def rows(p):
    """Regular controller updates only. Rows logged by --trip-start (mode_phase 'forced') are counted
    per file in FORCED and left out, so they do not break flat-run or pause bracketing."""
    with open(p) as f: allr = [x for x in csv.DictReader(l for l in f if not l.startswith('#'))]
    FORCED[p] = sum(1 for x in allr if x.get('mode_phase') == 'forced')
    return [x for x in allr if x.get('mode_phase') != 'forced']
def flat_run(c, start):
    first = None; n = 0
    for i in range(start + 1, len(c)):
        d = abs(float(c[i]['post_clamp_f']) - float(c[i-1]['post_clamp_f'])); du = abs(float(c[i]['u_ai']) - float(c[i-1]['u_ai']))
        if d < 2**-16 and du > 1e-6:
            if first is None: first = i
            n += 1
        elif first is not None: return first, n, i
    return first, n, None
print("== scenario a (SIGSTOP pauses)")
c = rows(f'{S}/a-01-control.csv'); o = rows(f'{S}/a-01-observer.csv')
axi_ok = hold_ok = fb_after = 0; rises = []
for i in range(1, len(c)):
    if int(c[i]['t_ns']) - int(c[i-1]['t_ns']) > 5e8:
        a, b = c[i-1], c[i]; t0, t1 = int(a['t_ns']), int(b['t_ns'])
        inside = [x for x in o if t0 < int(x['t_ns']) < t1]
        axi_ok += int(b['axi_write_count']) - int(a['axi_write_count']) == 3
        hold_ok += abs(float(b['post_clamp_f']) - float(a['post_clamp_f'])) <= 0.0006
        r = min((int(x['t_ns']) for x in inside if x['wd_timeout_bit'] == '1'), default=None)
        if r: rises.append((r - t0) / 1e6)
        f, n, _ = flat_run(c, i)
        fb_after += f is not None and f - i < 5 and n > 100
print(f"pauses={len(rises)} no_writes_during_pause={axi_ok} actuator_held={hold_ok} rise_after_last_update_ms min/med/max={min(rises):.3f}/{st.median(rises):.3f}/{max(rises):.3f} fallback_after_resume={fb_after}")
for scen in ['b1', 'b2', 'c1', 'c0']:
    res = []
    for p in sorted(glob.glob(f'{S}/{scen}-*-control.csv')):
        c = rows(p); o = rows(p.replace('control', 'observer'))
        last_norm = max(i for i, x in enumerate(c) if x['mode_phase'] == 'normal'); t_ref = int(c[last_norm]['t_ns'])
        hi = [int(x['t_ns']) for x in o if int(x['t_ns']) > t_ref and x['wd_timeout_bit'] == '1']; rise = hi[0] if hi else None
        lo = [int(x['t_ns']) for x in o if rise and int(x['t_ns']) > rise and x['wd_timeout_bit'] == '0']
        gi = [i for i, x in enumerate(c) if x['mode_phase'] == 'gap']; start = max(gi) if gi else last_norm
        f, n, end = flat_run(c, start)
        res.append(dict(trip_ms=None if rise is None else (rise - t_ref) / 1e6,
                        fb_lat_us=None if (f is None or rise is None) else (int(c[f]['t_ns']) - rise) / 1e3,
                        fb_step=None if f is None else abs(float(c[f]['post_clamp_f']) - float(c[f-1]['post_clamp_f'])),
                        flat_n=n, rec_s=None if (end is None or f is None) else (int(c[end]['t_ns']) - int(c[f]['t_ns'])) / 1e9,
                        rec_step=None if end is None else abs(float(c[end]['post_clamp_f']) - float(c[end-1]['post_clamp_f'])),
                        trip_delta=int(c[-1]['wd_trip_count']) - int(c[last_norm]['wd_trip_count']),
                        high_ms=None if not (hi and lo) else (lo[0] - hi[0]) / 1e6,
                        seen=sum(1 for x in c[last_norm+1:] if x['wd_timeout_bit'] == '1'),
                        bounds_ok=max(abs(float(x['u_ai'])) for x in c) <= 0.09 and max(abs(float(x['post_clamp_f'])) for x in c) <= 1.0))
    def stat(k, fmt="%.3f"):
        v = [r[k] for r in res if r[k] is not None]
        return "n/a" if not v else f"n={len(v)} min/med/max={fmt % min(v)}/{fmt % st.median(v)}/{fmt % max(v)}"
    print(f"== {scen} reps={len(res)}")
    print(f"  trip_ms {stat('trip_ms')}")
    print(f"  fallback_latency_us {stat('fb_lat_us', '%.0f')}  fallback_step {stat('fb_step', '%.5f')}")
    print(f"  flat_updates {stat('flat_n', '%d')}  recovery_s {stat('rec_s', '%.4f')}  recovery_step {stat('rec_step', '%.4f')}")
    print(f"  trip_delta==1: {sum(r['trip_delta'] == 1 for r in res)}/{len(res)}  timeout_high_ms {stat('high_ms')}  starts_seen_high: {sorted(set(r['seen'] for r in res))}  bounds_ok: {sum(r['bounds_ok'] for r in res)}/{len(res)}")
    print(f"  fell_back (flat>=100): {sum(r['flat_n'] >= 100 for r in res)}/{len(res)}")
    print(f"  forced starts logged (--trip-start): {sum(v for k, v in FORCED.items() if f'/{scen}-' in k)}")
