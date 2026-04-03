"""Contract tests against the golden reference dataset from the upstream simulator.

These tests validate that the golden dataset at
./data/golden/ conforms to the expected manifest schema
and that HDF5 shapes match manifest counts.
"""

from pathlib import Path

import h5py
import pytest

from odmr_edge_ml.data.contracts import validate_manifest_file

GOLDEN_DIR = Path(__file__).resolve().parent.parent.parent / "data/golden"
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
DATASET_PATH = GOLDEN_DIR / "dataset.h5"

pytestmark = pytest.mark.skipif(
    not MANIFEST_PATH.exists(), reason="Golden dataset not available"
)


@pytest.fixture
def manifest() -> dict:
    return validate_manifest_file(MANIFEST_PATH)


def test_golden_manifest_loads():
    """manifest.json loads without error."""
    validate_manifest_file(MANIFEST_PATH)


def test_golden_manifest_validates(manifest):
    """manifest.json passes full contract validation (implicit via fixture)."""
    assert manifest is not None


def test_golden_manifest_has_expected_splits(manifest):
    """100 train, 20 val, 20 test."""
    assert manifest["n_spectra_train"] == 100
    assert manifest["n_spectra_val"] == 20
    assert manifest["n_spectra_test"] == 20


def test_golden_manifest_seed_separation(manifest):
    """Train/val/test seeds are pairwise disjoint."""
    train = set(manifest["train_seeds"])
    val = set(manifest["val_seeds"])
    test = set(manifest["test_seeds"])
    assert train & val == set()
    assert train & test == set()
    assert val & test == set()


def test_golden_manifest_has_100_freq_points(manifest):
    """n_freq_points == 100."""
    assert manifest["n_freq_points"] == 100


def test_golden_manifest_units_si(manifest):
    """All units are SI."""
    units = manifest["units"]
    assert units["frequency"] == "Hz"
    assert units["magnetic_field"] == "T"
    assert units["temperature"] == "K"
    assert units["p1_concentration"] == "ppm"
    assert units["b1_gradient"] == "fraction"
    assert units["b_perp"] == "T"
    assert units["time"] == "s"


def test_golden_manifest_master_seed(manifest):
    """master_seed == 12345."""
    assert manifest["master_seed"] == 12345


@pytest.mark.skipif(not DATASET_PATH.exists(), reason="dataset.h5 not available")
def test_golden_dataset_shapes(manifest):
    """HDF5 shapes match manifest counts."""
    n_freq = manifest["n_freq_points"]

    with h5py.File(DATASET_PATH, "r") as f:
        for split, count_key in [
            ("train", "n_spectra_train"),
            ("val", "n_spectra_val"),
            ("test", "n_spectra_test"),
        ]:
            n = manifest[count_key]
            assert f[split]["spectra"].shape == (n, n_freq)
            assert f[split]["frequencies"].shape == (n_freq,)
            assert f[split]["labels"].shape == (n, 3)
            assert f[split]["corruption_params"].shape == (n, 4)
            assert f[split]["seeds"].shape == (n,)
