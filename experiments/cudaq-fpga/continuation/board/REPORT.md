# Full CUDA-Q-to-FPGA replay

Executed October 17, 2026. **All 1,024 new NV records matched the frozen integer references on the FPGA.**
Each comparison checked both the template index and the full unsigned 64-bit distance score.
The host and control receipts passed. No image, coefficients, or boot files changed.

CUDA-Q generated all quantum evolutions underlying these records.
CPU code then sampled the synthetic detector and produced fixed-point inputs.
The unchanged C reference verified every expected result before hardware access.
This establishes an end-to-end synthetic simulation/replay path. It does not establish measured NV accuracy.

## Execution

The board used the image previously validated in public commit `92cead757a9ef8cad2101ab694a184f889d7546f`.
Its boot ID still matched the earlier cold-boot suite.
The wrapper checked runner hashes, the approved pack hash, parser results, and the existing peripheral identity.
It restricted replay to the existing `0x60040000` interface.
All 15 established control checks passed before the replay.

| Measurement | Result |
| --- | ---: |
| New synthetic detector records | 1,024 |
| FPGA calls | 1,024 |
| Index or full-score mismatches | 0 |
| Fabric cycles per call | 23,479 |
| Nominal core time at configured 125 MHz | 187.832 microseconds |
| Median host time | 209 microseconds |
| Host p99 | 215 microseconds |
| Maximum host time | 290 microseconds |

Host timing includes register setup, input writes, polling, and result reads. It excludes CSV output and physical acquisition.
The nominal core conversion uses the configured clock. It is not an independent clock-frequency measurement.
The V250 regression completed afterward with `error_val=0`.

## Receipts

- `execution/acceptance.json`: command identities, times, hashes, and overall acceptance.
- `execution/nv-replay.json` and `nv-replay.csv`: timing summary and every full-width comparison.
- `execution/control-fabric.stdout.txt`: all 15 control checks.
- `execution/v250-regression.log`: the existing inference-path check.
- `local_verification.json`: independent revalidation of all saved rows on the Mac.
- `stress/nv/manifest.json`: exact input/reference bytes used on hardware.

Pack SHA256: `0055ab3fa477e42add618d068b408cf0000fa5bea4409c8da113d35d5aeda391`.
The original GPU and CPU receipts retain `board_executed=false` because they preceded this separate hardware run.
The board remained powered on with the same validated image after completion.
That statement records the end state. It is not a live status service.

No live sensor, quantum processor, board power, or radiation test occurred.
The original estimator's low-shot limitations and failed floating/fixed agreement gate remain unresolved.
