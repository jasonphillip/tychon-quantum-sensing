#!/usr/bin/env python3
"""Four fixed exploratory interventions on paired DEVELOPMENT spectra only."""
import argparse, hashlib, importlib.util, json, os, sys, time
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '2'
import numpy as np
import torch

SEEDS = (42, 20261014, 20261015)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m
def distribution(values):
    bins, counts = np.unique(values, return_counts=True)
    return {str(int(b)): int(n) for b, n in zip(bins, counts)}
def metrics(pred, truth):
    e = np.asarray(pred, dtype=np.float64)-truth
    assert np.isfinite(e).all()
    return {'mae_uT': float(abs(e).mean()), 'rmse_uT': float(np.sqrt((e**2).mean())),
            'bias_uT': float(e.mean())}
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--experiment', type=Path, required=True)
    a = p.parse_args()
    out = a.root / 'mechanism-diagnostic'
    out.mkdir(exist_ok=True)
    if (out/'results.json').exists():
        raise RuntimeError('Diagnostic already exists; no repeated intervention study')
    start = time.perf_counter()
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    paths = {'evaluator': a.root/'evaluate_stress.py',
             'generator': a.root/'generate_stress_data.py',
             'experiment': a.experiment/'run_experiment.py',
             'architecture': a.repo/'src/odmr_edge_ml/models/fcnn_v2.py',
             'pid': a.repo/'src/odmr_edge_ml/evaluation/pid_proxy.py'}
    source_hashes = {k: {'path': str(v), 'sha256': sha(v)} for k,v in paths.items()}
    exp = module('diagnostic_experiment', paths['experiment'])
    arch = module('diagnostic_arch', paths['architecture'])
    pid_mod = module('diagnostic_pid', paths['pid'])
    receipt_path = a.root/'DEV_ACCESS.json'
    receipt = json.loads(receipt_path.read_text())
    choices = [r for r in receipt['candidates'] if r['arm'] == 'C_direct']
    assert len(choices) == 3 and {r['seed'] for r in choices} == set(SEEDS)
    choices.sort(key=lambda r: SEEDS.index(r['seed']))
    arrays, saved, input_hashes = {}, {}, {}
    for cell in ('clean', 'realistic_anchor'):
        data_path = a.root/'data/dev'/(cell+'.npz')
        prediction_path = a.root/'results-dev'/(cell+'_predictions.npz')
        assert data_path.parent.name == 'dev' and prediction_path.parent.name == 'results-dev'
        with np.load(data_path, allow_pickle=False) as z:
            arrays[cell] = {k: z[k] for k in
                ('spectra','truth_vectors_T','frequencies_hz','sample_seeds')}
        with np.load(prediction_path, allow_pickle=False) as z:
            saved[cell] = {k: z[k] for k in
                ['truth_uT','sample_seeds','pid_lock_bins','pred__PID']+
                [f'pred__C_direct_seed{s}__fp32' for s in SEEDS]}
        input_hashes[str(data_path)] = sha(data_path)
        input_hashes[str(prediction_path)] = sha(prediction_path)
        np.testing.assert_array_equal(arrays[cell]['sample_seeds'], saved[cell]['sample_seeds'])
        np.testing.assert_array_equal(
            np.linalg.norm(arrays[cell]['truth_vectors_T'], axis=1)*1e6, saved[cell]['truth_uT'])
    clean, realistic = arrays['clean'], arrays['realistic_anchor']
    for key in ('sample_seeds','truth_vectors_T','frequencies_hz'):
        np.testing.assert_array_equal(clean[key], realistic[key])
    truth = saved['realistic_anchor']['truth_uT']
    freqs = realistic['frequencies_hz']
    assert len(truth) == 16 and realistic['spectra'].shape == (16,100)
    pid = pid_mod.DerivativeZeroCrossingPID(freqs)
    slope = .02*(freqs-(freqs[0]+freqs[-1])/2)/(freqs[-1]-freqs[0])
    detrended = realistic['spectra']-slope[None,:]
    detector_inputs = {'clean': clean['spectra'], 'original': realistic['spectra'],
                       'detrended': detrended}
    detectors, detector_arrays = {}, {}
    for label, spectra in detector_inputs.items():
        rows = pid.estimate_batch(spectra)
        locks = np.array([r.lock_bin for r in rows])
        projection = np.array([r.b_mag_uT for r in rows])
        detector_arrays[label] = {'locks': locks, 'projection_uT': projection}
        detectors[label] = {'lock_bin_distribution': distribution(locks),
            'PID_out_of_support_0_70_count': int(((projection<0)|(projection>70)).sum()),
            'PID_nonfinite_count': int((~np.isfinite(projection)).sum()),
            'PID_min_uT': float(projection.min()), 'PID_max_uT': float(projection.max()),
            'dip_count_distribution': distribution([r.n_dips for r in rows])}
    for label, cell in [('clean','clean'), ('original','realistic_anchor')]:
        np.testing.assert_array_equal(detector_arrays[label]['locks'], saved[cell]['pid_lock_bins'])
        np.testing.assert_array_equal(detector_arrays[label]['projection_uT'], saved[cell]['pred__PID'])
    variants = {
      'A_original_original_lock': (realistic['spectra'], detector_arrays['original']['locks'], 'original', False),
      'B_original_clean_lock': (realistic['spectra'], detector_arrays['clean']['locks'], 'original', True),
      'C_detrended_recomputed_lock': (detrended, detector_arrays['detrended']['locks'], 'detrended', True),
      'D_detrended_clean_lock': (detrended, detector_arrays['clean']['locks'], 'detrended', True)}
    models = {}
    for r in choices:
        assert sha(r['checkpoint']) == r['checkpoint_sha256']
        ckpt = torch.load(r['checkpoint'], map_location='cpu', weights_only=True)
        assert ckpt['arm']=='C_direct' and ckpt['seed']==r['seed']
        models[r['seed']] = exp.clean_model(arch, ckpt['state_dict'], torch.device('cpu'))
    stored = {'sample_seeds': realistic['sample_seeds'], 'truth_uT': truth}
    reports, reproduction = {}, {}
    clean_reference = {}
    for seed in SEEDS:
        pred = saved['clean'][f'pred__C_direct_seed{seed}__fp32']
        clean_reference[str(seed)] = metrics(pred, truth)
        stored[f'clean_reference_seed{seed}'] = pred
    clean_summary = {'source': 'saved development predictions; no clean model rerun',
        'per_seed': clean_reference,
        'mean_seed_mae_uT': float(np.mean([m['mae_uT'] for m in clean_reference.values()]))}
    for name, (spectra, locks, detector_label, oracle) in variants.items():
        # Exact spectrum normalization and 101-value packing from the frozen evaluator.
        lo = spectra.min(1,keepdims=True)
        hi = spectra.max(1,keepdims=True)
        normalized = 2*(spectra-lo)/np.where(hi==lo,1,hi-lo)-1
        packed = torch.from_numpy(np.concatenate([normalized,locks[:,None]],axis=1).astype(np.float32))
        per_seed = {}
        for seed in SEEDS:
            prediction = exp.predict(models[seed], packed)
            if name.startswith('A_'):
                reference = saved['realistic_anchor'][f'pred__C_direct_seed{seed}__fp32']
                reproduction[str(seed)] = {'max_abs_difference_uT':float(abs(prediction-reference).max()),
                    'array_equal': bool(np.array_equal(prediction, reference))}
                np.testing.assert_allclose(prediction, reference, rtol=0, atol=1e-6)
            per_seed[str(seed)] = metrics(prediction, truth)
            stored[f'{name}__seed{seed}'] = prediction
        stored[name+'__locks'] = locks
        reports[name] = {'per_seed':per_seed,
            'mean_seed_mae_uT':float(np.mean([m['mae_uT'] for m in per_seed.values()])),
            'anchor_bin_distribution': distribution(locks),
            'detector_for_raw_spectrum': detector_label,
            'PID_out_of_support_0_70_count': detectors[detector_label]['PID_out_of_support_0_70_count'],
            'uses_oracle_information': oracle}
    for label, values in detector_arrays.items():
        for key, value in values.items(): stored[f'detector__{label}__{key}'] = value
    np.savez_compressed(out/'predictions.npz', **stored)
    result = {'scope':'Exploratory paired development-only mechanism diagnostic; no deployable gain claim',
      'n':len(truth),'seeds':list(SEEDS),'variants':reports,'clean_reference':clean_summary,
      'detectors':detectors,'A_saved_prediction_reproduction':reproduction,
      'pairing_verified':['sample_seeds','truth_vectors_T','frequencies_hz'],
      'intervention': {'slope_amplitude':.02,
        'formula':'.02*(freq-midpoint)/(freqmax-freqmin)',
        'B_D':'matched clean-row PID lock; oracle diagnostic',
        'C_D':'known injected slope subtraction; oracle nuisance information'},
      'input_hashes':input_hashes,'source_hashes':source_hashes,
      'checkpoint_records':choices, 'script_sha256':sha(__file__),
      'predictions_sha256':sha(out/'predictions.npz'),
      'seconds':time.perf_counter()-start,
      'limitations':['Only 16 paired development rows and three fixed FP32 seeds.',
        'No model selection, threshold optimization, retraining, or validation/final reads.',
        'Clean locks use paired noiseless narrower-line spectra unavailable at deployment.',
        'Known slope subtraction is not an estimated deployable background correction.',
        'Residual noise, linewidth broadening, and frequency offset remain unchanged.']}
    for key, path in paths.items():
        assert sha(path) == source_hashes[key]['sha256'], 'Source changed during diagnostic'
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines = ['# Development-only mechanism diagnostic', '', 'Date: 2026-10-14.',
      '', 'All 16 rows retain paired sample seeds, true fields, and frequency grids.',
      'All three frozen C_direct FP32 models are scored. No training or seed selection occurs.',
      '', '| Variant | Seed 42 MAE | Seed 20261014 MAE | Seed 20261015 MAE | Mean seed MAE |',
      '|---|---:|---:|---:|---:|']
    for name, r in [('Clean reference',clean_summary)]+list(reports.items()):
        vals = [r['per_seed'][str(s)]['mae_uT'] for s in SEEDS]+[r['mean_seed_mae_uT']]
        lines.append('| '+name+' | '+' | '.join(f'{v:.6f}' for v in vals)+' |')
    lines += ['', 'All errors are in microtesla. Means average seed errors, not predictions.',
      '', 'Variant A reproduces saved outputs within 0.000001 microtesla.',
      'Exact comparison details, detector distributions, support violations, and hashes are in results.json.',
      '', 'B and D use matched clean locks. C and D subtract the known injected slope.',
      'These oracle interventions diagnose mechanisms. They do not demonstrate a deployable improvement.',
      'Noise, linewidth broadening, and frequency offset remain. Only four fixed variants were evaluated.',
      '', 'No validation/final raw data or predictions were opened. The evaluator remains unchanged.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'mean_seed_mae_uT':{k:v['mean_seed_mae_uT'] for k,v in reports.items()},
        'clean_reference':clean_summary, 'detectors':detectors,'reproduction':reproduction,
        'seconds':result['seconds']},indent=2))
if __name__=='__main__': main()
