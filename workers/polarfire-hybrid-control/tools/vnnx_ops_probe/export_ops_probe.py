#!/usr/bin/env python3
"""Tier-0 op-support probe: export two INT8 TFLite models that exercise the ops the
odmr-vector-tracking ops_guard currently BANS but the VectorBlox SDK OPS.md (Apr-2026)
lists as SUPPORTED — so `vnnx_compile -c V250` + the VNNX simulator can settle it by
measurement instead of doc archaeology.

Ops under test (ops_guard ban -> OPS.md TFLite name):
  aten.sigmoid -> LOGISTIC   aten.tanh -> TANH   aten.softmax -> SOFTMAX
  aten.mul     -> MUL        (SUB, ADD, FULLY_CONNECTED, CONCATENATION, RESHAPE also present)

Models:
  (a) gru_cell_onestep  — a one-step-unrolled GRU cell with the hidden state as a graph
      INPUT and the new state as a graph OUTPUT (the recurrence is unrolled to the host;
      the cell itself is feedforward). Elementary ops are used (not a fused GRU layer) so
      LOGISTIC/TANH/MUL are exposed to the compiler rather than hidden inside a fused op.
  (b) softmax_head_8x60  — Dense -> reshape to an 8x60 score matrix -> softmax over the
      60-candidate axis (the association/assignment head).

Outputs (written to --outdir): the two INT8 .tflite files, a per-model fixed-input npz with
the FLOAT reference outputs and the TFLite int8 quant params (for the VNNX-sim-vs-float
comparison on bee), and an ops.json listing each model's TFLite operators.

Run in the VectorBlox SDK's own venv on bee for exact version parity before the compile;
also runnable anywhere with TensorFlow to verify the export logic + capture the op set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

SEED = 20260702
I_DIM = 16          # GRU cell input width
H_DIM = 16          # GRU cell hidden/state width
FEAT_DIM = 64       # softmax-head input feature width
N_TRACKS, N_CAND = 8, 60
N_FIXED = 64        # size of the fixed input set for the sim-vs-float comparison


def build_gru_cell() -> tf.keras.Model:
    """One-step GRU cell, state as graph I/O, elementary ops (LOGISTIC/TANH/MUL/SUB/ADD/FC).

    Static batch=1: the V250 runs one sample at a time, and a dynamic (None) batch makes the
    converter emit SHAPE/STRIDED_SLICE/PACK dynamic-shape ops that vnnx_compile rejects (and
    that would confound the op-support probe).
    """
    x = tf.keras.Input(shape=(I_DIM,), batch_size=1, name="x_t")
    h = tf.keras.Input(shape=(H_DIM,), batch_size=1, name="h_prev")
    xh = tf.keras.layers.Concatenate(name="xh")([x, h])
    z = tf.keras.layers.Activation("sigmoid", name="update_gate")(
        tf.keras.layers.Dense(H_DIM, name="z_lin")(xh))          # LOGISTIC
    r = tf.keras.layers.Activation("sigmoid", name="reset_gate")(
        tf.keras.layers.Dense(H_DIM, name="r_lin")(xh))          # LOGISTIC
    r_h = tf.keras.layers.Multiply(name="reset_times_h")([r, h])  # MUL
    xrh = tf.keras.layers.Concatenate(name="x_rh")([x, r_h])
    n = tf.keras.layers.Activation("tanh", name="candidate")(
        tf.keras.layers.Dense(H_DIM, name="n_lin")(xrh))         # TANH
    one_minus_z = tf.keras.layers.Lambda(lambda t: 1.0 - t, name="one_minus_z")(z)  # SUB
    h_new = tf.keras.layers.Add(name="h_new")([
        tf.keras.layers.Multiply(name="cand_term")([one_minus_z, n]),  # MUL
        tf.keras.layers.Multiply(name="keep_term")([z, h]),            # MUL
    ])
    return tf.keras.Model([x, h], h_new, name="gru_cell_onestep")


def build_softmax_head() -> tf.keras.Model:
    """Dense -> 8x60 score matrix -> softmax over the candidate axis (FULLY_CONNECTED/RESHAPE/SOFTMAX)."""
    feat = tf.keras.Input(shape=(FEAT_DIM,), batch_size=1, name="feat")
    logits = tf.keras.layers.Dense(N_TRACKS * N_CAND, name="assoc_lin")(feat)
    scores = tf.keras.layers.Reshape((N_TRACKS, N_CAND), name="score_matrix")(logits)
    probs = tf.keras.layers.Softmax(axis=-1, name="assoc_softmax")(scores)  # SOFTMAX dim=-1
    return tf.keras.Model(feat, probs, name="softmax_head_8x60")


def to_int8_tflite(model: tf.keras.Model, rep_inputs: list[list[np.ndarray]]) -> bytes:
    def rep_ds():
        for sample in rep_inputs:
            yield sample
    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = rep_ds
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8
    conv.inference_output_type = tf.int8
    return conv.convert()


def tflite_ops(tfl: bytes) -> list[str]:
    interp = tf.lite.Interpreter(model_content=tfl)
    interp.allocate_tensors()
    # "DELEGATE" is an interpreter-runtime pseudo-op (XNNPACK wraps a subgraph); it is not a
    # flatbuffer operator, so vnnx_compile never sees it. Report the true builtin op set.
    return sorted({d["op_name"] for d in interp._get_ops_details()} - {"DELEGATE"})


def io_details(tfl: bytes) -> dict:
    interp = tf.lite.Interpreter(model_content=tfl)
    interp.allocate_tensors()
    def pack(dets):
        out = []
        for d in dets:
            s, zp = d["quantization"]
            out.append({"name": d["name"], "dtype": str(np.dtype(d["dtype"])),
                        "shape": [int(x) for x in d["shape"]], "scale": float(s), "zero_point": int(zp)})
        return out
    return {"inputs": pack(interp.get_input_details()), "outputs": pack(interp.get_output_details())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="libero/reports/2026-07-02-vnnx-ops-probe")
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    tf.random.set_seed(SEED)
    np.random.seed(SEED)
    rng = np.random.default_rng(SEED)

    gru, head = build_gru_cell(), build_softmax_head()

    # representative datasets (calibration) — plausible normalized ranges
    gru_rep = [[rng.standard_normal((1, I_DIM)).astype(np.float32) * 0.5,
                rng.standard_normal((1, H_DIM)).astype(np.float32) * 0.5] for _ in range(200)]
    head_rep = [[rng.standard_normal((1, FEAT_DIM)).astype(np.float32) * 0.5] for _ in range(200)]

    manifest = {"seed": SEED, "tf_version": tf.__version__, "models": {}}

    for name, model, rep, fixed in [
        ("gru_cell_onestep", gru, gru_rep, {
            "x_t": rng.standard_normal((N_FIXED, I_DIM)).astype(np.float32) * 0.5,
            "h_prev": rng.standard_normal((N_FIXED, H_DIM)).astype(np.float32) * 0.5}),
        ("softmax_head_8x60", head, head_rep, {
            "feat": rng.standard_normal((N_FIXED, FEAT_DIM)).astype(np.float32) * 0.5}),
    ]:
        tfl = to_int8_tflite(model, rep)
        tfl_path = out / f"{name}_int8.tflite"
        tfl_path.write_bytes(tfl)
        ops = tflite_ops(tfl)
        io = io_details(tfl)
        # float reference on the fixed input set (static batch=1 -> predict one sample at a time)
        cols = list(fixed.values())  # in model-input order
        ref = np.concatenate(
            [np.asarray(model([c[i:i + 1] for c in cols], training=False)) for i in range(N_FIXED)],
            axis=0)
        npz_path = out / f"{name}_fixed_io.npz"
        np.savez(npz_path, **{"ref": ref.astype(np.float32), **fixed})
        manifest["models"][name] = {
            "tflite": tfl_path.name, "tflite_sha256": hashlib.sha256(tfl).hexdigest()[:16],
            "tflite_bytes": len(tfl), "fixed_io": npz_path.name, "n_fixed": N_FIXED,
            "tflite_ops": ops, "io": io}
        print(f"[{name}] ops={ops}")
        print(f"    tflite={tfl_path.name} ({len(tfl)} B, sha256 {manifest['models'][name]['tflite_sha256']})  "
              f"fixed_io={npz_path.name}  ref_shape={list(ref.shape)}")

    (out / "ops_probe_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nmanifest -> {out / 'ops_probe_manifest.json'}")


if __name__ == "__main__":
    main()
