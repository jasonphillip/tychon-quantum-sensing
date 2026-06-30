"""Learned through-crossing tracker — SKELETON / INTERFACE ONLY (no training).

This module defines the *shapes and APIs* of the learned tracker; it does not train it and the
learnable internals are intentionally minimal (shape-correct, not fitted). Training, losses, and
real evaluation wait for the real upstream dataset (Increment 2).

Design (canonical, supersedes the pre-ops-guard reading of docs/design/02): **deployable-first
with an explicit V250/MSS graph partition.** The PolarFire SoC splits work between the V250 NPU
(strict INT8, ops-whitelisted) and the MSS RISC-V host (full float, no whitelist) — the same
split ``polarfire-hybrid-control`` already uses. So:

- **V250-targeted (ops-guarded):** only the per-frame feedforward :class:`FrameFeatureExtractor`
  (Conv2d (1,k) + ReLU + Linear). It must pass :func:`...validation.ops_guard.check_model_ops`.
- **host/MSS (unconstrained):** the recurrence, the association/assignment, and the BLUE decode.
  ``softmax``/``matmul``/``sigmoid``/``tanh`` are fine here because they never reach the NPU graph.

Every learnable block is offered as a **two-implementation / one-signature** pair so Increment 2
can train both and measure what the research variant buys:

- recurrent core: :class:`ReLURecurrentCell` (deployable-first) / :class:`GatedKalmanNetCore`
  (research; gated, off-NPU).
- association head: :class:`LinearScoreAssociation` (deployable-first; assignment off-graph) /
  :class:`AttentionAssociation` (research; softmax/matmul, off-NPU).

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
    """Architecture hyperparameters (shapes only; not tuned)."""

    n_lines: int = N_LINES_ELECTRONIC   # L resonances tracked
    n_axes: int = N_AXES                 # 4 NV axes (BLUE projections)
    n_freq: int = 400                    # F MW-frequency points per frame
    n_candidates: int = 16               # K per-frame peak candidates from the extractor
    feat_dim: int = 32                   # per-candidate feature width
    assoc_dim: int = 16                  # association scoring width
    state_dim: int = 64                  # recurrent state width
    conv_channels: int = 8               # V250 extractor channels
    conv_kernel: int = 5                 # Conv2d (1, k) kernel width
    dt_s: float = 1.0e-3                 # frame interval (for downstream dynamics)


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
    """

    b_est: torch.Tensor
    assignment: torch.Tensor
    covariance: torch.Tensor


# --- protocols (the one signature each variant pair shares) ------------------------------

class RecurrentCore(Protocol):
    """``(state, features) -> new_state``; both ``(B, state_dim)`` / ``(B, feat_dim)``."""

    def __call__(self, state: torch.Tensor, features: torch.Tensor) -> torch.Tensor: ...


class AssociationHead(Protocol):
    """``(track_feats (B,L,D), cand_feats (B,K,D)) -> scores (B,L,K)``."""

    def __call__(
        self, track_feats: torch.Tensor, cand_feats: torch.Tensor
    ) -> torch.Tensor: ...


# --- V250-targeted block (ops-guarded) --------------------------------------------------

class FrameFeatureExtractor(nn.Module):
    """Per-frame feedforward peak/feature extractor — the ONLY V250-targeted block.

    Input one spectrum frame ``(B, F)`` → reshape to ``(B, 1, 1, F)`` → Conv2d (1,k) + ReLU
    stack → Linear → ``(B, K, feat_dim)`` candidate features. Uses only V250-allowed ops
    (conv2d, relu, linear, layout ops), so it passes :func:`check_model_ops`.
    """

    EXECUTION_TARGET = ExecutionTarget.V250

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        self.cfg = cfg
        c, k = cfg.conv_channels, cfg.conv_kernel
        pad = k // 2
        self.conv1 = nn.Conv2d(1, c, (1, k), stride=(1, 2), padding=(0, pad))
        self.conv2 = nn.Conv2d(c, c, (1, k), stride=(1, 2), padding=(0, pad))
        self.act = nn.ReLU()
        # Two stride-2 convs downsample F by ~4.
        reduced = math.ceil(math.ceil(cfg.n_freq / 2) / 2)
        self.proj = nn.Linear(c * reduced, cfg.n_candidates * cfg.feat_dim)

    def forward(self, frame: torch.Tensor) -> torch.Tensor:
        b = frame.shape[0]
        x = frame.reshape(b, 1, 1, self.cfg.n_freq)
        x = self.act(self.conv1(x))
        x = self.act(self.conv2(x))
        x = x.reshape(b, -1)
        x = self.proj(x)
        return x.reshape(b, self.cfg.n_candidates, self.cfg.feat_dim)


# --- host/MSS recurrent cores (two-impl / one-signature) --------------------------------

class ReLURecurrentCell(nn.Module):
    """Deployable-first KalmanNet-style cell: ReLU MLP gain, residual state update.

    Ops-clean (linear + relu + add) — it would also pass the V250 guard, but it runs on the
    host per the partition. ``forward(state, features) -> new_state``.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        s, d = cfg.state_dim, cfg.feat_dim
        self.in_state = nn.Linear(s, s)
        self.in_feat = nn.Linear(d, s)
        self.act = nn.ReLU()
        self.update = nn.Linear(s, s)

    def forward(self, state: torch.Tensor, features: torch.Tensor) -> torch.Tensor:
        h = self.act(self.in_state(state) + self.in_feat(features))
        return state + self.update(h)  # residual (learned-gain) update


class GatedKalmanNetCore(nn.Module):
    """Research variant: GRU-style gated recurrent core (explicit sigmoid/tanh gates).

    FLAGGED off-NPU — the gates use ``sigmoid``/``tanh`` (V250-banned), so this runs only on the
    host. Same signature as :class:`ReLURecurrentCell`.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        s, d = cfg.state_dim, cfg.feat_dim
        self.w_z = nn.Linear(s + d, s)  # update gate
        self.w_r = nn.Linear(s + d, s)  # reset gate
        self.w_h = nn.Linear(s + d, s)  # candidate

    def forward(self, state: torch.Tensor, features: torch.Tensor) -> torch.Tensor:
        xh = torch.cat([state, features], dim=-1)
        z = torch.sigmoid(self.w_z(xh))
        r = torch.sigmoid(self.w_r(xh))
        h_tilde = torch.tanh(self.w_h(torch.cat([r * state, features], dim=-1)))
        return (1.0 - z) * state + z * h_tilde


# --- host/MSS association heads (two-impl / one-signature) -------------------------------

class LinearScoreAssociation(nn.Module):
    """Deployable-first association: additive-MLP cost (no matmul/softmax on the graph).

    ``forward(track_feats (B,L,D), cand_feats (B,K,D)) -> cost (B,L,K)`` via projected
    track/candidate features combined by a broadcast **add** + ReLU + Linear — all V250-allowed.
    The hard assignment is computed **off-graph** by :meth:`assign` (greedy argmax; scipy
    Hungarian is the Increment-2 upgrade), so no banned op ever reaches the NPU.
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
    a frozen ``Linear`` (no learnable parameters) — geometry stays exact. Runs on the host.
    """

    EXECUTION_TARGET = ExecutionTarget.HOST_MSS

    def __init__(self, cfg: LearnedTrackerConfig) -> None:
        super().__init__()
        N = NV_AXES_UNIT.astype("float32")               # (4, 3)
        pinv = torch.linalg.pinv(torch.from_numpy(N))    # (3, 4): B = pinv @ projections
        self.decode = nn.Linear(cfg.n_axes, 3, bias=False)
        with torch.no_grad():
            self.decode.weight.copy_(pinv)
        self.decode.weight.requires_grad_(False)
        # Fixed posterior covariance (AᵀA)⁻¹ for unit measurement noise; broadcast per frame.
        cov = torch.linalg.pinv(torch.from_numpy(N).T @ torch.from_numpy(N))  # (3, 3)
        self.register_buffer("_cov", cov)

    def forward(self, projections: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        b_vec = self.decode(projections)                 # (B, 3)
        cov = self.get_buffer("_cov").expand(projections.shape[0], 3, 3)
        return b_vec, cov


# --- top-level tracker ------------------------------------------------------------------

class LearnedTracker(nn.Module):
    """Wires extractor (V250) → recurrent core (host) → association (host) → BLUE (host).

    SKELETON: ``forward`` is shape-correct over a random init (no training). Swap the core /
    association variant via :func:`build_tracker`.
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
        self.feat_pool = nn.Linear(cfg.feat_dim, cfg.feat_dim)
        self.state_to_proj = nn.Linear(cfg.state_dim, cfg.n_axes)
        self.state_to_tracks = nn.Linear(cfg.state_dim, cfg.n_lines * cfg.feat_dim)

    def forward(self, spectra: torch.Tensor) -> LearnedTrackerOutput:
        """``spectra (B, T, F)`` → :class:`LearnedTrackerOutput` (all shape-correct)."""
        b, T, _ = spectra.shape
        cfg = self.cfg
        state = spectra.new_zeros(b, cfg.state_dim)

        b_est = spectra.new_zeros(b, T, 3)
        cov = spectra.new_zeros(b, T, 3, 3)
        assignment = spectra.new_zeros(b, T, cfg.n_lines, dtype=torch.long)

        for t in range(T):
            cand = self.extractor(spectra[:, t, :])            # (B, K, feat_dim)  [V250]
            feat = self.feat_pool(cand.mean(dim=1))            # (B, feat_dim)     [host]
            state = self.core(state, feat)                     # (B, state_dim)    [host]

            proj = self.state_to_proj(state)                   # (B, 4)
            b_vec, c = self.decoder(proj)                      # (B, 3), (B, 3, 3) [host BLUE]
            b_est[:, t] = b_vec
            cov[:, t] = c

            track_feats = self.state_to_tracks(state).reshape(b, cfg.n_lines, cfg.feat_dim)
            scores = self.association(track_feats, cand)       # (B, L, K)         [host]
            assignment[:, t] = torch.argmax(scores, dim=-1)    # hard assign (off-NPU)

        return LearnedTrackerOutput(b_est=b_est, assignment=assignment, covariance=cov)


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
    cfg = cfg or LearnedTrackerConfig()
    core_mod: nn.Module = (
        ReLURecurrentCell(cfg) if core == "relu" else GatedKalmanNetCore(cfg)
    )
    assoc_mod: nn.Module = (
        LinearScoreAssociation(cfg) if association == "linear" else AttentionAssociation(cfg)
    )
    if core not in ("relu", "gated"):
        raise ValueError(f"core must be 'relu' or 'gated', got {core!r}")
    if association not in ("linear", "attention"):
        raise ValueError(f"association must be 'linear' or 'attention', got {association!r}")
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
