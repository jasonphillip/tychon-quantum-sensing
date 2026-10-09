#!/usr/bin/env python3
"""Bisection probes for the gru_cell_onestep vnnx_compile crash (2026-07-02).

The full GRU-cell probe crashed vnnx_compile inside channels_first_array_reshape
(vnnx_tflite.py:664, np.squeeze ValueError) — a graph/shape-handling failure, not a
per-op VECTORBLOX ERROR. These minimal models isolate which construct triggers it:
single gate ops (LOGISTIC/TANH), two-input elementwise (MUL), CONCATENATION, SUB-vs-const,
and a 4D-tensor GRU variant (VectorBlox is CNN/NHWC-oriented; rank-2 tensors are the
prime suspect). Compile accept/reject on bee is the signal; no sim needed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf

SEED = 20260702
W = 16


def m_fc_act(act: str) -> tf.keras.Model:
    x = tf.keras.Input(shape=(W,), batch_size=1, name="x")
    y = tf.keras.layers.Activation(act)(tf.keras.layers.Dense(W)(x))
    return tf.keras.Model(x, y, name=f"fc_{act}")


def m_mul() -> tf.keras.Model:
    a = tf.keras.Input(shape=(W,), batch_size=1, name="a")
    b = tf.keras.Input(shape=(W,), batch_size=1, name="b")
    return tf.keras.Model([a, b], tf.keras.layers.Multiply()([a, b]), name="mul2in")


def m_concat_fc() -> tf.keras.Model:
    a = tf.keras.Input(shape=(W,), batch_size=1, name="a")
    b = tf.keras.Input(shape=(W,), batch_size=1, name="b")
    y = tf.keras.layers.Dense(W)(tf.keras.layers.Concatenate()([a, b]))
    return tf.keras.Model([a, b], y, name="concat_fc")


def m_sub_const() -> tf.keras.Model:
    x = tf.keras.Input(shape=(W,), batch_size=1, name="x")
    return tf.keras.Model(x, tf.keras.layers.Lambda(lambda t: 1.0 - t)(x), name="sub_const")


def m_gru4d() -> tf.keras.Model:
    """Same GRU-cell dataflow with rank-4 NHWC tensors (1,1,1,W)."""
    x = tf.keras.Input(shape=(1, 1, W), batch_size=1, name="x_t")
    h = tf.keras.Input(shape=(1, 1, W), batch_size=1, name="h_prev")
    xh = tf.keras.layers.Concatenate(axis=-1)([x, h])
    z = tf.keras.layers.Activation("sigmoid")(tf.keras.layers.Dense(W)(xh))
    r = tf.keras.layers.Activation("sigmoid")(tf.keras.layers.Dense(W)(xh))
    r_h = tf.keras.layers.Multiply()([r, h])
    xrh = tf.keras.layers.Concatenate(axis=-1)([x, r_h])
    n = tf.keras.layers.Activation("tanh")(tf.keras.layers.Dense(W)(xrh))
    omz = tf.keras.layers.Lambda(lambda t: 1.0 - t)(z)
    h_new = tf.keras.layers.Add()([
        tf.keras.layers.Multiply()([omz, n]),
        tf.keras.layers.Multiply()([z, h]),
    ])
    return tf.keras.Model([x, h], h_new, name="gru_cell_4d")


def to_int8(model: tf.keras.Model, rng: np.random.Generator) -> bytes:
    shapes = [tuple(int(d) for d in t.shape) for t in model.inputs]

    def rep():
        for _ in range(50):
            yield [rng.standard_normal(s).astype(np.float32) * 0.5 for s in shapes]

    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = rep
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8
    conv.inference_output_type = tf.int8
    return conv.convert()


def ops_of(tfl: bytes) -> list[str]:
    interp = tf.lite.Interpreter(model_content=tfl)
    interp.allocate_tensors()
    return sorted({d["op_name"] for d in interp._get_ops_details()} - {"DELEGATE"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="libero/reports/2026-07-02-vnnx-ops-probe/bisect")
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    tf.random.set_seed(SEED)
    rng = np.random.default_rng(SEED)

    models = [m_fc_act("sigmoid"), m_fc_act("tanh"), m_mul(), m_concat_fc(), m_sub_const(), m_gru4d()]
    for m in models:
        tfl = to_int8(m, rng)
        p = out / f"{m.name}_int8.tflite"
        p.write_bytes(tfl)
        print(f"[{m.name}] ops={ops_of(tfl)} -> {p.name} ({len(tfl)} B)")


if __name__ == "__main__":
    main()
