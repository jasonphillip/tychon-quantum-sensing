"""Batch dataset generation pipeline for CW ODMR synthetic data.

Generates train/val/test splits with uniformly sampled corruption parameters,
writes HDF5 + JSON manifest bundle for consumption by Repo 2 (tychon-odmr-ml).

Each spectrum is generated with a unique seed, and train/test seed separation
is enforced by the DatasetManifest validation.

Supports three noise modes:
- "deterministic": Uniform parameter sampling (default, original behavior).
- "stochastic": OU trajectory sampling for T(t) and B1(t) drift.
- "both": Paired deterministic + stochastic for comparison.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import subprocess
from pathlib import Path

import numpy as np

from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
from tychon_nv_sim.config import NoiseMode, OUNoiseConfig, SimulationConfig
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


def _generate_split_deterministic(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    split_seeds: list[int],
    p1_range_ppm: tuple[float, float],
    temp_range_K: tuple[float, float],
    b1_gradient_range: tuple[float, float],
    b_perp_range_T: tuple[float, float],
    bz_range_T: tuple[float, float],
    n_freq_points: int,
    split_name: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """Generate spectra for a split using deterministic (uniform) sampling."""
    n_split = len(split_seeds)
    spectra = np.zeros((n_split, n_freq_points))
    labels = np.zeros((n_split, 3))
    params = np.zeros((n_split, 4))
    freqs_out = None

    print(f"Generating {n_split} spectra for {split_name} split (deterministic)...")
    for idx, seed in enumerate(split_seeds):
        sp_rng = np.random.default_rng(seed)

        p1 = sp_rng.uniform(*p1_range_ppm)
        T_K = sp_rng.uniform(*temp_range_K)
        b1_grad = sp_rng.uniform(*b1_gradient_range)
        b_perp = sp_rng.uniform(*b_perp_range_T)
        Bz = sp_rng.uniform(*bz_range_T)

        adapter.config.temperature_K = T_K
        adapter.config.B_field_T = np.array([0.0, 0.0, Bz])
        adapter.config.p1_concentration_ppm = p1

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

    return spectra, labels, params, np.array(split_seeds), freqs_out


def _generate_split_stochastic(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    split_seeds: list[int],
    ou_noise_config: OUNoiseConfig,
    ou_trajectory_seed: int,
    p1_range_ppm: tuple[float, float],
    b1_gradient_range: tuple[float, float],
    b_perp_range_T: tuple[float, float],
    bz_range_T: tuple[float, float],
    n_freq_points: int,
    split_name: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """Generate spectra for a split using OU stochastic trajectory sampling."""
    from tychon_nv_sim.physics.noise_injection import sample_ou_trajectory_pair

    n_split = len(split_seeds)

    # Generate OU trajectories for this split
    T_traj, B1_traj = sample_ou_trajectory_pair(
        ou_noise_config, n_split, seed=ou_trajectory_seed
    )

    spectra = np.zeros((n_split, n_freq_points))
    labels = np.zeros((n_split, 3))
    params = np.zeros((n_split, 5))  # 5 columns: p1, T_K, b1_grad, b_perp, mw_power_scale
    freqs_out = None

    print(f"Generating {n_split} spectra for {split_name} split (stochastic)...")
    for idx, seed in enumerate(split_seeds):
        sp_rng = np.random.default_rng(seed)

        # T and mw_power_scale from OU trajectories
        T_K = float(T_traj[idx])
        mw_power_scale = float(B1_traj[idx])

        # Other params sampled uniformly (same seed → same values as deterministic)
        p1 = sp_rng.uniform(*p1_range_ppm)
        _T_K_unused = sp_rng.uniform(0.0, 1.0)  # noqa: F841 — advance RNG state to keep Bz etc. aligned
        b1_grad = sp_rng.uniform(*b1_gradient_range)
        b_perp = sp_rng.uniform(*b_perp_range_T)
        Bz = sp_rng.uniform(*bz_range_T)

        adapter.config.temperature_K = T_K
        adapter.config.B_field_T = np.array([0.0, 0.0, Bz])
        adapter.config.p1_concentration_ppm = p1

        freqs, signal, _ = corrupt_spectrum(
            adapter, adapter.config, b1_grad, b_perp,
            p1_ppm=p1, mw_power_scale=mw_power_scale,
        )

        if freqs_out is None:
            freqs_out = freqs

        spectra[idx] = signal
        labels[idx] = [0.0, 0.0, Bz]
        params[idx] = [p1, T_K, b1_grad, b_perp, mw_power_scale]

        if (idx + 1) % 100 == 0:
            print(f"  {split_name}: {idx + 1}/{n_split}")

    return spectra, labels, params, np.array(split_seeds), freqs_out


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
    noise_mode: str = "deterministic",
    ou_noise_config: OUNoiseConfig | None = None,
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
        Temperature sampling range in Kelvin (deterministic mode).
    b1_gradient_range : tuple[float, float]
        B1 gradient fraction sampling range.
    b_perp_range_T : tuple[float, float]
        Transverse field sampling range in Tesla.
    bz_range_T : tuple[float, float]
        Axial B-field sampling range in Tesla.
    noise_mode : str
        Noise injection mode: "deterministic" (default), "stochastic", or "both".
    ou_noise_config : OUNoiseConfig, optional
        OU trajectory config. Required when noise_mode is "stochastic" or "both".

    Returns
    -------
    str
        Absolute path to the output directory.
    """
    # Validate and normalize noise_mode
    try:
        noise_mode_enum = NoiseMode(noise_mode)
    except ValueError:
        valid = ", ".join(f'"{m.value}"' for m in NoiseMode)
        raise ValueError(f"Invalid noise_mode='{noise_mode}'. Must be one of: {valid}")

    if noise_mode_enum in (NoiseMode.STOCHASTIC, NoiseMode.BOTH) and ou_noise_config is None:
        raise ValueError(
            f"ou_noise_config is required when noise_mode='{noise_mode}'"
        )

    rng = np.random.default_rng(master_seed)
    total = n_train + n_val + n_test

    # Generate unique seeds — enforces train/test separation
    seeds = rng.choice(2**31, size=total, replace=False).tolist()
    train_seeds = seeds[:n_train]
    val_seeds = seeds[n_train:n_train + n_val]
    test_seeds = seeds[n_train + n_val:]

    # OU trajectory seeds: derived from master_seed but independent of spectrum seeds
    ou_traj_seeds: dict[str, int] = {}
    if noise_mode_enum in (NoiseMode.STOCHASTIC, NoiseMode.BOTH):
        ou_ss = np.random.SeedSequence(master_seed + 2**30)
        ou_spawned = ou_ss.spawn(3)
        ou_traj_seeds = {
            "train": int(ou_spawned[0].generate_state(1)[0]),
            "val": int(ou_spawned[1].generate_state(1)[0]),
            "test": int(ou_spawned[2].generate_state(1)[0]),
        }

    simos_ver, qutip_ver = _get_versions()

    # Build config hash for provenance
    config_str = (
        f"{master_seed}:{n_freq_points}:{freq_range_Hz}:{p1_range_ppm}:{temp_range_K}"
        f":{noise_mode}"
    )
    if ou_noise_config is not None:
        config_str += f":{dataclasses.asdict(ou_noise_config)}"
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    # Temperature range for manifest
    if noise_mode_enum == NoiseMode.DETERMINISTIC:
        manifest_temp_range = temp_range_K
    else:
        # OU stationary distribution 3σ bounds
        assert ou_noise_config is not None
        sigma_stat = ou_noise_config.sigma_T / np.sqrt(2 * ou_noise_config.theta_T)
        manifest_temp_range = (
            ou_noise_config.mu_T - 3 * sigma_stat,
            ou_noise_config.mu_T + 3 * sigma_stat,
        )

    # Serialize OU params for manifest
    ou_params_dict = (
        dataclasses.asdict(ou_noise_config) if ou_noise_config is not None else None
    )

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
        temperature_range_K=manifest_temp_range,
        b1_gradient_range=b1_gradient_range,
        b_perp_range_T=b_perp_range_T,
        noise_mode=noise_mode,
        ou_params=ou_params_dict,
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
        ("train", train_seeds),
        ("val", val_seeds),
        ("test", test_seeds),
    ]

    common_kwargs = dict(
        p1_range_ppm=p1_range_ppm,
        b1_gradient_range=b1_gradient_range,
        b_perp_range_T=b_perp_range_T,
        bz_range_T=bz_range_T,
        n_freq_points=n_freq_points,
    )

    for split_name, split_seeds in splits:
        if len(split_seeds) == 0:
            continue

        if noise_mode_enum == NoiseMode.DETERMINISTIC:
            spectra, labels, params, seed_arr, freqs = _generate_split_deterministic(
                adapter, config, split_seeds,
                temp_range_K=temp_range_K,
                split_name=split_name,
                **common_kwargs,
            )
            writer.write_spectra(spectra, freqs, labels, params, seed_arr, split_name)

        elif noise_mode_enum == NoiseMode.STOCHASTIC:
            assert ou_noise_config is not None
            spectra, labels, params, seed_arr, freqs = _generate_split_stochastic(
                adapter, config, split_seeds,
                ou_noise_config=ou_noise_config,
                ou_trajectory_seed=ou_traj_seeds[split_name],
                split_name=split_name,
                **common_kwargs,
            )
            writer.write_spectra(spectra, freqs, labels, params, seed_arr, split_name)

        elif noise_mode_enum == NoiseMode.BOTH:
            assert ou_noise_config is not None  # guaranteed by ValueError above; narrows type
            # Deterministic pass
            s_det, l_det, p_det, sd_det, f_det = _generate_split_deterministic(
                adapter, config, split_seeds,
                temp_range_K=temp_range_K,
                split_name=f"{split_name}_deterministic",
                **common_kwargs,
            )
            writer.write_spectra(
                s_det, f_det, l_det, p_det, sd_det, f"{split_name}_deterministic"
            )

            # Stochastic pass (same spectrum seeds → paired by index)
            s_sto, l_sto, p_sto, sd_sto, f_sto = _generate_split_stochastic(
                adapter, config, split_seeds,
                ou_noise_config=ou_noise_config,
                ou_trajectory_seed=ou_traj_seeds[split_name],
                split_name=f"{split_name}_stochastic",
                **common_kwargs,
            )
            writer.write_spectra(
                s_sto, f_sto, l_sto, p_sto, sd_sto, f"{split_name}_stochastic"
            )

    writer.write_manifest(manifest)
    output_path = writer.finalize()
    print(f"Dataset written to {output_path}")
    return output_path


if __name__ == "__main__":
    generate_dataset("./data/synthetic_v1")
