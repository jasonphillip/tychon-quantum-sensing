"""The vector-dataset CLI must forward the simulator-fit keys from the YAML config."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_cli_forwards_linewidth_and_contrast_keys(tmp_path):
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text(
        "n_train: 2\nn_val: 1\nn_test: 1\nmaster_seed: 3\nn_freq_points: 100\n"
        "freq_range_Hz: [2.83e9, 2.91e9]\nmulti_axis_mode: true\nfield_sampling: spherical\n"
        "bias_B0_range_T: [0.5e-3, 5.0e-3]\nb_mag_range_T: [0.5e-3, 5.0e-3]\n"
        "inhomogeneous_fwhm_hz: 2.0e+6\nbase_contrast: 0.05\noutput_format: h5\n")
    out = tmp_path / "ds"
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    subprocess.run([sys.executable, str(REPO / "scripts" / "generate_vector_dataset.py"),
                    "--config", str(cfg), "--output-dir", str(out)], check=True, env=env,
                   capture_output=True, text=True)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["inhomogeneous_fwhm_hz"] == 2e6
    assert manifest["base_contrast"] == 0.05
