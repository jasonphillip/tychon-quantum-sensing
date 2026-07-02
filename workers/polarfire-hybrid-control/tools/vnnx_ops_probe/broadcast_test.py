#!/usr/bin/env python3
"""Does the VNNX sim feed input0 to both operands of a two-input MUL? Compare sim vs a*b, a*a, b*b."""
import numpy as np
import vbx.sim

m = vbx.sim.Model(open("mul2in.vnnx", "rb").read())
rng = np.random.default_rng(7)
# mild, distinct codes (rep-dataset-like)
qa = rng.integers(-60, 60, size=16).astype(np.int8)
qb = rng.integers(-60, 60, size=16).astype(np.int8)
sa, za = m.input_scale_factor[0], m.input_zeropoint[0]
sb, zb = m.input_scale_factor[1], m.input_zeropoint[1]
so, zo = m.output_scale_factor[0], m.output_zeropoint[0]
a = (qa.astype(np.float64) - za) * sa
b = (qb.astype(np.float64) - zb) * sb
sim = m.run([qa, qb])[0].astype(np.float64)
sim_f = (sim - zo) * so
for label, expect in (("a*b", a * b), ("a*a", a * a), ("b*b", b * b), ("b*a_swapscale", ((qb - za) * sa) * ((qa - zb) * sb))):
    print(f"  sim vs {label:14s}: max_abs_err={np.abs(sim_f - expect).max():.6f}")
print(f"  sim codes : {m.run([qa, qb])[0][:8]}")
print(f"  a*b codes : {np.clip(np.round(a*b/so+zo),-128,127).astype(np.int8)[:8]}")
print(f"  a*a codes : {np.clip(np.round(a*a/so+zo),-128,127).astype(np.int8)[:8]}")
