"""Hierarchical INT8 cascade (P3-11B Path B).

Two cascaded INT8 models — COARSE predicts the heading correction, FINE
predicts the residual on top of COARSE — composed additively in raw-x
mode per ``tychon_shared_data.cascade.CascadeManifest``. Each stage
retains its own ±2.25 µT sector clamp so the Lur'e/Circle Criterion
sector bound is preserved per-stage; effective deployed authority widens
to ±4.5 µT via composition rather than via any single model gaining more
authority.

Public surface:
    manifest_emit.emit_cascade_manifest  — write cascade_manifest.json
    fine_labels.compute_fine_labels      — generate FINE training labels
                                           from COARSE's quantized output
    quant_gap.measure_quantization_gap   — float twin vs deployed delta
"""

from odmr_edge_ml.cascade.fine_labels import compute_fine_labels
from odmr_edge_ml.cascade.manifest_emit import emit_cascade_manifest
from odmr_edge_ml.cascade.quant_gap import measure_quantization_gap

__all__ = [
    "compute_fine_labels",
    "emit_cascade_manifest",
    "measure_quantization_gap",
]
