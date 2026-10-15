"""Manufactured single-axis spin-1 spectra. No datasets or model inference."""
from dataclasses import dataclass, replace
import numpy as np

D_HZ = 2_871_000_000.0
ELECTRON_GAMMA = -1.76085963023e11
NV_GAMMA = ELECTRON_GAMMA * 1.000357
GAMMA_MHZ_UT = abs(NV_GAMMA) / (2*np.pi) * 1e-12
FREQUENCIES_MHZ = np.linspace(2820., 2920., 100)
SX = np.array([[0,1,0],[1,0,1],[0,1,0]],complex)/np.sqrt(2)
SY = np.array([[0,-1j,0],[1j,0,-1j],[0,1j,0]],complex)/np.sqrt(2)
SZ = np.diag([1.,0.,-1.])
SZ2 = SZ @ SZ
NOMINAL_CONTRAST = .015

@dataclass(frozen=True)
class Point:
    field_uT: float = 45.
    theta: float = 0.
    phi: float = 0.
    bias_uT: float = 0.
    width_mhz: float = 5.
    contrast: float = .015
    center_mhz: float = .3
    slope: float = .02
    temperature_K: float = 293.15
    mw_scale: float = 1.
    gradient: float = .196875

def field_vector(p):
    s,c=np.sin(p.theta),np.cos(p.theta)
    return p.field_uT*np.array([s*np.cos(p.phi),s*np.sin(p.phi),c])

def transitions(p, vector_uT=None):
    field=field_vector(p) if vector_uT is None else np.asarray(vector_uT,float)
    field=field+np.array([0.,0.,p.bias_uT])
    # SimOS Hamiltonian is in rad/s. Divide by 2*pi*1e6 for stable MHz coordinates.
    H=(D_HZ/1e6)*(SZ2-2/3*np.eye(3))
    H+=(-.0742*(p.temperature_K-300))*SZ2
    H=H.astype(complex)-NV_GAMMA/(2*np.pi)*1e-12*(
        field[0]*SX+field[1]*SY+field[2]*SZ)
    energies,states=np.linalg.eigh(H)
    zero=int(np.argmax(abs(states[1,:])**2))
    strength=abs(states.conj().T @ SX @ states[:,zero])**2
    selected=[j for j in range(3) if j!=zero and strength[j]>1e-6]
    return abs(energies[selected]-energies[zero]),strength[selected],{
        "ms0_index":zero,"allowed_transitions":len(selected),
        "dipole_threshold_distance":float(min(abs(strength[j]-1e-6) for j in range(3) if j!=zero)),
        "eigenvalue_min_gap_mhz":float(np.min(np.diff(energies)))}

def raw_depth(p, vector_uT=None):
    centers,weights,diagnostics=transitions(p,vector_uT)
    factors=p.mw_scale*np.linspace(1-p.gradient/2,1+p.gradient/2,10)
    saturation=.1*factors**2
    hwhm=p.width_mhz*np.sqrt(1+saturation)/2
    amplitudes=.03*(saturation/(1+saturation))/(.1/1.1)
    distance=FREQUENCIES_MHZ[None,None,:]-centers[None,:,None]
    lines=hwhm[:,None,None]**2/(distance**2+hwhm[:,None,None]**2)
    depth=np.mean(amplitudes[:,None]*np.sum(weights[None,:,None]*lines,axis=1),axis=0)
    diagnostics.update({"max_bin":int(np.argmax(depth)),
        "max_gap":float(np.sort(depth)[-1]-np.sort(depth)[-2]),
        "raw_max_depth":float(depth.max())})
    return depth,diagnostics

def fixed_amplitude_factor():
    reference=Point(field_uT=45,theta=0,phi=0,bias_uT=1000,width_mhz=5)
    depth,_=raw_depth(reference)
    return NOMINAL_CONTRAST/float(depth.max())

def forward(p,normalization="historical",factor=None,vector_uT=None):
    depth,diagnostics=raw_depth(p,vector_uT)
    if normalization=="historical":
        scale=p.contrast/depth.max()
    elif normalization=="fixed_amplitude":
        if factor is None:raise ValueError("global amplitude factor required")
        scale=factor*(p.contrast/NOMINAL_CONTRAST)
    else:raise ValueError("unknown normalization")
    signal=1-depth*scale
    signal=np.interp(FREQUENCIES_MHZ-p.center_mhz,FREQUENCIES_MHZ,signal,
                     left=signal[0],right=signal[-1])
    signal=signal+p.slope*(FREQUENCIES_MHZ-2870)/100
    if not np.isfinite(signal).all() or np.any(signal<=0):
        raise ValueError("invalid manufactured mean")
    return signal,diagnostics

def photon_budget(snr,contrast=.015):
    return (snr/(.30*contrast))**2
