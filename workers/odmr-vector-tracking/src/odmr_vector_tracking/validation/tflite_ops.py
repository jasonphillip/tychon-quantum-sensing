"""TFLite-side op-set check for V250 / vnnx_compile compatibility.

Companion to :mod:`ops_guard` (which checks the PyTorch graph). This module inspects an
*exported* TFLite flatbuffer for ops the PolarFire VectorBlox compiler rejects — most notably
the dynamic-shape ops (``SHAPE``, ``STRIDED_SLICE``, ``PACK``) that leak in when a Keras model
is built with a dynamic batch dimension.

Mirrors ``odmr_edge_ml.validation.tflite_ops``. ``tensorflow`` is imported lazily inside
:func:`verify_tflite_ops` so it stays an optional dependency — this stage only runs in the
Increment-3 export path (no TFLite artifact exists yet), so its live test is deferred.

Scope note: the actual ``vnnx_compile -c V250`` step is owned by ``polarfire-hybrid-control``
(via the VectorBlox SDK on Beelink) and is intentionally **not** invoked here. This module only
*verifies ops* before handoff and parses compiler stderr if the handoff log is fed back.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

BANNED_TFLITE_OPS: frozenset[str] = frozenset({"SHAPE", "STRIDED_SLICE", "PACK"})

VNNX_ERROR_MARKER: str = "VECTORBLOX ERROR"


class TFLiteOpsError(RuntimeError):
    """Raised when a TFLite model contains ops vnnx_compile cannot handle."""


class VnnxCompileError(RuntimeError):
    """Raised when vnnx_compile stderr contains a VECTORBLOX ERROR marker."""


def verify_tflite_ops(
    model: bytes | Path | str,
    banned: frozenset[str] | set[str] = BANNED_TFLITE_OPS,
) -> set[str]:
    """Verify a TFLite model contains no banned ops.

    Parameters
    ----------
    model : bytes | Path | str
        TFLite flatbuffer bytes or path to a ``.tflite`` file.
    banned : set of str
        Op names vnnx_compile rejects. Defaults to the dynamic-shape ops.

    Returns
    -------
    set of str
        All op names present in the model (useful for logging).

    Raises
    ------
    TFLiteOpsError
        If any banned op is present.
    """
    import tensorflow as tf  # lazy: optional dependency, export increment only

    if isinstance(model, (str, Path)):
        tflite_bytes = Path(model).read_bytes()
    else:
        tflite_bytes = model

    interp = tf.lite.Interpreter(model_content=tflite_bytes)
    interp.allocate_tensors()
    ops: set[str] = {d["op_name"] for d in interp._get_ops_details()}

    log.info("TFLite ops: %s", sorted(ops))
    bad = ops & set(banned)
    if bad:
        raise TFLiteOpsError(
            f"TFLite contains banned ops {sorted(bad)} — vnnx_compile -c V250 will reject "
            f"this model. Rebuild the converter with a static batch dimension."
        )
    log.info("vnnx op-compat check: PASS (no dynamic-shape ops)")
    return ops


def verify_vnnx_compile_stderr(stderr_text: str) -> None:
    """Raise :class:`VnnxCompileError` if stderr contains the VECTORBLOX ERROR marker.

    Parses a handoff log produced by ``polarfire-hybrid-control``'s compile step; this repo
    does not invoke the compiler. The substring match is case-sensitive.
    """
    if VNNX_ERROR_MARKER in stderr_text:
        raise VnnxCompileError(f"vnnx_compile reported a fatal error:\n{stderr_text}")
