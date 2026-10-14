"""Exploratory training-only constant baselines; no estimator selection on test data."""
import os
from pathlib import Path
import hashlib
import json
import sys
import h5py
import numpy as np

ROOT = Path(os.environ.get('SCALAR_BASELINES_ROOT', '.scratch'))
work = ROOT / 'task6-codex'
dest = ROOT / 'task456-codex-handoff/task6-scalar-comparison'
paths = {
    'bench_test_200': work / 'bench_data/dataset.h5',
    'production_50k_v2_aic_test_5000': Path(os.environ.get('ODMR_DATASET_ROOT', 'data')) / 'production_50k_v2_aic' / 'dataset.h5',
}
result = {'scope': 'exploratory fixed train-mean/train-median baselines added after Task 6; no test-based selection',
          'rules_fixed_before_scoring': ['training mean magnitude', 'training median magnitude'],
          'measurement_date': '2026-10-14', 'cohorts': {}}
for cohort, path in paths.items():
    with h5py.File(path, 'r') as h:
        train = np.linalg.norm(h['train/labels'][:] * 1e6, axis=1)
        truth = np.linalg.norm(h['test/labels'][:] * 1e6, axis=1)
    assert np.isfinite(train).all() and np.isfinite(truth).all()
    constants = {'train_mean': float(np.mean(train)), 'train_median': float(np.median(train))}
    rows = {}
    for name, value in constants.items():
        error = np.abs(value - truth)
        rows[name] = {'prediction_uT': value, 'n_train': len(train), 'n_test': len(truth),
                      'mae_uT': float(np.mean(error)),
                      'rmse_uT': float(np.sqrt(np.mean(error**2))),
                      'p90_uT': float(np.quantile(error, .9)),
                      'worst_uT': float(np.max(error))}
    pred_file = work / ('bench_predictions.npz' if cohort == 'bench_test_200' else 'production_predictions.npz')
    with np.load(pred_file) as p:
        assert np.allclose(p['truth_uT'], truth, rtol=0, atol=1e-10)
        ideal_error = np.maximum(np.abs(p['pid_prediction_uT'] - truth) - 2.25, 0)
    rows['oracle_bounded_residual'] = {
        'scope': 'not an estimator: clairvoyant lower bound on MAE when correction magnitude is at most 2.25 uT',
        'mae_lower_bound_uT': float(np.mean(ideal_error)),
        'clamp_uT': 2.25,
    }
    result['cohorts'][cohort] = {
        'train_magnitude_sha256': hashlib.sha256(np.ascontiguousarray(train).tobytes()).hexdigest(),
        'test_magnitude_sha256': hashlib.sha256(np.ascontiguousarray(truth).tobytes()).hexdigest(),
        'results': rows,
    }
result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
dest.mkdir(parents=True, exist_ok=True)
(dest / 'constant-baselines.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
