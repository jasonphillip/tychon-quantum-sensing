#!/usr/bin/env python3
"""VNNX simulator vs TFLite-INT8 reference on identical random int8 inputs (per-op accuracy)."""
import sys
import numpy as np
import tensorflow as tf
import vbx.sim

name = sys.argv[1]
N = 64
rng = np.random.default_rng(20260702)
interp = tf.lite.Interpreter(model_path=f"{name}_int8.tflite")
interp.allocate_tensors()
ins, outs = interp.get_input_details(), interp.get_output_details()
m = vbx.sim.Model(open(f"{name}.vnnx", "rb").read())
maxe, meane = 0.0, []
for _ in range(N):
    bufs = []
    for d in ins:
        q = rng.integers(-128, 128, size=d["shape"]).astype(np.int8)
        interp.set_tensor(d["index"], q)
        bufs.append(q.flatten())
    interp.invoke()
    osc, ozp = outs[0]["quantization"]
    t = (interp.get_tensor(outs[0]["index"]).astype(np.float64) - ozp) * osc
    o = m.run(bufs)[0]
    s = (m.output_scale_factor[0] * (o.astype(np.float64) - m.output_zeropoint[0])).reshape(t.shape)
    e = np.abs(s - t)
    maxe = max(maxe, e.max())
    meane.append(e.mean())
print(f"SIMVS[{name}] n={N} max_abs_err={maxe:.6f} mean_abs_err={np.mean(meane):.6f} out_lsb={osc:.6f}")
