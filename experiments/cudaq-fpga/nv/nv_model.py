"""Synthetic NV electron/13C finite-pulse model; times us, frequencies MHz."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1., -1.]).astype(complex)
XE, YE, ZE = (np.kron(p, I) for p in (X, Y, Z))
ZN = np.kron(I, Z)
SZ = np.diag([0., -1.])
SZIZ = np.kron(SZ, Z / 2)
SZIX = np.kron(SZ, X / 2)
P0 = np.diag([1., 1., 0., 0.])
RHO0 = P0.astype(complex) / 2


def config():
    return json.loads((ROOT / "config.json").read_text())


def hamiltonian(detuning_mhz, model, phase_rad=0., drive=False):
    """H/hbar in rad/us; basis |0 up>, |0 down>, |-1 up>, |-1 down>."""
    vals = [detuning_mhz, phase_rad, *model.values()]
    if not np.all(np.isfinite(vals)) or model["rabi_mhz"] <= 0:
        raise ValueError("finite model values and positive Rabi frequency required")
    h = (detuning_mhz / 2 * ZE
         + model["nuclear_frequency_mhz"] / 2 * ZN
         + model["hyperfine_parallel_mhz"] * SZIZ
         + model["hyperfine_transverse_mhz"] * SZIX)
    if drive:
        h = h + model["rabi_mhz"] / 2 * (np.cos(phase_rad) * XE + np.sin(phase_rad) * YE)
    return 2 * np.pi * h


def unitary(h, duration_us):
    if not np.isfinite(duration_us) or duration_us < 0:
        raise ValueError("duration must be nonnegative and finite")
    e, v = np.linalg.eigh(h)
    return (v * np.exp(-1j * e * duration_us)) @ v.conj().T


def evolve(h, rho, duration_us):
    u = unitary(h, duration_us)
    return u @ rho @ u.conj().T


def rk4_density(h, rho, duration_us, max_step_us=0.0005):
    """Independent commutator ODE; does not use eigendecomposition."""
    if duration_us == 0:
        return rho.copy()
    n = int(np.ceil(duration_us / max_step_us))
    dt = duration_us / n
    def rhs(r):
        return -1j * (h @ r - r @ h)
    r = rho.copy()
    for _ in range(n):
        k1 = rhs(r)
        k2 = rhs(r + dt / 2 * k1)
        k3 = rhs(r + dt / 2 * k2)
        k4 = rhs(r + dt * k3)
        r += dt / 6 * (k1 + 2*k2 + 2*k3 + k4)
    return r


def sequence_density(detuning_mhz, delay_us, phase_rad, model, solver=evolve):
    pulse_us = 1 / (4 * model["rabi_mhz"])
    r = solver(hamiltonian(detuning_mhz, model, np.pi/2, True), RHO0, pulse_us)
    r = solver(hamiltonian(detuning_mhz, model), r, delay_us)
    return solver(hamiltonian(detuning_mhz, model, phase_rad-np.pi/2, True), r, pulse_us)


def probabilities(detuning_mhz, delays_us, phases_rad, model):
    """Return [phase, delay] bright-state probabilities without numerical clipping."""
    delays = np.asarray(delays_us)
    if delays.ndim != 1 or np.any(delays < 0) or not np.all(np.isfinite(delays)):
        raise ValueError("delays must be finite nonnegative vector")
    pulse = 1 / (4 * model["rabi_mhz"])
    prep = evolve(hamiltonian(detuning_mhz, model, np.pi/2, True), RHO0, pulse)
    e, v = np.linalg.eigh(hamiltonian(detuning_mhz, model))
    free_u = np.einsum("ij,tj,kj->tik", v, np.exp(-1j * delays[:, None]*e), v.conj())
    free_rho = free_u @ prep @ free_u.conj().transpose(0, 2, 1)
    p = []
    for phase in phases_rad:
        u = unitary(hamiltonian(detuning_mhz, model, phase-np.pi/2, True), pulse)
        observable = u.conj().T @ P0 @ u
        p.append(np.einsum("ij,tji->t", observable, free_rho).real)
    p = np.asarray(p)
    if p.min() < -1e-10 or p.max() > 1 + 1e-10:
        raise ArithmeticError("nonphysical probability")
    return p


def probability_features(p):
    return np.concatenate([p[0] - p[2], p[1] - p[3]])


def sample_counts(p, cfg, rng):
    r = cfg["repetitions"]
    # Clip only floating-point roundoff after physicality checks above.
    bright = rng.binomial(r, np.clip(p, 0, 1))
    rate = bright*cfg["photons_bright"] + (r-bright)*cfg["photons_dark"] + r*cfg["photons_background"]
    return rng.poisson(rate).astype(np.int32)


def count_features(counts, cfg):
    scale = cfg["repetitions"] * (cfg["photons_bright"] - cfg["photons_dark"])
    return np.concatenate([counts[0].astype(float)-counts[2], counts[1].astype(float)-counts[3]]) / scale


def quantize(values, fractional_bits=14):
    values = np.asarray(values)
    if not np.all(np.isfinite(values)):
        raise ValueError("nonfinite input")
    raw = np.rint(values * (1 << fractional_bits))
    clipped = int(np.count_nonzero((raw < -32768) | (raw > 32767)))
    return np.clip(raw, -32768, 32767).astype(np.int16), clipped


def integer_match(q, templates):
    diff = templates.astype(np.int64) - q.astype(np.int64)
    score = np.sum(diff*diff, axis=1, dtype=np.int64)
    idx = int(np.argmin(score))
    return idx, int(score[idx])


def golden_minimize(fn, left, right, iterations=30):
    ratio = (np.sqrt(5.) - 1) / 2
    c = right - ratio*(right-left)
    d = left + ratio*(right-left)
    fc, fd = fn(c), fn(d)
    for _ in range(iterations):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right-ratio*(right-left)
            fc = fn(c)
        else:
            left, c, fc = c, d, fd
            d = left+ratio*(right-left)
            fd = fn(d)
    candidates = [(left, fn(left)), (right, fn(right)), (c, fc), (d, fd)]
    return min(candidates, key=lambda pair: pair[1])[0]
