"""Fit comparable ODMR spectra by squared log linewidth and contrast ratios.

Shape MSE is reported but not optimized: offsets and broad wings can make its
min-max-normalized value prefer an unrealistically wide simulated line.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.datasets import external_datasets as ed
from nv_sensor_sim.physics.lineshape import generate_multi_axis_spectrum
from nv_sensor_sim.validation.reference_comparison import compare_spectra, load_experimental_odmr


GRID_FWHM_HZ = (0, 1e6, 2e6, 3e6, 5e6, 8e6, 12e6, 20e6)
GRID_CONTRAST = (0.001, 0.002, 0.003, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08)
OBJECTIVE = "Minimize squared log simulated-to-measured linewidth ratio, plus squared log contrast ratio when contrast is used."
FIT_DATASETS = {"zenodo_zerofield", "zenodo_odmr", "harvard"}


def fit_row(
    exp_freq_hz, exp_signal, B_lab_T, adapter_factory, *,
    grid_fwhm_hz=GRID_FWHM_HZ, grid_contrast=GRID_CONTRAST,
    use_contrast=True,
) -> dict:
    """Fit a clipped Nelder-Mead refinement after a coarse parameter grid."""
    freq = np.asarray(exp_freq_hz, dtype=float)
    signal = np.asarray(exp_signal, dtype=float)
    if freq.ndim != 1 or signal.shape != freq.shape or len(freq) < 2:
        raise ValueError("Experimental frequency and signal must be paired 1-D arrays")
    widths = np.asarray(grid_fwhm_hz, dtype=float)
    contrasts = np.asarray(grid_contrast, dtype=float)
    if (not len(widths) or not len(contrasts) or np.min(widths) < 0
            or np.min(contrasts) <= 0):
        raise ValueError("Fit grids require nonnegative widths and positive contrasts")
    bounds = ((float(widths.min()), float(widths.max())),
              (float(contrasts.min()), float(contrasts.max())))
    n_evals = 0

    def evaluate(width_hz: float, contrast: float):
        nonlocal n_evals
        n_evals += 1
        cfg = SimulationConfig(inhomogeneous_fwhm_hz=width_hz, base_contrast=contrast)
        sim_freq, sim_signal = generate_multi_axis_spectrum(
            adapter_factory(cfg), np.asarray(B_lab_T, dtype=float),
            freq_range=(float(freq.min()), float(freq.max())), n_points=len(freq),
        )
        result = compare_spectra(sim_freq, sim_signal, freq, signal)
        linewidth_sim = result.linewidth_sim_hz
        linewidth_exp = result.linewidth_exp_hz
        ratio = result.contrast_ratio
        if (not math.isfinite(linewidth_sim) or linewidth_sim <= 0
                or not math.isfinite(linewidth_exp) or linewidth_exp <= 0
                or not math.isfinite(ratio) or ratio <= 0):
            return math.inf, result
        score = math.log(linewidth_sim / linewidth_exp) ** 2
        if use_contrast:
            score += math.log(ratio) ** 2
        return score, result

    best_score = math.inf
    best = None
    for width in widths:
        for contrast in contrasts:
            score, _ = evaluate(float(width), float(contrast))
            if score < best_score:
                best_score, best = score, (float(width), float(contrast))
    if best is None:
        raise ValueError("No finite comparison score for the supplied spectrum")

    # Width is expressed in MHz during optimization for a well-scaled simplex.
    start = (best[0] / 1e6, best[1])
    width_bounds_mhz = (bounds[0][0] / 1e6, bounds[0][1] / 1e6)

    def objective_scaled(x):
        width = float(np.clip(x[0], *width_bounds_mhz)) * 1e6
        contrast = float(np.clip(x[1], *bounds[1]))
        return evaluate(width, contrast)[0]

    optimized = minimize(objective_scaled, start, method="Nelder-Mead",
                         options={"maxiter": 200, "xatol": 1e-5, "fatol": 1e-8})
    candidate = (float(np.clip(optimized.x[0], *width_bounds_mhz)) * 1e6,
                 float(np.clip(optimized.x[1], *bounds[1])))
    candidate_score, _ = evaluate(*candidate)
    chosen = candidate if candidate_score < best_score else best
    _, result = evaluate(*chosen)
    return {
        "inhomogeneous_fwhm_hz": chosen[0],
        "base_contrast": chosen[1],
        "shape_mse": result.shape_mse,
        "linewidth_ratio": result.linewidth_sim_hz / result.linewidth_exp_hz,
        "linewidth_sim_hz": result.linewidth_sim_hz,
        "linewidth_exp_hz": result.linewidth_exp_hz,
        "contrast_ratio": result.contrast_ratio,
        "n_evals": n_evals,
    }


def _load_row(dataset: str, item: str):
    if dataset == "zenodo_ml_scan":
        spectrum = ed.load_zenodo_ml_scan_spectrum(item)
        return spectrum.freq_MHz * 1e6, spectrum.signal
    if dataset == "zenodo_zerofield":
        grid = ed.load_zenodo_zerofield_odmr()
        index = grid.position_labels.index(item)
        return grid.freq_MHz * 1e6, grid.signal[:, index]
    if dataset == "harvard":
        grid = ed.load_harvard_lowfield_odmr("0.5mT")
        index = next(i for i, value in enumerate(grid.sweep_axis) if str(value) == item)
        return grid.freq_MHz * 1e6, grid.signal[:, index]
    if dataset == "zenodo_odmr":
        return load_experimental_odmr(str(ed.DATA_DIR / "zenodo_odmr" / item))
    raise ValueError(f"Unsupported comparable dataset: {dataset}")


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/experimental"))
    parser.add_argument("--rows-json", type=Path, default=Path("docs/external_validation_results.json"))
    parser.add_argument("--out", type=Path, default=Path("docs/simulator_fit_results.json"))
    args = parser.parse_args()
    ed.DATA_DIR = args.data_dir.resolve()
    source = json.loads(args.rows_json.read_text())
    rows = []
    for row in source["rows"]:
        if not row["comparable"] or row["dataset"] not in FIT_DATASETS:
            continue
        dataset, item = row["dataset"], row["item"]
        freq_hz, signal = _load_row(dataset, item)
        use_contrast = dataset in {"zenodo_zerofield", "zenodo_odmr"}
        field = np.asarray(row["B_lab_mT"], dtype=float) * 1e-3
        default_freq, default_signal = generate_multi_axis_spectrum(
            SimOSAdapter(SimulationConfig()), field,
            freq_range=(float(np.min(freq_hz)), float(np.max(freq_hz))),
            n_points=len(freq_hz),
        )
        default = compare_spectra(default_freq, default_signal, freq_hz, signal)
        fitted = fit_row(freq_hz, signal, field, SimOSAdapter,
                         use_contrast=use_contrast)
        rows.append({
            "dataset": dataset, "item": item,
            "B_lab_mT": row["B_lab_mT"],
            "sim_field_source": row["sim_field_source"],
            "use_contrast": use_contrast,
            "fwhm_default_hz": 0.0,
            "contrast_default": 0.03,
            "shape_mse_default": default.shape_mse,
            "linewidth_exp_hz": default.linewidth_exp_hz,
            "linewidth_sim_default_hz": default.linewidth_sim_hz,
            "fitted": {key: fitted[key] for key in ("inhomogeneous_fwhm_hz", "base_contrast")},
            "shape_mse_fitted": fitted["shape_mse"],
            "linewidth_sim_fitted_hz": fitted["linewidth_sim_hz"],
            "contrast_ratio_fitted": fitted["contrast_ratio"],
            "n_evals": fitted["n_evals"],
        })
    median = {key: float(np.median([row["fitted"][key] for row in rows]))
              for key in ("inhomogeneous_fwhm_hz", "base_contrast")} if rows else {}
    payload = {
        "date": date.today().isoformat(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                           cwd=Path(__file__).resolve().parents[1], text=True).strip(),
        "objective": OBJECTIVE,
        "rows": rows,
        "median": median,
        "fit_rows": [[row["dataset"], row["item"]] for row in rows],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n")
    lines = ["# Simulator fit to external ODMR", "", f"Date: {payload['date']}",
             f"Git SHA: {payload['git_sha']}", "", OBJECTIVE, "",
             "| Dataset | Item | Default linewidth (MHz) | Fitted linewidth (MHz) | Measured linewidth (MHz) | Default shape MSE | Fitted shape MSE | Fitted contrast | Contrast ratio |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(
            f"| {row['dataset']} | {row['item']} | "
            f"{row['linewidth_sim_default_hz'] / 1e6:.6g} | "
            f"{row['linewidth_sim_fitted_hz'] / 1e6:.6g} | "
            f"{row['linewidth_exp_hz'] / 1e6:.6g} | "
            f"{row['shape_mse_default']:.6g} | {row['shape_mse_fitted']:.6g} | "
            f"{row['fitted']['base_contrast']:.6g} | "
            f"{row['contrast_ratio_fitted']:.6g} |"
        )
    lines.extend(["", f"Median fitted inhomogeneous FWHM (Hz): {median.get('inhomogeneous_fwhm_hz', 'n/a')}",
                  f"Median fitted base contrast: {median.get('base_contrast', 'n/a')}", ""])
    args.out.with_suffix(".md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
