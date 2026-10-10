"""Dataset manifest schema for ODMR synthetic datasets.

The manifest is the data contract between the simulator and downstream ML
consumers. Every generated dataset MUST include a manifest
with provenance, seeds, splits, units, and corruption parameter ranges.

Critical: Train/test seed separation is enforced at the manifest level.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class DatasetManifest:
    """Manifest for a generated ODMR dataset. Consumed by downstream ML training pipelines.

    Parameters
    ----------
    generator_git_sha : str
        Git SHA of the generator code.
    config_hash : str
        Hash of the simulation config used.
    simos_version : str
        SimOS version string.
    qutip_version : str
        QuTiP version string.
    backend : str
        Backend used (e.g. "qutip", "numpy").
    generated_at : str
        ISO 8601 timestamp of generation.
    master_seed : int
        Master random seed.
    train_seeds : list[int]
        Per-spectrum seeds for training split.
    val_seeds : list[int]
        Per-spectrum seeds for validation split.
    test_seeds : list[int]
        Per-spectrum seeds for test split.
    n_spectra_train : int
        Number of training spectra.
    n_spectra_val : int
        Number of validation spectra.
    n_spectra_test : int
        Number of test spectra.
    train_indices : list[int]
        Index list for training split.
    val_indices : list[int]
        Index list for validation split.
    test_indices : list[int]
        Index list for test split.
    n_freq_points : int
        Number of frequency points per spectrum.
    freq_range_Hz : tuple[float, float]
        Frequency sweep range in Hz.
    p1_concentration_range_ppm : tuple[float, float]
        P1 concentration range used in ppm.
    temperature_range_K : tuple[float, float]
        Temperature range used in Kelvin.
    b1_gradient_range : tuple[float, float]
        B1 gradient fraction range.
    b_perp_range_T : tuple[float, float]
        Transverse field range in Tesla.
    units : dict[str, str]
        SI units for all quantities.
    """

    # Provenance
    generator_git_sha: str = ""
    config_hash: str = ""
    simos_version: str = ""
    qutip_version: str = ""
    # numpy version ("" on older manifests): the per-sequence seed streams
    # depend on numpy's Generator implementation, so bit-exact reproduction
    # needs the same numpy.
    numpy_version: str = ""
    backend: str = "qutip"
    generated_at: str = ""
    # Shared data-contract version tag. Empty for legacy/static datasets; the
    # time-series generator writes "v1". Additive — consumers accept it if present.
    contract_version: str = ""

    # Random seeds
    master_seed: int = 0
    train_seeds: list[int] = field(default_factory=list)
    val_seeds: list[int] = field(default_factory=list)
    test_seeds: list[int] = field(default_factory=list)

    # Split definitions
    n_spectra_train: int = 0
    n_spectra_val: int = 0
    n_spectra_test: int = 0
    train_indices: list[int] = field(default_factory=list)
    val_indices: list[int] = field(default_factory=list)
    test_indices: list[int] = field(default_factory=list)

    # Spectral resolution
    n_freq_points: int = 100
    freq_range_Hz: tuple[float, float] = (2.82e9, 2.92e9)

    # Corruption parameter ranges (train/val)
    p1_concentration_range_ppm: tuple[float, float] = (1.0, 300.0)
    temperature_range_K: tuple[float, float] = (280.0, 320.0)
    b1_gradient_range: tuple[float, float] = (0.05, 0.30)
    b_perp_range_T: tuple[float, float] = (0.0, 50e-6)

    # Anti-inverse-crime: shifted test-set parameter ranges
    # When non-None, test split uses these ranges instead of the train ranges.
    test_p1_concentration_range_ppm: tuple[float, float] | None = None
    test_temperature_range_K: tuple[float, float] | None = None
    test_b1_gradient_range: tuple[float, float] | None = None
    test_b_perp_range_T: tuple[float, float] | None = None
    inverse_crime_shift: bool = False

    # Field sampling mode and magnitude range
    field_sampling: str = "z_only"
    b_mag_range_T: tuple[float, float] | None = None
    labels_are: str | None = None

    # Vector-readiness: bias-field configuration (Path A magnet vs Path B concentrator).
    # bias_B0_T=0.0 + concentrator_amplification=1.0 + magnet_drift_ppm_per_K=0.0 reproduces
    # the legacy scalar regime, so older manifests without these keys load identically.
    bias_B0_T: float = 0.0
    bias_direction_uvw: tuple[float, float, float] = (0.0, 0.0, 1.0)
    concentrator_amplification: float = 1.0
    magnet_drift_ppm_per_K: float = 0.0
    bias_B0_range_T: tuple[float, float] | None = None
    multi_axis_mode: bool = False

    # Time-series (sequence) mode: per-frame ODMR over a swept field where the
    # resonances move and cross. sequence_mode=False (default) is the static
    # single-frame regime, so existing static manifests load unchanged.
    sequence_mode: bool = False
    n_timesteps: int = 0  # T frames per sequence
    dt_s: float = 0.0  # time between frames (seconds)
    n_lines: int = 8  # L resonances (8 electronic; 24 with 14N hyperfine)
    hyperfine: bool = False  # 14N hyperfine triplet on each electronic line
    linewidth_Hz: float = 0.0  # Gamma (FWHM) used for collision labelling
    collision_threshold_linewidths: float = 1.0  # k in the |f_i - f_j| < k*Gamma rule
    sweep_description: str = ""  # free-text description of the field sweep
    # Per-split label statistics (crossing counts, collision dwell, near-merge
    # margins) computed from the rendered labels at generation time. Additive:
    # None for static datasets and older sequence manifests.
    sequence_stats: dict | None = None
    # Structured sweep-geometry fields (sequence datasets). Additive: empty/None
    # on static datasets and older sequence manifests; sweep_description keeps
    # the human-readable prose.
    sweep_mode: str = ""  # "fixed" | "isotropic" ("" for static datasets)
    sweep_scalar_range_T: tuple[float, float] | None = None  # isotropic endpoint scalars
    min_sweep_delta_T: float | None = None  # isotropic minimum |s_end - s_start|
    min_ramp_window_frac: float | None = None  # isotropic minimum ramp-window fraction
    min_axis_projection_T: float | None = None  # reject ramps below this |B . n_i|
    n_ramp_resamples: int = 0  # total geometries rejected by the projection guard
    ramp_start_T: tuple[float, float, float] | None = None  # fixed-mode endpoints
    ramp_end_T: tuple[float, float, float] | None = None
    jitter_frac: float | None = None  # per-sequence endpoint jitter fraction
    # Rendered (power-broadened) linewidth alongside the labeling linewidth:
    # Gamma_rendered = linewidth_Hz * sqrt(1 + s0 * mw_scale^2) at mw_scale=1.
    # Collision labels use the intrinsic linewidth_Hz (includes intra-axis pairs).
    linewidth_rendered_Hz: float | None = None
    mw_saturation_s0: float | None = None
    # Per-axis MW polarization projection: Rabi-amplitude factors per NV axis
    # (contrast follows via saturation; identical contrast is the maximally
    # ambiguous case). Optional slow per-sequence drift (stationary AR(1) with
    # fractional std / correlation time in frames), seeded per sequence.
    axis_contrast_scale: tuple[float, ...] | None = None
    axis_contrast_drift_std: float | None = None
    axis_contrast_drift_tau_frames: float | None = None
    # Reference per-line dip depths (geometry-matrix order, averaged-spectrum
    # units) measured at the bias-only field with nominal scales, no drift.
    line_depths: list[float] | None = None
    # Per-sequence trajectory-family mixture (isotropic sweeps): normalized
    # weights keyed "held" / "reversal" / "ou". Per-sequence assignments and
    # stratified summaries live in sequence_stats; None = 100% held ramps.
    trajectory_family_weights: dict | None = None
    reversal_turn_frac_range: tuple[float, float] | None = None
    field_ou_sigma_T: float | None = None  # OU field perturbation std (Tesla)
    field_ou_tau_frames: float | None = None  # OU correlation time (frames)

    # v3 widened-envelope keys (sweep_mode="isotropic_widened"). Additive: None on
    # all prior lineages. min_field_T is the hard per-frame |B| floor (Tesla);
    # directed_fraction is the share of sequences drawn from the directed
    # merge-crossing sub-population (aimed at the cross-axis failure geometries);
    # directed_approach_lw_range is that sub-population's pre-merge separation
    # range (linewidths); offbias_angle_target_deg records the widened cone target;
    # window_margin_frac is the safety margin (fraction of the half-window) the
    # window-containment guard keeps below the pinned grid edge.
    min_field_T: float | None = None
    directed_fraction: float | None = None
    directed_approach_lw_range: tuple[float, float] | None = None
    offbias_angle_target_deg: float | None = None
    window_margin_frac: float | None = None
    # Angle-stratified widening law (Amendment 1 Option A). Records the training
    # DENSITY change vs v1/v2 isotropic sampling — the off-bias angle draw law, the
    # |B| draw law, the cold-start fraction, and carry parameters — so increment-6
    # coverage attribution is reproducible. None on all prior lineages.
    stratification_law: dict | None = None

    # Optional physics-cue knobs (dwell lineage). Additive: None on all existing
    # lineages, which therefore load unchanged. axis_offsets_hz is a per-axis
    # static strain / E-field ZFS offset ladder (Hz, common-mode per axis, split
    # preserved); nv_density_ppm drives the NV-NV cross-relaxation PL feature.
    axis_offsets_hz: tuple[float, ...] | None = None
    nv_density_ppm: float | None = None
    # md5 of the dataset HDF5 payload (set after the arrays are written).
    data_md5: str | None = None

    # Noise mode and OU parameters
    noise_mode: str = "deterministic"
    ou_params: dict | None = None  # OUNoiseConfig as dict, None for deterministic

    # Units (SI, explicit)
    units: dict[str, str] = field(
        default_factory=lambda: {
            "frequency": "Hz",
            "magnetic_field": "T",
            "temperature": "K",
            "p1_concentration": "ppm",
            "b1_gradient": "fraction",
            "b_perp": "T",
            "mw_power_scale": "dimensionless",
            "time": "s",
            "bias_field": "T",
            "bias_direction": "unit_vector",
            "concentrator_amplification": "dimensionless",
            "magnet_drift": "ppm/K",
            "resonance_frequency": "Hz",
            "linewidth": "Hz",
        }
    )

    def to_dict(self) -> dict:
        """Convert manifest to dictionary."""
        d = asdict(self)
        if d["labels_are"] is None:
            del d["labels_are"]
        # Convert tuples to lists for JSON serialization
        for key in (
            "freq_range_Hz",
            "p1_concentration_range_ppm",
            "temperature_range_K",
            "b1_gradient_range",
            "b_perp_range_T",
        ):
            d[key] = list(d[key])
        if d.get("b_mag_range_T") is not None:
            d["b_mag_range_T"] = list(d["b_mag_range_T"])
        # Shifted test ranges (None when not active)
        for key in (
            "test_p1_concentration_range_ppm",
            "test_temperature_range_K",
            "test_b1_gradient_range",
            "test_b_perp_range_T",
        ):
            if d.get(key) is not None:
                d[key] = list(d[key])
        # Bias-field vector and range (always serialize direction as list)
        d["bias_direction_uvw"] = list(d["bias_direction_uvw"])
        if d.get("bias_B0_range_T") is not None:
            d["bias_B0_range_T"] = list(d["bias_B0_range_T"])
        # Sweep-geometry / contrast / family tuples (None when not applicable)
        for key in (
            "sweep_scalar_range_T",
            "ramp_start_T",
            "ramp_end_T",
            "axis_contrast_scale",
            "reversal_turn_frac_range",
            "axis_offsets_hz",
            "directed_approach_lw_range",
        ):
            if d.get(key) is not None:
                d[key] = list(d[key])
        return d

    def to_json(self, path: str | Path) -> None:
        """Write manifest to JSON file.

        Parameters
        ----------
        path : str or Path
            Output file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: str | Path) -> DatasetManifest:
        """Load manifest from JSON file.

        Parameters
        ----------
        path : str or Path
            Input file path.

        Returns
        -------
        DatasetManifest
            Loaded manifest instance.
        """
        with open(path) as f:
            d = json.load(f)

        # Convert lists back to tuples for tuple fields
        for key in (
            "freq_range_Hz",
            "p1_concentration_range_ppm",
            "temperature_range_K",
            "b1_gradient_range",
            "b_perp_range_T",
        ):
            if key in d:
                d[key] = tuple(d[key])

        # Backward compat: older manifests lack noise fields
        d.setdefault("noise_mode", "deterministic")
        d.setdefault("ou_params", None)
        d.setdefault("field_sampling", "z_only")
        d.setdefault("b_mag_range_T", None)
        d.setdefault("labels_are", None)

        # Backward compat: older manifests lack inverse-crime fields
        d.setdefault("test_p1_concentration_range_ppm", None)
        d.setdefault("test_temperature_range_K", None)
        d.setdefault("test_b1_gradient_range", None)
        d.setdefault("test_b_perp_range_T", None)
        d.setdefault("inverse_crime_shift", False)

        # Convert b_mag_range_T list back to tuple if present
        if d.get("b_mag_range_T") is not None:
            d["b_mag_range_T"] = tuple(d["b_mag_range_T"])

        # Convert test range lists back to tuples if present
        for key in (
            "test_p1_concentration_range_ppm",
            "test_temperature_range_K",
            "test_b1_gradient_range",
            "test_b_perp_range_T",
        ):
            if d.get(key) is not None:
                d[key] = tuple(d[key])

        # Backward compat: bias-field fields (zero-bias scalar default = previous behavior)
        d.setdefault("bias_B0_T", 0.0)
        d.setdefault("bias_direction_uvw", [0.0, 0.0, 1.0])
        d.setdefault("concentrator_amplification", 1.0)
        d.setdefault("magnet_drift_ppm_per_K", 0.0)
        d.setdefault("bias_B0_range_T", None)
        d.setdefault("multi_axis_mode", False)
        # Direction is a length-3 tuple; range (if present) is a length-2 tuple
        d["bias_direction_uvw"] = tuple(d["bias_direction_uvw"])
        if d.get("bias_B0_range_T") is not None:
            d["bias_B0_range_T"] = tuple(d["bias_B0_range_T"])

        # Backward compat: time-series (sequence) fields (static default = previous behavior)
        d.setdefault("contract_version", "")
        d.setdefault("sequence_mode", False)
        d.setdefault("n_timesteps", 0)
        d.setdefault("dt_s", 0.0)
        d.setdefault("n_lines", 8)
        d.setdefault("hyperfine", False)
        d.setdefault("linewidth_Hz", 0.0)
        d.setdefault("collision_threshold_linewidths", 1.0)
        d.setdefault("sweep_description", "")
        d.setdefault("sequence_stats", None)

        # Backward compat: structured sweep-geometry / linewidth / provenance fields
        d.setdefault("numpy_version", "")
        d.setdefault("sweep_mode", "")
        d.setdefault("sweep_scalar_range_T", None)
        d.setdefault("min_sweep_delta_T", None)
        d.setdefault("min_ramp_window_frac", None)
        d.setdefault("min_axis_projection_T", None)
        d.setdefault("n_ramp_resamples", 0)
        d.setdefault("ramp_start_T", None)
        d.setdefault("ramp_end_T", None)
        d.setdefault("jitter_frac", None)
        d.setdefault("linewidth_rendered_Hz", None)
        d.setdefault("mw_saturation_s0", None)
        d.setdefault("axis_contrast_scale", None)
        d.setdefault("axis_contrast_drift_std", None)
        d.setdefault("axis_contrast_drift_tau_frames", None)
        d.setdefault("line_depths", None)
        d.setdefault("trajectory_family_weights", None)
        d.setdefault("reversal_turn_frac_range", None)
        d.setdefault("field_ou_sigma_T", None)
        d.setdefault("field_ou_tau_frames", None)
        # Dwell-lineage optional keys (None/absent on all prior lineages).
        d.setdefault("axis_offsets_hz", None)
        d.setdefault("nv_density_ppm", None)
        d.setdefault("data_md5", None)
        # v3 widened-envelope keys (None/absent on all prior lineages).
        d.setdefault("min_field_T", None)
        d.setdefault("directed_fraction", None)
        d.setdefault("directed_approach_lw_range", None)
        d.setdefault("offbias_angle_target_deg", None)
        d.setdefault("window_margin_frac", None)
        d.setdefault("stratification_law", None)
        for key in (
            "sweep_scalar_range_T",
            "ramp_start_T",
            "ramp_end_T",
            "axis_contrast_scale",
            "reversal_turn_frac_range",
            "axis_offsets_hz",
            "directed_approach_lw_range",
        ):
            if d.get(key) is not None:
                d[key] = tuple(d[key])

        return cls(**d)

    def validate(self) -> None:
        """Validate manifest completeness and train/test seed separation.

        Raises
        ------
        ValueError
            If manifest is incomplete or train/test seeds overlap.
        """
        # Check seed counts match split sizes
        if len(self.train_seeds) != self.n_spectra_train:
            raise ValueError(
                f"train_seeds length ({len(self.train_seeds)}) != "
                f"n_spectra_train ({self.n_spectra_train})"
            )
        if len(self.val_seeds) != self.n_spectra_val:
            raise ValueError(
                f"val_seeds length ({len(self.val_seeds)}) != n_spectra_val ({self.n_spectra_val})"
            )
        if len(self.test_seeds) != self.n_spectra_test:
            raise ValueError(
                f"test_seeds length ({len(self.test_seeds)}) != "
                f"n_spectra_test ({self.n_spectra_test})"
            )

        # CRITICAL: train/val/test seed separation (pairwise disjoint)
        train_set = set(self.train_seeds)
        val_set = set(self.val_seeds)
        test_set = set(self.test_seeds)

        if train_set & test_set:
            raise ValueError(f"Train/test seed overlap detected! Seeds: {train_set & test_set}")
        if train_set & val_set:
            raise ValueError(f"Train/val seed overlap detected! Seeds: {train_set & val_set}")
        if val_set & test_set:
            raise ValueError(f"Val/test seed overlap detected! Seeds: {val_set & test_set}")

        # Check index counts
        if len(self.train_indices) != self.n_spectra_train:
            raise ValueError(
                f"train_indices length ({len(self.train_indices)}) != "
                f"n_spectra_train ({self.n_spectra_train})"
            )
        if len(self.val_indices) != self.n_spectra_val:
            raise ValueError(
                f"val_indices length ({len(self.val_indices)}) != "
                f"n_spectra_val ({self.n_spectra_val})"
            )
        if len(self.test_indices) != self.n_spectra_test:
            raise ValueError(
                f"test_indices length ({len(self.test_indices)}) != "
                f"n_spectra_test ({self.n_spectra_test})"
            )

        # Check units are all present
        required_units = {"frequency", "magnetic_field", "temperature"}
        missing = required_units - set(self.units.keys())
        if missing:
            raise ValueError(f"Missing required units: {missing}")

        # Check parameter ranges are valid (min < max)
        for name, (lo, hi) in [
            ("freq_range_Hz", self.freq_range_Hz),
            ("p1_concentration_range_ppm", self.p1_concentration_range_ppm),
            ("temperature_range_K", self.temperature_range_K),
            ("b1_gradient_range", self.b1_gradient_range),
            ("b_perp_range_T", self.b_perp_range_T),
        ]:
            if lo > hi:
                raise ValueError(f"{name}: min ({lo}) > max ({hi})")

        # Validate shifted test ranges (when present)
        for name, rng in [
            ("test_p1_concentration_range_ppm", self.test_p1_concentration_range_ppm),
            ("test_temperature_range_K", self.test_temperature_range_K),
            ("test_b1_gradient_range", self.test_b1_gradient_range),
            ("test_b_perp_range_T", self.test_b_perp_range_T),
        ]:
            if rng is not None:
                lo, hi = rng
                if lo > hi:
                    raise ValueError(f"{name}: min ({lo}) > max ({hi})")

        if self.field_sampling == "bias_plus_ambient":
            if self.bias_B0_T <= 0.0:
                raise ValueError("bias_plus_ambient requires bias_B0_T > 0")
            if self.b_mag_range_T is None:
                raise ValueError("bias_plus_ambient requires b_mag_range_T")

        # Validate sampled spherical magnitude range.
        if self.field_sampling in ("spherical", "bias_plus_ambient") and self.b_mag_range_T is not None:
            lo, hi = self.b_mag_range_T
            if lo > hi:
                raise ValueError(f"b_mag_range_T: min ({lo}) > max ({hi})")
            if self.field_sampling == "bias_plus_ambient" and lo < 0.0:
                raise ValueError("b_mag_range_T lower bound must be non-negative")

        # Validate bias-field configuration
        if self.bias_B0_T < 0.0:
            raise ValueError(f"bias_B0_T must be non-negative, got {self.bias_B0_T}")
        if self.concentrator_amplification < 0.0:
            raise ValueError(
                f"concentrator_amplification must be non-negative, got "
                f"{self.concentrator_amplification}"
            )
        if len(self.bias_direction_uvw) != 3:
            raise ValueError(
                f"bias_direction_uvw must be a 3-vector, got length {len(self.bias_direction_uvw)}"
            )
        if self.bias_B0_range_T is not None:
            lo, hi = self.bias_B0_range_T
            if lo > hi:
                raise ValueError(f"bias_B0_range_T: min ({lo}) > max ({hi})")
            if lo < 0.0:
                raise ValueError(f"bias_B0_range_T lower bound must be non-negative, got {lo}")

        # Validate time-series (sequence) configuration
        if self.sequence_mode:
            if self.n_timesteps <= 0:
                raise ValueError(f"sequence_mode requires n_timesteps > 0, got {self.n_timesteps}")
            if self.dt_s <= 0.0:
                raise ValueError(f"sequence_mode requires dt_s > 0, got {self.dt_s}")
            if self.linewidth_Hz <= 0.0:
                raise ValueError(
                    f"sequence_mode requires linewidth_Hz > 0, got {self.linewidth_Hz}"
                )
            if self.collision_threshold_linewidths <= 0.0:
                raise ValueError(
                    "sequence_mode requires collision_threshold_linewidths > 0, got "
                    f"{self.collision_threshold_linewidths}"
                )
            expected_lines = 24 if self.hyperfine else 8
            if self.n_lines != expected_lines:
                raise ValueError(
                    f"n_lines ({self.n_lines}) inconsistent with hyperfine="
                    f"{self.hyperfine} (expected {expected_lines})"
                )
            if self.sweep_scalar_range_T is not None:
                lo, hi = self.sweep_scalar_range_T
                if lo >= hi:
                    raise ValueError(f"sweep_scalar_range_T: min ({lo}) >= max ({hi})")
            if self.n_ramp_resamples < 0:
                raise ValueError(
                    f"n_ramp_resamples must be non-negative, got {self.n_ramp_resamples}"
                )
