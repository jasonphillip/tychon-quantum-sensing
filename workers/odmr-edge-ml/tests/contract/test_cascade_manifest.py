"""Contract test: emit_cascade_manifest produces a structurally valid manifest.

The TBD rounding_mode placeholder is intentionally written by
emit_cascade_manifest per LOCKED CONTRACT #1, and CascadeManifest.validate()
intentionally rejects it. So this test:

  1. Emits a real manifest via the production helper (with TBD placeholder).
  2. Re-loads it via CascadeManifest.from_json and checks structural
     fields (granularity, mode, SHA256s, schema version).
  3. Substitutes a real rounding mode and confirms validate() now passes
     end-to-end (catches per_tensor / additive_raw_x / scale checks).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tychon_shared_data.cascade import CascadeManifest
from tychon_shared_data.cascade.manifest import ROUNDING_MODE_TBD

from odmr_edge_ml.cascade import emit_cascade_manifest


@pytest.fixture
def fake_tflite_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Two byte-distinct dummy TFLite files for SHA256 to differ."""
    coarse = tmp_path / "coarse_int8.tflite"
    fine = tmp_path / "fine_int8.tflite"
    coarse.write_bytes(b"\x00" * 64 + b"COARSE")
    fine.write_bytes(b"\x00" * 64 + b"FINE")
    return coarse, fine, tmp_path


def test_emit_cascade_manifest_writes_locked_contract(
    fake_tflite_pair: tuple[Path, Path, Path],
) -> None:
    coarse, fine, out_dir = fake_tflite_pair
    path = emit_cascade_manifest(
        output_dir=out_dir,
        coarse_tflite=coarse,
        fine_tflite=fine,
        input_dim=200,
        output_dim=1,
        coarse_input_quant=(1.0e-5, 0),
        coarse_output_quant=(1.77e-8, 0),
        fine_input_quant=(1.0e-5, 0),
        fine_output_quant=(1.0e-9, 0),
        composition_output_quant=(1.77e-8, 0),
        notes="commit-2 contract test fixture",
        generator_git_sha="0" * 40,
    )

    raw = json.loads(path.read_text())
    assert raw["coarse_model"]["quantization_granularity"] == "per_tensor"
    assert raw["fine_model"]["quantization_granularity"] == "per_tensor"
    assert raw["composition"]["mode"] == "additive_raw_x"
    assert raw["composition"]["rounding_mode"] == ROUNDING_MODE_TBD
    assert raw["composition"]["saturate_int8"] is True
    assert raw["coarse_model"]["tflite_path"] == "coarse_int8.tflite"
    assert raw["fine_model"]["tflite_path"] == "fine_int8.tflite"
    # SHA256 differs between the two payloads
    assert (
        raw["coarse_model"]["tflite_sha256"]
        != raw["fine_model"]["tflite_sha256"]
    )


def test_emitted_manifest_validates_after_rounding_resolution(
    fake_tflite_pair: tuple[Path, Path, Path],
) -> None:
    """Once polarfire-hybrid-control resolves the TBD rounding_mode in CI,
    the manifest must pass full validate(). Simulate that step here."""
    coarse, fine, out_dir = fake_tflite_pair
    path = emit_cascade_manifest(
        output_dir=out_dir,
        coarse_tflite=coarse,
        fine_tflite=fine,
        input_dim=200,
        output_dim=1,
        coarse_input_quant=(1.0e-5, 0),
        coarse_output_quant=(1.77e-8, 0),
        fine_input_quant=(1.0e-5, 0),
        fine_output_quant=(1.0e-9, 0),
        composition_output_quant=(1.77e-8, 0),
        generator_git_sha="0" * 40,
    )
    data = json.loads(path.read_text())
    data["composition"]["rounding_mode"] = "round_half_to_even"
    path.write_text(json.dumps(data, indent=2))

    manifest = CascadeManifest.from_json(path)
    manifest.validate()


def test_validate_rejects_tbd_placeholder(
    fake_tflite_pair: tuple[Path, Path, Path],
) -> None:
    """The TBD placeholder MUST be rejected — that's the whole gating
    mechanism that prevents half-configured manifests from reaching CI."""
    coarse, fine, out_dir = fake_tflite_pair
    path = emit_cascade_manifest(
        output_dir=out_dir,
        coarse_tflite=coarse, fine_tflite=fine,
        input_dim=200, output_dim=1,
        coarse_input_quant=(1.0e-5, 0), coarse_output_quant=(1.77e-8, 0),
        fine_input_quant=(1.0e-5, 0), fine_output_quant=(1.0e-9, 0),
        composition_output_quant=(1.77e-8, 0),
        generator_git_sha="0" * 40,
    )
    manifest = CascadeManifest.from_json(path)
    with pytest.raises(ValueError, match="TBD_AFTER_VECTORBLOX_DOC_CHECK"):
        manifest.validate()


def test_emit_rejects_invalid_quant_inputs(
    fake_tflite_pair: tuple[Path, Path, Path],
) -> None:
    coarse, fine, out_dir = fake_tflite_pair
    with pytest.raises(ValueError, match="scale must be > 0"):
        emit_cascade_manifest(
            output_dir=out_dir,
            coarse_tflite=coarse, fine_tflite=fine,
            input_dim=200, output_dim=1,
            coarse_input_quant=(0.0, 0), coarse_output_quant=(1.77e-8, 0),
            fine_input_quant=(1.0e-5, 0), fine_output_quant=(1.0e-9, 0),
            composition_output_quant=(1.77e-8, 0),
        )
    with pytest.raises(ValueError, match="zero_point"):
        emit_cascade_manifest(
            output_dir=out_dir,
            coarse_tflite=coarse, fine_tflite=fine,
            input_dim=200, output_dim=1,
            coarse_input_quant=(1.0e-5, 0), coarse_output_quant=(1.77e-8, 200),
            fine_input_quant=(1.0e-5, 0), fine_output_quant=(1.0e-9, 0),
            composition_output_quant=(1.77e-8, 0),
        )
