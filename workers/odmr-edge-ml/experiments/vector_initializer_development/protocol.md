# P1 speed at matched accuracy — prospective protocol

Date: 2026-10-15. Status: DRAFT_ROOT_REVIEW_NOT_AUTHORIZED.
Owner: Codex vector lane. Root owns seeds, approval, accounting, and release.
This additive study preserves every original solver, P0 source, and consumed dataset.
This is synthetic development. It cannot establish sensing reliability, clinical value, or hardware performance.

## Question and fixed scope

Can one compact learned initializer reduce total eight-line inversion time without losing field accuracy?
Can a simpler classical refinement provide the same engineering benefit?
Generic neural inversion speedup is prior art. This study claims no new algorithm.
The inspectable contribution is a matched-device comparison with strong shortcuts, physical refinement, and counted fallback.
The motivating workload is offline processing of large current maps. No instrument deadline is asserted.
External accuracy, failure, and useful workload requirements remain unresolved before confirmation.
The separate tied12 comparator remains mandatory before any classical opportunity or final comparison is accepted.

## Fresh data and custody

Root issues five distinct unsigned128-bit PCG64/training streams after source freeze.
Names: train_parameter_seed, train_noise_seed, validation_parameter_seed, validation_noise_seed, training_seed.
Certificate purpose: vector_p1. Status: ISSUED. Attestation: ROOT_CONFIRMED_NOT_PREVIOUSLY_USED.
Generate exactly32768 training latents and2048 validation latents. Use one independent Poisson observation per latent.
Both groups use independent uniform draws from every frozen full-B parameter bound.
Never load P0 data, old tests, held confirmation, or measured spectra.
Keep every validation case, including rejected estimates. No clipping of reported field errors.
The existing eight-line Hamiltonian,512bins,known orientation,bias and2million photons/bin remain unchanged.
Check32 prospectively evenly spaced means per split against the independent laboratory Hamiltonian.
Reject duplicates across or within splits. Save all counts, labels, physical-mean checks, source hashes, and seed certificate hash.

## One model and one training recipe

Architecture:512→256→128→64→8. Hidden activations:ReLU. Output:linear. Parameters:173000.
Normalize each input frequency using the training-only mean and population standard deviation of fluorescence counts/2million.
Floor each input standard deviation at1e-6. Never fit scaling to validation or reference outputs.
Normalize all8 true targets using frozen bound midpoint and half-range. Loss:mean squared normalized parameter error.
Use PyTorch float32 CUDA training. Adam lr0.001,betas(0.9,0.999),epsilon1e-8,weight decay0.
Use batch512 and exactly20epochs. Shuffle each epoch with the sole root-issued training stream.
Use deterministic algorithms, disable TF32, no scheduler, augmentation, early stopping, checkpoint selection, architecture search, or seed sweep.
The final epoch is the only candidate. A timeout preserves evidence and stops; no automatic resumed training.
Save incremental loss history, latest optimizer/RNG checkpoint, final weights, feature and target scaling.

## Strong matched classical controls

Methods: full original40iteration×3width LM; affine+exactly1,3,5LM attempts; learned+exactly1LM attempt.
The refinement copies the qualified LM update algebra with fixed0.01 initial damping and unchanged acceptance/damping/bounds.
Retain all8 initializer outputs, including width. Do not silently replace either initializer's width.
Each short route always performs its declared steps, even after a small update. It then applies the unchanged observed-data guard.
Every rejected estimate receives the original full fallback, with all costs counted. Never pass labels to a solver or guard.
Full LM stays an accuracy reference. The deviance guard alone is not an accuracy certificate.
All compared inference and physical calculations use float64 and chunk1024.
Cast learned float32 weights once to float64 before inference. No precision or chunk tuning is allowed here.
Every method may retain its Engine and affine-calibration cache equally. Count each one-time initialization separately.
The neural route retains its one-time loaded/cast weights. No checkpoint loading is charged to every inference.

## Metrics, timing, and gates

Score2048 unique validation spectra: mean,p95,RMS,max vector error; rejection and fallback counts.
No outcome-based exclusions, field alignment, label matching, or conditional error reporting.
A classical route is adequate if mean andp95≤1.05×fullLM and rejections≤fullLM.
Neural mean andp95 must each be≤1.05×the best corresponding adequate-classical metric.
Neural rejections must not exceed the lowest adequate-classical rejection count.
Primary speed gate:≥2×the fastest adequate classical host-to-host median at batch4096, with finite setup amortization.
Report batch1 and64 as diagnostics. They do not override the frozen4096 gate.
For4096 timing, repeat the same2048 validation inputs twice in original order. This is timing only, not4096 independent accuracy cases.
For1/64 timing, use the first1/64 validation observations. Do not select easy examples.
Use three timed repeats per method/batch after one equal warmup. Save every timing and host prediction/flag array.
Steady-state host-to-host timing starts with host counts. Include transfer, inference, refinement, guard, fallback, synchronization, and output transfer.
Resident timing starts with device counts and includes the full policy. Report it separately; it cannot satisfy the primary gate.
Report total time per million spectra and absolute time saved. Measure generation,training,checkpointing,calibration,model setup separately.
Neural break-even includes all fresh generation/training/setup cost divided by saved seconds per spectrum.
Select the classical candidate using4096 host timing. Among routes within5%of the fastest, favor fewer steps.
Report a separate classical engineering opportunity only if it matches fullLM within5%and is≥2×faster than fullLM and every adequate tied-line comparator.
Until tied12 is evaluated, the latter result is pending; a fullLM-only result is explicitly provisional.
A classical result cannot be relabeled a neural win or novel algorithm. Fresh confirmation and usefulness requirements remain mandatory.

## Budget and stopping

Prospective development reservation:≤1800CPU seconds and≤600GPU/wall seconds, one numerical CPU thread.
Root must reserve≥15%of total stage resources for independent verification: proposed360CPU/120wall seconds for saved verification.
CPU fixtures:proposed20CPU/wall seconds. They require separate root approval.
GPU policy:one PyTorch process,zero descendants/DataLoader workers,16GiB host RSS+16GiB allocator,24GiB host free-memory floor.
No services, installs, paid compute, hardware, FPGA, or Beelink actions.
Stop on source/custody drift, missing context, nonfinite output/loss, resource termination, or verification mismatch.
A failed opportunity gate ends this candidate. No retuning or hidden extra epochs.
No final data or confirmation is authorized by this document.

## Independent verification

Recompute all error metrics, physical Poisson deviance, acceptance flags, train-only scaling, timing medians, selected classical route, and both gates from saved arrays.
Check artifact hashes, exact split sizes, unique latent identities, original label arrays, all timing rows, and source pins.
The checker must not call a forward generator, estimator, model, optimizer, or random sampler.
Root separately reviews the unchanged physical implementation and this copied finite-step update.
