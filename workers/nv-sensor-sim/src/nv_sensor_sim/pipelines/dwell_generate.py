"""Dwell-sweep eval dataset generator (identity-through-merge lineage).

Builds an eval-only, contract-v1, noiseless dataset of held-template merged-dwell
sequences: each sequence drives one chosen cross-axis line pair (and, by NV
symmetry, its mirror pair) together for a parameterized number of frames D, then
either crosses or bounces. Balanced 50/50 cross-vs-bounce per D bucket so a
constant-velocity prior cannot decide identity from kinematics alone.

Reuses the v1 render stack, manifest, writer and stats. Two default-OFF physics
knobs (``axis_offsets_hz`` static strain ladder, ``nv_density_ppm`` NV-NV
cross-relaxation) flow through unchanged; with both off the generation is
byte-identical to the same call without them. See docs/dataset-contract.md
(optional keys -- dwell lineage) and logs/sequence_dwell_v1_generation.md.
"""

from __future__ import annotations

import datetime
import hashlib
import time
from pathlib import Path

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.datasets.writer import DatasetWriter
from nv_sensor_sim.dynamics.dwell_trajectory import (
    build_dwell_trajectory,
    dwell_scalars,
    enumerate_dwell_templates,
)
from nv_sensor_sim.dynamics.field_trajectory import static_bias_vector
from nv_sensor_sim.dynamics.render import render_sequence
from nv_sensor_sim.dynamics.sequence_stats import split_sequence_stats
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT
from nv_sensor_sim.physics.parameters import compute_linewidth
from nv_sensor_sim.pipelines.batch_generate import _get_git_sha, _get_versions
from nv_sensor_sim.pipelines.sequence_generate import _axis_scale_trajectory

# Per-sequence rng spawn keys (disjoint from the contrast-drift key = 1).
_JITTER_KEY = 5

_DWELL_TOPOLOGIES = ("cross", "bounce")


def _content_md5(arrays: dict[str, np.ndarray]) -> str:
    """Reproducible md5 over array content (dtype + shape + bytes, key-sorted).

    Independent of HDF5 container timestamps, so two generations with the same
    seed hash identically -- the determinism signal used in the pre-flight check
    and recorded in the manifest.
    """
    h = hashlib.md5()
    for key in sorted(arrays):
        a = np.ascontiguousarray(arrays[key])
        h.update(key.encode())
        h.update(str(a.dtype).encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def _realized_dwell_frames(sep_hz: np.ndarray, gamma_fwhm_hz: float) -> int:
    """Longest contiguous run of frames with pair separation below one linewidth."""
    within = sep_hz < gamma_fwhm_hz
    best = run = 0
    for w in within:
        run = run + 1 if w else 0
        best = max(best, run)
    return int(best)


def generate_dwell_sequence_dataset(
    output_dir: str,
    *,
    master_seed: int,
    n_timesteps: int = 256,
    dt_s: float = 1.0e-3,
    p1_ppm: float = 40.0,
    temperature_K: float = 300.0,
    bias_B0_T: float,
    bias_direction_uvw: tuple[float, float, float],
    freq_range_Hz: tuple[float, float],
    n_freq_points: int,
    axis_contrast_scale: tuple[float, ...] | None = None,
    axis_contrast_drift_std: float = 0.0,
    axis_contrast_drift_tau_frames: float = 64.0,
    collision_threshold_linewidths: float = 1.0,
    dwell_frames_list: tuple[int, ...] = (8, 16, 32, 64, 128, 192),
    seqs_per_bucket: int = 24,
    approach_linewidths: float = 6.0,
    ramp_frames: int = 4,
    sep_min_linewidths: float = 1.5,
    min_axis_projection_T: float = 0.4e-3,
    jitter_frac: float = 0.05,
    position_jitter_frames: int = 8,
    min_hold_frames: int = 8,
    axis_offsets_hz: tuple[float, ...] | None = None,
    nv_density_ppm: float = 0.0,
    sweep_description: str = "",
) -> str:
    """Generate the dwell-sweep eval dataset (all sequences in the ``test`` split).

    Parameters mirror the v1 sequence generator where shared (bias, contrast
    ladder + AR(1) drift, pinned freq grid, collision threshold). Dwell-specific
    controls: ``dwell_frames_list`` x ``_DWELL_TOPOLOGIES`` buckets of
    ``seqs_per_bucket`` sequences each; the merged dwell is held for D frames
    with steep ``ramp_frames``-frame ramps approaching from
    ``approach_linewidths`` of separation. ``axis_offsets_hz`` /
    ``nv_density_ppm`` are the default-OFF physics cues.

    Returns the absolute output directory path.
    """
    nv_axes = NV_AXES_UNIT
    n_lines = 2 * len(nv_axes)
    gamma_fwhm_hz = compute_linewidth(p1_ppm)
    bias_vec = static_bias_vector(bias_B0_T, bias_direction_uvw)
    freq_range = (float(freq_range_Hz[0]), float(freq_range_Hz[1]))
    if not freq_range[0] < freq_range[1]:
        raise ValueError(f"freq_range_Hz must satisfy lo < hi, got {freq_range}")
    if axis_offsets_hz is not None:
        axis_offsets_hz = tuple(float(v) for v in axis_offsets_hz)
        if len(axis_offsets_hz) != len(nv_axes):
            raise ValueError(f"axis_offsets_hz must have {len(nv_axes)} entries")
    axis_offsets_arr = None if axis_offsets_hz is None else np.asarray(axis_offsets_hz, dtype=float)

    # --- Adapters: pinned render grid + coarse planning grid (centers are grid
    # independent, so plan on a cheap grid). ---
    render_cfg = SimulationConfig(
        random_seed=master_seed,
        use_optics=False,
        include_nitrogen=False,
        temperature_K=temperature_K,
        n_freq_points=n_freq_points,
        mw_freq_range_Hz=freq_range,
    )
    adapter = SimOSAdapter(render_cfg)
    plan_cfg = SimulationConfig(
        use_optics=False,
        include_nitrogen=False,
        temperature_K=temperature_K,
        n_freq_points=41,
        mw_freq_range_Hz=freq_range,
    )
    plan_adapter = SimOSAdapter(plan_cfg)

    templates = enumerate_dwell_templates(
        plan_adapter,
        bias_vec,
        approach_linewidths,
        gamma_fwhm_hz,
        sep_min_linewidths=sep_min_linewidths,
        min_axis_projection_T=min_axis_projection_T,
        nv_axes=nv_axes,
    )
    if not templates:
        raise RuntimeError(
            "no viable single-event dwell templates at this bias/grid; loosen "
            "sep_min_linewidths or check the bias geometry"
        )
    n_variants = len(templates) * 2  # x approach_sign
    print(
        f"D={compute_linewidth(p1_ppm) / 1e6:.4f} MHz Gamma; {len(templates)} merge templates "
        f"(pairs {[(t['p'], t['q']) for t in templates]}); {n_variants} kinematic variants"
    )

    # --- Seeds: one disjoint seed per sequence (eval-only -> all in test). ---
    n_seq = len(dwell_frames_list) * len(_DWELL_TOPOLOGIES) * seqs_per_bucket
    rng = np.random.default_rng(master_seed)
    seeds = rng.choice(2**31, size=n_seq, replace=False).tolist()

    # --- Build + render every sequence. ---
    per_seq_out: list[dict[str, np.ndarray]] = []
    frequencies: np.ndarray | None = None
    meta = {
        k: []
        for k in (
            "exit_topology",
            "dwell_frames",
            "dwell_frames_target",
            "merge_p",
            "merge_q",
            "mirror_p",
            "mirror_q",
            "approach_sign",
            "template_idx",
        )
    }
    contrast_scale_tuple = (
        None if axis_contrast_scale is None else tuple(float(v) for v in axis_contrast_scale)
    )

    seq_idx = 0
    t_start = time.perf_counter()
    for dwell in dwell_frames_list:
        for topo in _DWELL_TOPOLOGIES:
            for b in range(seqs_per_bucket):
                seed = int(seeds[seq_idx])
                combo = b % n_variants
                template = templates[combo // 2]
                approach_sign = 1 if combo % 2 == 0 else -1

                jrng = np.random.default_rng([seed, _JITTER_KEY])
                delta_a = float(template["delta_a"] * (1.0 + jitter_frac * jrng.standard_normal()))
                delta_a = max(delta_a, 0.25 * template["delta_a"])  # keep the ramp meaningful
                a_in, a_out = dwell_scalars(
                    template["a_merge"], delta_a, topo, approach_sign=approach_sign
                )

                rem = n_timesteps - 2 * ramp_frames - dwell
                if rem < 2 * min_hold_frames:
                    raise ValueError(
                        f"n_timesteps={n_timesteps} too small for dwell={dwell} + 2x"
                        f"ramp={ramp_frames} + 2x min_hold={min_hold_frames}"
                    )
                pre_base = rem // 2
                lo = min_hold_frames
                hi = rem - min_hold_frames
                off = int(jrng.integers(-position_jitter_frames, position_jitter_frames + 1))
                pre_hold = int(np.clip(pre_base + off, lo, hi))
                post_hold = rem - pre_hold

                traj = build_dwell_trajectory(
                    bias_vec,
                    template["w_hat"],
                    a_in,
                    template["a_merge"],
                    a_out,
                    pre_hold,
                    ramp_frames,
                    dwell,
                    post_hold,
                )
                axis_scales = _axis_scale_trajectory(
                    contrast_scale_tuple,
                    axis_contrast_drift_std,
                    axis_contrast_drift_tau_frames,
                    n_timesteps,
                    len(nv_axes),
                    seed,
                )
                out = render_sequence(
                    adapter,
                    traj,
                    p1_ppm=p1_ppm,
                    gamma_fwhm_hz=gamma_fwhm_hz,
                    k=collision_threshold_linewidths,
                    nv_axes=nv_axes,
                    axis_mw_scales=axis_scales,
                    axis_offsets_hz=axis_offsets_arr,
                    nv_density_ppm=nv_density_ppm,
                )
                if frequencies is None:
                    frequencies = out["frequencies"]
                per_seq_out.append(out)

                p, q = template["p"], template["q"]
                res = out["resonance_freqs"].astype(float)
                realized = _realized_dwell_frames(np.abs(res[:, p] - res[:, q]), gamma_fwhm_hz)
                meta["exit_topology"].append(0 if topo == "cross" else 1)
                meta["dwell_frames"].append(realized)
                meta["dwell_frames_target"].append(int(dwell))
                meta["merge_p"].append(p)
                meta["merge_q"].append(q)
                meta["mirror_p"].append(template["p_mirror"])
                meta["mirror_q"].append(template["q_mirror"])
                meta["approach_sign"].append(approach_sign)
                meta["template_idx"].append(combo // 2)
                seq_idx += 1
        print(
            f"  dwell D={dwell}: {seq_idx}/{n_seq} rendered ({time.perf_counter() - t_start:.0f}s)"
        )

    assert frequencies is not None
    data = {
        key: np.stack([s[key] for s in per_seq_out], axis=0)
        for key in (
            "spectra",
            "B_true",
            "resonance_freqs",
            "line_axis",
            "line_transition",
            "collision_mask",
            "line_collision",
        )
    }

    # --- Guards on the realized labels. ---
    res_lo, res_hi = float(data["resonance_freqs"].min()), float(data["resonance_freqs"].max())
    if res_lo < freq_range[0] or res_hi > freq_range[1]:
        raise RuntimeError(
            f"resonance labels leave the pinned window: [{res_lo / 1e9:.4f}, {res_hi / 1e9:.4f}] "
            f"GHz vs [{freq_range[0] / 1e9:.4f}, {freq_range[1] / 1e9:.4f}] GHz"
        )
    realized = np.asarray(meta["dwell_frames"])
    target = np.asarray(meta["dwell_frames_target"])
    tol = np.maximum(1, np.ceil(0.1 * target))
    bad = np.abs(realized - target) > tol
    if bad.any():
        raise RuntimeError(
            f"{int(bad.sum())} sequences miss the +/-10% realized-dwell target; "
            f"worst |realized-target| = {int(np.max(np.abs(realized - target)))}"
        )

    # --- Provenance + manifest. ---
    simos_ver, qutip_ver = _get_versions()
    config_str = (
        f"dwell:{master_seed}:{n_timesteps}:{dt_s}:{p1_ppm}:{bias_B0_T}:{bias_direction_uvw}"
        f":{tuple(dwell_frames_list)}:{seqs_per_bucket}:{approach_linewidths}:{ramp_frames}"
        f":{sep_min_linewidths}:{min_axis_projection_T}:{jitter_frac}:{position_jitter_frames}"
        f":{collision_threshold_linewidths}:{freq_range}:{n_freq_points}"
        f":{contrast_scale_tuple}:{axis_contrast_drift_std}:{axis_contrast_drift_tau_frames}"
        f":offsets={axis_offsets_hz}:density={nv_density_ppm}"
    )
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

    if not sweep_description:
        sweep_description = (
            f"dwell-sweep eval: held template, one cross-axis coalescing pair (+ its NV-symmetry "
            f"mirror pair) driven together for a merged dwell of D in {tuple(dwell_frames_list)} "
            f"frames on a {bias_B0_T * 1e3:.2f} mT bias along {bias_direction_uvw}; exit topology "
            f"balanced 50/50 cross vs bounce per D bucket; {seqs_per_bucket} sequences per "
            f"(D, topology) bucket over {len(templates)} merge templates x 2 approach signs; "
            f"ramp {ramp_frames} frames from {approach_linewidths:.0f} linewidths of separation; "
            f"per-sequence endpoint/position jitter and AR(1) contrast drift; four spectator lines "
            f"separation-protected (>= {sep_min_linewidths:.1f} Gamma). Cues: "
            f"axis_offsets_hz={axis_offsets_hz}, nv_density_ppm={nv_density_ppm}."
        )

    mw_s0 = float(getattr(render_cfg, "base_saturation_s0", 0.1))
    linewidth_rendered_hz = gamma_fwhm_hz * float(np.sqrt(1.0 + mw_s0))
    manifest = DatasetManifest(
        generator_git_sha=_get_git_sha(),
        config_hash=config_hash,
        simos_version=simos_ver,
        qutip_version=qutip_ver,
        numpy_version=np.__version__,
        backend="qutip",
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        contract_version="v1",
        master_seed=master_seed,
        train_seeds=[],
        val_seeds=[],
        test_seeds=seeds,
        n_spectra_train=0,
        n_spectra_val=0,
        n_spectra_test=n_seq,
        train_indices=[],
        val_indices=[],
        test_indices=list(range(n_seq)),
        n_freq_points=n_freq_points,
        freq_range_Hz=freq_range,
        p1_concentration_range_ppm=(p1_ppm, p1_ppm),
        temperature_range_K=(temperature_K, temperature_K),
        b1_gradient_range=(0.0, 0.0),
        b_perp_range_T=(0.0, 0.0),
        sequence_mode=True,
        n_timesteps=n_timesteps,
        dt_s=dt_s,
        n_lines=n_lines,
        hyperfine=False,
        linewidth_Hz=gamma_fwhm_hz,
        linewidth_rendered_Hz=linewidth_rendered_hz,
        mw_saturation_s0=mw_s0,
        collision_threshold_linewidths=collision_threshold_linewidths,
        sweep_description=sweep_description,
        sweep_mode="dwell",
        jitter_frac=jitter_frac,
        axis_contrast_scale=contrast_scale_tuple,
        axis_contrast_drift_std=(axis_contrast_drift_std if axis_contrast_drift_std > 0 else None),
        axis_contrast_drift_tau_frames=(
            axis_contrast_drift_tau_frames if axis_contrast_drift_std > 0 else None
        ),
        bias_B0_T=bias_B0_T,
        bias_direction_uvw=bias_direction_uvw,
        axis_offsets_hz=axis_offsets_hz,
        nv_density_ppm=(nv_density_ppm if nv_density_ppm > 0 else None),
    )

    # Standard label stats + dwell-specific block, in sequence_stats["test"].
    stats = split_sequence_stats(
        data["resonance_freqs"],
        data["collision_mask"],
        data["B_true"],
        gamma_fwhm_hz,
        nv_axes=nv_axes,
    )
    stats["dwell_config"] = {
        "dwell_frames_list": list(dwell_frames_list),
        "seqs_per_bucket": seqs_per_bucket,
        "topologies": list(_DWELL_TOPOLOGIES),
        "approach_linewidths": approach_linewidths,
        "ramp_frames": ramp_frames,
        "sep_min_linewidths": sep_min_linewidths,
        "n_merge_templates": len(templates),
        "merge_templates": [
            {
                "p": t["p"],
                "q": t["q"],
                "p_mirror": t["p_mirror"],
                "q_mirror": t["q_mirror"],
                "a_merge_T": t["a_merge"],
                "axes": [t["p"] // 2, t["q"] // 2],
            }
            for t in templates
        ],
        "mirror_pair_note": (
            "NV C3v symmetry forces the mirror pair (p^1,q^1) to coalesce with the target at "
            "the reflected frequency; each sequence therefore has one target coalescing pair + "
            "its mirror (four spectator lines protected). A single-pair cross-axis merge is "
            "physically impossible in the noiseless L=8 model."
        ),
    }
    per_bucket = {}
    et = np.asarray(meta["exit_topology"])
    for d in dwell_frames_list:
        for ti, topo in enumerate(_DWELL_TOPOLOGIES):
            mask = (target == d) & (et == ti)
            per_bucket[f"D{d}_{topo}"] = {
                "n": int(mask.sum()),
                "realized_dwell_mean": float(realized[mask].mean()),
                "realized_dwell_min": int(realized[mask].min()),
                "realized_dwell_max": int(realized[mask].max()),
            }
    stats["dwell_buckets"] = per_bucket
    manifest.sequence_stats = {"test": stats}
    manifest.validate()

    # --- Write. ---
    writer = DatasetWriter(Path(output_dir))
    per_sequence = {
        "exit_topology": np.asarray(meta["exit_topology"], dtype=np.int8),
        "dwell_frames": np.asarray(meta["dwell_frames"], dtype=np.int32),
        "dwell_frames_target": np.asarray(meta["dwell_frames_target"], dtype=np.int32),
        "merge_p": np.asarray(meta["merge_p"], dtype=np.int8),
        "merge_q": np.asarray(meta["merge_q"], dtype=np.int8),
        "mirror_p": np.asarray(meta["mirror_p"], dtype=np.int8),
        "mirror_q": np.asarray(meta["mirror_q"], dtype=np.int8),
        "approach_sign": np.asarray(meta["approach_sign"], dtype=np.int8),
        "template_idx": np.asarray(meta["template_idx"], dtype=np.int8),
    }
    seeds_arr = np.asarray(seeds, dtype=np.int64)
    manifest.data_md5 = _content_md5(
        {
            **data,
            "frequencies": frequencies,
            "bias": bias_vec,
            "seeds": seeds_arr,
            **{f"per_seq/{k}": v for k, v in per_sequence.items()},
        }
    )
    writer.write_sequences(
        spectra=data["spectra"],
        frequencies=frequencies,
        B_true=data["B_true"],
        resonance_freqs=data["resonance_freqs"],
        line_axis=data["line_axis"],
        line_transition=data["line_transition"],
        collision_mask=data["collision_mask"],
        line_collision=data["line_collision"],
        bias=bias_vec,
        seeds=seeds_arr,
        split="test",
        per_sequence=per_sequence,
    )
    writer.write_manifest(manifest)
    output_path = writer.finalize()
    print(f"Dwell dataset written to {output_path} (dataset.h5 md5 {manifest.data_md5})")
    return output_path
