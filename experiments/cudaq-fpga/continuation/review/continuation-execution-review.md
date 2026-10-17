# Continuation execution review — stage 2

Reviewed 2026-10-17T18:38:26.689548+00:00. This is ordinary AI code/methods review, not human review or external endorsement.
Only this review file was written. No hardware, GPU, scientific generation, network call, or child agent was used.

## Status

The initial board-wrapper blockers were corrected and the changed source was re-read.
The reviewed wrapper has no remaining blocking issue for the coordinator's pinned, already-validated image and approved pack.
Acceptance still depends on final GPU numerical gates, compiled-C parity, and the expected manifest hash from that exact handoff.
The final GPU/CPU/comparison/C-parity receipts were absent locally at 18:37:32 UTC. Their result review is explicitly deferred.

## Corrected before board execution

1. `run_new_nv.py` originally accepted child exit code zero without checking the helper's timeout/interruption marker. It now requires both zero exit and no `failure` key before validation. The original helper deliberately preserves failure markers even when a terminated child returns zero.
2. The original summary left `board_executed:false` after failed partial hardware activity. Separate `fabric_attempted` and `replay_attempted` flags now persist before the corresponding launches. `board_executed` remains a successful-replay indicator; inspect the attempt flags on failures.
3. Importing the helper did not install its top-level SIGTERM handler. The wrapper now maps SIGTERM to `InterruptedError`, allowing the helper to terminate its separate child process group and save failure evidence.
4. The manifest digest was originally learned only from the supplied directory. The wrapper now requires `--expected-manifest-sha256` and rejects disagreement before any command. The coordinator must obtain that digest from the accepted GPU/C-parity pack, not recompute it blindly from an arbitrary board directory.

## Verified execution boundaries

- `reference_acceptance.py` is byte-identical to the previously tested acceptance helper, SHA256 `ed777b7f5075ebed53500607572a8a0befb9400e34c6c9218640b4f7ec2ae0f7`.
- Every board command checks the prior accepted boot UUID, both fixed binary hashes, every pack hash/length, and the pinned manifest. A changed boot requires requalification.
- Exact file names, NV schema, fixed ROM hash, and integer count `1..2048` are required. Parser-only and static control checks precede fabric access. Fabric access requires `--run`.
- The pinned C binaries own the fixed `0x60040000` 4 KiB mapping and verify ID/ABI before writes. The Python wrapper has no programming, power, alternate-base, or legacy PID operation.
- The command helper records argv, stdout, stderr, exit status, elapsed time, and failure markers. It imposes a 30-second command timeout, followed by bounded TERM/KILL grace periods. Any command or receipt failure stops later commands.
- Replay validation checks every full-width index and uint64 score against the pinned files. It enforces complete row count/order, one completion increment per row, contiguous replay counters, successful status, positive fabric cycles, and host-call time below 100 ms.
- Output directories cannot be reused. A coordinator file lock prevents cooperating replay wrappers from overlapping. This is not a claim that a lock can prevent unrelated non-cooperating hardware access.

These are source-review findings. No new mock or hardware test was executed by this reviewer. Early failures before output initialization rely on the invoking coordinator's captured command log.

## Frozen launcher and comparison caveats

`run_registered_nv.py` pins registration SHA256 `096a1f08ca40840502119a4e276a6e45fcafc9f509c1c724744915f12db447c8`.
All eleven registered source/config/core hashes matched locally. It uses one fixed Python environment and one-thread settings for both backends, sequentially.
The launch receipt is created exclusively before final execution and marks the final set consumed. A failed GPU command prevents CPU execution.
Do not modify registered experiment files while the final job runs.

The already-running launcher uses GNU `timeout 1800` without `--kill-after`.
This sends TERM at the deadline; an unresponsive process can outlast it. Do not describe it as a guaranteed hard kill.
Normal completion within the cap requires no rerun. Any overrun needs coordinator termination and a preserved failed receipt.
The launcher also lacks a termination handler: interrupted runs can retain `RUNNING` or incomplete command metadata. Such receipts must never be accepted as PASS.

`compare_runs.py` checks successful receipts, protocol/platform equality, and equal parameter coordinates.
It computes full probability/density differences but does **not** enforce those differences against tolerance or verify loaded NPZ hashes.
Before accepting the final comparison, independently verify each dataset hash against its receipt, exact shapes/counts, and frozen probability/density limits.
Do this without changing the running frozen implementation.
Platform-string equality alone is not host identity; the fixed-host launch record provides that evidence for this coordinated run.

Keep first-call, warm timing, initialization, validation, CPU detector, and output costs distinct.
The comparison's pipeline sum is explicitly a component sum, not a separately measured total.
Sampled device memory remains device-wide and can miss peaks. A four-level analytic CPU comparison does not establish general GPU speedup.

## Processor-readout protocol review

The new proposal is under `measured_readout/processor_readout/`.
No blocker was found for the **training-only phase**. All fitting and eight method/window choices use source-train reference/calibration/validation rows.
The 8,192 fixed source-test rows remain sealed until protocol approval and saved model/selection freeze.
The full trace and paper-prior window are predeclared. Baselines have equal access to the same labelled fitting records.
The proposal correctly avoids independent-acquisition, drift-transfer, physical-state-fidelity, and paper-performance claims.
New integer coefficients are boxcar-only; selected LDA must not be presented as FPGA-compatible.

Before final registration, specify uncertainty semantics if final class balance differs:
use per-preparation Wilson intervals, or label a pooled Wilson interval as ordinary accuracy only.
A pooled Wilson interval is not an interval for balanced accuracy with unequal class counts.
This clarification does not require reading final labels or changing model selection.

The proposed ranges total 24,576 signal rows × 1,540 float64 values = 302,776,320 bytes.
The stated cumulative data budget is below 400 MB. Enforce response lengths/Content-Range, immutable headers, per-range hashes, and source-row mapping.
Retrieve source-train signals first. Freeze model, selection, code, and protocol before retrieving any selected source-test labels or signals.
If final class counts fail the predeclared minimum, stop without resampling.
Source-format facts here derive from the supplied qualification record; this reviewer did not independently redownload source data.

## Reviewed snapshot

| File | SHA256 |
| --- | --- |
| `board/run_new_nv.py` | `797f86ad799b9b595ed9c1eff9e755f96b35a1033bfd210ce7fb9159c68ef29a` |
| `board/reference_acceptance.py` | `ed777b7f5075ebed53500607572a8a0befb9400e34c6c9218640b4f7ec2ae0f7` |
| `run_registered_nv.py` | `292aaaf35731d806f425e6d15d53899d4e64c9b28166b8393ab9cbb1b8c6009b` |
| `nv_scaling/compare_runs.py` | `fb174b265b937e99af86d86cb997476b69e4f18ae8210f8f71d715ec6c2ac4ca` |
| `nv_scaling/REGISTRATION.json` | `096a1f08ca40840502119a4e276a6e45fcafc9f509c1c724744915f12db447c8` |
| `measured_readout/processor_readout/PROPOSED_PROTOCOL.json` | `bffb0be2cf21e6d34c95afdbed6adb2e70e4a20f9db1a442f52f30a398d7ea44` |
| `measured_readout/processor_readout/QUALIFICATION.md` | `34e8caab7d6b0820b74cc27d4c42c511f548c130f14e2e9cddeccb21a742e8dd` |
