"""Learned through-crossing tracker — anchored detector + recurrent association (Increment 2).

This module defines the trainable tracker. Increment 1 shipped it as a shape-only skeleton;
Increment 2a grounds the per-frame candidates on a fixed frequency-anchor grid so the
association head has stable supervision targets, and extends the outputs with everything the
training losses and the Increment-1 metrics consume.

Design (canonical, supersedes the pre-ops-guard reading of docs/design/02): **deployable-first
with an explicit V250/MSS graph partition.** The PolarFire SoC splits work between the V250 NPU
(strict INT8, ops-whitelisted) and the MSS RISC-V host (full float, no whitelist) — the same
split ``polarfire-hybrid-control`` already uses. So:

- **V250-targeted (ops-guarded):** only the per-frame feedforward :class:`FrameFeatureExtractor`
  (stride-2 Conv2d (1,k) + ReLU stages + 1x1-conv heads). It must pass
  :func:`...validation.ops_guard.check_model_ops`.
- **host/MSS (unconstrained):** the recurrence, the association/assignment, and the BLUE decode.
  ``softmax``/``matmul``/``sigmoid``/``tanh`` are fine here because they never reach the NPU graph.

Every learnable block is offered as a **two-implementation / one-signature** pair so Increment 2
can train both and measure what the research variant buys:

- recurrent core: :class:`ReLURecurrentCell` (deployable-first) / :class:`GatedKalmanNetCore`
  (research; gated, off-NPU).
- association head: :class:`LinearScoreAssociation` (deployable-first; assignment off-graph) /
  :class:`AttentionAssociation` (research; softmax/matmul, off-NPU).

Anchor grounding (the Increment-2a upgrade): the extractor is fully convolutional. After
``n_downsample`` stride-2 stages, output position ``k`` corresponds to input frequency bin
``k * 2**n_downsample`` (stride-2, ``k//2``-padded convs keep centers aligned), so each of the
``K = ceil(n_freq / 2**n_downsample)`` candidates carries a **fixed anchor frequency** plus a
learned scalar offset. Anchors are exact receptive-field centers — the offset head has shared
weights and no positional input, so it could not correct a per-anchor bias; it only refines
within an anchor cell. All positions are in normalized window units (bin / (n_freq - 1) in
[0, 1]); Hz conversion happens outside the model.

Units convention: spectra enter as contract-normalized PL (~1 off-resonance); the tracker feeds
``(1 - PL) * input_gain`` to the extractor (host-side preprocessing — dips become positive
peaks of order 1). ``input_gain`` matters because the real ODMR dips are only ~0.4% of the PL
baseline (measured 0.37–0.77% max depth per frame on ``sequence_sanity_v0``): float32 training
merely absorbs the scale into the first conv, but INT8 deployment (Increment 3) must fold this
gain into the input quantization scale — quantizing raw ``1 - PL`` over a [0, 1] range would
leave the entire signal ~1 LSB deep. Frequencies are normalized window units; axis projections
are regressed in units of ``proj_scale_T`` Tesla (the scale is folded into the frozen BLUE
decode so ``b_est`` is Tesla).

Each block carries an :data:`ExecutionTarget` tag; :func:`v250_targeted_modules` lists the blocks
the ops-guard test treats as the deployability contract.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Protocol

import torch
import torch.nn as nn

from odmr_vector_tracking.vector.geometry import N_AXES, N_LINES_ELECTRONIC, NV_AXES_UNIT


class ExecutionTarget(enum.Enum):
    """Where a block runs in the PolarFire hybrid (drives the ops-guard contract)."""

    V250 = "v250"          # NPU: strict INT8, ops-whitelisted, must pass ops_guard
    HOST_MSS = "host_mss"  # RISC-V host: full float, no op whitelist


@dataclass
class LearnedTrackerConfig:
    """Architecture hyperparameters.

    ``n_candidates`` (K) is derived: ``ceil(n_freq / 2**n_downsample)`` anchor positions from
    the extractor's stride-2 stages — one candidate per output position of the conv stack.
    """

    n_lines: int = N_LINES_ELECTRONIC   # L resonances tracked
    n_axes: int = N_AXES                 # 4 NV axes (BLUE projections)
    n_freq: int = 400                    # F MW-frequency points per frame
    n_downsample: int = 4                # stride-2 conv stages; K = ceil(F / 2**n_downsample)
    feat_dim: int = 32                   # per-candidate feature width
    assoc_dim: int = 16                  # association scoring width
    state_dim: int = 64                  # recurrent state width
    conv_channels: int = 8               # first-stage channels (doubled per stage, capped at 4x)
    conv_kernel: int = 5                 # Conv2d (1, k) kernel width
    dt_s: float = 1.0e-3                 # frame interval (for downstream dynamics)
    proj_scale_T: float = 1.0e-2         # Tesla per unit of the regressed axis projections
    input_gain: float = 1.0              # scale on (1 - PL); set ~1/nominal_contrast so dips
                                         # enter O(1) (INT8 input-quantization scale, Incr. 3)
    motion_prior: bool = False           # explicit per-slot CV kinematics: track_pos =
                                         # (pos + vel) + learned delta; association gates on
                                         # the CV prediction (the KF's inductive bias)
    scheduled_sampling: bool = False     # 2c lever 3: position-recurrence query
                                         # (pred_t = prev_pos + learned delta) whose prev_pos
                                         # is teacher-forced (GT) or model-own per a training
                                         # schedule; prev_pos is a SOFT query prior only — the
                                         # assignment stays unmasked greedy on scores (no
                                         # self-referential hard gate, unlike B3 motion_prior)
    gate_cells: float = 2.0              # assignment gate around the CV prediction, in
                                         # anchor cells (~9 linewidths on the real grid);
                                         # inference-only masking, CE scores stay unmasked
    vel_beta: float = 0.25               # fixed velocity-EMA gain of the CV scaffold (the
                                         # scaffold carries detached — see LearnedTracker —
                                         # so the gain is a constant, not a parameter)

    @property
    def n_candidates(self) -> int:
        """K per-frame anchor candidates (one per extractor output position)."""
        return math.ceil(self.n_freq / 2**self.n_downsample)


@dataclass
class LearnedTrackerOutput:
    """Per-frame outputs over a ``(B, T, F)`` batch.

    Attributes
    ----------
    b_est
        ``(B, T, 3)`` lab-frame B estimate (Tesla) from the BLUE decode.
    assignment
        ``(B, T, L)`` candidate index each line-lock attends to (the data-association result).
    covariance
        ``(B, T, 3, 3)`` posterior covariance of ``b_est``.
    scores
        ``(B, T, L, K)`` raw association-head output (logits for the linear head, soft
        probabilities for the attention head) — the training target for the association CE.
    projections
        ``(B, T, 4)`` regressed axis projections in units of ``cfg.proj_scale_T`` Tesla.
    cand_pos
        ``(B, T, K)`` candidate positions in normalized window units (anchor + learned offset).
    track_pos
        ``(B, T, L)`` per-slot line positions predicted from the recurrent state (normalized
        window units) — the KalmanNet-style state readout that drives the association's
        distance branch; directly supervised against the true line centers.
    tracked_freqs
        ``(B, T, L)`` claimed-identity line centers the Increment-1 metrics consume
        (normalized window units). This is the **state posterior** ``track_pos`` — the MOT
        convention scores track estimates, not raw detections, and the anchored candidates
        are quantized to the conv grid (sub-stride offset regression is aliasing-limited).
        The assigned candidate's position is recoverable as
        ``gather(cand_pos, assignment)`` for diagnostics.
    """

    b_est: torch.Tensor
    assignment: torch.Tensor
    covariance: torch.Tensor
    scores: torch.Tensor
    projections: torch.Tensor
    cand_pos: torch.Tensor
    track_pos: torch.Tensor
    tracked_freqs: torch.Tensor


# --- protocols (the one signature each variant pair shares) ------------------------------

class RecurrentCore(Protocol):
    """``(state, obs) -> new_state``; ``(B, state_dim)`` / ``(B, state_dim)``."""

    def __call__(self, state: torch.Tensor, obs: torch.Tensor) -> torch.Tensor: ...


class AssociationHead(Protocol):
    """``(track_feats (B,L,D), cand_feats (B,K,D), track_pos (B,L), cand_pos (B,K)) ->
    scores (B,L,K)``.

    Positions are in normalized window units. They matter: a purely additive feature score
    ``f(track) + g(cand)`` is separable — its argmax over candidates is the same for every
    slot — so the head needs an explicit track↔candidate *relational* input (position
    differences) to express "the candidate nearest MY predicted position".
    """

    def __call__(
        self,
        track_feats: torch.Tensor,
        cand_feats: torch.Tensor,
        track_pos: torch.Tensor,
        cand_pos: torch.Tensor,
    ) -> torch.Tensor: ...


# --- V250-targeted block (ops-guarded) --------------------------------------------------

class FrameFeatureExtractor(nn.Module):
    """Per-frame anchored peak/feature extractor — the ONLY V250-targeted block.

    Fully convolutional: one spectrum frame ``(B, F)`` → ``(B, 1, 1, F)`` → ``n_downsample``
    stride-2 Conv2d (1,k) + ReLU stages → two 1x1-conv heads:

    - feature head → ``(B, K, feat_dim)`` per-anchor candidate features;
    - offset head (zero-init) → scalar position refinement per anchor; candidate position =
      fixed anchor + offset, in normalized window units.

    Anchors are the exact conv receptive-field centers ``k * 2**n_downsample / (n_freq - 1)``
    (stride-2, ``k//2``-padded stages keep output k centered on input bin ``2k``). Weight
    sharing makes the extractor translation-equivariant — a resonance dip looks the same to
    the heads wherever it sits on the grid.

    Uses only V250-allowed ops (conv2d, relu, add, layout ops), so it passes
    :func:`check_model_ops`. No ``mul`` reaches the graph: any offset scaling lives inside the
    learned head weights.
    """

    EXECUTION_TARGET = ExecutionTarget.V250

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        self.cfg = cfg
        c, k = cfg.conv_channels, cfg.conv_kernel
        pad = k // 2
        convs: list[nn.Conv2d] = []
        in_ch = 1
        for i in range(cfg.n_downsample):
            out_ch = min(c * 2**i, 4 * c)
            convs.append(nn.Conv2d(in_ch, out_ch, (1, k), stride=(1, 2), padding=(0, pad)))
            in_ch = out_ch
        self.convs = nn.ModuleList(convs)
        self.act = nn.ReLU()
        self.feat_head = nn.Conv2d(in_ch, cfg.feat_dim, (1, 1))
        self.offset_head = nn.Conv2d(in_ch, 1, (1, 1))
        # Zero-init offsets: candidate positions start exactly on the anchors.
        nn.init.zeros_(self.offset_head.weight)
        nn.init.zeros_(self.offset_head.bias)  # type: ignore[arg-type]

        anchors = (
            torch.arange(cfg.n_candidates, dtype=torch.float32)
            * float(2**cfg.n_downsample)
            / float(cfg.n_freq - 1)
        )
        self.register_buffer("anchors", anchors)  # (K,) normalized window units

    def forward(self, frame: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """``frame (B, F)`` → ``(cand_feats (B, K, feat_dim), cand_pos (B, K))``."""
        b = frame.shape[0]
        x = frame.reshape(b, 1, 1, self.cfg.n_freq)
        for conv in self.convs:
            x = self.act(conv(x))
        feat = self.feat_head(x)                                   # (B, D, 1, K)
        offset = self.offset_head(x)                               # (B, 1, 1, K)
        cand_feats = feat.reshape(b, self.cfg.feat_dim, -1).permute(0, 2, 1)  # (B, K, D)
        cand_pos = offset.reshape(b, -1) + self.get_buffer("anchors")         # (B, K)
        return cand_feats, cand_pos


# --- host/MSS recurrent cores (two-impl / one-signature) --------------------------------

class ReLURecurrentCell(nn.Module):
    """Deployable-first KalmanNet-style cell: ReLU MLP gain, residual state update.

    Ops-clean (linear + relu + add) — it would also pass the V250 guard, but it runs on the
    host per the partition. ``forward(state, obs) -> new_state``; ``obs`` is the per-frame
    observation embedding ``(B, state_dim)``.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        s = cfg.state_dim
        self.in_state = nn.Linear(s, s)
        self.in_obs = nn.Linear(s, s)
        self.act = nn.ReLU()
        self.update = nn.Linear(s, s)
        # Small-gain init of the residual branch: default init compounds over T recurrent
        # steps and explodes the state (observed ~1e8 at T=128), saturating every downstream
        # head. Scaling the update weights down keeps the state O(1) across the sequence at
        # init while (unlike an exact zero init) every path still carries gradient from the
        # first step; training grows the gain only as far as the loss pushes it.
        with torch.no_grad():
            self.update.weight.mul_(0.05)
        nn.init.zeros_(self.update.bias)  # type: ignore[arg-type]

    def forward(self, state: torch.Tensor, obs: torch.Tensor) -> torch.Tensor:
        h = self.act(self.in_state(state) + self.in_obs(obs))
        return state + self.update(h)  # residual (learned-gain) update


class GatedKalmanNetCore(nn.Module):
    """Research variant: GRU-style gated recurrent core (explicit sigmoid/tanh gates).

    FLAGGED off-NPU — measured 2026-07-02: ``sigmoid``/``tanh`` themselves are V250-supported
    (ban falsified), but a recurrent cell needs its state as a second graph input, and
    multi-graph-input models are broken in the SDK 2.0.x flow (sim corruption; the one-step
    cell composition also crashes ``vnnx_compile``). So this still runs only on the host.
    Same signature as :class:`ReLURecurrentCell`. See polarfire
    ``docs/vnnx_ops_support_probe_2026-07-02.md``.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        s = cfg.state_dim
        self.w_z = nn.Linear(2 * s, s)  # update gate
        self.w_r = nn.Linear(2 * s, s)  # reset gate
        self.w_h = nn.Linear(2 * s, s)  # candidate

    def forward(self, state: torch.Tensor, obs: torch.Tensor) -> torch.Tensor:
        xh = torch.cat([state, obs], dim=-1)
        z = torch.sigmoid(self.w_z(xh))
        r = torch.sigmoid(self.w_r(xh))
        h_tilde = torch.tanh(self.w_h(torch.cat([r * state, obs], dim=-1)))
        return (1.0 - z) * state + z * h_tilde


def exclusive_greedy_assign(scores: torch.Tensor) -> torch.Tensor:
    """One-to-one greedy assignment by descending score. ``(B, L, K) -> (B, L)`` long.

    Iteratively claims the best remaining (slot, candidate) pair per batch element, masking
    the claimed slot row and candidate column — mutual exclusion so two locks can never claim
    the same candidate (a per-line independent argmax can). Greedy-on-scores is the
    lightweight alternative to Hungarian; L is tiny (8) and K ≥ L, so every slot gets a
    distinct candidate. Off-graph (inference bookkeeping only — never on the NPU).
    """
    b, n_slots, n_cand = scores.shape
    s = scores.detach().clone()
    out = torch.zeros(b, n_slots, dtype=torch.long, device=scores.device)
    neg = torch.finfo(s.dtype).min
    rows = torch.arange(b, device=scores.device)
    for _ in range(min(n_slots, n_cand)):
        flat = s.reshape(b, n_slots * n_cand).argmax(dim=-1)
        li, ki = flat // n_cand, flat % n_cand
        out[rows, li] = ki
        s[rows, li, :] = neg
        s[rows, :, ki] = neg
    return out


# --- host/MSS association heads (two-impl / one-signature) -------------------------------

class LinearScoreAssociation(nn.Module):
    """Deployable-first association: additive-MLP cost with relational distance + appearance branches.

    ``forward(track_feats, cand_feats, track_pos, cand_pos) -> logits (B,L,K)``. Projected
    track/candidate features combine by broadcast **add**, plus two relational branches built
    from rectified signed differences:

    - **position** ``relu(p_l - x_k)`` / ``relu(x_k - p_l)`` — the ReLU pair encodes |distance|
      without ``mul``/``abs`` and is what breaks additive separability: without it the score is
      ``f(track) + g(cand)`` and every slot argmaxes the same candidate.
    - **appearance** (increment-3 lever B) ``relu(t_app - c_app)`` / ``relu(c_app - t_app)`` on
      the projected per-line/per-candidate appearance vectors — a physically-meaningful
      fingerprint (per-axis Zeeman depth/contrast; see ``docs/design/04…`` §Tier-1 #1) folded
      into the score to break the identity tie at a crossing where positions coincide. Its
      output projection is **zero-initialized** so the head starts *exactly* at the pre-lever
      baseline and the fingerprint is learned in (repo idiom).

    Compute stays linear + relu + add (+ layout cat). The hard assignment is computed
    **off-graph** by :meth:`assign` (greedy argmax), so no banned op ever reaches the NPU.
    Training applies ``log_softmax`` to these logits inside the loss only — loss machinery
    never ships.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        d, a = cfg.feat_dim, cfg.assoc_dim
        self.track_proj = nn.Linear(d, a)
        self.cand_proj = nn.Linear(d, a)
        self.dist_proj = nn.Linear(2, a)
        # Appearance relational branch (lever B): mirrors the position branch on projected
        # appearance vectors. Zero-init the output projection so the branch is inert at start.
        self.app_track_proj = nn.Linear(d, a)
        self.app_cand_proj = nn.Linear(d, a)
        self.app_proj = nn.Linear(2 * a, a)
        nn.init.zeros_(self.app_proj.weight)
        nn.init.zeros_(self.app_proj.bias)  # type: ignore[arg-type]
        self.act = nn.ReLU()
        self.score = nn.Linear(a, 1)

    def forward(
        self,
        track_feats: torch.Tensor,
        cand_feats: torch.Tensor,
        track_pos: torch.Tensor,
        cand_pos: torch.Tensor,
    ) -> torch.Tensor:
        t = self.track_proj(track_feats)[:, :, None, :]   # (B, L, 1, A)
        c = self.cand_proj(cand_feats)[:, None, :, :]     # (B, 1, K, A)
        dpos = track_pos[:, :, None] - cand_pos[:, None, :]           # (B, L, K)
        rel = torch.stack([self.act(dpos), self.act(-dpos)], dim=-1)  # (B, L, K, 2)
        g = self.dist_proj(rel)                           # (B, L, K, A)
        # Appearance relational branch: rectified difference of projected appearance vectors.
        ta = self.app_track_proj(track_feats)[:, :, None, :]         # (B, L, 1, A)
        ca = self.app_cand_proj(cand_feats)[:, None, :, :]           # (B, 1, K, A)
        dapp = ta - ca                                               # (B, L, K, A) broadcast
        app_rel = torch.cat([self.act(dapp), self.act(-dapp)], dim=-1)  # (B, L, K, 2A)
        app = self.app_proj(app_rel)                      # (B, L, K, A) — zero at init
        h = self.act(t + c + g + app)                     # (B, L, K, A)
        return self.score(h).squeeze(-1)                  # (B, L, K)

    @staticmethod
    def assign(cost: torch.Tensor) -> torch.Tensor:
        """Mutually exclusive off-graph assignment. ``(B,L,K) -> (B,L)``."""
        return exclusive_greedy_assign(cost)


class AttentionAssociation(nn.Module):
    """Research variant: scaled dot-product attention assignment (softmax + matmul).

    FLAGGED off-NPU — ``matmul``/``softmax`` are V250-banned. Same signature; returns a soft
    assignment ``(B, L, K)`` that already sums to 1 over candidates.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        d, a = cfg.feat_dim, cfg.assoc_dim
        # +1 input: the track/candidate position joins the feature vector before projection.
        self.q = nn.Linear(d + 1, a)
        self.k = nn.Linear(d + 1, a)
        self._scale = 1.0 / math.sqrt(a)

    def forward(
        self,
        track_feats: torch.Tensor,
        cand_feats: torch.Tensor,
        track_pos: torch.Tensor,
        cand_pos: torch.Tensor,
    ) -> torch.Tensor:
        q = self.q(torch.cat([track_feats, track_pos.unsqueeze(-1)], dim=-1))  # (B, L, A)
        k = self.k(torch.cat([cand_feats, cand_pos.unsqueeze(-1)], dim=-1))    # (B, K, A)
        logits = torch.matmul(q, k.transpose(1, 2)) * self._scale  # (B, L, K)
        return torch.softmax(logits, dim=-1)

    @staticmethod
    def assign(attn: torch.Tensor) -> torch.Tensor:
        """Mutually exclusive hard assignment from the soft attention. ``(B,L,K) -> (B,L)``."""
        return exclusive_greedy_assign(attn)


# --- host/MSS geometry decode (fixed BLUE) ----------------------------------------------

class GeometryDecoder(nn.Module):
    """Fixed BLUE decode: 4 axis-projections (Σ=0) → 3D vector + covariance.

    The projection→vector map is the analytic pseudo-inverse of the 4×3 NV-axis matrix, held as
    a frozen ``Linear`` (no learnable parameters) — geometry stays exact. The model regresses
    projections in units of ``cfg.proj_scale_T`` Tesla; that scale is folded into the frozen
    weights so ``b_est`` comes out in Tesla. Runs on the host.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        N = NV_AXES_UNIT.astype("float32")               # (4, 3)
        pinv = torch.linalg.pinv(torch.from_numpy(N))    # (3, 4): B = pinv @ projections
        self.decode = nn.Linear(cfg.n_axes, 3, bias=False)
        with torch.no_grad():
            self.decode.weight.copy_(pinv * cfg.proj_scale_T)
        self.decode.weight.requires_grad_(False)
        # Fixed posterior covariance (AᵀA)⁻¹ for unit measurement noise in projection units,
        # scaled to Tesla²; broadcast per frame.
        cov = torch.linalg.pinv(torch.from_numpy(N).T @ torch.from_numpy(N))  # (3, 3)
        self.register_buffer("_cov", cov * cfg.proj_scale_T**2)

    def forward(self, projections: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        b_vec = self.decode(projections)                 # (B, 3) Tesla
        cov = self.get_buffer("_cov").expand(projections.shape[0], 3, 3)
        return b_vec, cov


# --- top-level tracker ------------------------------------------------------------------

class LearnedTracker(nn.Module):
    """Wires extractor (V250) → recurrent core (host) → association (host) → BLUE (host).

    A pure observation-driven filter: the state consumes only the current frame's candidate
    features (never the model's own outputs), so full-BPTT training has no exposure bias and
    needs no teacher forcing. Swap the core / association variant via :func:`build_tracker`.
    """

    def __init__(
        self,
        cfg: LearnedTrackerConfig,
        core: nn.Module,
        association: nn.Module,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.extractor = FrameFeatureExtractor(cfg)   # V250
        self.core = core                              # host
        self.association = association                # host
        self.decoder = GeometryDecoder(cfg)           # host
        # Host glue (small linears; unconstrained).
        self.obs_embed = nn.Linear(cfg.n_candidates * cfg.feat_dim, cfg.state_dim)
        self.state_to_proj = nn.Linear(cfg.state_dim, cfg.n_axes)
        self.state_to_tracks = nn.Linear(cfg.state_dim, cfg.n_lines * cfg.feat_dim)
        self.state_to_track_pos = nn.Linear(cfg.state_dim, cfg.n_lines)
        if cfg.motion_prior and cfg.scheduled_sampling:
            raise ValueError(
                "motion_prior and scheduled_sampling are mutually exclusive query paths; "
                "enable at most one"
            )
        if cfg.scheduled_sampling:
            # Position-recurrence delta head (2c lever 3). Zero-init → at start the query is a
            # constant-position prior (pred_t = prev_pos), a sane tracker prior the loss grows
            # into a learned motion delta. The recurrence carries DETACHED (see forward) so
            # BPTT stays truncated — the O(T)-leverage explosion the motion_prior comment
            # describes does not arise.
            self.ss_delta = nn.Linear(cfg.state_dim, cfg.n_lines)
            nn.init.zeros_(self.ss_delta.weight)
            nn.init.zeros_(self.ss_delta.bias)  # type: ignore[arg-type]
        if cfg.motion_prior:
            # CV kinematic scaffold (2c identity fix): a learned-gain alpha-beta tracker on
            # MEASUREMENTS, with the network refining the output. Per slot and frame:
            #   pred = pos + vel                                  (CV prediction)
            #   z    = association-softmax-weighted candidate position  (the measurement)
            #   kin  = pred + g * (z - pred),  g = sigmoid(gain_head(state))
            #   vel += vel_beta * g * (z - pred)
            #   track_pos = kin + delta(state)   (zero-init free refinement, NOT carried)
            # The scaffold carries DETACHED across steps and is anchored to data through z,
            # so it is stable by construction (convex combination of prediction and
            # measurement) — two failure modes this replaces: full BPTT through the coupled
            # pos/vel recurrences explodes (O(T) leverage of early innovations; training
            # stalls under clipping), and a detached scaffold driven by the free delta head
            # runs away (nothing anchors it to data). Association gates on pred, so
            # merge-exit identity comes from CV coasting exactly as it does for the KF;
            # sigmoid/softmax here are host-side glue (MSS runs float), not NPU ops.
            self.state_to_track_delta = nn.Linear(cfg.state_dim, cfg.n_lines)
            nn.init.zeros_(self.state_to_track_delta.weight)
            nn.init.zeros_(self.state_to_track_delta.bias)  # type: ignore[arg-type]
            self.gain_head = nn.Linear(cfg.state_dim, cfg.n_lines)
            self._gate_n = cfg.gate_cells * float(2**cfg.n_downsample) / float(cfg.n_freq - 1)

    def forward(
        self,
        spectra: torch.Tensor,
        teacher_pos: torch.Tensor | None = None,
        ss_prob: float = 1.0,
    ) -> LearnedTrackerOutput:
        """``spectra (B, T, F)`` (contract-normalized PL) → :class:`LearnedTrackerOutput`.

        ``teacher_pos`` / ``ss_prob`` drive scheduled sampling (2c lever 3) and are ignored
        unless ``cfg.scheduled_sampling``. ``teacher_pos`` is the ``(B, T, L)`` ground-truth
        line centers (normalized window units); at frame ``t`` each slot's previous-position
        query prior is the model's own previous ``track_pos`` with probability ``ss_prob`` and
        the teacher center ``teacher_pos[:, t-1]`` otherwise. ``teacher_pos=None`` (the default,
        and every inference/eval call) forces fully free-running: the query prior is always the
        model's own previous estimate — the exact test-time condition the schedule ramps toward.
        """
        b, T, _ = spectra.shape
        cfg = self.cfg
        # Host-side preprocessing: dips → positive peaks of order 1 (see module docstring;
        # input_gain becomes the INT8 input quantization scale at deployment).
        x = (1.0 - spectra) * cfg.input_gain
        state = spectra.new_zeros(b, cfg.state_dim)

        outs: dict[str, list[torch.Tensor]] = {
            k: [] for k in
            ("b_est", "cov", "scores", "proj", "cand_pos", "track_pos", "assignment")
        }

        kin_pos = kin_vel = None  # CV kinematic scaffold (motion_prior only)
        prev_track: torch.Tensor | None = None  # previous track_pos carry (scheduled_sampling)
        for t in range(T):
            feat, pos = self.extractor(x[:, t, :])             # (B,K,D), (B,K)   [V250]
            obs = self.obs_embed(feat.reshape(b, -1))          # (B, state_dim)   [host]
            state = self.core(state, obs)                      # (B, state_dim)   [host]

            p = self.state_to_proj(state)                      # (B, 4) proj_scale_T units
            b_vec, c = self.decoder(p)                         # (B, 3) T, (B,3,3) [host BLUE]

            track_feats = self.state_to_tracks(state).reshape(b, cfg.n_lines, cfg.feat_dim)
            if cfg.motion_prior and kin_pos is not None:
                assert kin_vel is not None
                pred = kin_pos + kin_vel                       # CV prediction (detached carry)
            elif cfg.scheduled_sampling and prev_track is not None:
                # Position recurrence: query prior = previous position + learned motion delta.
                # The previous position is teacher-forced (GT) or model-own per the schedule;
                # it is a SOFT query prior only (assignment below stays unmasked on scores).
                if teacher_pos is not None:
                    use_model = torch.rand(
                        b, cfg.n_lines, device=spectra.device
                    ) < float(ss_prob)
                    prev_used = torch.where(use_model, prev_track, teacher_pos[:, t - 1, :])
                else:
                    prev_used = prev_track                     # free-running (inference/eval)
                pred = prev_used + self.ss_delta(state)
            else:
                pred = self.state_to_track_pos(state)          # absolute readout (t=0 / plain)
            # Association gates against the (CV-predicted) slot positions.
            sc = self.association(track_feats, feat, pred, pos)  # (B, L, K)      [host]
            if cfg.motion_prior:
                # Measurement = association-weighted candidate position (soft, differentiable).
                z = torch.softmax(sc, dim=-1) @ pos.unsqueeze(-1)   # (B, L, 1)
                z = z.squeeze(-1)                                    # (B, L)
                if kin_vel is None:
                    kin_vel = torch.zeros_like(pred)
                g = torch.sigmoid(self.gain_head(state))             # (B, L) learned gain
                innov = g * (z - pred)
                kin = pred + innov                                   # alpha-beta update
                tpos = kin + self.state_to_track_delta(state)        # free refinement
                kin_vel = (kin_vel + cfg.vel_beta * innov).detach()
                kin_pos = kin.detach()  # scaffold carries without BPTT (see __init__)
                # Motion-gated one-to-one assignment (inference bookkeeping only — the CE
                # trains on the raw scores; masking them would blow up when the target sits
                # outside an early-training garbage gate).
                far = (pred[:, :, None] - pos[:, None, :]).abs() > self._gate_n
                assign = exclusive_greedy_assign(sc.masked_fill(far, -1e9))
            else:
                tpos = pred
                assign = exclusive_greedy_assign(sc)           # one-to-one assign (off-NPU)

            if cfg.scheduled_sampling:
                # Carry the estimate DETACHED so the position recurrence is truncated-BPTT
                # (bounds the O(T) leverage of early innovations; see __init__).
                prev_track = tpos.detach()

            outs["b_est"].append(b_vec)
            outs["cov"].append(c)
            outs["scores"].append(sc)
            outs["proj"].append(p)
            outs["cand_pos"].append(pos)
            outs["track_pos"].append(tpos)
            outs["assignment"].append(assign)

        stacked = {k: torch.stack(v, dim=1) for k, v in outs.items()}
        return LearnedTrackerOutput(
            b_est=stacked["b_est"],
            assignment=stacked["assignment"],
            covariance=stacked["cov"],
            scores=stacked["scores"],
            projections=stacked["proj"],
            cand_pos=stacked["cand_pos"],
            track_pos=stacked["track_pos"],
            tracked_freqs=stacked["track_pos"],  # posterior state readout (see dataclass doc)
        )


def build_tracker(
    cfg: LearnedTrackerConfig | None = None,
    core: str = "relu",
    association: str = "linear",
) -> LearnedTracker:
    """Construct a :class:`LearnedTracker` with the chosen core/association variants.

    Parameters
    ----------
    cfg
        Architecture config (defaults to :class:`LearnedTrackerConfig`).
    core
        ``"relu"`` (deployable-first) or ``"gated"`` (research, off-NPU).
    association
        ``"linear"`` (deployable-first) or ``"attention"`` (research, off-NPU).
    """
    if core not in ("relu", "gated"):
        raise ValueError(f"core must be 'relu' or 'gated', got {core!r}")
    if association not in ("linear", "attention"):
        raise ValueError(f"association must be 'linear' or 'attention', got {association!r}")
    cfg = cfg or LearnedTrackerConfig()
    core_mod: nn.Module = (
        ReLURecurrentCell(cfg) if core == "relu" else GatedKalmanNetCore(cfg)
    )
    assoc_mod: nn.Module = (
        LinearScoreAssociation(cfg) if association == "linear" else AttentionAssociation(cfg)
    )
    return LearnedTracker(cfg, core_mod, assoc_mod)


def load_tracker_state(tracker: LearnedTracker, state: dict) -> None:
    """Load weights, tolerating a pre-lever-B checkpoint that lacks the appearance branch.

    The appearance branch's output projection is zero-initialized, so a checkpoint without those
    keys loads inert and reproduces the exact baseline behavior. Any missing key OUTSIDE that
    branch, or any unexpected key, is still a hard error.
    """
    result = tracker.load_state_dict(state, strict=False)
    app_branch = (".app_track_proj.", ".app_cand_proj.", ".app_proj.")
    stray = [k for k in result.missing_keys if not any(s in k for s in app_branch)]
    if stray or result.unexpected_keys:
        raise RuntimeError(
            f"checkpoint mismatch: missing={stray} unexpected={list(result.unexpected_keys)}"
        )


def v250_targeted_modules(tracker: LearnedTracker) -> list[nn.Module]:
    """Return the sub-modules tagged :attr:`ExecutionTarget.V250` (the ops-guard contract).

    These — and only these — must pass :func:`...validation.ops_guard.check_model_ops`. Host/MSS
    blocks (recurrence, association, BLUE) are intentionally exempt.
    """
    return [
        m
        for m in tracker.modules()
        if getattr(m, "EXECUTION_TARGET", None) is ExecutionTarget.V250
    ]
