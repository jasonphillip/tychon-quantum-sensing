"""Fixed smooth broad-line contrast. No signals determine its scale or mask."""
import numpy as np


def kernel():
    offsets=np.arange(-6,7,dtype=float)
    weights=np.exp(-0.5*(offsets/2)**2)
    return weights/weights.sum()


def smooth(values):
    windows=np.lib.stride_tricks.sliding_window_view(np.asarray(values,dtype=float),13,axis=-1)
    return windows@kernel()


def spectral_contrast(values):
    s=smooth(values)
    return s[...,10:-10]-(s[...,:-20]+s[...,20:])/2

