#!/usr/bin/env python3
"""Test whether the huge two-input error is an input-order mismatch (tflite vs vnnx)."""
import sys
import numpy as np
import tensorflow as tf
import vbx.sim

name = sys.argv[1]
rng = np.random.default_rng(20260702)
interp = tf.lite.Interpreter(model_path=f"{name}_int8.tflite")
interp.allocate_tensors()
ins, outs = interp.get_input_details(), interp.get_output_details()
print(f"[{name}] tflite input order: {[ (d['name'], d['quantization']) for d in ins ]}")
m = vbx.sim.Model(open(f"{name}.vnnx", "rb").read())
for a in dir(m):
    if not a.startswith("_") and ("input" in a or "output" in a):
        try:
            print(f"  m.{a} = {getattr(m, a)}")
        except Exception as ex:
            print(f"  m.{a} -> {ex}")
errs = {"normal": [], "swapped": []}
for _ in range(16):
    qs = [rng.integers(-128, 128, size=d["shape"]).astype(np.int8) for d in ins]
    for d, q in zip(ins, qs):
        interp.set_tensor(d["index"], q)
    interp.invoke()
    osc, ozp = outs[0]["quantization"]
    t = (interp.get_tensor(outs[0]["index"]).astype(np.float64) - ozp) * osc
    for label, order in (("normal", [0, 1]), ("swapped", [1, 0])):
        o = m.run([qs[j].flatten() for j in order])[0]
        s = (m.output_scale_factor[0] * (o.astype(np.float64) - m.output_zeropoint[0])).reshape(t.shape)
        errs[label].append(np.abs(s - t).max())
for label, e in errs.items():
    print(f"  {label}: max_abs_err over 16 runs = {max(e):.6f}")
