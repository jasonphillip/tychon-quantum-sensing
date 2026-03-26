"""Batch dataset generation pipeline for CW ODMR synthetic data.

Generates train/val/test splits with uniformly sampled corruption parameters,
writes HDF5 + JSON manifest bundle for consumption by Repo 2 (tychon-odmr-ml).

Each spectrum is generated with a unique seed, and train/test seed separation
is enforced by the DatasetManifest validation.
"""

from __future__ import annotations

import datetime
import hashlib
import subprocess
from pathlib import Path

import numpy as np

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


def generate_dataset(
    output_dir: str,
    n_train: int = 1000,
    n_val: int = 200,
    n_test: int = 200,
    master_seed: int = 42,
    n_freq_points: int = 100,
    freq_range_Hz: tuple[float, float] = (2.82e9, 2.92e9),
    p1_range_ppm: tuple[float, float] = (1.0, 300.0),
    temp_range_K: tuple[float, float] = (280.0, 320.0),
    b1_gradient_range: tuple[float, float] = (0.05, 0.30),
    b_perp_range_T: tuple[float, float] = (0.0, 50e-6),
    bz_range_T: tuple[float, float] = (0.005, 0.015),
) -> str:
    """Generate a complete synthetic ODMR dataset with manifest.

    Parameters
    ----------
    output_dir : str
        Output directory for HDF5 + manifest.
    n_train, n_val, n_test : int
        Number of spectra per split.
    master_seed : int
        Master random seed for reproducibility.
    n_freq_points : int
        Number of frequency points per spectrum.
    freq_range_Hz : tuple[float, float]
        MW frequency sweep range in Hz.
    p1_range_ppm : tuple[float, float]
        P1 concentration sampling range in ppm.
    temp_range_K : tuple[float, float]
        Temperature sampling range in Kelvin.
    b1_gradient_range : tuple[float, float]
        B1 gradient fraction sampling range.
    b_perp_range_T : tuple[float, float]
        Transverse field sampling range in Tesla.
    bz_range_T : tuple[float, float]
        Axial B-field sampling range in Tesla.

    Returns
    -------
    str
        Absolute path to the output directory.
    """
    rng = np.random.default_rng(master_seed)
    total = n_train + n_val + n_test

    # Generate unique seeds — enforces train/test separation
    seeds = rng.choice(2**31, size=total, replace=False).tolist()
    train_seeds = seeds[:n_train]
    val_seeds = seeds[n_train:n_train + n_val]
    test_seeds = seeds[n_train + n_val:]

    simos_ver, qutip_ver = _get_versions()

    # Build config hash for provenance
    config_str = f"{master_seed}:{n_freq_points}:{freq_range_Hz}:{p1_range_ppm}:{temp_range_K}"
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    manifest = DatasetManifest(
        generator_git_sha=_get_git_sha(),
        config_hash=config_hash,
        simos_version=simos_ver,
        qutip_version=qutip_ver,
        backend="qutip",
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        master_seed=master_seed,
        train_seeds=train_seeds,
        val_seeds=val_seeds,
        test_seeds=test_seeds,
        n_spectra_train=n_train,
        n_spectra_val=n_val,
        n_spectra_test=n_test,
        train_indices=list(range(n_train)),
        val_indices=list(range(n_train, n_train + n_val)),
        test_indices=list(range(n_train + n_val, total)),
        n_freq_points=n_freq_points,
        freq_range_Hz=freq_range_Hz,
        p1_concentration_range_ppm=p1_range_ppm,
        temperature_range_K=temp_range_K,
        b1_gradient_range=b1_gradient_range,
        b_perp_range_T=b_perp_range_T,
    )
    manifest.validate()

    writer = DatasetWriter(Path(output_dir))

    # Base config — per-spectrum params will be overridden
    config = SimulationConfig(
        random_seed=master_seed,
        use_optics=False,
        include_nitrogen=False,
        n_freq_points=n_freq_points,
        mw_freq_range_Hz=freq_range_Hz,
    )
    adapter = SimOSAdapter(config)

    splits = [
        ("train", manifest.train_seeds),
        ("val", manifest.val_seeds),
        ("test", manifest.test_seeds),
    ]

    for split_name, split_seeds in splits:
        n_split = len(split_seeds)
        if n_split == 0:
            continue

        spectra = np.zeros((n_split, n_freq_points))
        labels = np.zeros((n_split, 3))
        params = np.zeros((n_split, 4))
        freqs_out = None

        print(f"Generating {n_split} spectra for {split_name} split...")
        for idx, seed in enumerate(split_seeds):
            sp_rng = np.random.default_rng(seed)

            # Sample corruption parameters uniformly
            p1 = sp_rng.uniform(*p1_range_ppm)
            T_K = sp_rng.uniform(*temp_range_K)
            b1_grad = sp_rng.uniform(*b1_gradient_range)
            b_perp = sp_rng.uniform(*b_perp_range_T)
            Bz = sp_rng.uniform(*bz_range_T)

            # Configure adapter for this spectrum
            adapter.config.temperature_K = T_K
            adapter.config.B_field_T = np.array([0.0, 0.0, Bz])
            adapter.config.p1_concentration_ppm = p1

            # Generate corrupted spectrum
            freqs, signal, _ = corrupt_spectrum(
                adapter, adapter.config, b1_grad, b_perp, p1_ppm=p1
            )

            if freqs_out is None:
                freqs_out = freqs

            spectra[idx] = signal
            labels[idx] = [0.0, 0.0, Bz]
            params[idx] = [p1, T_K, b1_grad, b_perp]

            if (idx + 1) % 100 == 0:
                print(f"  {split_name}: {idx + 1}/{n_split}")

        writer.write_spectra(spectra, freqs_out, labels, params, np.array(split_seeds), split_name)

    writer.write_manifest(manifest)
    output_path = writer.finalize()
    print(f"Dataset written to {output_path}")
    return output_path


if __name__ == "__main__":
    generate_dataset("./data/synthetic_v1")
