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
    backend: str = "qutip"
    generated_at: str = ""

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
        }
    )

    def to_dict(self) -> dict:
        """Convert manifest to dictionary."""
        d = asdict(self)
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

        # Validate b_mag_range_T if spherical mode
        if self.field_sampling == "spherical" and self.b_mag_range_T is not None:
            lo, hi = self.b_mag_range_T
            if lo > hi:
                raise ValueError(f"b_mag_range_T: min ({lo}) > max ({hi})")
