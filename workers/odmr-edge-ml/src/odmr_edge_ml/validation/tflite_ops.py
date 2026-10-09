"""TFLite-side op-set check for vnnx_compile compatibility.

Companion to ops_guard.py (which checks the PyTorch graph). This module
inspects the *exported* TFLite flatbuffer for ops that the PolarFire
VectorBlox compiler rejects — most notably the dynamic-shape ops
(SHAPE, STRIDED_SLICE, PACK) that leak in when a Keras model is built
with a dynamic batch dimension.

Run verify_tflite_ops() right after every TFLite conversion in the
training pipeline. Run verify_vnnx_compile_stderr() (or the
run_vnnx_compile() wrapper) to catch downstream compiler errors.
"""

from __future__ import annotations

import logging
import subprocess
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
        TFLite flatbuffer bytes or path to a .tflite file.
    banned : set of str
        Op names that vnnx_compile rejects. Defaults to dynamic-shape ops.

    Returns
    -------
    set of str
        All op names present in the model (sorted set, useful for logging).

    Raises
    ------
    TFLiteOpsError
        If any banned op is present.
    """
    import tensorflow as tf

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
            f"TFLite contains banned ops {sorted(bad)} — vnnx_compile -c V250 "
            f"will reject this model. (See scripts/fix_fcnn_export.py for the "
            f"static-batch Keras workaround.)"
        )
    log.info("vnnx op-compat check: PASS (no dynamic-shape ops)")
    return ops


def verify_vnnx_compile_stderr(stderr_text: str) -> None:
    """Raise VnnxCompileError if stderr contains the VECTORBLOX ERROR marker.

    The substring match is case-sensitive; vnnx_compile emits the marker
    in upper case for fatal errors.
    """
    if VNNX_ERROR_MARKER in stderr_text:
        raise VnnxCompileError(
            f"vnnx_compile reported a fatal error:\n{stderr_text}"
        )


def run_vnnx_compile(
    tflite_path: Path | str,
    target: str = "V250",
    extra_args: list[str] | None = None,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run vnnx_compile and raise on VECTORBLOX ERROR or non-zero exit.

    Captures stdout and stderr; scans stderr for the VECTORBLOX ERROR marker
    and raises VnnxCompileError with the captured stderr if present. Also
    raises CalledProcessError on non-zero exit (caller can chain).

    Parameters
    ----------
    tflite_path : Path | str
        Path to the input TFLite file.
    target : str
        VectorBlox target chip; defaults to "V250".
    extra_args : list of str | None
        Additional CLI args appended after `-c {target}`.
    cwd : Path | str | None
        Working directory for the subprocess.
    """
    cmd = ["vnnx_compile", "-c", target, str(tflite_path)]
    if extra_args:
        cmd.extend(extra_args)

    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, check=False,
    )
    verify_vnnx_compile_stderr(result.stderr)
    result.check_returncode()
    return result
