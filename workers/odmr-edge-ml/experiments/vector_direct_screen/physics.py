"""Ideal spin-1 Hamiltonian and equal-weight Lorentzian ensemble.

Units are MHz and microtesla. This is not an optical pumping model.
Geometry matches the existing vector BLUE and simulator axes.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

CFG = json.loads((Path(__file__).with_name("config.json")).read_text())
AXES = np.array([[1,1,1],[1,-1,-1],[-1,1,-1],[-1,-1,1]], dtype=float) / np.sqrt(3)
SX = np.array([[0,1,0],[1,0,1],[0,1,0]], dtype=complex) / np.sqrt(2)
SY = np.array([[0,-1j,0],[1j,0,-1j],[0,1j,0]], dtype=complex) / np.sqrt(2)
SZ = np.diag([1.,0.,-1.]).astype(complex)
SPIN = np.stack([SX,SY,SZ])
# Rows map laboratory vectors into a right-handed local NV frame.
EX = np.cross(np.broadcast_to([0.,0.,1.], AXES.shape), AXES)
EX /= np.linalg.norm(EX, axis=1, keepdims=True)
FRAMES = np.stack([EX, np.cross(AXES, EX), AXES], axis=1)
FIELD_OPS = CFG["gamma_MHz_per_uT"] * np.einsum("alj,lik->ajik", FRAMES, SPIN)
OPS = np.concatenate([FIELD_OPS, np.broadcast_to(SZ @ SZ, (4,1,3,3))], axis=1)

class Engine:
    """One formula with NumPy or PyTorch batched linear algebra."""
    def __init__(self, backend="numpy", device="cpu", dtype="float64"):
        if backend not in ("numpy", "torch") or dtype not in ("float64", "float32"):
            raise ValueError("Unsupported backend or dtype")
        if backend == "numpy" and device != "cpu":
            raise ValueError("NumPy is CPU-only")
        self.backend, self.device, self.dtype_name = backend, device, dtype
        if backend == "torch":
            import torch
            self.xp = torch
            self.real_dtype = getattr(torch, dtype)
            self.complex_dtype = torch.complex128 if dtype == "float64" else torch.complex64
        else:
            self.xp = np
            self.real_dtype = getattr(np, dtype)
            self.complex_dtype = np.complex128 if dtype == "float64" else np.complex64
        self.ops = self.array(OPS, complex_=True)
        self.bias = self.array(CFG["bias_uT"])
        self.freq = self.array(np.linspace(CFG["frequency_start_MHz"],
                                         CFG["frequency_stop_MHz"], CFG["frequency_bins"]))
        self.x = (self.freq - 2870.) / 65.
        self.lower = self.array(CFG["lower"])
        self.upper = self.array(CFG["upper"])
        self.scale = self.array(CFG["scales"])

    def array(self, value, complex_=False):
        dtype = self.complex_dtype if complex_ else self.real_dtype
        if self.backend == "torch":
            return self.xp.as_tensor(value, dtype=dtype, device=self.device)
        return np.asarray(value, dtype=dtype)

    def numpy(self, value):
        return value.detach().cpu().numpy() if self.backend == "torch" else np.asarray(value)

    def sync(self):
        if self.backend == "torch" and self.device.startswith("cuda"):
            self.xp.cuda.synchronize()

    def clamp(self, value, low, high=None):
        if self.backend == "torch":
            return self.xp.clamp(value, min=low, max=high)
        return np.clip(value, low, high)

    def stack(self, arrays, axis):
        return self.xp.stack(arrays, dim=axis) if self.backend == "torch" else np.stack(arrays, axis=axis)

    def sum(self, value, axis):
        return value.sum(dim=axis) if self.backend == "torch" else value.sum(axis=axis)

    def affine_calibration(self):
        """Cache the fixed nominal Jacobian inverse; no labels or observed fit."""
        if not hasattr(self,"_affine"):
            rates,jac = self.spectrum(self.array([CFG["nominal"]]),True)
            scaled = jac[0]*self.scale[None,:]
            weights = self.xp.sqrt(1/rates[0])
            whitened = scaled*weights[:,None]
            inverse = self.xp.linalg.pinv(whitened)*weights[None,:]
            self._affine = (rates[0],inverse)
        return self._affine

    def transitions(self, params, derivatives=False):
        if params.ndim != 2 or params.shape[1] != 8:
            raise ValueError("Parameters must have shape (N,8)")
        x = self.xp
        field = params[:, :3] + self.bias
        h = x.einsum("nj,ajik->naik", field.to(self.complex_dtype) if self.backend == "torch" else field, self.ops[:,:3])
        h = h + params[:,3,None,None,None] * self.ops[None,:,3,:,:]
        energies, vectors = x.linalg.eigh(h)
        centers = (energies[:,:,1:] - energies[:,:,:1]).reshape(-1,8)
        if not derivatives:
            return centers
        d_e = x.einsum("naij,apik,nakj->napj", vectors.conj(), self.ops, vectors).real
        d_f = d_e[:,:,:,1:] - d_e[:,:,:,:1]
        if self.backend == "torch":
            d_f = d_f.permute(0,1,3,2)
        else:
            d_f = d_f.transpose(0,1,3,2)
        return centers, d_f.reshape(-1,8,4)

    def spectrum(self, params, jacobian=False):
        if jacobian:
            centers, d_f = self.transitions(params, True)
        else:
            centers = self.transitions(params)
        w = params[:,4,None,None]
        t = 2 * (self.freq[None,None,:] - centers[:,:,None]) / w
        lorentz = 1 / (1 + t*t)
        summed = self.sum(lorentz, 1)
        base, contrast = params[:,6,None], params[:,5,None]
        values = base * (1 - contrast * summed / 8) + params[:,7,None] * self.x[None,:]
        if not jacobian:
            return values
        d_l_center = 4*t/w * lorentz*lorentz
        d_l_width = 2*t*t/w * lorentz*lorentz
        first = -base[:,:,None] * contrast[:,:,None] / 8 * self.xp.einsum("nlf,nlp->nfp", d_l_center, d_f)
        rest = [-base*contrast/8*self.sum(d_l_width,1), -base*summed/8,
                1-contrast*summed/8, self.x[None,:] + params[:,0,None]*0]
        tail = self.stack(rest, -1)
        return values, (self.xp.cat([first,tail],dim=-1) if self.backend=="torch"
                        else np.concatenate([first,tail],axis=-1))

def validate_counts(counts):
    a = np.asarray(counts)
    if a.ndim != 2 or a.shape[1] != CFG["frequency_bins"]:
        raise ValueError("Wrong count shape")
    if not np.isfinite(a).all() or np.any(a < 0):
        raise ValueError("Counts must be finite and nonnegative")
    return a

def poisson_counts(params, seed, photons_per_bin=None):
    """Only a future approved data producer may call this explicit-noise helper."""
    exposure = CFG["photons_per_bin"] if photons_per_bin is None else photons_per_bin
    if not np.isfinite(exposure) or exposure <= 0:
        raise ValueError("Exposure must be positive")
    rates = Engine().spectrum(np.asarray(params,dtype=float))
    if np.any(rates <= 0):
        raise ValueError("Nonpositive photon rate")
    return np.random.default_rng(seed).poisson(exposure*rates)
