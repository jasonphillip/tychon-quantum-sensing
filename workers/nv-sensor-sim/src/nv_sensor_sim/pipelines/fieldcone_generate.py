"""Field-cone eval dataset generator (sequence_eval_fieldcone_v1).

A held-out (off-bias angle x |B|) ladder that measures the tracker's field
acquisition across and BEYOND the v3 training envelope. Three bucket classes:

- ``failure``  — the exact increment-5 cross-axis merge geometries (pairs
  (0,2)/(4,6)); built via the dwell merge machinery so the field passes through
  the true degeneracy.
- ``control``  — in-envelope (angle, |B|) strata the tracker should lock on;
  calibrates the eval.
- ``beyond``   — probes PAST the training walls (> the widened angle cone and/or
  below the 3.0 mT |B| floor); measures the acquisition boundary.

Eval-only (all sequences in the ``test`` split), contract v1, stored noiseless,
grid pinned to v1. The |B| floor and angle cap are deliberately NOT enforced (the
beyond probes must exceed them); the min-per-axis-projection guard (label validity)
and window containment (pinned grid) DO apply. A bucket that cannot fit the pinned
window at valid projections is a stop-and-report error, not a silent drop.
"""

from __future__ import annotations

import datetime
import hashlib
import time
from pathlib import Path

import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.datasets.hashing import content_md5
from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.datasets.writer import DatasetWriter
from nv_sensor_sim.dynamics.angle_stratified import field_at_angle
from nv_sensor_sim.dynamics.coverage_geometry import (
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
    offbias_angle_deg,
)
from nv_sensor_sim.dynamics.dwell_trajectory import (
    first_order_a_merge,
    merge_direction,
    refine_a_merge,
)
from nv_sensor_sim.dynamics.field_trajectory import (
    held_ramp_trajectory,
    static_bias_vector,
)
from nv_sensor_sim.dynamics.render import render_sequence
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT
from nv_sensor_sim.physics.parameters import compute_linewidth
from nv_sensor_sim.pipelines.batch_generate import _get_git_sha, _get_versions
from nv_sensor_sim.pipelines.sequence_generate import _axis_scale_trajectory

_GEOM_KEY = 7  # per-sequence rng spawn key for fieldcone geometry
_BUCKET_CLASS_CODE = {"failure": 0, "control": 1, "beyond": 2}


def _build_bucket_trajectory(
    bucket: dict,
    bias_vec: np.ndarray,
    n_timesteps: int,
    rng: np.random.Generator,
    *,
    plan_adapter: SimOSAdapter,
    gamma_fwhm_hz: float,
    azimuth_sweep_deg: float,
    window_pin_Hz: tuple[float, float],
    D_hz: float,
    window_margin_hz: float,
    min_axis_projection_T: float,
    nv_axes: np.ndarray,
    max_tries: int,
) -> tuple[np.ndarray, dict]:
    """Build one held-ramp trajectory for a bucket, retrying the azimuth.

    ``failure`` buckets ramp through the true (p, q) merge; ``control``/``beyond``
    buckets sweep azimuth at the fixed (angle, |B|) stratum so the lines move while
    the off-bias angle and magnitude stay pinned. Returns ``(traj, meta)`` or raises
    if no valid geometry is found (stop-and-report).
    """
    allowed = min(D_hz - window_pin_Hz[0], window_pin_Hz[1] - D_hz) - window_margin_hz

    def _ok(traj: np.ndarray) -> bool:
        proj = np.abs(traj @ np.asarray(nv_axes, dtype=float).T)
        if float(proj.min()) < min_axis_projection_T:
            return False
        return max_line_offset_over_traj_hz(traj, nv_axes, D_hz, gamma_fwhm_hz) <= allowed

    pair = bucket.get("pair")
    t0 = int(round(0.3 * (n_timesteps - 1)))
    t1 = int(round(0.7 * (n_timesteps - 1)))
    for _ in range(max_tries):
        if pair is not None:
            p, q = int(pair[0]), int(pair[1])
            w_hat, w_norm = merge_direction(p, q, nv_axes)
            a0 = first_order_a_merge(bias_vec, p, q, nv_axes)
            delta_a = float(6.0 * gamma_fwhm_hz / (GAMMA_HZ_PER_T * w_norm))
            a_merge, _sep = refine_a_merge(plan_adapter, bias_vec, w_hat, p, q, a0, delta_a, nv_axes)
            sign = 1.0 if rng.random() < 0.5 else -1.0
            jig = 1.0 + 0.05 * rng.standard_normal()
            ext_start = (a_merge + sign * delta_a * jig) * w_hat
            ext_end = (a_merge - sign * delta_a * jig) * w_hat
            traj = held_ramp_trajectory(bias_vec, ext_start, ext_end, n_timesteps, t0, t1)
        else:
            angle = float(bucket["angle_deg"])
            b_mag = float(bucket["B_mT"]) * 1e-3
            phi0 = float(rng.uniform(0.0, 2.0 * np.pi))
            dphi = np.radians(azimuth_sweep_deg)
            ext_start = field_at_angle(bias_vec, angle, b_mag, phi0) - bias_vec
            ext_end = field_at_angle(bias_vec, angle, b_mag, phi0 + dphi) - bias_vec
            traj = held_ramp_trajectory(bias_vec, ext_start, ext_end, n_timesteps, t0, t1)
        if _ok(traj):
            realized_angle = float(offbias_angle_deg(traj, bias_vec).max())
            realized_min_b = min_field_magnitude_T(traj)
            return traj, {
                "bucket_class": _BUCKET_CLASS_CODE[bucket["class"]],
                "target_angle_deg": float(bucket.get("angle_deg", realized_angle)),
                "target_B_mT": float(bucket.get("B_mT", realized_min_b * 1e3)),
                "realized_max_offbias_angle_deg": realized_angle,
                "realized_min_B_T": realized_min_b,
                "merge_pair_p": int(pair[0]) if pair is not None else -1,
                "merge_pair_q": int(pair[1]) if pair is not None else -1,
            }
    raise RuntimeError(
        f"fieldcone bucket {bucket} admits no window-fitting, projection-valid geometry "
        f"in {max_tries} azimuth tries -- stop-and-report (this (angle,|B|) cannot be "
        f"realized inside the pinned grid)"
    )


def generate_fieldcone_dataset(
    output_dir: str,
    *,
    master_seed: int,
    bucket_spec: list[dict],
    seqs_per_bucket: int = 12,
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
    min_axis_projection_T: float = 0.4e-3,
    window_margin_frac: float = 0.02,
    azimuth_sweep_deg: float = 20.0,
    axis_offsets_hz: tuple[float, ...] | None = None,
    nv_density_ppm: float = 0.0,
    sweep_description: str = "",
) -> str:
    """Generate the field-cone eval dataset (all sequences in the ``test`` split)."""
    nv_axes = NV_AXES_UNIT
    n_lines = 2 * len(nv_axes)
    gamma_fwhm_hz = compute_linewidth(p1_ppm)
    bias_vec = static_bias_vector(bias_B0_T, bias_direction_uvw)
    freq_range = (float(freq_range_Hz[0]), float(freq_range_Hz[1]))
    if not freq_range[0] < freq_range[1]:
        raise ValueError(f"freq_range_Hz must satisfy lo < hi, got {freq_range}")
    if seqs_per_bucket < 12:
        raise ValueError(f"seqs_per_bucket must be >= 12 (dispatch), got {seqs_per_bucket}")
    valid_classes = set(_BUCKET_CLASS_CODE)
    for b in bucket_spec:
        if b.get("class") not in valid_classes:
            raise ValueError(f"bucket class must be one of {valid_classes}, got {b.get('class')!r}")
    D_hz = 0.5 * (freq_range[0] + freq_range[1])
    window_margin_hz = window_margin_frac * 0.5 * (freq_range[1] - freq_range[0])
    if axis_offsets_hz is not None:
        axis_offsets_hz = tuple(float(v) for v in axis_offsets_hz)
        if len(axis_offsets_hz) != len(nv_axes):
            raise ValueError(f"axis_offsets_hz must have {len(nv_axes)} entries")
    axis_offsets_arr = None if axis_offsets_hz is None else np.asarray(axis_offsets_hz, dtype=float)
    contrast_tuple = (
        None if axis_contrast_scale is None else tuple(float(v) for v in axis_contrast_scale)
    )

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

    n_seq = len(bucket_spec) * seqs_per_bucket
    rng = np.random.default_rng(master_seed)
    seeds = rng.choice(2**31, size=n_seq, replace=False).tolist()

    per_seq_out: list[dict[str, np.ndarray]] = []
    frequencies: np.ndarray | None = None
    meta: dict[str, list] = {
        k: []
        for k in (
            "bucket_class",
            "target_angle_deg",
            "target_B_mT",
            "realized_max_offbias_angle_deg",
            "realized_min_B_T",
            "merge_pair_p",
            "merge_pair_q",
        )
    }
    t_start = time.perf_counter()
    seq_idx = 0
    for bucket in bucket_spec:
        for _ in range(seqs_per_bucket):
            seed = int(seeds[seq_idx])
            geom_rng = np.random.default_rng([seed, _GEOM_KEY])
            traj, bmeta = _build_bucket_trajectory(
                bucket,
                bias_vec,
                n_timesteps,
                geom_rng,
                plan_adapter=plan_adapter,
                gamma_fwhm_hz=gamma_fwhm_hz,
                azimuth_sweep_deg=azimuth_sweep_deg,
                window_pin_Hz=freq_range,
                D_hz=D_hz,
                window_margin_hz=window_margin_hz,
                min_axis_projection_T=min_axis_projection_T,
                nv_axes=nv_axes,
                max_tries=200,
            )
            axis_scales = _axis_scale_trajectory(
                contrast_tuple,
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
            for key in meta:
                meta[key].append(bmeta[key])
            seq_idx += 1
        print(
            f"  bucket {bucket['class']} angle={bucket.get('angle_deg')} B={bucket.get('B_mT')} "
            f"pair={bucket.get('pair')}: {seq_idx}/{n_seq} ({time.perf_counter() - t_start:.0f}s)"
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
    res_lo, res_hi = float(data["resonance_freqs"].min()), float(data["resonance_freqs"].max())
    if res_lo < freq_range[0] or res_hi > freq_range[1]:
        raise RuntimeError(
            f"resonance labels leave the pinned window: [{res_lo / 1e9:.4f}, {res_hi / 1e9:.4f}] "
            f"GHz vs [{freq_range[0] / 1e9:.4f}, {freq_range[1] / 1e9:.4f}] GHz"
        )

    simos_ver, qutip_ver = _get_versions()
    config_str = (
        f"fieldcone:{master_seed}:{n_timesteps}:{dt_s}:{p1_ppm}:{bias_B0_T}:{bias_direction_uvw}"
        f":{bucket_spec}:{seqs_per_bucket}:{min_axis_projection_T}:{window_margin_frac}"
        f":{azimuth_sweep_deg}:{collision_threshold_linewidths}:{freq_range}:{n_freq_points}"
        f":{contrast_tuple}:{axis_contrast_drift_std}:{axis_contrast_drift_tau_frames}"
        f":offsets={axis_offsets_hz}:density={nv_density_ppm}"
    )
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]
    if not sweep_description:
        sweep_description = (
            f"field-cone eval ladder: {len(bucket_spec)} (off-bias angle x |B|) buckets "
            f"x {seqs_per_bucket} sequences (failure = exact (0,2)/(4,6) merges, control = "
            f"in-envelope, beyond = past the widened cone / below the 3.0 mT floor) on a "
            f"{bias_B0_T * 1e3:.2f} mT bias along {bias_direction_uvw}; azimuth-sweep "
            f"{azimuth_sweep_deg:.0f} deg per sequence; grid pinned to v1. Cues: "
            f"axis_offsets_hz={axis_offsets_hz}, nv_density_ppm={nv_density_ppm}."
        )

    mw_s0 = float(getattr(render_cfg, "base_saturation_s0", 0.1))
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
        linewidth_rendered_Hz=gamma_fwhm_hz * float(np.sqrt(1.0 + mw_s0)),
        mw_saturation_s0=mw_s0,
        collision_threshold_linewidths=collision_threshold_linewidths,
        sweep_description=sweep_description,
        sweep_mode="fieldcone",
        min_axis_projection_T=min_axis_projection_T,
        window_margin_frac=window_margin_frac,
        axis_contrast_scale=contrast_tuple,
        axis_contrast_drift_std=(axis_contrast_drift_std if axis_contrast_drift_std > 0 else None),
        axis_contrast_drift_tau_frames=(
            axis_contrast_drift_tau_frames if axis_contrast_drift_std > 0 else None
        ),
        bias_B0_T=bias_B0_T,
        bias_direction_uvw=bias_direction_uvw,
        axis_offsets_hz=axis_offsets_hz,
        nv_density_ppm=(nv_density_ppm if nv_density_ppm > 0 else None),
    )

    ang = np.asarray(meta["realized_max_offbias_angle_deg"], dtype=float)
    minb = np.asarray(meta["realized_min_B_T"], dtype=float)
    bc = np.asarray(meta["bucket_class"], dtype=int)
    manifest.sequence_stats = {
        "test": {
            "n_sequences": int(n_seq),
            "fieldcone_buckets": [
                {**b, "n": seqs_per_bucket, "class_code": _BUCKET_CLASS_CODE[b["class"]]}
                for b in bucket_spec
            ],
            "realized_offbias_angle_deg": {
                "min": float(ang.min()),
                "mean": float(ang.mean()),
                "max": float(ang.max()),
            },
            "realized_field_magnitude_mT": {
                "min": float(minb.min() * 1e3),
                "max": float(minb.max() * 1e3),
            },
            "class_counts": {
                name: int((bc == code).sum()) for name, code in _BUCKET_CLASS_CODE.items()
            },
        }
    }
    manifest.validate()

    per_sequence = {
        "bucket_class": np.asarray(meta["bucket_class"], dtype=np.int8),
        "target_angle_deg": np.asarray(meta["target_angle_deg"], dtype=np.float32),
        "target_B_mT": np.asarray(meta["target_B_mT"], dtype=np.float32),
        "realized_max_offbias_angle_deg": np.asarray(
            meta["realized_max_offbias_angle_deg"], dtype=np.float32
        ),
        "realized_min_B_T": np.asarray(meta["realized_min_B_T"], dtype=np.float32),
        "merge_pair_p": np.asarray(meta["merge_pair_p"], dtype=np.int8),
        "merge_pair_q": np.asarray(meta["merge_pair_q"], dtype=np.int8),
    }
    seeds_arr = np.asarray(seeds, dtype=np.int64)
    manifest.data_md5 = content_md5(
        {
            **data,
            "frequencies": frequencies,
            "bias": bias_vec,
            "seeds": seeds_arr,
            **{f"per_seq/{k}": v for k, v in per_sequence.items()},
        }
    )
    writer = DatasetWriter(Path(output_dir))
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
    print(f"Field-cone eval written to {output_path} (data_md5 {manifest.data_md5})")
    return output_path
