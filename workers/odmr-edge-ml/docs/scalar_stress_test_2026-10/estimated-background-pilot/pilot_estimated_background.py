#!/usr/bin/env python3
"""One fixed outer-bin OLS background pilot. Development only; no tuning."""
import argparse, hashlib, importlib.util, json, os, sys, time
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='-1'
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='2'
import numpy as np
import torch
SEEDS=(42,20261014,20261015)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(name,p):
    spec=importlib.util.spec_from_file_location(name,p)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def metric(p,t):
    e=p-t
    assert np.isfinite(e).all()
    return dict(mae_uT=float(abs(e).mean()),rmse_uT=float(np.sqrt((e**2).mean())),
                bias_uT=float(e.mean()),min_uT=float(p.min()),max_uT=float(p.max()))
def main():
    parser=argparse.ArgumentParser()
    for name in ('root','repo','experiment'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();start=time.perf_counter()
    out=a.root/'estimated-background-pilot';out.mkdir(exist_ok=True)
    if (out/'results.json').exists():raise RuntimeError('Pilot already exists; no repeated method selection')
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.use_deterministic_algorithms(True)
    sources={'experiment':a.experiment/'run_experiment.py',
        'architecture':a.repo/'src/odmr_edge_ml/models/fcnn_v2.py',
        'pid':a.repo/'src/odmr_edge_ml/evaluation/pid_proxy.py'}
    source_hashes={k:sha(v) for k,v in sources.items()}
    exp=module('pilot_experiment',sources['experiment'])
    arch=module('pilot_architecture',sources['architecture'])
    pid_module=module('pilot_pid',sources['pid'])
    prior_dir=a.root/'mechanism-diagnostic'
    prior_paths=[prior_dir/f for f in ('results.json','REPORT.md','predictions.npz','diagnose_mechanism.py')]
    prior_hashes={str(p):sha(p) for p in prior_paths}
    previous=json.loads((prior_dir/'results.json').read_text())
    data_path=a.root/'data/dev/realistic_anchor.npz'
    with np.load(data_path,allow_pickle=False) as z:
        y=z['spectra'];f=z['frequencies_hz'];seeds=z['sample_seeds']
        truth=np.linalg.norm(z['truth_vectors_T'],axis=1)*1e6
    with np.load(prior_dir/'predictions.npz',allow_pickle=False) as z:
        reference={k:z[k] for k in ['sample_seeds','truth_uT','detector__original__locks',
            'detector__original__projection_uT']+[f'A_original_original_lock__seed{s}' for s in SEEDS]}
    assert y.shape==(16,100)
    np.testing.assert_array_equal(seeds,reference['sample_seeds'])
    np.testing.assert_array_equal(truth,reference['truth_uT'])
    # Fixed before execution: first20 and last20 bins, ordinary least squares with intercept.
    x=(f-(f[0]+f[-1])/2)/(f[-1]-f[0])
    edge=np.r_[np.arange(20),np.arange(80,100)]
    design=np.column_stack([np.ones(len(edge)),x[edge]])
    coeff=np.linalg.lstsq(design,y[:,edge].T,rcond=None)[0]
    intercept,slope=coeff[0],coeff[1]
    corrected=y-slope[:,None]*x[None,:]
    detector=pid_module.DerivativeZeroCrossingPID(f)
    pid_rows=detector.estimate_batch(corrected)
    locks=np.array([r.lock_bin for r in pid_rows])
    pid=np.array([r.b_mag_uT for r in pid_rows])
    def pack(spectra,anchor):
        lo=spectra.min(1,keepdims=True);hi=spectra.max(1,keepdims=True)
        norm=2*(spectra-lo)/np.where(hi==lo,1,hi-lo)-1
        return torch.from_numpy(np.concatenate([norm,anchor[:,None]],axis=1).astype(np.float32))
    packed=pack(corrected,locks)
    original=pack(y,reference['detector__original__locks'])
    predictions={'truth_uT':truth,'sample_seeds':seeds,'estimated_slope':slope,
        'estimated_intercept':intercept,'pid_projection_uT':pid,'lock_bins':locks}
    per_seed={};reproduction={}
    choices=previous['checkpoint_records']
    assert len(choices)==3 and {r['seed'] for r in choices}==set(SEEDS)
    for r in choices:
        assert r['arm']=='C_direct' and sha(r['checkpoint'])==r['checkpoint_sha256']
        ckpt=torch.load(r['checkpoint'],map_location='cpu',weights_only=True)
        assert ckpt['arm']=='C_direct' and ckpt['seed']==r['seed']
        model=exp.clean_model(arch,ckpt['state_dict'],torch.device('cpu'))
        check=exp.predict(model,original)
        old=reference[f'A_original_original_lock__seed{r["seed"]}']
        np.testing.assert_array_equal(check,old)
        reproduction[str(r['seed'])]={'array_equal':True,'max_abs_difference_uT':0.}
        pred=exp.predict(model,packed)
        per_seed[str(r['seed'])]=metric(pred,truth)
        predictions[f'C_direct_seed{r["seed"]}']=pred
    # Known slope enters diagnostic scoring only; it never enters the correction.
    slope_error=slope-.02
    bins,counts=np.unique(locks,return_counts=True)
    original_pid=reference['detector__original__projection_uT']
    result={'scope':'Single fixed implementable development pilot; no adoption or held-out claim',
        'n':16,'seeds':list(SEEDS),'method':{'outer_bins':edge.tolist(),
        'x':'(frequency-midpoint)/(maximum-minimum)','fit':'OLS slope plus intercept',
        'correction':'spectrum minus estimated slope*x; fitted intercept retained'},
        'model_per_seed':per_seed,
        'model_mean_seed_mae_uT':float(np.mean([v['mae_uT'] for v in per_seed.values()])),
        'slope_diagnostic':{'known_injected_slope_for_scoring_only':.02,
            'estimated_min':float(slope.min()),'estimated_max':float(slope.max()),
            'mean_estimate':float(slope.mean()),'mae':float(abs(slope_error).mean()),
            'rmse':float(np.sqrt((slope_error**2).mean())),'bias':float(slope_error.mean())},
        'PID_after_correction':{**metric(pid,truth),
            'out_of_support_0_70_count':int(((pid<0)|(pid>70)).sum()),
            'nonfinite_count':int((~np.isfinite(pid)).sum()),
            'lock_bin_distribution':{str(int(b)):int(c) for b,c in zip(bins,counts)}},
        'PID_original':{**metric(original_pid,truth),
            'out_of_support_0_70_count':int(((original_pid<0)|(original_pid>70)).sum())},
        'saved_descriptive_comparisons':{
            'original_mean_seed_mae_uT':previous['variants']['A_original_original_lock']['mean_seed_mae_uT'],
            'known_slope_recomputed_lock_mean_seed_mae_uT':previous['variants']['C_detrended_recomputed_lock']['mean_seed_mae_uT'],
            'clean_mean_seed_mae_uT':previous['clean_reference']['mean_seed_mae_uT']},
        'original_output_reproduction':reproduction,
        'pairing':'exact sample seed and truth equality with previous 16-row diagnostic',
        'previous_diagnostic_hashes':prior_hashes,'data_sha256':sha(data_path),
        'source_hashes':source_hashes,'checkpoint_records':choices,'script_sha256':sha(__file__),
        'seconds':time.perf_counter()-start,
        'limits':['One fixed method and mask; no tuning, seed selection, or training.',
            'Only 16 previously used development rows; not independent evidence.',
            'No validation/final data or predictions opened.',
            'Original four-variant diagnostic and evaluator remain unchanged.',
            'Known slope is used only to measure slope-estimation error.']}
    for key,path in sources.items():assert sha(path)==source_hashes[key]
    for path,digest in prior_hashes.items():assert sha(path)==digest
    np.savez_compressed(out/'predictions.npz',**predictions)
    result['predictions_sha256']=sha(out/'predictions.npz')
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# Estimated background pilot','','Date: 2026-10-14.',
        '', 'Method fixed before execution: OLS using bins 0-19 and 80-99.',
        'Subtract only the estimated slope. Recompute the unchanged PID detector and lock.',
        'Score all three frozen C_direct FP32 models. No training or tuning occurs.',
        '', '| Seed | MAE in microtesla |','|---|---:|']
    lines += [f'| {seed} | {per_seed[str(seed)]["mae_uT"]:.6f} |' for seed in SEEDS]
    lines += [f'| Mean seed error | {result["model_mean_seed_mae_uT"]:.6f} |','',
        'Saved comparison MAEs: original %.6f; known-slope correction %.6f; clean %.6f microtesla.' %
        tuple(result['saved_descriptive_comparisons'].values()),'',
        'All original outputs reproduced exactly. Sample pairing and source hashes passed.',
        'Slope errors, PID errors, lock distribution, support counts, and provenance are in results.json.',
        'Only 16 development rows were used. This does not establish held-out improvement or justify adoption.',
        'The previous diagnostic remains unchanged. No further method or mask was tested.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:result[k] for k in ('model_per_seed','model_mean_seed_mae_uT',
        'slope_diagnostic','PID_after_correction','PID_original','saved_descriptive_comparisons','seconds')},indent=2))
if __name__=='__main__':main()
