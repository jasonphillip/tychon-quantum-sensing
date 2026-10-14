# Scalar stress generation and sealing receipt

| Partition | Rows per cell | Cells | Cell rows | Generation seconds | Manifest SHA256 |
|---|---:|---:|---:|---:|---|
| dev | 16 | 7 | 112 | 1.170287 | bcc4faca60f5edb7617149961849b704b4bf863a5cec48644934892e71d9193b |
| val | 128 | 7 | 896 | 2.427473 | 1e02b26c5313dffbe631aec2dcecd693acc672d76e5820d15b897bd9eccf2f3f |
| final | 256 | 7 | 1792 | 3.725677 | 6ce3db6ee01687d17b3015e773e75303c3f5e8877f5a05a385a4eca21f438e41 |

Unique sample seeds: 400. Seed overlaps: 0.
Total generation wall time, including failures: 7.323437 seconds.
Generation failures: 0. Shape failures: 0. Finiteness failures: 0. Cross-cell vector, nuisance-trajectory, and noise-seed mismatches: 0.
Writable sealed files or directories: 0. Model invocations: 0. Prior metric or truth arrays accessed: 0.

## Exact generator commands

```sh
<path> <experiment-dir>/generate_stress_data.py --sim-repo <path> --original-manifest <data-root>/production_50k_v2_aic/manifest.json --prior-predictions <path> --protocol <experiment-dir>/PROTOCOL.md --out <experiment-dir>/data --partition dev
```

```sh
<path> <experiment-dir>/generate_stress_data.py --sim-repo <path> --original-manifest <data-root>/production_50k_v2_aic/manifest.json --prior-predictions <path> --protocol <experiment-dir>/PROTOCOL.md --out <experiment-dir>/data --partition val
```

```sh
<path> <experiment-dir>/generate_stress_data.py --sim-repo <path> --original-manifest <data-root>/production_50k_v2_aic/manifest.json --prior-predictions <path> --protocol <experiment-dir>/PROTOCOL.md --out <experiment-dir>/data --partition final
```

Metadata receipts: <experiment-dir>/sealing/VERIFICATION.json
Per-attempt receipts: <experiment-dir>/sealing/attempts.json
Protocol SHA256: 39cde896ef333889806d176e3e162af645608de9c02a59310b9884925f746072
Generator SHA256: 44ff2d0fca79fb1ca32fa6124006eb788fd8d3e735bb2aa1b417cfbb24a590e4
