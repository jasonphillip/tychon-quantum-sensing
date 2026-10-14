"""One bounded original-training-only timing pilot; reads no labels or other splits."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='2'
import argparse, hashlib, json, time
from pathlib import Path
import h5py
import numpy as np
from prior_aware_scalar import fit_batch

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--dataset',type=Path,required=True)
p.add_argument('--scalar-repo',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
args=p.parse_args()
start=time.perf_counter()
with h5py.File(args.dataset/'dataset.h5','r') as f:
    grid=f['train/frequencies'][:]
    rows=f['train/spectra'][:16]
result={'scope':'original train rows0..15 only; no labels read; no accuracy scoring',
        'n_rows':16,'row_indices':list(range(16)),
        'train_spectra_sha256':hashlib.sha256(rows.tobytes()).hexdigest(),
        'frequency_sha256':hashlib.sha256(grid.tobytes()).hexdigest(),
        'threads':2,'arms':{}}
for backend in ('two_line','pid'):
    receipt=fit_batch(rows,grid,scalar_repo=args.scalar_repo,backend=backend)
    elapsed=receipt['latency_seconds']
    result['arms'][backend]={'failed':int(receipt['failed'].sum()),
        'out_of_support':int(receipt['out_of_support'].sum()),
        'latency_ms_median':float(np.median(elapsed)*1000),
        'latency_ms_p90':float(np.percentile(elapsed,90)*1000),
        'latency_ms_max':float(np.max(elapsed)*1000),
        'timed_total_seconds':float(elapsed.sum()),
        'estimated_seconds_2688_rows_at_observed_mean':float(elapsed.mean()*2688),
        'raw_projection_uT':[None if not np.isfinite(x) else float(x) for x in receipt['raw_projection_uT']],
        'magnitude_uT':[None if not np.isfinite(x) else float(x) for x in receipt['magnitude_uT']],
        'failure_mask':receipt['failed'].tolist(),
        'out_of_support_mask':receipt['out_of_support'].tolist()}
result['wall_seconds_including_imported_source_setup']=time.perf_counter()-start
result['source_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).with_name('prior_aware_scalar.py'),args.scalar_repo/'experiments/scalar_fit_baseline.py',args.scalar_repo/'src/odmr_edge_ml/evaluation/pid_proxy.py']}
args.out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
