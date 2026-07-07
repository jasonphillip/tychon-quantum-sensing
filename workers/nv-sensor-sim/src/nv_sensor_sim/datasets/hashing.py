"""Reproducible content hashing for dataset arrays.

The md5 is taken over array content (dtype + shape + raw bytes, key-sorted) rather
than the HDF5 file, which embeds per-object timestamps. Two generations from the
same seed therefore hash identically — the determinism signal recorded in the
manifest as ``data_md5``.
"""

from __future__ import annotations

import hashlib

import numpy as np


def content_md5(arrays: dict[str, np.ndarray]) -> str:
    """md5 over array content (dtype + shape + bytes, key-sorted).

    Parameters
    ----------
    arrays : dict[str, np.ndarray]
        Named arrays to hash. Keys are hashed alongside the data so a renamed or
        reordered array changes the digest.

    Returns
    -------
    str
        Hex md5 digest, independent of HDF5 container timestamps.
    """
    h = hashlib.md5()
    for key in sorted(arrays):
        a = np.ascontiguousarray(arrays[key])
        h.update(key.encode())
        h.update(str(a.dtype).encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()
