"""Only the outer chunk size differs from the frozen classical policy.

The solver, initialization, likelihood, bounds, residual check and fallback are
imported unchanged. CFG is never mutated. The private policy body has a
structural equality fixture against the frozen source.
"""
from __future__ import annotations
import numpy as np
from experiments.vector_direct_screen.physics import Engine, validate_counts
from experiments.vector_direct_screen.baseline import initialize, observed_check, full_fallback

CHUNKS = (256, 1024, 4096)

def _chunked_policy(engine,counts,variant,chunk_size):
    """Resident-data policy, including its residual guard and all rejected rows."""
    e,x = engine,engine.xp
    if variant not in ("affine","peaks","calibrated","lm"):
        raise ValueError("Unknown policy")
    parts = {"parameters":[],"accepted":[],"reduced_deviance":[],"fallback":[]}
    for start in range(0,len(counts),chunk_size):
        batch = counts[start:start+chunk_size]
        if variant=="lm":
            solution = full_fallback(e,batch)
            fallback = x.ones(len(batch),dtype=x.bool,device=e.device) if e.backend=="torch" else np.ones(len(batch),dtype=bool)
        else:
            p = initialize(e,batch,variant)
            accepted,reduced = observed_check(e,batch,p)
            fallback = ~accepted
            # The mask comes only from observed likelihood. It never sees target parameters.
            if bool(fallback.any()):
                repaired = full_fallback(e,batch[fallback])
                p[fallback] = repaired["parameters"]
                accepted[fallback] = repaired["accepted"]
                reduced[fallback] = repaired["reduced_deviance"]
            solution = {"parameters":p,"accepted":accepted,"reduced_deviance":reduced}
        for key in parts:
            parts[key].append(fallback if key=="fallback" else solution[key])
    if not len(counts):
        raise ValueError("Empty batch")
    return {key:(x.cat(value,dim=0) if e.backend=="torch" else np.concatenate(value,axis=0))
            for key,value in parts.items()}


def policy_device(engine, counts, variant="affine", *, chunk_size=256):
    if type(chunk_size) is not int or chunk_size not in CHUNKS:
        raise ValueError("Only the three prospectively declared chunks are allowed")
    return _chunked_policy(engine, counts, variant, chunk_size)


def fit_counts(counts, *, backend="numpy", device="cpu", dtype="float64",
               variant="affine", chunk_size=256):
    """Fresh engine/calibration; host inputs and outputs, including all fallback."""
    counts = validate_counts(counts)
    engine = Engine(backend, device, dtype)
    result = policy_device(engine, engine.array(counts), variant,
                           chunk_size=chunk_size)
    engine.sync()
    return {key: engine.numpy(value) for key, value in result.items()}
