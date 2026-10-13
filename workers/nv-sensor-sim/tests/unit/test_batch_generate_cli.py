"""CLI regression checks for the documented batch config interface."""

from pathlib import Path

import h5py
import pytest

from nv_sensor_sim.pipelines import batch_generate

REPO = Path(__file__).resolve().parents[2]


def test_config_reaches_generator(monkeypatch, tmp_path):
    config = tmp_path / "tiny.yaml"
    config.write_text(
        "noise_mode: stochastic\nn_train: 2\nn_val: 1\nn_test: 1\n"
        "master_seed: 73\nn_freq_points: 24\nfreq_range_Hz: [2.82e9, 2.92e9]\n"
        "ou_noise:\n  theta_T: 1.0e-3\n  alpha_B1: -0.0035\n"
        "include_nitrogen: false\nuse_optics: false\n"
    )
    calls = []
    monkeypatch.setattr(batch_generate, "generate_dataset", lambda **kw: calls.append(kw))
    output = tmp_path / "dataset"

    batch_generate.main(["--config", str(config), "--output-dir", str(output)])

    assert len(calls) == 1
    assert calls[0]["output_dir"] == str(output)
    assert (calls[0]["noise_mode"], calls[0]["n_train"], calls[0]["n_val"],
            calls[0]["n_test"], calls[0]["master_seed"]) == ("stochastic", 2, 1, 1, 73)
    assert calls[0]["freq_range_Hz"] == (2.82e9, 2.92e9)
    assert calls[0]["ou_noise_config"].theta_T == 0.001
    assert calls[0]["ou_noise_config"].alpha_B1 == -0.0035


@pytest.mark.parametrize("extra", ["unknown_key: 1", "ou_noise:\n  unknown_key: 1",
                                   "include_nitrogen: true"])
def test_unsupported_config_fails(monkeypatch, tmp_path, extra):
    config = tmp_path / "invalid.yaml"
    config.write_text("n_train: 1\n" + extra + "\n")
    monkeypatch.setattr(batch_generate, "generate_dataset", lambda **kw: pytest.fail("generated"))
    with pytest.raises(ValueError, match="unknown_key|include_nitrogen"):
        batch_generate.main(["--config", str(config), "--output-dir", str(tmp_path / "out")])


def test_no_args_keeps_default(monkeypatch):
    calls = []
    monkeypatch.setattr(batch_generate, "generate_dataset", lambda *args: calls.append(args))
    batch_generate.main([])
    assert calls == [("./data/synthetic_v1",)]


def test_config_writes_splits_to_output_dir(tmp_path):
    output = tmp_path / "generated"
    batch_generate.main([
        "--config", str(REPO / "configs" / "quickstart_tiny.yaml"),
        "--output-dir", str(output),
    ])
    assert sorted(path.name for path in output.iterdir()) == ["dataset.h5", "manifest.json"]
    with h5py.File(output / "dataset.h5") as dataset:
        assert [dataset[split]["spectra"].shape for split in ("train", "val", "test")] == [
            (2, 2000), (1, 2000), (1, 2000),
        ]
