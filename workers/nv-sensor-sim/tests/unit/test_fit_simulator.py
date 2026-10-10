"""fit_row recovers a known linewidth and contrast from synthetic zero-field dips."""

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.physics.lineshape import generate_multi_axis_spectrum
from nv_sensor_sim.physics.parameters import compute_linewidth
from scripts.fit_simulator_to_external import fit_row

FREQ = np.linspace(2.84e9, 2.90e9, 600)


def _lorentzian_dip(freqs_hz, center_hz, fwhm_hz, contrast, baseline=1.0):
    hw = fwhm_hz / 2.0
    return baseline * (1.0 - contrast * hw**2 / ((freqs_hz - center_hz) ** 2 + hw**2))


def _sim_center_hz():
    f, s = generate_multi_axis_spectrum(SimOSAdapter(SimulationConfig()), np.zeros(3),
                                        freq_range=(FREQ[0], FREQ[-1]), n_points=len(FREQ))
    return float(f[np.argmin(s)])


def _expected_inhomogeneous_hz(target_fwhm_hz):
    # Simulated FWHM = compute_linewidth(p1, inh) * sqrt(1 + s0), default p1 10 ppm, s0 0.1.
    cfg = SimulationConfig()
    total = target_fwhm_hz / np.sqrt(1.0 + cfg.base_saturation_s0)
    hom = compute_linewidth(cfg.p1_concentration_ppm, 0.0)
    return float(np.sqrt(total**2 - hom**2))


def test_fit_recovers_width_and_contrast():
    exp = _lorentzian_dip(FREQ, _sim_center_hz(), 6e6, 0.05)
    fit = fit_row(FREQ, exp, B_lab_T=np.zeros(3), adapter_factory=lambda cfg: SimOSAdapter(cfg))
    assert abs(fit["inhomogeneous_fwhm_hz"] - _expected_inhomogeneous_hz(6e6)) < 2e6
    assert abs(fit["base_contrast"] - 0.05) < 0.3 * 0.05
    assert fit["n_evals"] > 0 and np.isfinite(fit["shape_mse"])


def test_fit_without_contrast_term_still_recovers_width():
    exp = _lorentzian_dip(FREQ, _sim_center_hz(), 3e6, 0.004)
    fit = fit_row(FREQ, exp, B_lab_T=np.zeros(3), adapter_factory=lambda cfg: SimOSAdapter(cfg), use_contrast=False)
    assert abs(fit["inhomogeneous_fwhm_hz"] - _expected_inhomogeneous_hz(3e6)) < 2e6


def test_fit_matches_measured_linewidth_with_offset_and_wings():
    # Real spectra (zero-field Zenodo) sit ~3 MHz off the simulator's centre and carry broad wings;
    # a min-max shape metric then prefers the widest allowed line. The fit must match the measured width.
    from nv_sensor_sim.validation.reference_comparison import compare_spectra
    c = _sim_center_hz()
    exp = _lorentzian_dip(FREQ, c - 3e6, 6e6, 0.035) - 0.015 * (1 - _lorentzian_dip(FREQ, c - 3e6, 40e6, 1.0))
    fit = fit_row(FREQ, exp, B_lab_T=np.zeros(3), adapter_factory=lambda cfg: SimOSAdapter(cfg))
    cfg = SimulationConfig(inhomogeneous_fwhm_hz=fit["inhomogeneous_fwhm_hz"], base_contrast=fit["base_contrast"])
    f, s = generate_multi_axis_spectrum(SimOSAdapter(cfg), np.zeros(3), freq_range=(FREQ[0], FREQ[-1]), n_points=len(FREQ))
    cmp = compare_spectra(f, s, FREQ, exp)
    assert abs(cmp.linewidth_sim_hz / cmp.linewidth_exp_hz - 1) < 0.10
    assert abs(fit["linewidth_ratio"] - cmp.linewidth_sim_hz / cmp.linewidth_exp_hz) < 1e-9


def test_cli_payload_matches_plan_interface(tmp_path, monkeypatch):
    import json
    import sys
    import scripts.fit_simulator_to_external as F

    c = _sim_center_hz()
    monkeypatch.setattr(F, "_load_row", lambda dataset, item: (FREQ, _lorentzian_dip(FREQ, c, 6e6, 0.05)))
    rows = [dict(dataset="zenodo_zerofield", item="Position 1", comparable=True, B_lab_mT=[0, 0, 0], sim_field_source="zero"),
            dict(dataset="harvard", item="0.40579", comparable=True, B_lab_mT=[0, 0, 0], sim_field_source="documented"),
            dict(dataset="zenodo_ml_scan", item="x_1", comparable=True, B_lab_mT=[0, 0, 0], sim_field_source="fitted-grid"),
            dict(dataset="zenodo_odmr", item="f0_odmr.csv", comparable=False, B_lab_mT=None, sim_field_source=None)]
    src = tmp_path / "rows.json"
    src.write_text(json.dumps({"rows": rows}))
    out = tmp_path / "fit.json"
    monkeypatch.setattr(sys, "argv", ["fit", "--data-dir", str(tmp_path), "--rows-json", str(src), "--out", str(out)])
    F.main()
    payload = json.loads(out.read_text())
    assert payload["fit_rows"] == [["zenodo_zerofield", "Position 1"], ["harvard", "0.40579"]]
    assert set(payload["median"]) == {"inhomogeneous_fwhm_hz", "base_contrast"}
    row = payload["rows"][0]
    for key in ("dataset", "item", "B_lab_mT", "sim_field_source", "use_contrast", "fwhm_default_hz", "contrast_default",
                "shape_mse_default", "shape_mse_fitted", "contrast_ratio_fitted", "linewidth_exp_hz",
                "linewidth_sim_default_hz", "linewidth_sim_fitted_hz", "n_evals"):
        assert key in row, key
    assert set(row["fitted"]) == {"inhomogeneous_fwhm_hz", "base_contrast"}
    assert payload["rows"][1]["use_contrast"] is False
    assert out.with_suffix(".md").is_file()


def test_median_contrast_uses_only_contrast_fitted_rows(tmp_path, monkeypatch):
    # Harvard rows fit width only; their contrast is unconstrained and must not enter the contrast median.
    import json
    import sys
    import scripts.fit_simulator_to_external as F

    c = _sim_center_hz()
    monkeypatch.setattr(F, "_load_row", lambda dataset, item: (FREQ, _lorentzian_dip(FREQ, c, 6e6, 0.05)))
    rows = [dict(dataset="zenodo_zerofield", item="Position 1", comparable=True, B_lab_mT=[0, 0, 0], sim_field_source="zero")] + [
        dict(dataset="harvard", item=f"h{i}", comparable=True, B_lab_mT=[0, 0, 0], sim_field_source="documented") for i in range(2)]
    src = tmp_path / "rows.json"
    src.write_text(json.dumps({"rows": rows}))
    out = tmp_path / "fit.json"
    monkeypatch.setattr(sys, "argv", ["fit", "--rows-json", str(src), "--out", str(out)])
    F.main()
    payload = json.loads(out.read_text())
    assert abs(payload["median"]["base_contrast"] - 0.05) < 0.05 * 0.05
    assert payload["rows"][1]["fitted"]["base_contrast"] is None
