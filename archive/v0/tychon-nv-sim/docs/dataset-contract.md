# Dataset Manifest Contract

*Extracted from Section 3.4 of the architecture decisions document.*

Every generated dataset MUST include a manifest with the following fields. This contract defines what Repo 2 (`tychon-odmr-ml`) expects from Repo 1.

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

### Corruption Parameter Ranges
- `p1_concentration_range_ppm` — P1 concentration range in ppm
- `temperature_range_K` — Temperature range in Kelvin
- `b1_gradient_range` — B1 gradient fraction range
- `b_perp_range_T` — Transverse field range in Tesla

### Units
- `units` — Dictionary mapping quantity names to SI unit strings

## Train/Test Data Separation Protocol

**Critical:** Train seeds MUST NOT overlap with test seeds. This is enforced by `DatasetManifest.validate()`.

- Training set uses one set of random seeds and corruption parameter distributions
- Test set uses DIFFERENT random seeds AND can use DIFFERENT noise parameter distributions (shifted means, wider variance)
- This separation is enforced at the manifest level and documented explicitly

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

See `src/tychon_nv_sim/datasets/schema.py` for the `DatasetManifest` dataclass and validation logic.
