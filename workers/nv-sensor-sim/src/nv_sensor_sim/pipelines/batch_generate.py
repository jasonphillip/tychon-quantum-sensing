"""Batch dataset generation pipeline for CW ODMR synthetic data.

Generates train/val/test splits with uniformly sampled corruption parameters,
writes HDF5 + JSON manifest bundle for consumption by downstream ML training pipelines.

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
import inspect
import json
import subprocess
from pathlib import Path

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import FieldSampling, NoiseMode, OUNoiseConfig, SimulationConfig
from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.datasets.hashing import content_md5
from nv_sensor_sim.datasets.writer import DatasetWriter
from nv_sensor_sim.physics.lineshape import corrupt_spectrum, corrupt_spectrum_multi_axis


# These parameters only control the destination, never the generated arrays.
CONFIG_HASH_EXCLUDED_FIELDS = frozenset({"output_dir"})


def _canonical_config_value(value):
    """Convert supported configuration values to stable JSON values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _canonical_config_value(dataclasses.asdict(value))
    if isinstance(value, np.ndarray):
        return _canonical_config_value(value.tolist())
    if isinstance(value, np.generic):
        return _canonical_config_value(value.item())
    if isinstance(value, dict):
        return {key: _canonical_config_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_config_value(item) for item in value]
    return value


def _config_hash(config: dict) -> str:
    """Hash the effective generator arguments with a canonical JSON encoding."""
    effective = {
        key: _canonical_config_value(value)
        for key, value in config.items()
        if key not in CONFIG_HASH_EXCLUDED_FIELDS
    }
    serialized = json.dumps(effective, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def _shift_range(
    lo: float,
    hi: float,
    mean_shift_frac: float = 0.125,
    width_factor: float = 1.2,
    floor: float | None = None,
) -> tuple[float, float]:
    """Compute a shifted parameter range for anti-inverse-crime test sets.

    Parameters
    ----------
    lo, hi : float
        Original (train) range bounds.
    mean_shift_frac : float
        Fractional shift applied to the range midpoint (default 12.5%).
    width_factor : float
        Multiplicative expansion of the range width (default 1.2 = +20%).
    floor : float, optional
        Hard lower bound (e.g. 0.0 for non-negative quantities).

    Returns
    -------
    tuple[float, float]
        Shifted (lo, hi) range.
    """
    mean = (lo + hi) / 2.0
    width = hi - lo
    new_mean = mean * (1.0 + mean_shift_frac)
    new_width = width * width_factor
    new_lo = new_mean - new_width / 2.0
    new_hi = new_mean + new_width / 2.0
    if floor is not None:
        new_lo = max(new_lo, floor)
    return (new_lo, new_hi)


def _get_git_sha() -> str:
    """Get current git SHA ("-dirty" suffixed on uncommitted tracked changes).

    Untracked files (e.g. the generation log being written) do not count as
    dirty, matching ``git describe --dirty`` semantics. Returns 'unknown' if
    not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return "unknown"
        sha = result.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=5,
        )
        if status.returncode == 0 and status.stdout.strip():
            sha += "-dirty"
        return sha
    except Exception:
        return "unknown"


def _get_versions() -> tuple[str, str]:
    """Get SimOS and QuTiP version strings."""
    import qutip
    import simos
    return simos.__version__, qutip.__version__


def _sample_spherical_field(
    rng: np.random.Generator, b_mag_range_T: tuple[float, float]
) -> np.ndarray:
    """Sample a B-field vector uniformly on the sphere.

    Parameters
    ----------
    rng : np.random.Generator
        NumPy random generator for reproducibility.
    b_mag_range_T : tuple[float, float]
        (min, max) field magnitude in Tesla.

    Returns
    -------
    np.ndarray
        3-vector [Bx, By, Bz] in Tesla.
    """
    b_mag = rng.uniform(*b_mag_range_T)
    cos_theta = rng.uniform(-1.0, 1.0)
    phi = rng.uniform(0.0, 2 * np.pi)
    sin_theta = np.sqrt(1.0 - cos_theta * cos_theta)
    return np.array([
        b_mag * sin_theta * np.cos(phi),
        b_mag * sin_theta * np.sin(phi),
        b_mag * cos_theta,
    ])


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
    field_sampling: str = "z_only",
    b_mag_range_T: tuple[float, float] = (20e-6, 70e-6),
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

        if field_sampling == "spherical":
            B_vec = _sample_spherical_field(sp_rng, b_mag_range_T)
        else:
            Bz = sp_rng.uniform(*bz_range_T)
            B_vec = np.array([0.0, 0.0, Bz])

        adapter.config.temperature_K = T_K
        adapter.config.B_field_T = B_vec
        adapter.config.p1_concentration_ppm = p1

        freqs, signal, _ = corrupt_spectrum(
            adapter, adapter.config, b1_grad, b_perp, p1_ppm=p1
        )

        if freqs_out is None:
            freqs_out = freqs

        spectra[idx] = signal
        labels[idx] = B_vec
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
    field_sampling: str = "z_only",
    b_mag_range_T: tuple[float, float] = (20e-6, 70e-6),
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """Generate spectra for a split using OU stochastic trajectory sampling."""
    from nv_sensor_sim.physics.noise_injection import sample_ou_trajectory_pair

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

        if field_sampling == "spherical":
            B_vec = _sample_spherical_field(sp_rng, b_mag_range_T)
        else:
            Bz = sp_rng.uniform(*bz_range_T)
            B_vec = np.array([0.0, 0.0, Bz])

        adapter.config.temperature_K = T_K
        adapter.config.B_field_T = B_vec
        adapter.config.p1_concentration_ppm = p1

        freqs, signal, _ = corrupt_spectrum(
            adapter, adapter.config, b1_grad, b_perp,
            p1_ppm=p1, mw_power_scale=mw_power_scale,
        )

        if freqs_out is None:
            freqs_out = freqs

        spectra[idx] = signal
        labels[idx] = B_vec
        params[idx] = [p1, T_K, b1_grad, b_perp, mw_power_scale]

        if (idx + 1) % 100 == 0:
            print(f"  {split_name}: {idx + 1}/{n_split}")

    return spectra, labels, params, np.array(split_seeds), freqs_out


def _generate_split_multi_axis(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    split_seeds: list[int],
    p1_range_ppm: tuple[float, float],
    temp_range_K: tuple[float, float],
    b1_gradient_range: tuple[float, float],
    extra_b_perp_range_T: tuple[float, float],
    b_mag_range_T: tuple[float, float],
    n_freq_points: int,
    split_name: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """Generate vector-regime spectra: isotropic field sampling + 4-axis lineshape.

    Each spectrum samples an isotropic lab-frame B-field whose magnitude is
    drawn from ``b_mag_range_T`` (the bias-amplified regime, typically
    0.5-5 mT), then averages the spectrum over the 4 NV crystallographic axes.
    Labels are the total lab-frame field B_lab (what the geometry matrix A
    inverts to recover from the resonance residuals).
    """
    n_split = len(split_seeds)
    spectra = np.zeros((n_split, n_freq_points))
    labels = np.zeros((n_split, 3))
    params = np.zeros((n_split, 4))
    freqs_out = None

    print(f"Generating {n_split} spectra for {split_name} split (multi-axis)...")
    for idx, seed in enumerate(split_seeds):
        sp_rng = np.random.default_rng(seed)

        p1 = sp_rng.uniform(*p1_range_ppm)
        T_K = sp_rng.uniform(*temp_range_K)
        b1_grad = sp_rng.uniform(*b1_gradient_range)
        extra_b_perp = sp_rng.uniform(*extra_b_perp_range_T)

        # Isotropic direction on the sphere, magnitude from bias-regime range
        B_lab = _sample_spherical_field(sp_rng, b_mag_range_T)

        adapter.config.temperature_K = T_K
        adapter.config.p1_concentration_ppm = p1
        adapter.config.B_field_T = B_lab

        freqs, signal, _ = corrupt_spectrum_multi_axis(
            adapter,
            adapter.config,
            B_lab,
            b1_grad,
            extra_b_perp_T=extra_b_perp,
            p1_ppm=p1,
        )

        if freqs_out is None:
            freqs_out = freqs

        spectra[idx] = signal
        labels[idx] = B_lab
        params[idx] = [p1, T_K, b1_grad, extra_b_perp]

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
    field_sampling: str = "spherical",
    b_mag_range_T: tuple[float, float] = (20e-6, 70e-6),
    shift_test_ranges: bool = False,
    test_p1_range_ppm: tuple[float, float] | None = None,
    test_temp_range_K: tuple[float, float] | None = None,
    test_b1_gradient_range: tuple[float, float] | None = None,
    test_b_perp_range_T: tuple[float, float] | None = None,
    multi_axis_mode: bool = False,
    bias_B0_T: float = 0.0,
    bias_direction_uvw: tuple[float, float, float] = (0.0, 0.0, 1.0),
    concentrator_amplification: float = 1.0,
    magnet_drift_ppm_per_K: float = 0.0,
    bias_B0_range_T: tuple[float, float] | None = None,
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
        Axial B-field sampling range in Tesla (z_only mode).
    noise_mode : str
        Noise injection mode: "deterministic" (default), "stochastic", or "both".
    ou_noise_config : OUNoiseConfig, optional
        OU trajectory config. Required when noise_mode is "stochastic" or "both".
    field_sampling : str
        B-field sampling mode: "spherical" (uniform on sphere, default) or
        "z_only" (legacy z-axis only).
    b_mag_range_T : tuple[float, float]
        B-field magnitude range in Tesla (spherical mode only).
    shift_test_ranges : bool
        When True and no explicit test_*_range params are given, automatically
        shift test-set corruption parameter distributions (mean +12.5%,
        width +20%) to prevent inverse crime. Default False (backward compat).
    test_p1_range_ppm : tuple[float, float], optional
        Explicit P1 range for test split. Overrides auto-shift.
    test_temp_range_K : tuple[float, float], optional
        Explicit temperature range for test split. Overrides auto-shift.
    test_b1_gradient_range : tuple[float, float], optional
        Explicit B1 gradient range for test split. Overrides auto-shift.
    test_b_perp_range_T : tuple[float, float], optional
        Explicit transverse field range for test split. Overrides auto-shift.

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

    # Validate field_sampling
    try:
        field_sampling_enum = FieldSampling(field_sampling)
    except ValueError:
        valid = ", ".join(f'"{m.value}"' for m in FieldSampling)
        raise ValueError(f"Invalid field_sampling='{field_sampling}'. Must be one of: {valid}")

    # In spherical mode, override b_perp to (0, 0) — transverse field is in B_field_T
    if field_sampling_enum == FieldSampling.SPHERICAL:
        b_perp_range_T = (0.0, 0.0)

    if noise_mode_enum in (NoiseMode.STOCHASTIC, NoiseMode.BOTH) and ou_noise_config is None:
        raise ValueError(
            f"ou_noise_config is required when noise_mode='{noise_mode}'"
        )

    # --- Anti-inverse-crime: compute test-split parameter ranges ---
    # Explicit overrides take precedence, then auto-shift, then same as train.
    has_any_test_override = any(
        r is not None for r in (
            test_p1_range_ppm, test_temp_range_K,
            test_b1_gradient_range, test_b_perp_range_T,
        )
    )
    inverse_crime_active = shift_test_ranges or has_any_test_override

    if test_p1_range_ppm is None and shift_test_ranges:
        test_p1_range_ppm = _shift_range(*p1_range_ppm, floor=0.0)
    if test_temp_range_K is None and shift_test_ranges:
        test_temp_range_K = _shift_range(*temp_range_K, floor=0.0)
    if test_b1_gradient_range is None and shift_test_ranges:
        test_b1_gradient_range = _shift_range(*b1_gradient_range, floor=0.0)
    if test_b_perp_range_T is None and shift_test_ranges:
        # In spherical mode b_perp is always (0,0); don't shift zeros.
        if b_perp_range_T != (0.0, 0.0):
            test_b_perp_range_T = _shift_range(*b_perp_range_T, floor=0.0)

    # Effective test ranges (fall back to train ranges when not shifted)
    eff_test_p1 = test_p1_range_ppm if test_p1_range_ppm is not None else p1_range_ppm
    eff_test_temp = test_temp_range_K if test_temp_range_K is not None else temp_range_K
    eff_test_b1 = test_b1_gradient_range if test_b1_gradient_range is not None else b1_gradient_range
    eff_test_bperp = test_b_perp_range_T if test_b_perp_range_T is not None else b_perp_range_T

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

    # Temperature range for manifest
    if noise_mode_enum == NoiseMode.DETERMINISTIC:
        manifest_temp_range = temp_range_K
    else:
        assert ou_noise_config is not None
        sigma_stat = ou_noise_config.sigma_T / np.sqrt(2 * ou_noise_config.theta_T)
        if ou_noise_config.alpha_B1 != 0.0:
            # Cascaded mode: orbital baseline + OU fluctuation
            T_mean_K = ou_noise_config.T_mean_C + 273.15
            manifest_temp_range = (
                T_mean_K - ou_noise_config.delta_T_orb_C - 3 * sigma_stat,
                T_mean_K + ou_noise_config.delta_T_orb_C + 3 * sigma_stat,
            )
        else:
            # Legacy: stationary distribution around mu_T
            manifest_temp_range = (
                ou_noise_config.mu_T - 3 * sigma_stat,
                ou_noise_config.mu_T + 3 * sigma_stat,
            )

    # Serialize OU params for manifest
    ou_params_dict = (
        dataclasses.asdict(ou_noise_config) if ou_noise_config is not None else None
    )

    # Multi-axis (vector-readiness) mode: bias-amplified regime, isotropic field
    # sampling with magnitudes covering ~0.5-5 mT (union of Path A magnet + Path B
    # concentrator operational ranges). When enabled, b_mag_range_T defaults to
    # bias_B0_range_T (if supplied) so the spectrum samples the bias regime.
    if multi_axis_mode:
        if field_sampling_enum != FieldSampling.SPHERICAL:
            raise ValueError(
                "multi_axis_mode requires field_sampling='spherical' to draw "
                "isotropic bias-regime fields"
            )
        if bias_B0_range_T is not None:
            b_mag_range_T = bias_B0_range_T

    # Capture every generator argument after field and test-range overrides.
    effective_values = locals()
    config_hash = _config_hash({
        name: effective_values[name]
        for name in inspect.signature(generate_dataset).parameters
    })

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
        field_sampling=field_sampling,
        b_mag_range_T=b_mag_range_T if field_sampling == "spherical" else None,
        # Anti-inverse-crime: test-specific ranges (None when same as train)
        inverse_crime_shift=inverse_crime_active,
        test_p1_concentration_range_ppm=test_p1_range_ppm,
        test_temperature_range_K=test_temp_range_K,
        test_b1_gradient_range=test_b1_gradient_range,
        test_b_perp_range_T=test_b_perp_range_T,
        # Vector-readiness metadata
        multi_axis_mode=multi_axis_mode,
        bias_B0_T=bias_B0_T,
        bias_direction_uvw=bias_direction_uvw,
        concentrator_amplification=concentrator_amplification,
        magnet_drift_ppm_per_K=magnet_drift_ppm_per_K,
        bias_B0_range_T=bias_B0_range_T,
    )
    manifest.validate()

    writer = DatasetWriter(Path(output_dir))
    written_arrays: dict[str, np.ndarray] = {}

    def write_spectra(spectra, frequencies, labels, params, seeds, split):
        writer.write_spectra(spectra, frequencies, labels, params, seeds, split)
        for key, array in (
            ("spectra", spectra), ("frequencies", frequencies),
            ("labels", labels), ("corruption_params", params), ("seeds", seeds),
        ):
            written_arrays[f"{split}/{key}"] = array

    # Base config — per-spectrum params will be overridden
    config = SimulationConfig(
        random_seed=master_seed,
        use_optics=False,
        include_nitrogen=False,
        n_freq_points=n_freq_points,
        mw_freq_range_Hz=freq_range_Hz,
    )
    adapter = SimOSAdapter(config)

    # Per-split parameter ranges: test uses shifted ranges when active
    split_ranges: dict[str, dict] = {}
    train_val_kwargs = dict(
        p1_range_ppm=p1_range_ppm,
        b1_gradient_range=b1_gradient_range,
        b_perp_range_T=b_perp_range_T,
        bz_range_T=bz_range_T,
        n_freq_points=n_freq_points,
        field_sampling=field_sampling,
        b_mag_range_T=b_mag_range_T,
    )
    test_kwargs = dict(
        p1_range_ppm=eff_test_p1,
        b1_gradient_range=eff_test_b1,
        b_perp_range_T=eff_test_bperp,
        bz_range_T=bz_range_T,
        n_freq_points=n_freq_points,
        field_sampling=field_sampling,
        b_mag_range_T=b_mag_range_T,
    )
    split_ranges["train"] = train_val_kwargs
    split_ranges["val"] = train_val_kwargs
    split_ranges["test"] = test_kwargs

    splits = [
        ("train", train_seeds),
        ("val", val_seeds),
        ("test", test_seeds),
    ]

    for split_name, split_seeds in splits:
        if len(split_seeds) == 0:
            continue

        kwargs = split_ranges[split_name]
        split_temp = eff_test_temp if split_name == "test" else temp_range_K

        if multi_axis_mode:
            # Vector-readiness path: 4-axis ensemble, isotropic bias-regime field.
            # In multi-axis mode b_perp acts as *extra* residual transverse field
            # beyond the geometric per-axis projection of B_lab.
            spectra, labels, params, seed_arr, freqs = _generate_split_multi_axis(
                adapter, config, split_seeds,
                p1_range_ppm=kwargs["p1_range_ppm"],
                temp_range_K=split_temp,
                b1_gradient_range=kwargs["b1_gradient_range"],
                extra_b_perp_range_T=kwargs["b_perp_range_T"],
                b_mag_range_T=kwargs["b_mag_range_T"],
                n_freq_points=kwargs["n_freq_points"],
                split_name=split_name,
            )
            write_spectra(spectra, freqs, labels, params, seed_arr, split_name)
            continue

        if noise_mode_enum == NoiseMode.DETERMINISTIC:
            spectra, labels, params, seed_arr, freqs = _generate_split_deterministic(
                adapter, config, split_seeds,
                temp_range_K=split_temp,
                split_name=split_name,
                **kwargs,
            )
            write_spectra(spectra, freqs, labels, params, seed_arr, split_name)

        elif noise_mode_enum == NoiseMode.STOCHASTIC:
            assert ou_noise_config is not None
            spectra, labels, params, seed_arr, freqs = _generate_split_stochastic(
                adapter, config, split_seeds,
                ou_noise_config=ou_noise_config,
                ou_trajectory_seed=ou_traj_seeds[split_name],
                split_name=split_name,
                **kwargs,
            )
            write_spectra(spectra, freqs, labels, params, seed_arr, split_name)

        elif noise_mode_enum == NoiseMode.BOTH:
            assert ou_noise_config is not None  # guaranteed by ValueError above; narrows type
            # Deterministic pass
            s_det, l_det, p_det, sd_det, f_det = _generate_split_deterministic(
                adapter, config, split_seeds,
                temp_range_K=split_temp,
                split_name=f"{split_name}_deterministic",
                **kwargs,
            )
            write_spectra(
                s_det, f_det, l_det, p_det, sd_det, f"{split_name}_deterministic"
            )

            # Stochastic pass (same spectrum seeds → paired by index)
            s_sto, l_sto, p_sto, sd_sto, f_sto = _generate_split_stochastic(
                adapter, config, split_seeds,
                ou_noise_config=ou_noise_config,
                ou_trajectory_seed=ou_traj_seeds[split_name],
                split_name=f"{split_name}_stochastic",
                **kwargs,
            )
            write_spectra(
                s_sto, f_sto, l_sto, p_sto, sd_sto, f"{split_name}_stochastic"
            )

    manifest.data_md5 = content_md5(written_arrays)
    writer.write_manifest(manifest)
    output_path = writer.finalize()
    print(f"Dataset written to {output_path}")
    return output_path


if __name__ == "__main__":
    generate_dataset("./data/synthetic_v1")
