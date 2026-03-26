#!/usr/bin/env python3
"""Generate production sweep dataset from YAML config.

Iterates over a grid of P1 concentrations x temperatures, generating
n_replicates corrupted ODMR spectra per combination with randomly sampled
B1 gradient and B_perp corruption parameters.

Resumable: tracks progress via a .progress file and skips already-generated
spectra on restart.

Usage
-----
    python scripts/generate_sweep.py --config configs/production_sweep.yaml --output-dir artifacts/sweep_v1/
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import subprocess
from pathlib import Path

import numpy as np
import yaml

from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
from tychon_nv_sim.config import SimulationConfig
from tychon_nv_sim.datasets.schema import DatasetManifest
from tychon_nv_sim.datasets.writer import DatasetWriter
from tychon_nv_sim.physics.lineshape import corrupt_spectrum


def _get_git_sha() -> str:
    """Get current git SHA, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_versions() -> tuple[str, str]:
    """Get SimOS and QuTiP version strings."""
    import qutip
    import simos
    return simos.__version__, qutip.__version__


def load_sweep_config(config_path: Path) -> dict:
    """Load sweep configuration from YAML file.

    Ensures numeric lists are properly typed (YAML safe_load sometimes
    parses scientific notation inside flow sequences as strings).
    """
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # Coerce numeric fields that YAML may parse as strings
    float_list_keys = [
        "freq_range_Hz", "B_field_T", "b1_gradient_range", "b_perp_range_T",
        "p1_sweep_ppm", "temperature_sweep_K",
    ]
    for key in float_list_keys:
        if key in cfg and isinstance(cfg[key], list):
            cfg[key] = [float(v) for v in cfg[key]]

    return cfg


def build_grid(cfg: dict) -> list[tuple[float, float, int]]:
    """Build (p1_ppm, temp_K, replicate_idx) grid."""
    return list(itertools.product(
        cfg["p1_sweep_ppm"],
        cfg["temperature_sweep_K"],
        range(cfg["n_replicates"]),
    ))


def get_completed_count(progress_path: Path) -> int:
    """Count completed spectra from progress file."""
    if not progress_path.exists():
        return 0
    return sum(1 for _ in progress_path.open())


def run_sweep(config_path: Path, output_dir: Path) -> str:
    """Run the parameter sweep and write output.

    Parameters
    ----------
    config_path : Path
        Path to sweep YAML config.
    output_dir : Path
        Output directory for HDF5 + manifest.

    Returns
    -------
    str
        Absolute path to output directory.
    """
    cfg = load_sweep_config(config_path)
    grid = build_grid(cfg)
    total = len(grid)

    # Pre-generate unique seeds deterministically
    rng = np.random.default_rng(cfg["master_seed"])
    all_seeds = rng.choice(2**31, size=total, replace=False).tolist()

    # Check resume state
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / ".progress"
    completed = get_completed_count(progress_path)

    if completed >= total:
        print(f"Already complete: {total}/{total} spectra")
        return str(output_dir.resolve())

    if completed > 0:
        print(f"Resuming: {completed}/{total} spectra already generated")

    # Setup adapter
    n_freq = cfg["n_freq_points"]
    freq_range = tuple(cfg["freq_range_Hz"])
    B_field = np.array(cfg["B_field_T"])

    sim_config = SimulationConfig(
        random_seed=cfg["master_seed"],
        use_optics=cfg.get("use_optics", False),
        include_nitrogen=cfg.get("include_nitrogen", False),
        n_freq_points=n_freq,
        mw_freq_range_Hz=freq_range,
        B_field_T=B_field,
        inhomogeneous_fwhm_hz=cfg.get("inhomogeneous_fwhm_hz", 0.0),
        base_saturation_s0=cfg.get("base_saturation_s0", 0.1),
    )
    adapter = SimOSAdapter(sim_config)

    b1_range = cfg["b1_gradient_range"]
    bp_range = cfg["b_perp_range_T"]

    # Accumulate results
    all_spectra = []
    all_params = []  # [p1, T, b1_grad, b_perp]
    all_labels = []  # [Bx, By, Bz]
    freqs_out = None

    # If resuming, replay completed spectra from the existing output
    # (we regenerate from scratch for simplicity — deterministic seeds
    # guarantee identical results)
    for idx, ((p1, temp_K, rep), seed) in enumerate(zip(grid, all_seeds)):
        if idx < completed:
            continue

        sp_rng = np.random.default_rng(seed)
        b1_grad = float(sp_rng.uniform(*b1_range))
        b_perp = float(sp_rng.uniform(*bp_range))

        adapter.config.temperature_K = temp_K
        adapter.config.B_field_T = B_field.copy()
        adapter.config.p1_concentration_ppm = p1

        freqs, signal, _ = corrupt_spectrum(
            adapter, adapter.config, b1_grad, b_perp, p1_ppm=p1
        )
        if freqs_out is None:
            freqs_out = freqs

        all_spectra.append(signal)
        all_params.append([p1, temp_K, b1_grad, b_perp])
        all_labels.append(B_field.tolist())

        # Track progress
        with open(progress_path, "a") as pf:
            pf.write(f"{idx}\n")

        print(f"  [{idx + 1}/{total}] P1={p1:>3g} ppm  T={temp_K}K  rep={rep}  seed={seed}")

    # If resuming, we need to regenerate earlier spectra for the HDF5 file
    if completed > 0:
        print(f"Regenerating {completed} earlier spectra for HDF5 output...")
        prefix_spectra = []
        prefix_params = []
        prefix_labels = []
        for idx in range(completed):
            p1, temp_K, rep = grid[idx]
            seed = all_seeds[idx]
            sp_rng = np.random.default_rng(seed)
            b1_grad = float(sp_rng.uniform(*b1_range))
            b_perp = float(sp_rng.uniform(*bp_range))

            adapter.config.temperature_K = temp_K
            adapter.config.B_field_T = B_field.copy()
            adapter.config.p1_concentration_ppm = p1

            freqs, signal, _ = corrupt_spectrum(
                adapter, adapter.config, b1_grad, b_perp, p1_ppm=p1
            )
            if freqs_out is None:
                freqs_out = freqs

            prefix_spectra.append(signal)
            prefix_params.append([p1, temp_K, b1_grad, b_perp])
            prefix_labels.append(B_field.tolist())

        all_spectra = prefix_spectra + all_spectra
        all_params = prefix_params + all_params
        all_labels = prefix_labels + all_labels

    # Convert to arrays
    spectra_arr = np.array(all_spectra)
    params_arr = np.array(all_params)
    labels_arr = np.array(all_labels)

    # Build manifest — all spectra go into "train" split
    simos_ver, qutip_ver = _get_versions()
    config_str = f"{cfg['master_seed']}:{n_freq}:{freq_range}:{cfg['p1_sweep_ppm']}:{cfg['temperature_sweep_K']}"
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    manifest = DatasetManifest(
        generator_git_sha=_get_git_sha(),
        config_hash=config_hash,
        simos_version=simos_ver,
        qutip_version=qutip_ver,
        backend="qutip",
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        master_seed=cfg["master_seed"],
        train_seeds=all_seeds,
        val_seeds=[],
        test_seeds=[],
        n_spectra_train=total,
        n_spectra_val=0,
        n_spectra_test=0,
        train_indices=list(range(total)),
        val_indices=[],
        test_indices=[],
        n_freq_points=n_freq,
        freq_range_Hz=freq_range,
        p1_concentration_range_ppm=(
            min(cfg["p1_sweep_ppm"]),
            max(cfg["p1_sweep_ppm"]),
        ),
        temperature_range_K=(
            min(cfg["temperature_sweep_K"]),
            max(cfg["temperature_sweep_K"]),
        ),
        b1_gradient_range=tuple(cfg["b1_gradient_range"]),
        b_perp_range_T=tuple(cfg["b_perp_range_T"]),
    )
    manifest.validate()

    # Write output
    writer = DatasetWriter(output_dir, format=cfg.get("output_format", "h5"))
    writer.write_spectra(
        spectra_arr, freqs_out, labels_arr, params_arr,
        np.array(all_seeds), "train",
    )
    writer.write_manifest(manifest)
    result_path = writer.finalize()

    # Clean up progress file
    progress_path.unlink(missing_ok=True)

    print(f"\nDataset written to {result_path}")
    print(f"  {total} spectra, {n_freq} freq points each")
    print(f"  P1: {cfg['p1_sweep_ppm']} ppm")
    print(f"  Temperature: {cfg['temperature_sweep_K']} K")
    return result_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate CW ODMR sweep dataset from YAML config."
    )
    parser.add_argument(
        "--config", type=Path, default=Path("configs/production_sweep.yaml"),
        help="Path to sweep YAML config file",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/sweep_v1"),
        help="Output directory for HDF5 + manifest",
    )
    args = parser.parse_args()
    run_sweep(args.config, args.output_dir)


if __name__ == "__main__":
    main()
