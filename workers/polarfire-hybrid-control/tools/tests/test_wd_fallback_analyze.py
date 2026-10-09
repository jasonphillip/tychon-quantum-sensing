import csv
import importlib.util
import subprocess
import sys
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("analyze", Path(__file__).parents[1] / "wd_fallback_analyze.py")
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


def pair(tmp_path, scenario, flat=1000, step=0.0005, tracking=False):
    obs = tmp_path / "observer.csv"
    ctl = tmp_path / "control.csv"
    observer = [
        (0, 0, 1, 0, 0, 0, 100),
        (0, 1_000_000, 0, 0, 0, 0, 100),
        (0, 3_000_000, 3, 1, 1, 9, 100),
        (0, 3_500_000, 2, 0, 1, 15, 100),
    ]
    with obs.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(("rdtime_ticks", "t_ns", "wd_raw", "wd_timeout_bit", "wd_trip_count", "axi_write_count", "post_clamp_q16", "poll_gap_max_ns"))
        for ticks, t, raw, bit, count, writes, gap in observer:
            w.writerow((ticks, t, hex(raw), bit, count, writes, 10000, gap))
    with ctl.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(("idx", "rdtime_ticks", "t_ns", "error", "u_ai", "post_clamp_q16", "post_clamp_f", "wd_raw", "wd_timeout_bit", "wd_trip_count", "axi_write_count", "mode_phase", "overrun_ns"))
        f.write("# out_min=-1.0 out_max=1.0 inner_clamp=0.045\n")
        total = 1010 if scenario == "b1" else 1010
        for idx in range(total):
            t = 2_700_000 + idx * 300_000
            ai = (idx % 160) * .0005 - .04
            if idx < 2:
                post = 10000 + idx * 33
            elif tracking:
                post = 10000 + idx * 33
            elif idx < 2 + flat:
                post = 10033
            else:
                post = 10033 + round(step * 65536) + (idx - 2 - flat) * 33
            raw = 3 if 3_000_000 <= t < 3_500_000 else 2 if t >= 3_500_000 else 0
            w.writerow((idx, 0, t, .2, ai, post, post / 65536, hex(raw), raw & 1,
                        raw >> 1, idx * 3, "skip" if idx < 202 else "resume", 0))
    return obs, ctl


def result(tmp_path, scenario, **kwargs):
    obs, ctl = pair(tmp_path, scenario, **kwargs)
    return {(criterion, state) for _, criterion, state, _ in
            analyze.grade(analyze.load(obs), analyze.load(ctl, True), scenario, 300, analyze.settings(ctl))[1]}


def test_clean_b1(tmp_path):
    grades = result(tmp_path, "b1", flat=2000)
    assert ("B1", "PASS") in grades
    assert ("B2", "PASS") in grades
    assert ("B4", "PASS") in grades
    assert not any(state == "FAIL" for _, state in grades)
    out = tmp_path / "analysis"
    subprocess.run([sys.executable, str(Path(__file__).parents[1] / "wd_fallback_analyze.py"),
                    str(tmp_path / "observer.csv"), str(tmp_path / "control.csv"),
                    "--scenario", "b1", "--period-us", "300", "--out-dir", str(out)], check=True)
    assert "B4 | PASS" in (out / "criteria.md").read_text()
    assert "fallback_latency_ns" in (out / "events.csv").read_text()


def test_b2_cooldown_pass_recovery_step_fail(tmp_path):
    grades = result(tmp_path, "b2", flat=1000, step=.08)
    assert ("B5", "PASS") in grades
    assert ("B7", "FAIL") in grades


def test_c1_tracking_fails(tmp_path):
    grades = result(tmp_path, "c1", tracking=True)
    assert ("C3", "FAIL") in grades


def test_c0_core_visible_start_and_cooldown(tmp_path):
    grades = result(tmp_path, "c0", flat=1000, step=.0005)
    assert ("C1", "PASS") in grades
    assert ("C4", "PASS") in grades
