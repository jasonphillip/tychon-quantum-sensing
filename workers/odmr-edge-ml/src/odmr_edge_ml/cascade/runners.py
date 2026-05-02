"""Batched runner factories for the cascade composition utilities.

``tychon_shared_data.cascade.compose_*`` accepts custom runners with the
contract ``Callable[[np.ndarray], np.ndarray]``. The default runners
expect ``tflite_runtime`` and run one sample at a time. These helpers
provide tensorflow-fallback runners that loop internally over a batch of
the static-batch (1, 1, input_dim, in_channels) NHWC inputs the
OdmrFCNNv2-via-Keras export produces.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np


def _make_interpreter(tflite_path: Path):
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter  # type: ignore[no-redef]
    interp = Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    return interp


def make_float_runner(
    tflite_path: Path,
) -> Callable[[np.ndarray], np.ndarray]:
    """Build a float-in/float-out runner that loops over batched inputs.

    Accepts ``x`` of shape ``(B, 1, input_dim, in_channels)`` NHWC float32
    (matches the static-batch Keras export) and returns ``(B, output_dim)``
    float32 (last three trailing 1-dims squeezed). Single-sample input is
    accepted via the leading-dim broadcast.
    """
    interp = _make_interpreter(tflite_path)
    in_det = interp.get_input_details()[0]
    out_det = interp.get_output_details()[0]
    in_scale, in_zp = in_det["quantization"]
    out_scale, out_zp = out_det["quantization"]

    def _run(x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 3:
            x = x[None, ...]
        n = x.shape[0]
        outs = []
        for i in range(n):
            sample = x[i:i + 1]
            if in_det["dtype"] == np.int8:
                q = np.round(sample / in_scale + in_zp).clip(-128, 127).astype(np.int8)
                interp.set_tensor(in_det["index"], q)
            else:
                interp.set_tensor(in_det["index"], sample.astype(in_det["dtype"]))
            interp.invoke()
            y = interp.get_tensor(out_det["index"])
            if out_det["dtype"] == np.int8:
                outs.append((y.astype(np.float32) - out_zp) * out_scale)
            else:
                outs.append(y.astype(np.float32))
        return np.concatenate(outs, axis=0).reshape(n, -1)

    return _run


def make_int8_runner(
    tflite_path: Path,
) -> Callable[[np.ndarray], np.ndarray]:
    """Build an int8-in/int8-out runner that loops over batched inputs.

    Accepts ``x_int8`` of shape ``(B, 1, input_dim, in_channels)`` int8
    and returns ``(B, output_dim)`` int8.
    """
    interp = _make_interpreter(tflite_path)
    in_det = interp.get_input_details()[0]
    out_det = interp.get_output_details()[0]
    if in_det["dtype"] != np.int8 or out_det["dtype"] != np.int8:
        raise TypeError(
            f"int8 runner requires int8 IO; got "
            f"input={in_det['dtype']} output={out_det['dtype']}"
        )

    def _run(x_int8: np.ndarray) -> np.ndarray:
        if x_int8.dtype != np.int8:
            raise TypeError(f"x_int8 must be int8, got {x_int8.dtype}")
        if x_int8.ndim == 3:
            x_int8 = x_int8[None, ...]
        n = x_int8.shape[0]
        outs = []
        for i in range(n):
            interp.set_tensor(in_det["index"], x_int8[i:i + 1])
            interp.invoke()
            outs.append(interp.get_tensor(out_det["index"]))
        return np.concatenate(outs, axis=0).reshape(n, -1).astype(np.int8)

    return _run


def quantize_input(
    x_float: np.ndarray, scale: float, zero_point: int,
) -> np.ndarray:
    """Quantize a float NHWC input array to int8 per (scale, zero_point)."""
    return (
        np.round(x_float.astype(np.float32) / scale + zero_point)
        .clip(-128, 127)
        .astype(np.int8)
    )
