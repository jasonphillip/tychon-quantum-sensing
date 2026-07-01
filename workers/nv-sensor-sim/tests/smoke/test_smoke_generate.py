"""CPU-only smoke tests. No CUDA, Julia, or vendor tools required.

These tests verify the core simulation pipeline works end-to-end on CPU:
- SimOS adapter generates ODMR spectra
- OU noise trajectories have correct statistics
- Dataset manifest roundtrips through JSON
- Tiny dataset generation produces valid output files
"""

from __future__ import annotations

import tempfile

import numpy as np
import pytest

# Suppress grid aliasing warnings from low-resolution test grids
pytestmark = pytest.mark.filterwarnings("ignore:Grid aliasing risk:UserWarning")


@pytest.mark.smoke
def test_simos_adapter_generates_spectrum():
    """Generate a single ODMR spectrum via SimOS adapter on CPU."""
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
    from nv_sensor_sim.config import SimulationConfig

    config = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, 0.01]),
        temperature_K=300.0,
        mw_freq_range_Hz=(2.84e9, 2.90e9),
        n_freq_points=20,
        include_nitrogen=False,  # Faster without hyperfine
        use_optics=True,
        b_perp_T=0.0,
        random_seed=42,
    )

    adapter = SimOSAdapter(config)
    frequencies, signal = adapter.generate_odmr_spectrum()

    # Shape checks
    assert frequencies.shape == (20,), f"Expected (20,), got {frequencies.shape}"
    assert signal.shape == (20,), f"Expected (20,), got {signal.shape}"

    # Frequency range check
    assert frequencies[0] == pytest.approx(2.84e9, rel=1e-6)
    assert frequencies[-1] == pytest.approx(2.90e9, rel=1e-6)

    # Signal should be real and finite
    assert np.all(np.isfinite(signal)), "Signal contains non-finite values"

    # Signal should show some variation (ODMR dips)
    signal_range = np.max(signal) - np.min(signal)
    assert signal_range > 0, "Signal has no variation — no ODMR features detected"


@pytest.mark.smoke
def test_ou_noise_trajectory():
    """Generate OU noise trajectories for T(t) and B1(t)."""
    from nv_sensor_sim.physics.noise_injection import (
        generate_b1_trajectory,
        generate_temperature_trajectory,
    )
    from nv_sensor_sim.physics.parameters import OUProcessParams

    params = OUProcessParams()
    dt = 0.01
    n_steps = 10000

    # Temperature trajectory
    T_traj = generate_temperature_trajectory(params, dt, n_steps, seed=42)
    assert T_traj.shape == (n_steps,)
    assert np.all(np.isfinite(T_traj))
    # Mean should be near mu_T
    assert np.abs(np.mean(T_traj) - params.mu_T) < 5.0  # within 5K

    # B1 trajectory
    B1_traj = generate_b1_trajectory(params, dt, n_steps, seed=43)
    assert B1_traj.shape == (n_steps,)
    assert np.all(np.isfinite(B1_traj))
    # Mean should be near mu_B1
    assert np.abs(np.mean(B1_traj) - params.mu_B1) < 0.1


@pytest.mark.smoke
def test_manifest_roundtrip():
    """Create manifest, write to JSON, read back, validate."""
    import tempfile
    from pathlib import Path

    from nv_sensor_sim.datasets.schema import DatasetManifest

    manifest = DatasetManifest(
        generator_git_sha="abc123",
        config_hash="def456",
        simos_version="0.2.3",
        qutip_version="5.2.3",
        backend="qutip",
        generated_at="2026-03-11T00:00:00Z",
        master_seed=42,
        train_seeds=[100, 101, 102],
        val_seeds=[200, 201],
        test_seeds=[300, 301],
        n_spectra_train=3,
        n_spectra_val=2,
        n_spectra_test=2,
        train_indices=[0, 1, 2],
        val_indices=[0, 1],
        test_indices=[0, 1],
        n_freq_points=100,
        freq_range_Hz=(2.82e9, 2.92e9),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "manifest.json"
        manifest.to_json(json_path)

        loaded = DatasetManifest.from_json(json_path)

        # Validate roundtrip
        assert loaded.generator_git_sha == "abc123"
        assert loaded.master_seed == 42
        assert loaded.train_seeds == [100, 101, 102]
        assert loaded.test_seeds == [300, 301]
        assert loaded.n_spectra_train == 3
        assert loaded.freq_range_Hz == pytest.approx((2.82e9, 2.92e9))

        # Validate should pass
        loaded.validate()


@pytest.mark.smoke
def test_tiny_dataset_generation():
    """Generate a 3-spectrum dataset (1 train, 1 val, 1 test) with manifest."""
    from nv_sensor_sim.datasets.schema import DatasetManifest
    from nv_sensor_sim.datasets.writer import DatasetWriter

    n_freq = 10

    with tempfile.TemporaryDirectory() as tmpdir:
        writer = DatasetWriter(tmpdir, format="h5")

        # Write train split
        writer.write_spectra(
            spectra=np.random.randn(1, n_freq),
            frequencies=np.linspace(2.82e9, 2.92e9, n_freq),
            labels=np.array([[0.0, 0.0, 0.01]]),
            corruption_params=np.array([[10.0, 300.0, 0.1, 1e-5]]),
            seeds=np.array([100]),
            split="train",
        )

        # Write val split
        writer.write_spectra(
            spectra=np.random.randn(1, n_freq),
            frequencies=np.linspace(2.82e9, 2.92e9, n_freq),
            labels=np.array([[0.0, 0.0, 0.02]]),
            corruption_params=np.array([[20.0, 310.0, 0.15, 2e-5]]),
            seeds=np.array([200]),
            split="val",
        )

        # Write test split
        writer.write_spectra(
            spectra=np.random.randn(1, n_freq),
            frequencies=np.linspace(2.82e9, 2.92e9, n_freq),
            labels=np.array([[0.0, 0.0, 0.03]]),
            corruption_params=np.array([[30.0, 320.0, 0.2, 3e-5]]),
            seeds=np.array([300]),
            split="test",
        )

        # Write manifest
        manifest = DatasetManifest(
            generator_git_sha="smoke_test",
            config_hash="test_hash",
            simos_version="0.2.3",
            qutip_version="5.2.3",
            backend="qutip",
            generated_at="2026-03-11T00:00:00Z",
            master_seed=42,
            train_seeds=[100],
            val_seeds=[200],
            test_seeds=[300],
            n_spectra_train=1,
            n_spectra_val=1,
            n_spectra_test=1,
            train_indices=[0],
            val_indices=[0],
            test_indices=[0],
            n_freq_points=n_freq,
        )
        writer.write_manifest(manifest)
        output_path = writer.finalize()

        # Verify files exist
        from pathlib import Path

        out = Path(output_path)
        assert (out / "dataset.h5").exists(), "HDF5 file not created"
        assert (out / "manifest.json").exists(), "Manifest JSON not created"

        # Verify manifest validates
        loaded = DatasetManifest.from_json(out / "manifest.json")
        loaded.validate()

        # Verify HDF5 content via loader
        from nv_sensor_sim.datasets.loaders import DatasetLoader

        loader = DatasetLoader(output_path)
        spectra, freqs, labels, corruption, seeds = loader.load_split("train")
        assert spectra.shape == (1, n_freq)
        assert labels.shape == (1, 3)
