# Recipe

Date: 2026-10-14.

Command:

```bash
PYTHONPATH=~/projects/nv-sensor-sim/src MPLCONFIGDIR=/tmp/odmr-mpl ~/miniconda3/bin/python3 ~/projects/portfolio-publication/wt/odmr-edge-ml-s3-recipe/scripts/make_production_50k_v2_aic.py --out ~/projects/portfolio-publication/wt/odmr-edge-ml-s3-recipe/.scratch/production_50k_v2_aic_verified
```

The full 40,000/5,000/5,000 regeneration reproduced the existing train, validation, and test arrays with matching per-split MD5 hashes. The run used nv-sensor-sim commit `9df6dd161719b369e90c0e284cbef0bae39a0612`, and its generated config hash matched the archived `cfec5b0afe89`.
