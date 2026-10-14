#!/usr/bin/env python3
"""Evaluate fixed scalar estimators, with a one-read final-data guard."""
from __future__ import annotations
import argparse, datetime, hashlib, importlib.util, json, os, platform, sys, time
from pathlib import Path
os.environ['CUDA_VISIBLE_DEVICES']='-1'
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','TF_NUM_INTRAOP_THREADS'):
    os.environ[key]='2'
os.environ['TF_NUM_INTEROP_THREADS']='1'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import numpy as np

SEEDS=(42,20261014,20261015)
ARMS=('B_full_residual','C_direct')
PRIMARY=('clean','realistic_anchor')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(path,obj): Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def metrics(pred,truth):
    err=np.asarray(pred,dtype=np.float64)-truth
    if not np.isfinite(err).all(): raise RuntimeError('Nonfinite error; rows cannot be dropped')
    return {'n':len(err),'mae_uT':float(np.mean(abs(err))),'rmse_uT':float(np.sqrt(np.mean(err**2))),
        'median_abs_uT':float(np.median(abs(err))),'p90_abs_uT':float(np.quantile(abs(err),.9)),
        'bias_uT':float(err.mean())}

def candidates(a):
    old=json.loads((a.experiment/'run-1/FROZEN_CHOICES.json').read_text())
    original_exports={r['name']:r for r in json.loads((a.experiment/'evaluation/exports.json').read_text())}
    repairs=json.loads((a.calibration/'run-1/results.json').read_text())
    records=[]
    for item in old['choices']:
        if item['arm'] not in ARMS:continue
        name=f"{item['arm']}_seed{item['seed']}"
        cp=Path(item['checkpoint'])
        if sha(cp)!=item['checkpoint_sha256']:raise RuntimeError('Original checkpoint hash changed')
        if item['arm']=='B_full_residual':
            repair=repairs['models'][name];export=Path(repair['new_export'])
            if sha(export)!=repair['new_export_sha256']:raise RuntimeError('Repaired export hash changed')
        else:
            export=a.experiment/'evaluation'/(name+'.tflite')
            if sha(export)!=original_exports[name]['sha256']:raise RuntimeError('Original direct export hash changed')
        records.append({'name':name,'arm':item['arm'],'seed':item['seed'],
            'checkpoint':str(cp),'checkpoint_sha256':sha(cp),'export':str(export),'export_sha256':sha(export)})
    if {(r['arm'],r['seed']) for r in records}!={(x,s) for x in ARMS for s in SEEDS}:
        raise RuntimeError('Candidate set does not match protocol')
    return records

def source_paths(a):
    return [Path(__file__),a.protocol,a.work/'generate_stress_data.py',a.work/'s2b/prior_aware_scalar.py',
        a.work/'s2b/test_prior_aware_scalar.py',a.experiment/'run_experiment.py',
        a.repo/'src/odmr_edge_ml/models/fcnn_v2.py',a.repo/'src/odmr_edge_ml/training/qat.py',
        a.repo/'experiments/scalar_fit_baseline.py',a.repo/'src/odmr_edge_ml/evaluation/pid_proxy.py',
        a.repo/'experiments/fcnn_v2_int8_float_equivalence.py',a.repo/'src/odmr_edge_ml/models/fcnn.py']

def bound_paths(a):
    return {name:str(getattr(a,name).resolve()) for name in
        ('work','repo','experiment','calibration','data','protocol','freeze')}

def verify_frozen_sources(a,frozen):
    if bound_paths(a)!=frozen['bound_paths']:raise RuntimeError('CLI paths differ from frozen paths')
    current={str(p):sha(p) for p in source_paths(a)}
    if current!=frozen['source_hashes']:raise RuntimeError('Frozen imported source set or hash changed')
    if (Path(frozen['bound_paths']['work'])/'FINAL_ACCESS.json').exists():
        raise RuntimeError('Final partition already consumed')

def verify_partition(data,expected_manifest_hash=None,check_payload=True):
    manifest=data/'manifest.json'
    if expected_manifest_hash and sha(manifest)!=expected_manifest_hash:raise RuntimeError('Data manifest hash mismatch')
    if data.is_symlink() or data.stat().st_mode&0o222:raise RuntimeError('Partition is not sealed')
    d=json.loads(manifest.read_text())
    if not d['single_orientation']:raise RuntimeError('Wrong simulator cohort')
    for record in d['cells'].values():
        p=data/record['file']
        if p.is_symlink() or p.stat().st_mode&0o222:raise RuntimeError('Data file is not sealed')
        if check_payload and sha(p)!=record['sha256']:raise RuntimeError('Data hash mismatch')
    if manifest.stat().st_mode&0o222:raise RuntimeError('Manifest is not sealed')
    return d

def freeze(a):
    if a.freeze.exists():raise RuntimeError('Freeze already exists')
    if not (a.work/'results-val/SUMMARY.json').exists():raise RuntimeError('Fixed-candidate validation check is required')
    final=verify_partition(a.data/'final',check_payload=False)
    if final['protocol_sha256']!=sha(a.protocol):raise RuntimeError('Protocol differs from generated data')
    record={'created_utc':now(),'status':'frozen','candidates':candidates(a),
        'bound_paths':bound_paths(a),
        'source_hashes':{str(p):sha(p) for p in source_paths(a)},
        'final_manifest_sha256':sha(a.data/'final/manifest.json'),
        'data_manifest_sha256':{p:sha(a.data/p/'manifest.json') for p in ('dev','val','final')},
        'validation_summary_sha256':sha(a.work/'results-val/SUMMARY.json'),
        'fixed_seeds':list(SEEDS),'primary_cells':list(PRIMARY),'final_accessed':False,
        'training_mean_uT':45.064080128749545,'training_median_uT':44.90404360960018,
        'prior_support_uT':[20,70]}
    with a.freeze.open('x') as f:json.dump(record,f,indent=2)
    print(json.dumps({'event':'frozen','path':str(a.freeze),'sha256':sha(a.freeze)}),flush=True)

def paired(errors):
    names=list(errors);matrix=np.stack([errors[k] for k in names],axis=1)
    rng=np.random.default_rng(202610143);draws=[]
    for _ in range(100):
        idx=rng.integers(0,len(matrix),size=(100,len(matrix)))
        draws.append(matrix[idx].mean(axis=1))
    bs=np.concatenate(draws)
    return {k:{'mean_difference_uT':float(matrix[:,i].mean()),
        'ci95_uT':np.quantile(bs[:,i],[.025,.975]).tolist(),'resamples':10000,
        'bootstrap_seed':202610143} for i,k in enumerate(names)}

def run(a):
    import torch
    start=time.monotonic();partition=a.mode;out=a.work/('results-'+partition)
    if out.exists():raise RuntimeError('Partition output already exists; repeat scoring refused')
    if partition=='final':
        if not a.freeze_sha256 or sha(a.freeze)!=a.freeze_sha256:raise RuntimeError('Freeze hash not accepted')
        frozen=json.loads(a.freeze.read_text())
        if frozen['final_accessed'] or frozen['status']!='frozen':raise RuntimeError('Invalid freeze state')
        verify_frozen_sources(a,frozen)
        records=frozen['candidates']
        manifest=verify_partition(a.data/partition,frozen['final_manifest_sha256'],check_payload=False)
    else:
        records=candidates(a);manifest=verify_partition(a.data/partition,check_payload=False)
    if manifest['protocol_sha256']!=sha(a.protocol):raise RuntimeError('Data/protocol mismatch')
    for r in records:
        if sha(r['checkpoint'])!=r['checkpoint_sha256'] or sha(r['export'])!=r['export_sha256']:
            raise RuntimeError('Candidate artifact changed')
    # All source and artifact checks precede any reserved-data read.
    exp=module('stress_experiment',a.experiment/'run_experiment.py')
    arch,_,_=exp.setup(a.repo)
    helpers=module('stress_helpers',a.repo/'experiments/fcnn_v2_int8_float_equivalence.py')
    baseline=module('stress_prior',a.work/'s2b/prior_aware_scalar.py')
    pid_module=module('stress_pid',a.repo/'src/odmr_edge_ml/evaluation/pid_proxy.py')
    loaded=[]
    for r in records:
        ckpt=torch.load(r['checkpoint'],map_location='cpu',weights_only=True)
        if float(ckpt['state_dict']['sigma'])<.1:raise RuntimeError('Sigma below FP32 preprocessing clamp')
        loaded.append({**r,'model':exp.clean_model(arch,ckpt['state_dict'],torch.device('cpu')),
            'sigma':float(ckpt['state_dict']['sigma']),'interpreter':helpers.load_interpreter(Path(r['export']))})
    out.mkdir()
    receipt={'partition':partition,'first_read_utc':now(),'status':'in_progress',
        'data_manifest_sha256':sha(a.data/partition/'manifest.json'),'evaluator_sha256':sha(__file__),
        'protocol_sha256':sha(a.protocol),'freeze_sha256':a.freeze_sha256 if partition=='final' else None,
        'candidates':records,'scope':'single-orientation synthetic; CPU only; no retraining'}
    access=a.work/(partition.upper()+'_ACCESS.json')
    with access.open('x') as f:json.dump(receipt,f,indent=2)
    # The exclusive receipt now owns this campaign, including the first payload hash.
    verify_partition(a.data/partition,receipt['data_manifest_sha256'],check_payload=True)
    mean=45.064080128749545;median=44.90404360960018;summary={}
    for cell,record in manifest['cells'].items():
        if time.monotonic()-start>900:raise RuntimeError('Evaluation wall cap exceeded; accessed partition is consumed')
        with np.load(a.data/partition/record['file'],allow_pickle=False) as z:
            spectra=z['spectra'];truth=np.linalg.norm(z['truth_vectors_T'],axis=1)*1e6
            freqs=z['frequencies_hz'];seeds=z['sample_seeds']
        np.testing.assert_array_equal(freqs,np.linspace(2.82e9,2.92e9,100))
        if not (len(truth)==manifest['rows_per_cell'] and np.isfinite(spectra).all()):raise RuntimeError('Invalid data')
        begin=time.perf_counter()
        pid_rows=pid_module.DerivativeZeroCrossingPID(freqs).estimate_batch(spectra)
        pid=np.array([r.b_mag_uT for r in pid_rows]);locks=np.array([r.lock_bin for r in pid_rows])
        pid_seconds=time.perf_counter()-begin
        stored={'truth_uT':truth,'sample_seeds':seeds,'pid_lock_bins':locks,
            'pred__PID':pid,'pred__training_mean':np.full(len(truth),mean),
            'pred__training_median':np.full(len(truth),median)}
        failures={};timing={'PID':{'batch_seconds':pid_seconds}}
        for backend,label in [('two_line','prior_fit'),('pid','prior_PID')]:
            begin=time.perf_counter();r=baseline.fit_batch(spectra,freqs,scalar_repo=a.repo,backend=backend)
            elapsed=time.perf_counter()-begin
            fail=r['failed']|~np.isfinite(r['magnitude_uT'])
            stored['pred__'+label]=np.where(fail,mean,r['magnitude_uT'])
            stored['failed__'+label]=fail;stored['outside__'+label]=r['out_of_support']
            stored['raw_projection__'+label]=r['raw_projection_uT']
            if backend=='two_line':stored['pred__two_line_projection']=np.where(fail,mean,r['raw_projection_uT'])
            failures[label]={'failed':int(fail.sum()),'out_of_support':int(r['out_of_support'].sum()),
                'n':len(fail),'failure_fraction':float(fail.mean())}
            timing[label]={'batch_seconds':elapsed,'median_row_seconds':float(np.median(r['latency_seconds'])),
                'p90_row_seconds':float(np.quantile(r['latency_seconds'],.9))}
        quant={}
        for item in loaded:
            name=item['name'];begin=time.perf_counter()
            lo=spectra.min(1,keepdims=True);hi=spectra.max(1,keepdims=True)
            normalized=2*(spectra-lo)/np.where(hi==lo,1,hi-lo)-1
            packed=torch.from_numpy(np.concatenate([normalized,locks[:,None]],axis=1).astype(np.float32))
            output=exp.predict(item['model'],packed)
            fp=exp.field_predictions(item['arm'],output,pid)
            timing[name+'__fp32']={'batch_seconds':time.perf_counter()-begin,'timing_kind':'batch preprocessing and inference; not per-request latency'}
            begin=time.perf_counter();flat=helpers.preprocess(spectra,locks,item['sigma'])
            qo,stats=helpers.run_tflite(item['interpreter'],flat)
            qi=exp.field_predictions(item['arm'],qo.astype(np.float64),pid)
            timing[name+'__int8']={'batch_seconds':time.perf_counter()-begin,'timing_kind':'batch preprocessing and sequential inference; not per-request latency'}
            stored['pred__'+name+'__fp32']=fp;stored['pred__'+name+'__int8']=qi
            quant[name]={**stats,'int8_vs_fp32':metrics(qi,fp)}
        scored={k.removeprefix('pred__'):metrics(v,truth) for k,v in stored.items() if k.startswith('pred__')}
        arm={};errors={}
        for armname in ARMS:
            for precision in ('fp32','int8'):
                names=[f'{armname}_seed{s}__{precision}' for s in SEEDS]
                errors[armname+'__'+precision]=np.mean([abs(stored['pred__'+n]-truth) for n in names],axis=0)
                arm[armname+'__'+precision]={'mean_seed_mae_uT':float(np.mean([scored[n]['mae_uT'] for n in names])),
                    'seed_mae_uT':[scored[n]['mae_uT'] for n in names]}
        c=errors['C_direct__int8']
        differences={'C_minus_mean':c-abs(stored['pred__training_mean']-truth),
            'C_minus_prior_fit':c-abs(stored['pred__prior_fit']-truth),
            'C_minus_prior_PID':c-abs(stored['pred__prior_PID']-truth),
            'C_minus_repaired_B':c-errors['B_full_residual__int8']}
        comparisons=paired(differences)
        path=out/(cell+'_predictions.npz');np.savez_compressed(path,**stored)
        result={'cell':cell,'partition':partition,'data':record,'models':scored,'arm_summary':arm,
            'paired_comparisons':comparisons,'failures':failures,'quantization':quant,'timing':timing,
            'prediction_file':path.name,'prediction_sha256':sha(path)}
        dump(out/(cell+'_metrics.json'),result);summary[cell]=result
        print(json.dumps({'event':'cell_complete','partition':partition,'cell':cell,
            'C_INT8_MAE':arm['C_direct__int8']['mean_seed_mae_uT'],
            'B_repaired_INT8_MAE':arm['B_full_residual__int8']['mean_seed_mae_uT'],
            'mean_MAE':scored['training_mean']['mae_uT'],'prior_fit_MAE':scored['prior_fit']['mae_uT']}),flush=True)
    criterion=all(summary[c]['paired_comparisons'][k]['mean_difference_uT']<0 and summary[c]['paired_comparisons'][k]['ci95_uT'][1]<0
        for c in PRIMARY for k in ('C_minus_mean','C_minus_prior_fit'))
    result={'partition':partition,'status':'complete','cells':summary,'primary_criterion_passed':criterion,
        'criterion':'C_INT8 lower MAE with upper paired CI <0 against mean and prior-aware fit in both primary cells',
        'scope':'conditional on simulator and fixed nuisance trajectories; descriptive synthetic robustness',
        'seconds':time.monotonic()-start,'versions':{'python':sys.version,'platform':platform.platform(),
            'numpy':np.__version__,'torch':torch.__version__},'source_hashes':{str(p):sha(p) for p in source_paths(a)}}
    dump(out/'SUMMARY.json',result)
    receipt.update(status='complete',completed_utc=now(),seconds=result['seconds'],summary_sha256=sha(out/'SUMMARY.json'))
    dump(access,receipt)
    print(json.dumps({'event':'complete','partition':partition,'seconds':result['seconds'],'primary_criterion_passed':criterion}),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('dev','val','freeze','final'),required=True)
    for name in ('work','repo','experiment','calibration','data','protocol','freeze'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--freeze-sha256')
    a=p.parse_args()
    for name in ('work','repo','experiment','calibration','data','protocol','freeze'):
        setattr(a,name,getattr(a,name).resolve())
    if a.mode=='freeze':freeze(a)
    else:run(a)

if __name__=='__main__':main()
