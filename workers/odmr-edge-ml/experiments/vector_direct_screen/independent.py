"""Slow manufactured reference only: laboratory-frame Hamiltonian in SciPy.

This does not share the local-frame Hamiltonian or its derivative implementation.
It checks mathematical fidelity, not optical pumping or measured NV spectra.
"""
from __future__ import annotations
import numpy as np
from scipy.linalg import eigvalsh

def reference_transitions(parameters, bias_uT, gamma):
    # Cartesian spin-1 representation (S_i)jk = -i epsilon_ijk.
    spin = np.array([[[0,0,0],[0,0,-1j],[0,1j,0]],
                     [[0,0,1j],[0,0,0],[-1j,0,0]],
                     [[0,-1j,0],[1j,0,0],[0,0,0]]],dtype=complex)
    axes = [(1,1,1),(1,-1,-1),(-1,1,-1),(-1,-1,1)]
    output = []
    for row in np.asarray(parameters):
        field = np.asarray(bias_uT) + row[:3]
        zeeman = sum(gamma*field[j]*spin[j] for j in range(3))
        transitions = []
        for axis in axes:
            n = np.array(axis,dtype=float)/np.sqrt(3)
            ns = sum(n[j]*spin[j] for j in range(3))
            h = row[3]*(ns@ns) + zeeman
            eigen = eigvalsh(h,check_finite=True)
            transitions.extend([eigen[1]-eigen[0],eigen[2]-eigen[0]])
        output.append(transitions)
    return np.asarray(output)

def manufactured_parameters():
    # Fixed non-evaluation cases. No population, calibration selection or RNG.
    return np.array([
        [0,0,0,2870,2,.06,1,0],
        [-18,11,7,2869.65,1.1,.025,.985,-.009],
        [19,-17,13,2870.35,2.9,.115,1.015,.009],
        [8,19,-19,2870.1,1.7,.08,.995,.003],
        [-13,-11,-9,2869.8,2.6,.04,1.005,-.004],
    ],dtype=float)
