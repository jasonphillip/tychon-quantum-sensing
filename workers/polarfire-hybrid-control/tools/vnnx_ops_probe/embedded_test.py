#!/usr/bin/env python3
"""3-way check: VNNX sim vs the vnnx's own embedded test vector vs TFLite, same inputs."""
import sys
import numpy as np
import tensorflow as tf
import vbx.sim

name = sys.argv[1]
m = vbx.sim.Model(open(f"{name}.vnnx", "rb").read())
sim_out = m.run([t.flatten() for t in m.test_input])[0].astype(np.int64)
emb_out = np.asarray(m.test_output[0]).astype(np.int64)
print(f"[{name}] sim(test_input) == embedded test_output ? "
      f"{np.array_equal(sim_out, emb_out)}  max_lsb_diff={np.abs(sim_out - emb_out).max()}")
interp = tf.lite.Interpreter(model_path=f"{name}_int8.tflite")
interp.allocate_tensors()
ins, outs = interp.get_input_details(), interp.get_output_details()
# vnnx input order is REVERSED vs tflite input_details (scales [a,b] vs [b,a]) -> map by scale
for d in ins:
    sc = d["quantization"][0]
    idx = int(np.argmin([abs(s - sc) for s in m.input_scale_factor]))
    interp.set_tensor(d["index"], m.test_input[idx].reshape(d["shape"]))
interp.invoke()
tfl_out = interp.get_tensor(outs[0]["index"]).flatten().astype(np.int64)
print(f"[{name}] tflite(test_input) vs embedded: eq={np.array_equal(tfl_out, emb_out)} "
      f"max_lsb_diff={np.abs(tfl_out - emb_out).max()}")
print(f"[{name}] tflite(test_input) vs sim:      eq={np.array_equal(tfl_out, sim_out)} "
      f"max_lsb_diff={np.abs(tfl_out - sim_out).max()}")
print(f"  emb : {emb_out[:8]}")
print(f"  sim : {sim_out[:8]}")
print(f"  tfl : {tfl_out[:8]}")
