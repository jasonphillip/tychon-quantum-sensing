# Claim evaluation

## Decision policy

Decision per row: accept iff every critic verdict is SUPPORTED; reject iff any CONTRADICTED or all UNSUPPORTED; else abstain; ERROR counts as parser failure and abstain.

## Labelers

| Labeler | Constructed binary accuracy | Constructed five-class accuracy | Original supported |
|---|---:|---:|---:|
| a | 1.000 | 0.833 | 7 |
| b | 1.000 | 0.867 | 17 |
| c | 1.000 | 0.867 | 12 |

Cohen's kappa AB on original rows: 0.283
Cohen's kappa AC on original rows: 0.514
Cohen's kappa BC on original rows: 0.626
Three-way raw agreement on original rows: 0.467

## Contested original rows

| ID | A | B | C | Final |
|---|---|---|---|---|
| ea0116be5ab0c1681 | unsupported | supported | supported | supported |
| e85776e9add84f39e | unsupported | contradicted | contradicted | contradicted |
| e5a92118719c78df4 | contradicted | supported | contradicted | contradicted |
| e17e0aa3c03983ca8 | unsupported | supported | unsupported | unsupported |
| ec8f8e3d0d3290a4c | contradicted | unsupported | contradicted | contradicted |
| e1759edc372ae2244 | unsupported | contradicted | contradicted | contradicted |
| ecda8056c3d15eef7 | contradicted | supported | supported | supported |
| e38c1962e9148624f | unsupported | supported | unsupported | unsupported |
| eeac1c14f30e9c5cc | unsupported | contradicted | contradicted | contradicted |
| e71545a137a1d5006 | contradicted | supported | supported | supported |
| ed71037d1b83e90ec | unsupported | contradicted | contradicted | contradicted |
| ee005b86051ef1922 | contradicted | contradicted | stale | contradicted |
| ebaf3897a3e70f16a | contradicted | supported | contradicted | contradicted |
| eb421eaeb534097ca | contradicted | supported | supported | supported |
| e3458a748e9bb17bc | unsupported | supported | supported | supported |
| efe43c49e149818d1 | unsupported | supported | unsupported | unsupported |

Undefined rates use — when their denominator is zero. Parser failure means any ERROR in the evaluated critic set.
Error dependence treats accepting a non-supported row or failing to accept a supported row as wrong.
Gain is ensemble minus the single critic with the lowest false acceptance rate; ties use higher accept recall.

## All rows

### Pooled

| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |
|---|---:|---:|---:|---:|---:|---:|
| ensemble | 60 | 0.375 | 0.500 | 0.625 | 0.583 | 0.283 |
| qwen3-coder-30b | 60 | 0.196 | 0.833 | 0.804 | 0.067 | 0.000 |
| nemotron-mini | 60 | 0.256 | 0.917 | 0.744 | 0.283 | 0.283 |
| deepseek-v4-flash | 60 | 0.318 | 0.583 | 0.682 | 0.333 | 0.000 |

Gain versus deepseek-v4-flash: false acceptance rate -0.057; accept recall -0.083.

| Critic | False acceptances by origin |
|---|---|
| ensemble | causal: 2, original: 6, revision_mismatch: 1, unit_error: 1 |
| qwen3-coder-30b | causal: 6, original: 18, revision_mismatch: 8, stale: 1, unit_error: 7, unmeasured: 1 |
| nemotron-mini | causal: 5, original: 11, revision_mismatch: 6, unit_error: 5, unmeasured: 5 |
| deepseek-v4-flash | causal: 2, original: 9, revision_mismatch: 1, stale: 1, unit_error: 2 |

Both critics wrong on same row: —; error correlation: —.

### Original

| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |
|---|---:|---:|---:|---:|---:|---:|
| ensemble | 30 | 0.500 | 0.500 | 0.500 | 0.500 | 0.267 |
| qwen3-coder-30b | 30 | 0.357 | 0.833 | 0.643 | 0.033 | 0.000 |
| nemotron-mini | 30 | 0.500 | 0.917 | 0.500 | 0.267 | 0.267 |
| deepseek-v4-flash | 30 | 0.438 | 0.583 | 0.562 | 0.267 | 0.000 |

Gain versus nemotron-mini: false acceptance rate 0.000; accept recall -0.417.

| Critic | False acceptances by origin |
|---|---|
| ensemble | original: 6 |
| qwen3-coder-30b | original: 18 |
| nemotron-mini | original: 11 |
| deepseek-v4-flash | original: 9 |

Both critics wrong on same row: —; error correlation: —.

### Perturbed

| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |
|---|---:|---:|---:|---:|---:|---:|
| ensemble | 30 | 0.000 | — | 1.000 | 0.667 | 0.300 |
| qwen3-coder-30b | 30 | 0.000 | — | 1.000 | 0.100 | 0.000 |
| nemotron-mini | 30 | 0.000 | — | 1.000 | 0.300 | 0.300 |
| deepseek-v4-flash | 30 | 0.000 | — | 1.000 | 0.400 | 0.000 |

Gain versus qwen3-coder-30b: false acceptance rate 0.000; accept recall —.

| Critic | False acceptances by origin |
|---|---|
| ensemble | causal: 2, revision_mismatch: 1, unit_error: 1 |
| qwen3-coder-30b | causal: 6, revision_mismatch: 8, stale: 1, unit_error: 7, unmeasured: 1 |
| nemotron-mini | causal: 5, revision_mismatch: 6, unit_error: 5, unmeasured: 5 |
| deepseek-v4-flash | causal: 2, revision_mismatch: 1, stale: 1, unit_error: 2 |

Both critics wrong on same row: —; error correlation: —.


## Uncontested rows

### Pooled

| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |
|---|---:|---:|---:|---:|---:|---:|
| ensemble | 44 | 0.444 | 0.571 | 0.556 | 0.659 | 0.318 |
| qwen3-coder-30b | 44 | 0.143 | 0.714 | 0.857 | 0.091 | 0.000 |
| nemotron-mini | 44 | 0.200 | 0.857 | 0.800 | 0.318 | 0.318 |
| deepseek-v4-flash | 44 | 0.385 | 0.714 | 0.615 | 0.364 | 0.000 |

Gain versus deepseek-v4-flash: false acceptance rate -0.060; accept recall -0.143.

| Critic | False acceptances by origin |
|---|---|
| ensemble | causal: 2, original: 1, revision_mismatch: 1, unit_error: 1 |
| qwen3-coder-30b | causal: 6, original: 7, revision_mismatch: 8, stale: 1, unit_error: 7, unmeasured: 1 |
| nemotron-mini | causal: 5, original: 3, revision_mismatch: 6, unit_error: 5, unmeasured: 5 |
| deepseek-v4-flash | causal: 2, original: 2, revision_mismatch: 1, stale: 1, unit_error: 2 |

Both critics wrong on same row: —; error correlation: —.

### Original

| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |
|---|---:|---:|---:|---:|---:|---:|
| ensemble | 14 | 0.800 | 0.571 | 0.200 | 0.643 | 0.357 |
| qwen3-coder-30b | 14 | 0.417 | 0.714 | 0.583 | 0.071 | 0.000 |
| nemotron-mini | 14 | 0.667 | 0.857 | 0.333 | 0.357 | 0.357 |
| deepseek-v4-flash | 14 | 0.714 | 0.714 | 0.286 | 0.286 | 0.000 |

Gain versus deepseek-v4-flash: false acceptance rate -0.086; accept recall -0.143.

| Critic | False acceptances by origin |
|---|---|
| ensemble | original: 1 |
| qwen3-coder-30b | original: 7 |
| nemotron-mini | original: 3 |
| deepseek-v4-flash | original: 2 |

Both critics wrong on same row: —; error correlation: —.

### Perturbed

| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |
|---|---:|---:|---:|---:|---:|---:|
| ensemble | 30 | 0.000 | — | 1.000 | 0.667 | 0.300 |
| qwen3-coder-30b | 30 | 0.000 | — | 1.000 | 0.100 | 0.000 |
| nemotron-mini | 30 | 0.000 | — | 1.000 | 0.300 | 0.300 |
| deepseek-v4-flash | 30 | 0.000 | — | 1.000 | 0.400 | 0.000 |

Gain versus qwen3-coder-30b: false acceptance rate 0.000; accept recall —.

| Critic | False acceptances by origin |
|---|---|
| ensemble | causal: 2, revision_mismatch: 1, unit_error: 1 |
| qwen3-coder-30b | causal: 6, revision_mismatch: 8, stale: 1, unit_error: 7, unmeasured: 1 |
| nemotron-mini | causal: 5, revision_mismatch: 6, unit_error: 5, unmeasured: 5 |
| deepseek-v4-flash | causal: 2, revision_mismatch: 1, stale: 1, unit_error: 2 |

Both critics wrong on same row: —; error correlation: —.

