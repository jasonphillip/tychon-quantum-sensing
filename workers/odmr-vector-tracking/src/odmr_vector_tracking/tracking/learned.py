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
``1 - PL`` to the extractor (host-side preprocessing — dips become positive peaks). Frequencies
are normalized window units; axis projections are regressed in units of ``proj_scale_T`` Tesla
(the scale is folded into the frozen BLUE decode so ``b_est`` is Tesla).

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
    tracked_freqs
        ``(B, T, L)`` position of each lock's assigned candidate (normalized window units) —
        the claimed-identity line centers the Increment-1 metrics consume.
    """

    b_est: torch.Tensor
    assignment: torch.Tensor
    covariance: torch.Tensor
    scores: torch.Tensor
    projections: torch.Tensor
    cand_pos: torch.Tensor
    tracked_freqs: torch.Tensor


# --- protocols (the one signature each variant pair shares) ------------------------------

class RecurrentCore(Protocol):
    """``(state, obs) -> new_state``; ``(B, state_dim)`` / ``(B, state_dim)``."""

    def __call__(self, state: torch.Tensor, obs: torch.Tensor) -> torch.Tensor: ...


class AssociationHead(Protocol):
    """``(track_feats (B,L,D), cand_feats (B,K,D)) -> scores (B,L,K)``."""

    def __call__(
        self, track_feats: torch.Tensor, cand_feats: torch.Tensor
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

    def forward(self, state: torch.Tensor, obs: torch.Tensor) -> torch.Tensor:
        h = self.act(self.in_state(state) + self.in_obs(obs))
        return state + self.update(h)  # residual (learned-gain) update


class GatedKalmanNetCore(nn.Module):
    """Research variant: GRU-style gated recurrent core (explicit sigmoid/tanh gates).

    FLAGGED off-NPU — the gates use ``sigmoid``/``tanh`` (V250-banned), so this runs only on the
    host. Same signature as :class:`ReLURecurrentCell`.
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


# --- host/MSS association heads (two-impl / one-signature) -------------------------------

class LinearScoreAssociation(nn.Module):
    """Deployable-first association: additive-MLP cost (no matmul/softmax on the graph).

    ``forward(track_feats (B,L,D), cand_feats (B,K,D)) -> logits (B,L,K)`` via projected
    track/candidate features combined by a broadcast **add** + ReLU + Linear — all V250-allowed.
    The hard assignment is computed **off-graph** by :meth:`assign` (greedy argmax), so no
    banned op ever reaches the NPU. Training applies ``log_softmax`` to these logits inside the
    loss only — loss machinery never ships.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        d, a = cfg.feat_dim, cfg.assoc_dim
        self.track_proj = nn.Linear(d, a)
        self.cand_proj = nn.Linear(d, a)
        self.act = nn.ReLU()
        self.score = nn.Linear(a, 1)

    def forward(self, track_feats: torch.Tensor, cand_feats: torch.Tensor) -> torch.Tensor:
        t = self.track_proj(track_feats)[:, :, None, :]   # (B, L, 1, A)
        c = self.cand_proj(cand_feats)[:, None, :, :]     # (B, 1, K, A)
        h = self.act(t + c)                               # (B, L, K, A) broadcast add
        return self.score(h).squeeze(-1)                  # (B, L, K)

    @staticmethod
    def assign(cost: torch.Tensor) -> torch.Tensor:
        """Greedy off-graph assignment: best candidate per line-lock. ``(B,L,K) -> (B,L)``."""
        return torch.argmax(cost, dim=-1)


class AttentionAssociation(nn.Module):
    """Research variant: scaled dot-product attention assignment (softmax + matmul).

    FLAGGED off-NPU — ``matmul``/``softmax`` are V250-banned. Same signature; returns a soft
    assignment ``(B, L, K)`` that already sums to 1 over candidates.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        d, a = cfg.feat_dim, cfg.assoc_dim
        self.q = nn.Linear(d, a)
        self.k = nn.Linear(d, a)
        self._scale = 1.0 / math.sqrt(a)

    def forward(self, track_feats: torch.Tensor, cand_feats: torch.Tensor) -> torch.Tensor:
        q = self.q(track_feats)                       # (B, L, A)
        k = self.k(cand_feats)                        # (B, K, A)
        logits = torch.matmul(q, k.transpose(1, 2)) * self._scale  # (B, L, K)
        return torch.softmax(logits, dim=-1)

    @staticmethod
    def assign(attn: torch.Tensor) -> torch.Tensor:
        """Hard assignment from the soft attention. ``(B,L,K) -> (B,L)``."""
        return torch.argmax(attn, dim=-1)


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

    def forward(self, spectra: torch.Tensor) -> LearnedTrackerOutput:
        """``spectra (B, T, F)`` (contract-normalized PL) → :class:`LearnedTrackerOutput`."""
        b, T, _ = spectra.shape
        cfg = self.cfg
        x = 1.0 - spectra  # host-side preprocessing: dips → positive peaks
        state = spectra.new_zeros(b, cfg.state_dim)

        outs: dict[str, list[torch.Tensor]] = {
            k: [] for k in
            ("b_est", "cov", "scores", "proj", "cand_pos", "assignment", "tracked")
        }

        for t in range(T):
            feat, pos = self.extractor(x[:, t, :])             # (B,K,D), (B,K)   [V250]
            obs = self.obs_embed(feat.reshape(b, -1))          # (B, state_dim)   [host]
            state = self.core(state, obs)                      # (B, state_dim)   [host]

            p = self.state_to_proj(state)                      # (B, 4) proj_scale_T units
            b_vec, c = self.decoder(p)                         # (B, 3) T, (B,3,3) [host BLUE]

            track_feats = self.state_to_tracks(state).reshape(b, cfg.n_lines, cfg.feat_dim)
            sc = self.association(track_feats, feat)           # (B, L, K)        [host]
            assign = torch.argmax(sc, dim=-1)                  # hard assign (off-NPU)

            outs["b_est"].append(b_vec)
            outs["cov"].append(c)
            outs["scores"].append(sc)
            outs["proj"].append(p)
            outs["cand_pos"].append(pos)
            outs["assignment"].append(assign)
            outs["tracked"].append(torch.gather(pos, 1, assign))  # (B, L) claimed positions

        stacked = {k: torch.stack(v, dim=1) for k, v in outs.items()}
        return LearnedTrackerOutput(
            b_est=stacked["b_est"],
            assignment=stacked["assignment"],
            covariance=stacked["cov"],
            scores=stacked["scores"],
            projections=stacked["proj"],
            cand_pos=stacked["cand_pos"],
            tracked_freqs=stacked["tracked"],
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
