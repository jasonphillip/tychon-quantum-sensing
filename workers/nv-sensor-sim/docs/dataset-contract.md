# Dataset Manifest Contract

Every generated dataset MUST include a manifest with the following fields. This contract defines what downstream ML consumers expect from the simulator.

## Required Manifest Fields

### Provenance
- `generator_git_sha` — Git SHA of the generator code
- `config_hash` — Hash of the simulation config used
- `simos_version` — SimOS version string
- `qutip_version` — QuTiP version string
- `backend` — Backend used (e.g. "qutip", "numpy")
- `generated_at` — ISO 8601 timestamp

### Random Seeds
- `master_seed` — Master random seed
- `train_seeds` — Per-spectrum seeds for training split
- `val_seeds` — Per-spectrum seeds for validation split
- `test_seeds` — Per-spectrum seeds for test split

### Split Definitions
- `n_spectra_train`, `n_spectra_val`, `n_spectra_test` — Split sizes
- `train_indices`, `val_indices`, `test_indices` — Index lists

### Spectral Resolution
- `n_freq_points` — Frequency points per spectrum
- `freq_range_Hz` — Sweep range (start, stop) in Hz

### Corruption Parameter Ranges (Train/Val)
- `p1_concentration_range_ppm` — P1 concentration range in ppm
- `temperature_range_K` — Temperature range in Kelvin
- `b1_gradient_range` — B1 gradient fraction range
- `b_perp_range_T` — Transverse field range in Tesla

### Anti-Inverse-Crime: Test-Specific Ranges
- `inverse_crime_shift` — Boolean flag: whether test-split distributions are shifted
- `test_p1_concentration_range_ppm` — Test P1 range (null when same as train)
- `test_temperature_range_K` — Test temperature range (null when same as train)
- `test_b1_gradient_range` — Test B1 gradient range (null when same as train)
- `test_b_perp_range_T` — Test transverse field range (null when same as train)

When `inverse_crime_shift` is true, the test split draws corruption parameters from
shifted distributions (default: mean +12.5%, width +20%) so the model is evaluated
on out-of-training-distribution conditions. This prevents the "inverse crime" where
train and test data share identical generative distributions.

Callers can also supply explicit test ranges for full control (e.g., to shift only
temperature while keeping P1 the same).

### Units
- `units` — Dictionary mapping quantity names to SI unit strings

## Train/Test Data Separation Protocol

**Two-layer separation:**

1. **Seed separation (always enforced):** Train, val, and test splits use pairwise
   disjoint random seeds. Enforced at generation time (`replace=False`) and validated
   by `DatasetManifest.validate()`, which raises `ValueError` on any overlap.

2. **Distribution separation (opt-in):** When `shift_test_ranges=True` is passed to
   `generate_dataset()`, or when explicit `test_*_range` parameters are provided, the
   test split samples corruption parameters from shifted distributions. The manifest
   records the exact test ranges used.

Default behavior (backward compatible): all splits share the same parameter ranges;
only seeds differ.

## File Format

- HDF5 (`.h5`) with JSON sidecar manifest, OR
- Numpy compressed (`.npz`) per split with JSON sidecar manifest

### HDF5 Layout

```
/{split}/spectra          — shape (N, n_freq_points)
/{split}/frequencies      — shape (n_freq_points,)
/{split}/labels           — shape (N, 3)  [B-field vector ground truth]
/{split}/corruption_params — shape (N, 4)  [p1, T, b1_grad, b_perp]
/{split}/seeds            — shape (N,)    [per-spectrum seeds]
```

## Schema Implementation

See `src/nv_sensor_sim/datasets/schema.py` for the `DatasetManifest` dataclass and validation logic.
