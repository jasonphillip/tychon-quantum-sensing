# 01 — Build order and data interfaces between three repos

- Date: 2026-03-12 to 2026-03-27
- Context: Jason asks the project chat whether to keep improving repo 1 or start repo 2, then uses it to write the first prompt for the repo 2 session.
- Shows: result -> review (snapshot of repo 1 judged), then spec -> prompt to a repo session, then a hand-off prompt for the next chat thread.

### Result -> review: the chat judges a status snapshot of repo 1

> **Jason:**
>
> Thoughts on how the repo looks and if i made good progress?
>
> **Claude (project chat):**
>
> Let me analyze this snapshot carefully against the architecture decisions doc and playbook requirements.This is substantially further than I expected. Let me give you an honest assessment.
>
> **The good news is real:** 30/30 tests passing, all data contract fields implemented, the batch pipeline works end-to-end, you have real SimOS integration (282 lines, not a stub), coupled noise injection is implemented (250 lines), asymmetric lineshapes work, and you can generate, write, and read back datasets with valid manifests. You also already pulled down the Zenodo experimental ODMR data (25 files). The public API surface is clean and the signatures look right for downstream consumption.
>
> **You are solidly ready to scaffold Repo 2.** The entire point of Repo 1's existence from Repo 2's perspective is: "give me HDF5 datasets with frequency arrays, PL signal arrays, ground-truth labels, corruption parameters, and a JSON manifest I can validate." You can do all of that right now. The `DatasetLoader.load_split()` returns exactly the tuple Repo 2 needs: `(spectra, frequencies, labels, corruption_params, seeds)`.
> […]
>
> **On your original question — the answer is now clear:** Start Repo 2. Repo 1 can produce everything Repo 2 needs. The data contract is 100% implemented. The batch pipeline generates train/val/test splits with different seeds and corruption parameter distributions, which is exactly the anti-inverse-crime protocol the playbook requires.
> […]
>
> First, commit everything in Repo 1. Second, generate a small reference dataset (maybe 100 train / 20 val / 20 test) and save the manifest — this becomes your "golden dataset" for Repo 2 contract testing. Third, scaffold Repo 2 using the spec in your architecture decisions doc Section 6. The first files to create are `contracts.py` (validates Repo 1 manifests), `loaders.py` (wraps `DatasetLoader`), `test_repo1_manifest_compat.py` (contract test against your golden dataset), and the MLP/CNN model stubs with shape tests. Fourth, run the contract test. If it passes, your interface is solid and you can start model work with confidence.

### Spec -> prompt: the chat writes the golden-dataset step and the repo 2 planning prompt

> **Jason:**
>
> Summary:
>   - 1 commit (ddcc0c8), all March 12 work included, sanitized
>   - Working tree clean
>   - No golden dataset at ~/projects/tychon-shared-data/golden/
>
> ✻ Brewed for 1m 10s
>     So how easy would it be to setup the next phase? What would be the prompt i can give to claude code cli in that project? Im assuming plan mode?
>
> **Claude (project chat):**
>
> Good — clean state. One commit, clean tree, 30/30 tests, all contract fields implemented, sensitive data scrubbed. Exactly where you should be.
> […]
>
> ```
> I am in Plan Mode. Do not edit files or run commands. Analysis only.
>
> This is tychon-odmr-ml (Repo 2) for Tychon AI. I am a solo founder on a 90-day sprint. Repo 1 (tychon-nv-sim) is complete and generates NV-diamond ODMR synthetic datasets with manifests. This repo consumes those datasets to train, quantize, and evaluate neural networks.
>
> Read docs/phase1-context/repo2-odmr-ml-spec.md — that is the authoritative spec for this repo (Section 6 of the architecture decisions doc).
> […]
>
> PRIORITY ORDER — build these first, everything else second:
> 1. contracts.py — validates incoming Repo 1 manifests against the Section 3.4 schema
> 2. loaders.py — wraps Repo 1's DatasetLoader, applies input normalization
> […]
>
> Do NOT plan:
> - CI workflows, pre-commit hooks, editorconfig
> - Claude skills or agents
> - TorchAO quantization pipeline (defer)
> - ONNX/TFLite/VNNX export pipeline (defer)
> - MagNav.jl bridge (defer — needs Julia)
> - ADEV or PSD evaluation modules (defer — need trained model first)
> - Any FPGA or Repo 3 code
>
> Give me the plan. I will review it and then tell you to implement.
> […]
> ```

### Hand-off: a short prompt that carries state into the next thread

> **Jason:**
>
> dont make it so verbosie. It should be 2 paragraphs or 3 at most. Remember it is inthsi project so sitll has all the project info
>
> **Claude (project chat):**
>
> I'm Jason Phillip, sole founder of Tychon AI, executing a 90-day plan. Continuing from yesterday's thread. Repo 1 is done and pushed (30/30 tests). Repo 2 scaffold is complete (40/40 tests) but needs to be committed — do that first. A golden dataset exists at ~/projects/tychon-shared-data/golden/. The FPGA workstation has Libero 2025.2 and SmartHLS 2025.2 installed but no VectorBlox SDK or Python yet (that's Day 45+ work).
>
> Today's priorities in order: (1) Commit Repo 2 if not done. (2) Check sign ambiguity in Repo 1 — grep for bz_range in batch_generate.py. If the B-field range spans negative values, training will predict zeros (Gemini Deep Think flagged this). (3) Build the training loop in Repo 2 — losses.py with composite angular + Huber loss, loop.py, and run a first training pass on the golden dataset. Reference gemini-dt-training-loop.md in project files for the loss function design and physics failure modes — my review notes are inline. Key points: train in µT not Tesla, use cosine similarity loss weighted 0.7 for angular error, use AdamW with Kaiming He init to avoid dead ReLUs.

Result in the repos: repo 1 was committed and tested (30/30), a golden dataset (100/20/20 spectra, seed 12345) was generated for repo 2 interface tests, and repo 2 reached a 40/40-test scaffold before the next thread began.
