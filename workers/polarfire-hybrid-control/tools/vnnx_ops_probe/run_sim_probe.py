#!/usr/bin/env python3
"""Run the VNNX simulator over the fixed input set and compare to the float reference.

API per SDK vbx/sim/model_run.py: Model(bytes).run([flat_arrays]); dequant with
model.output_scale_factor / output_zeropoint. Inputs quantized with the TFLite converter
quant params recorded in ops_probe_manifest.json.
"""
import json
import sys

import numpy as np
import vbx.sim

model_name = sys.argv[1]
man = json.load(open("ops_probe_manifest.json"))["models"][model_name]
ins = man["io"]["inputs"]
data = np.load(man["fixed_io"])
ref = data["ref"].astype(np.float64)
n = ref.shape[0]

m = vbx.sim.Model(open(model_name + ".vnnx", "rb").read())

keys = [k for k in data.files if k != "ref"]
def map_key(name):
    for k in keys:
        if k in name:
            return k
    raise SystemExit(f"cannot map tflite input '{name}' to npz keys {keys}")
order = [map_key(d["name"]) for d in ins]
print("input mapping:", [(d["name"], k) for d, k in zip(ins, order)])

outs = []
for i in range(n):
    bufs = []
    for d, k in zip(ins, order):
        q = np.clip(np.round(data[k][i] / d["scale"] + d["zero_point"]), -128, 127).astype(np.int8)
        bufs.append(q.flatten())
    o = m.run(bufs)[0]
    deq = m.output_scale_factor[0] * (o.astype(np.float32) - m.output_zeropoint[0])
    outs.append(deq.reshape(ref.shape[1:]))
sim = np.stack(outs).astype(np.float64)
np.save(model_name + "_sim_out.npy", sim.astype(np.float32))
err = np.abs(sim - ref)
print(f"RESULT[{model_name}] n={ref.size} max_abs_err={err.max():.6f} "
      f"mean_abs_err={err.mean():.6f} ref_range=[{ref.min():.4f},{ref.max():.4f}]")
