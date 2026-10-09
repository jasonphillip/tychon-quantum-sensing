"""Round-trip + backward-compat tests for the v3 widened-envelope manifest keys."""

from __future__ import annotations

import json

from nv_sensor_sim.datasets.schema import DatasetManifest


def test_v3_keys_round_trip(tmp_path):
    m = DatasetManifest(
        contract_version="v1",
        sequence_mode=True,
        n_timesteps=256,
        dt_s=1e-3,
        linewidth_Hz=1.5e6,
        sweep_mode="isotropic_widened",
        min_field_T=3.0e-3,
        directed_fraction=0.30,
        directed_approach_lw_range=(3.0, 6.0),
        offbias_angle_target_deg=60.0,
        window_margin_frac=0.02,
    )
    p = tmp_path / "manifest.json"
    m.to_json(p)
    back = DatasetManifest.from_json(p)
    assert back.min_field_T == 3.0e-3
    assert back.directed_fraction == 0.30
    assert back.directed_approach_lw_range == (3.0, 6.0)
    assert isinstance(back.directed_approach_lw_range, tuple)
    assert back.offbias_angle_target_deg == 60.0
    assert back.window_margin_frac == 0.02


def test_old_manifest_without_v3_keys_loads(tmp_path):
    # A minimal legacy manifest dict lacking every v3 key must still load.
    legacy = {
        "contract_version": "",
        "master_seed": 1,
        "n_freq_points": 100,
        "freq_range_Hz": [2.82e9, 2.92e9],
        "p1_concentration_range_ppm": [40.0, 40.0],
        "temperature_range_K": [300.0, 300.0],
        "b1_gradient_range": [0.0, 0.0],
        "b_perp_range_T": [0.0, 0.0],
    }
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps(legacy))
    back = DatasetManifest.from_json(p)
    assert back.min_field_T is None
    assert back.directed_fraction is None
    assert back.directed_approach_lw_range is None
    assert back.offbias_angle_target_deg is None
    assert back.window_margin_frac is None
