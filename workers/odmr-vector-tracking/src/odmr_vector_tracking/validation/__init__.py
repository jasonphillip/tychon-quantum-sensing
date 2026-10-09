"""Deployability validation for V250 hand-off.

Two-stage guard mirroring ``odmr_edge_ml.validation``:

- ``ops_guard`` — PyTorch-graph stage (``torch.export`` whitelist). Run before training at
  scale; gates any block tagged V250-targeted.
- ``tflite_ops`` — exported-flatbuffer stage (lazy TensorFlow). Runs in the Increment-3
  export path; its live test is deferred until a TFLite artifact exists.
"""

from odmr_vector_tracking.validation.ops_guard import (
    VECTORBLOX_ALLOWED_OPS,
    VECTORBLOX_BANNED_MODULES,
    VECTORBLOX_BANNED_OPS,
    OpsGuardError,
    OpsReport,
    assert_v250_compatible,
    check_model_ops,
)
from odmr_vector_tracking.validation.tflite_ops import (
    BANNED_TFLITE_OPS,
    TFLiteOpsError,
    VnnxCompileError,
    verify_tflite_ops,
    verify_vnnx_compile_stderr,
)

__all__ = [
    "VECTORBLOX_ALLOWED_OPS",
    "VECTORBLOX_BANNED_MODULES",
    "VECTORBLOX_BANNED_OPS",
    "OpsGuardError",
    "OpsReport",
    "assert_v250_compatible",
    "check_model_ops",
    "BANNED_TFLITE_OPS",
    "TFLiteOpsError",
    "VnnxCompileError",
    "verify_tflite_ops",
    "verify_vnnx_compile_stderr",
]
