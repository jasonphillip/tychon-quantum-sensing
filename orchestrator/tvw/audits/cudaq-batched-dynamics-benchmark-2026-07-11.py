"""Smoke test: batched open-system dynamics on DGX Spark GB10 (sm_121).
Mimics NV-center workload shape: 3-level system, many Hamiltonians batched,
Lindblad collapse operators, expectation values stored at every step.
"""
import time
import numpy as np
import cupy as cp
import cudaq
from cudaq import boson, Schedule, RungeKuttaIntegrator

cudaq.set_target("dynamics")

# 3-level system (spin-1 ground-state manifold), proper spin-1 matrices
dimensions = {0: 3}
from cudaq import operators
sz_m = np.diag([1.0, 0.0, -1.0]).astype(np.complex128)
sx_m = (1.0 / np.sqrt(2.0)) * np.array(
    [[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=np.complex128)
operators.define("Sz", [3], lambda: sz_m)
operators.define("Sz2", [3], lambda: sz_m @ sz_m)
operators.define("Sx", [3], lambda: sx_m)
Sz = operators.instantiate("Sz", [0])
Sz2 = operators.instantiate("Sz2", [0])
Sx_like = operators.instantiate("Sx", [0])
a = boson.annihilate(0)

D = 2.0 * np.pi * 2.87       # zero-field splitting (arb. units)
drive = 2.0 * np.pi * 0.05

BATCH = 1024
b_fields = np.linspace(-0.5, 0.5, BATCH)

hamiltonians = [D * Sz2 + 2.0 * np.pi * b * Sz + drive * Sx_like for b in b_fields]

# initial state: equal superposition of the 3 levels
psi0_vec = cp.array([1.0, 1.0, 1.0], dtype=cp.complex128) / np.sqrt(3.0)
initial_states = [cudaq.State.from_data(psi0_vec) for _ in range(BATCH)]

# Lindblad collapse: dephasing + decay
gamma = 0.1
# one collapse-operator list per Hamiltonian in the batch
collapse = [[np.sqrt(gamma) * Sz, np.sqrt(gamma / 2) * a] for _ in range(BATCH)]

steps = np.linspace(0, 5.0, 201)
schedule = Schedule(steps, ["t"])

t0 = time.time()
results = cudaq.evolve(
    hamiltonians,
    dimensions,
    schedule,
    initial_states,
    observables=[Sz],
    collapse_operators=collapse,
    store_intermediate_results=cudaq.IntermediateResultSave.EXPECTATION_VALUE,
    integrator=RungeKuttaIntegrator(),
)
t1 = time.time()

print(f"BATCH={BATCH} 3-level Lindblad evolutions, 201 steps: {t1-t0:.2f} s wall")
print(f"n results: {len(results)}")
r0 = results[0].expectation_values()
final_sz_first = [res.expectation_values()[-1][0].expectation() for res in results[:3]]
final_sz_last = [res.expectation_values()[-1][0].expectation() for res in results[-3:]]
print("final <Sz> first 3 of batch:", [f"{v:.4f}" for v in final_sz_first])
print("final <Sz> last 3 of batch:", [f"{v:.4f}" for v in final_sz_last])
print("PASS: batched dynamics ran on GB10 sm_121 aarch64")
