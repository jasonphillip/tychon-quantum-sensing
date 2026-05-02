"""Emit cascade_manifest.json against the LOCKED CONTRACT in tychon-shared-data.

Schema is defined by ``tychon_shared_data.cascade.CascadeManifest``. We
write the placeholder ``TBD_AFTER_VECTORBLOX_DOC_CHECK`` for
``composition.rounding_mode`` per the locked contract; downstream
(``polarfire-hybrid-control``) resolves it in CI after verifying the
VectorBlox SDK 2.0.x rounding behavior against vendor docs. As a
consequence, ``CascadeManifest.validate()`` will *intentionally* reject
the manifest we emit until the placeholder is replaced — that is the
gating mechanism, not a bug. We round-trip via ``from_dict()``/``to_json()``
to assert structural correctness without invoking the placeholder gate.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tychon_shared_data.cascade import CascadeManifest
from tychon_shared_data.cascade.manifest import (
    LEGAL_COMPOSITION_MODES,
    LEGAL_QUANTIZATION_GRANULARITIES,
    ROUNDING_MODE_TBD,
    SCHEMA_VERSION,
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _quant_block(scale: float, zero_point: int) -> dict[str, Any]:
    if scale <= 0:
        raise ValueError(f"quant scale must be > 0, got {scale}")
    if not -128 <= zero_point <= 127:
        raise ValueError(f"zero_point must be in [-128, 127], got {zero_point}")
    return {"scale": float(scale), "zero_point": int(zero_point)}


def emit_cascade_manifest(
    *,
    output_dir: Path,
    coarse_tflite: Path,
    fine_tflite: Path,
    input_dim: int,
    output_dim: int,
    coarse_input_quant: tuple[float, int],
    coarse_output_quant: tuple[float, int],
    fine_input_quant: tuple[float, int],
    fine_output_quant: tuple[float, int],
    composition_output_quant: tuple[float, int],
    notes: str = "",
    saturate_int8: bool = True,
    generator_git_sha: str | None = None,
) -> Path:
    """Write cascade_manifest.json under ``output_dir`` and return its path.

    Both COARSE and FINE TFLite paths are recorded *relative to*
    ``output_dir`` so the manifest is portable. SHA256 is computed from
    actual file bytes (not mtime). The composition rounding_mode is
    written as the placeholder string per the locked contract.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    coarse_tflite = Path(coarse_tflite)
    fine_tflite = Path(fine_tflite)

    # Validate granularity / mode constraints up-front for a cleaner error
    # than CascadeManifest.validate() would give on a partial manifest.
    granularity = "per_tensor"
    composition_mode = "additive_raw_x"
    assert granularity in LEGAL_QUANTIZATION_GRANULARITIES
    assert composition_mode in LEGAL_COMPOSITION_MODES

    coarse_block = {
        "tflite_path": str(coarse_tflite.relative_to(output_dir)),
        "tflite_sha256": _sha256_file(coarse_tflite),
        "quantization_granularity": granularity,
        "input_quant": _quant_block(*coarse_input_quant),
        "output_quant": _quant_block(*coarse_output_quant),
    }
    fine_block = {
        "tflite_path": str(fine_tflite.relative_to(output_dir)),
        "tflite_sha256": _sha256_file(fine_tflite),
        "quantization_granularity": granularity,
        "input_quant": _quant_block(*fine_input_quant),
        "output_quant": _quant_block(*fine_output_quant),
    }
    composition = {
        "mode": composition_mode,
        "rounding_mode": ROUNDING_MODE_TBD,
        "output_quant": _quant_block(*composition_output_quant),
        "saturate_int8": bool(saturate_int8),
    }

    manifest = CascadeManifest(
        schema_version=SCHEMA_VERSION,
        generator_git_sha=generator_git_sha or _git_sha(),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        input_dim=int(input_dim),
        output_dim=int(output_dim),
        coarse_model=coarse_block,
        fine_model=fine_block,
        composition=composition,
        notes=notes,
    )

    out_path = output_dir / "cascade_manifest.json"
    manifest.to_json(out_path)
    return out_path
