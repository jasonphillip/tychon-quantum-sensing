"""verify_bit_exact CI scaffold for the Phase II hierarchical INT8 cascade (P3-11B).

Asserts bit-exact equality between the canonical numpy reference at
``tychon_shared_data.cascade.cascade_ref:compose_int8`` and either:

  --mode=sim  — the C++ ``tb_cascade.cpp`` golden output (cached in
                ``hls/tb/stimulus/cascade_synthetic_v1/expected_int8.csv``),
                proving software/numerical agreement across implementations.
  --mode=hil  — an FPGA capture under ``tests/cascade/fixtures/hil/`` produced
                by Track 0's debug capture path (UART0 console dump or
                SmartDebug readback). Proves silicon agreement.

Pre-Track-0, only ``--mode=sim`` runs green. Post-Track-0, both must agree.

The synthetic fixture lives at ``hls/tb/stimulus/cascade_synthetic_v1/`` —
shared with the C++ testbench so a single source of truth drives both sides.

The actual VectorBlox FPGA path's INT8 rounding mode is the resolution target
of HW-05 (see ``docs/vectorblox_rounding_resolution.md``). Pre-resolution, the
fixture pins ``composition.rounding_mode = "round_half_to_even"``. A mismatch
in ``--mode=hil`` against the resolved silicon mode would manifest as
``n_mismatch > 0`` with ``max_abs_diff_int8 == 1`` on roughly half the
elements (the ``.5`` ties).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


# Repo root = parents[2] from this test file (tests/cascade/test_*.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_FIXTURE_DIR = REPO_ROOT / "hls" / "tb" / "stimulus" / "cascade_synthetic_v1"
HIL_FIXTURES_DIR = REPO_ROOT / "tests" / "cascade" / "fixtures" / "hil"


# ---------------------------------------------------------------------------
# Skip the whole module if tychon-shared-data isn't installed.
# Pinned via this repo's pyproject / requirements (Track 3 dependency).
# ---------------------------------------------------------------------------

tsd_cascade_ref = pytest.importorskip(
    "tychon_shared_data.cascade.cascade_ref",
    reason="tychon-shared-data not installed — pip install -e ~/projects/tychon-shared-data",
)
tsd_manifest = pytest.importorskip(
    "tychon_shared_data.cascade.manifest",
    reason="tychon-shared-data not installed",
)

compose_int8 = tsd_cascade_ref.compose_int8
verify_bit_exact = tsd_cascade_ref.verify_bit_exact
CascadeManifest = tsd_manifest.CascadeManifest


# ---------------------------------------------------------------------------
# Fixture loaders
# ---------------------------------------------------------------------------


def _load_synthetic_fixture() -> tuple[CascadeManifest, np.ndarray, np.ndarray, np.ndarray]:
    """Load the canonical synthetic fixture shared with hls/tb/tb_cascade.cpp."""
    with open(SYNTHETIC_FIXTURE_DIR / "manifest.json") as f:
        manifest = CascadeManifest.from_dict(json.load(f), root=None)
    manifest.validate()  # exercises the full schema invariants

    coarse = np.loadtxt(
        SYNTHETIC_FIXTURE_DIR / "coarse_int8.csv",
        delimiter=",", dtype=np.int8,
    ).reshape(-1)
    fine = np.loadtxt(
        SYNTHETIC_FIXTURE_DIR / "fine_int8.csv",
        delimiter=",", dtype=np.int8,
    ).reshape(-1)
    expected = np.loadtxt(
        SYNTHETIC_FIXTURE_DIR / "expected_int8.csv",
        delimiter=",", dtype=np.int8,
    ).reshape(-1)
    return manifest, coarse, fine, expected


# ---------------------------------------------------------------------------
# Tests — sim mode (always available)
# ---------------------------------------------------------------------------


def test_synthetic_compose_matches_golden() -> None:
    """compose_int8 against the static fixture must match expected_int8.csv."""
    manifest, coarse, fine, expected = _load_synthetic_fixture()

    # Inject identity runners so no .tflite files are touched.
    actual = compose_int8(
        coarse,                      # x_int8 unused by identity runners
        manifest,
        coarse_runner=lambda _x: coarse,
        fine_runner=lambda _x: fine,
    )
    assert actual.dtype == np.int8
    assert actual.shape == expected.shape
    np.testing.assert_array_equal(
        actual, expected,
        err_msg="numpy compose_int8 disagrees with hls/tb/stimulus/cascade_synthetic_v1/expected_int8.csv",
    )


def test_synthetic_identity_residual_is_coarse() -> None:
    """When fine_int8 == z_fine elementwise, composed must equal coarse bit-exactly."""
    manifest, coarse, _fine, _expected = _load_synthetic_fixture()
    z_fine = int(manifest.fine_model["output_quant"]["zero_point"])
    fine_zero = np.full_like(coarse, z_fine, dtype=np.int8)

    composed = compose_int8(
        coarse, manifest,
        coarse_runner=lambda _x: coarse,
        fine_runner=lambda _x: fine_zero,
    )
    np.testing.assert_array_equal(
        composed, coarse,
        err_msg="zero-residual cascade composition is not the identity over coarse",
    )


def test_verify_bit_exact_reports_match() -> None:
    """verify_bit_exact must report ok=True with zero mismatches against the golden."""
    manifest, coarse, fine, expected = _load_synthetic_fixture()
    ok, report = verify_bit_exact(
        coarse, expected, manifest,
        coarse_runner=lambda _x: coarse,
        fine_runner=lambda _x: fine,
    )
    assert ok, f"verify_bit_exact reported mismatch: {report}"
    assert report["n_mismatch"] == 0
    assert report["max_abs_diff_int8"] == 0
    assert report["first_mismatch_index"] == -1
    assert report["rounding_mode"] == "round_half_up"


# ---------------------------------------------------------------------------
# Tests — hil mode (post-Track-0)
# ---------------------------------------------------------------------------


def _list_hil_captures() -> list[Path]:
    """Find captures under tests/cascade/fixtures/hil/<name>/{coarse,fine,fpga}_int8.csv."""
    if not HIL_FIXTURES_DIR.exists():
        return []
    return sorted(p for p in HIL_FIXTURES_DIR.iterdir() if p.is_dir())


def test_hil_capture_matches_numpy_reference(cascade_mode: str) -> None:
    """For each HIL capture, the FPGA INT8 output must agree with numpy compose_int8.

    A capture directory contains:
        coarse_int8.csv  — the coarse model's FPGA output for the test input set
        fine_int8.csv    — the fine model's FPGA output
        fpga_int8.csv    — the FPGA's composed output (the silicon-side reference)
        manifest.json    — the manifest used for that capture (rounding_mode locked)

    Captures are produced by the Track 0 debug capture path (UART0 console
    dump or SmartDebug readback).
    """
    if cascade_mode != "hil":
        pytest.skip("not in --mode=hil")
    captures = _list_hil_captures()
    if not captures:
        pytest.skip(
            f"no HIL captures under {HIL_FIXTURES_DIR} — Track 0 must close first"
        )

    failures: list[str] = []
    for capture_dir in captures:
        manifest_path = capture_dir / "manifest.json"
        if not manifest_path.exists():
            failures.append(f"{capture_dir.name}: manifest.json missing")
            continue
        with open(manifest_path) as f:
            manifest = CascadeManifest.from_dict(json.load(f), root=None)
        manifest.validate()

        try:
            coarse = np.loadtxt(capture_dir / "coarse_int8.csv",
                                delimiter=",", dtype=np.int8).reshape(-1)
            fine = np.loadtxt(capture_dir / "fine_int8.csv",
                              delimiter=",", dtype=np.int8).reshape(-1)
            fpga = np.loadtxt(capture_dir / "fpga_int8.csv",
                              delimiter=",", dtype=np.int8).reshape(-1)
        except OSError as exc:
            failures.append(f"{capture_dir.name}: {exc}")
            continue

        ok, report = verify_bit_exact(
            coarse, fpga, manifest,
            coarse_runner=lambda _x, c=coarse: c,
            fine_runner=lambda _x, f=fine: f,
        )
        if not ok:
            failures.append(
                f"{capture_dir.name}: {report['n_mismatch']} mismatches "
                f"(max_abs_diff={report['max_abs_diff_int8']}, "
                f"first_idx={report['first_mismatch_index']}, "
                f"rounding_mode={report['rounding_mode']})"
            )

    assert not failures, "HIL captures disagree with numpy reference:\n  " + "\n  ".join(failures)
