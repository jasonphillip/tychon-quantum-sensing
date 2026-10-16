# Reproduce the published evidence

`make verify-evidence` checks seven named parts of the public record.
It verifies hashes and recomputes saved arithmetic.
It does not train a model, run inference, fetch data, or use an FPGA.
A reproduced scientific failure is a successful verification.
The command does not establish sensing performance beyond the original evidence.

## Install the arithmetic dependencies

Use Python 3.11 for the documented CI route.
Python 3.12 and 3.13 are also accepted by the installer.
Later Python versions are rejected until checked.
The arithmetic environment needs only NumPy 2.4.2 and SciPy 1.17.1.
It does not need PyTorch, a GPU, the simulator, or vendor software.

From the repository root:

```sh
make install-evidence BENCH_PY=python3.11
```

This setup step downloads packages into `.venv`.
To keep the environment elsewhere, add `VENV=/absolute/path/to/environment` to setup and verification.
An existing environment can be selected with `EVIDENCE_PY=/absolute/path/to/python`.

## Fetch the pinned public kit records separately

The original kit output lives in a second public repository.
The main repository contains its labels, CPU predictions and exact reference hashes.
Verification requires the five original kit files.
It never substitutes simulated or newly generated output.

Choose a new directory outside this checkout.
The following command creates a sparse public checkout in a temporary directory:

```sh
KIT_CHECKOUT="$(mktemp -d /tmp/tychon-kit-evidence.XXXXXX)"
git -C "$KIT_CHECKOUT" init --quiet
git -C "$KIT_CHECKOUT" remote add origin https://github.com/jasonphillip/polarfire-agent-skills.git
git -C "$KIT_CHECKOUT" sparse-checkout init --cone
git -C "$KIT_CHECKOUT" sparse-checkout set evidence/2026-10-14-deployed-fcnn
git -C "$KIT_CHECKOUT" fetch --depth=1 origin 53acad6aff3424e36662972348ef535392f4859b
git -C "$KIT_CHECKOUT" checkout --detach FETCH_HEAD
test "$(git -C "$KIT_CHECKOUT" rev-parse HEAD)" = 53acad6aff3424e36662972348ef535392f4859b
```

The required files are `hw.bin`, `hw.json`, `sim.npz`, `sim.json`, and `input.int8.npy`.
The pinned [array manifest](../workers/odmr-edge-ml/docs/kit-run-2026-10-14/ARRAYS.manifest.json) records their sizes and hashes.
These hashes are mandatory even when files come from an existing local copy.

## Run the offline verification

Keep the shell variable from the preceding step:

```sh
make verify-evidence KIT_EVIDENCE_DIR="$KIT_CHECKOUT/evidence/2026-10-14-deployed-fcnn"
```

The command prints a new temporary report directory and finishes with `RESULT: PASS` only if every check passes.
Missing files, changed hashes, or checker failures produce a nonzero exit.
Nothing is silently skipped.
To choose a report directory, add `EVIDENCE_OUT=/absolute/new/report-directory`.
It must not exist and must be outside both checkouts.
Verification works without network access after setup.
Reports include package versions, manifest pins, per-check logs, wall time and child-process resource use.

| Check | What it reproduces | Boundary |
| --- | --- | --- |
| Kit | 512 saved labels and predictions; CPU/simulator/kit parity; field errors; constant baselines; recorded latency statistics | Synthetic replay; does not rerun the board |
| Scalar validation | Saved predictions, labels, flags, bootstrap intervals and the registered STOP decision | Validation only; no final dataset or inference |
| Advantage package | Hashes of every file in its pinned artifact manifest | Integrity check, not every lane's arithmetic |
| Raw compatibility | 192 saved feature comparisons and qualification arithmetic | Training-only compatibility; not acquisition transfer |
| Vector package | Hashes of every file in its pinned artifact manifest | Integrity check |
| Vector P1 | Saved errors, flags, timing arithmetic and gate decisions | Recorded timing; no model deserialization |
| Vector challenge | Saved errors, flags, classical comparisons and the failed 2× gate | The scientific FAIL must remain FAIL |

The wrapper calls existing checkers.
It does not replace their formulas.
Its six fixed manifest hashes are visible in [the wrapper](../scripts/verify_evidence.py).
The underlying reports remain the source for interpretation:
[kit](../workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md),
[scalar](../workers/odmr-edge-ml/docs/scalar_repair_cycle_2026-10.md),
[advantage search](nv_advantage_search_2026-10/),
and [vector development](nv_vector_development_2026-10/).

Verification runs one checker at a time with one BLAS thread.
It has a 15-minute total execution deadline.
On Linux, each child has a 4-GiB address-space limit.
The report records peak child memory on both Linux and macOS.
macOS does not receive the Linux address-space limit; its reported memory is observational.
The command does not reproduce every historical experiment, validate hardware physics, or remeasure timing.

## Observed local acceptance

These local checks ran on 2026-10-16, before publication.
CI for these edits was pending at that point; inspect the workflow for the published commit.

| Platform | Python | Observed outcome |
| --- | --- | --- |
| macOS 27.0.1, arm64 | 3.11.17 | Fresh CPU install, four-spectrum smoke, seven failure tests and all seven saved checks passed |
| Linux, arm64 | 3.13.11 | Fresh CPU install and four-spectrum smoke passed |
| Linux, arm64 | 3.12.3 | Minimal arithmetic install, seven failure tests and all seven saved checks passed |

Saved verification took 3.30 seconds on the Mac and 5.64 seconds on Linux.
Peak child memory was 635.1 MiB and 475.2 MiB, respectively.
These are observations from these runs, not a runtime guarantee.
The Linux full installation used a Python distribution that included development headers.
A separate system-Python attempt lacked `Python.h` and stopped during the QuTiP build.
The arithmetic-only route does not build QuTiP.

## Check the full CPU installation

This separate route installs the simulator and ML worker.
The Linux PyTorch pin is `2.11.0+cpu`; macOS uses the official `2.11.0` wheel.
Both come from the official [CPU wheel index](https://download.pytorch.org/whl/cpu/torch/).
The macOS package has no `+cpu` suffix.

```sh
make install BENCH_PY=python3.11
make smoke BENCH_PY=python3.11
```

The smoke check imports the dependencies and generates four temporary synthetic spectra.
It does not train, score, or load a model.
Its temporary spectra are deleted afterward.
The [Reproduction workflow](../.github/workflows/reproduction.yml) checks Python 3.11 on Linux x86-64, Linux arm64 and macOS arm64.
Read the workflow result for the commit you inspect; a configured job alone is not execution evidence.

Linux arm64 may build the pinned QuTiP package from source.
That needs Python development headers and a C/C++ compiler.
The benchmark's existing pins remain unchanged except for the macOS PyTorch suffix.
`make bench` still trains and scores the separate synthetic benchmark; see [its guide](../bench/README.md).

Failure contracts can be checked without numerical packages:

```sh
make test-reproduction BENCH_PY=python3.11
```

These tests reject missing kit evidence, changed bytes, unsafe report destinations and disabled Python assertions.
