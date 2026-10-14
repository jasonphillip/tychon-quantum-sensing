#!/usr/bin/env python3
"""Two-Lorentzian splitting proxy and two separately scoped scalar comparisons.

The splitting proxy is not an orientation-independent total-field inverse.
The bench MLP and deployed FCNN have different frequency grids. Incompatible
cross-cohort model rows are marked not applicable, without resampling or padding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.signal import find_peaks, peak_widths

ROOT = Path(__file__).resolve().parents[1]
GAMMA_HZ_T = 2.8035e10  # Task 6 release specification; PID keeps its published constant.
BENCH_RECIPE = dict(n_train=1000, n_val=200, n_test=200, master_seed=12345,
                    n_freq_points=100, freq_range_Hz=[2.866e9, 2.874e9],
                    noise_mode='deterministic', field_sampling='spherical',
                    shift_test_ranges=False)
PRODUCTION_TEST_MD5 = 'b350320066a4c6a4553f05cd1f469704'
BENCH_SOURCE_COMMIT = '92bacb92ea4b9a102223fb4dcba3a4b07bf9ccb4'
MODEL_SEED = 20261009
EPOCHS = 1000


def _profile(x, baseline, slope, c1, c2, d1, d2, width):
    a, b = (x-c1)/width, (x-c2)/width
    return baseline + slope*x - d1/(1+a*a) - d2/(1+b*b)


def _jacobian(x, baseline, slope, c1, c2, d1, d2, width):
    a, b = (x-c1)/width, (x-c2)/width
    u, v = 1+a*a, 1+b*b
    return np.column_stack((np.ones_like(x), x,
        -2*d1*a/(width*u*u), -2*d2*b/(width*v*v), -1/u, -1/v,
        -2*(d1*a*a/(u*u)+d2*b*b/(v*v))/width))


def fit_field_magnitude(spectrum, freqs_hz):
    """Return splitting/(2 gamma) in microtesla and raw-signal RMS residual.

    Inputs must be finite, ordered, one-dimensional samples. A flat signal is
    rejected. Missing a second local minimum triggers a symmetric initialization
    around the deepest minimum; no field label or reference center is supplied.
    """
    y, f = np.asarray(spectrum, dtype=float), np.asarray(freqs_hz, dtype=float)
    if (y.ndim != 1 or f.ndim != 1 or y.shape != f.shape or len(f) < 8
            or not np.isfinite(y).all() or not np.isfinite(f).all()
            or np.any(np.diff(f) <= 0)):
        raise ValueError('need matching finite 1D spectra and strictly increasing frequencies')
    amplitude = float(np.ptp(y))
    if amplitude <= 1e-12 * max(1.0, float(np.max(np.abs(y)))):
        raise ValueError('flat signal cannot identify two resonances')
    center = 0.5*(f[0]+f[-1]); scale = f[-1]-f[0]
    x = (f-center)/scale
    target = (y-y.min())/amplitude
    minima, _ = find_peaks(-target)
    deepest = int(np.argmin(target))
    if len(minima) >= 2:
        selected = np.sort(minima[np.argsort(target[minima], kind='stable')[:2]])
        centers = x[selected]
        widths = peak_widths(-target, selected, rel_height=0.5)[0]
        width = max(float(np.median(widths)*np.median(np.diff(x))/2), 0.005)
    else:
        width = 0.05
        if 0 < deepest < len(x)-1:
            width = max(float(peak_widths(-target, [deepest])[0][0]*np.median(np.diff(x))/2),0.005)
        centers = np.clip(x[deepest]+np.array([-0.5,0.5])*width,-0.49,0.49)
    edge = float(np.median(np.r_[target[:3],target[-3:]]))
    depth = max(0.05, edge-float(np.min(target)))
    initial = [edge,0.0,centers[0],centers[1],depth,depth,width]
    lower = [-2.0,-5.0,-0.5,-0.5,0.0,0.0,0.0001]
    upper = [3.0,5.0,0.5,0.5,4.0,4.0,1.0]
    initial = np.clip(initial,np.asarray(lower)+1e-8,np.asarray(upper)-1e-8)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',OptimizeWarning)
        params, _ = curve_fit(_profile,x,target,p0=initial,bounds=(lower,upper),
                              jac=_jacobian,method='trf',max_nfev=200,
                              ftol=1e-9,xtol=1e-9,gtol=1e-9)
    if not np.isfinite(params).all():
        raise RuntimeError('nonfinite fit')
    splitting = abs(params[3]-params[2])*scale
    residual = float(np.sqrt(np.mean((_profile(x,*params)-target)**2))*amplitude)
    return float(splitting/(2*GAMMA_HZ_T)*1e6), residual


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def _split_md5(group):
    h=hashlib.md5()
    for key in sorted(group):
        a=np.ascontiguousarray(group[key][:])
        h.update(f'test/{key}'.encode());h.update(str(a.dtype).encode())
        h.update(str(a.shape).encode());h.update(a.tobytes())
    return h.hexdigest()


def _statistics(pred, truth, timings, **extra):
    pred=np.asarray(pred);truth=np.asarray(truth);error=np.abs(pred-truth)
    if pred.shape!=truth.shape or not np.isfinite(pred).all():
        raise RuntimeError('predictions must cover every row with finite values')
    return dict(status='evaluated',n=len(pred),mae_uT=float(error.mean()),
        rmse_uT=float(np.sqrt(np.mean(error**2))),p90_uT=float(np.percentile(error,90)),
        worst_uT=float(error.max()),latency_us_median=float(np.median(timings)),
        latency_us_p90=float(np.percentile(timings,90)),**extra)


def _not_applicable(reason):
    return dict(status='not_applicable_frequency_grid',reason=reason,n=0,mae_uT=None,
        rmse_uT=None,p90_uT=None,worst_uT=None,latency_us_median=None,latency_us_p90=None)


def _normalize(row):
    spread=float(np.ptp(row))
    return ((row-row.min())/(spread if spread else 1.0)).astype(np.float32)


def _measure_fit_pid(spectra, frequencies, truth):
    from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
    pid=DerivativeZeroCrossingPID(frequencies)
    # Warm up each path without changing the fixed estimator configuration.
    pid.estimate(spectra[0])
    try:fit_field_magnitude(spectra[0],frequencies)
    except (RuntimeError,ValueError):pass
    pid_pred=[];pid_us=[];fit_pred=[];fit_us=[];residuals=[];failed=[]
    for i,row in enumerate(spectra):
        start=time.perf_counter_ns();p=pid.estimate(row).b_mag_uT
        pid_us.append((time.perf_counter_ns()-start)/1000);pid_pred.append(p)
        start=time.perf_counter_ns()
        try:b,residual=fit_field_magnitude(row,frequencies)
        except (RuntimeError,ValueError):
            # Include fallback computation in the timed path; never drop failures.
            b=pid.estimate(row).b_mag_uT;residual=None;failed.append(i)
        fit_us.append((time.perf_counter_ns()-start)/1000);fit_pred.append(b);residuals.append(residual)
    return {'two_lorentzian':_statistics(fit_pred,truth,fit_us,
                failed_fits=len(failed),failure_row_indices=failed,fallback='published PID proxy',
                gamma_Hz_per_T=GAMMA_HZ_T,target_caveat='splitting proxy; total field requires orientation information'),
            'pid_proxy':_statistics(pid_pred,truth,pid_us,
                gamma_Hz_per_T=pid.NV_GYROMAGNETIC_RATIO_HZ_T)},np.asarray(pid_pred),dict(
                    fit_prediction_uT=np.asarray(fit_pred),pid_prediction_uT=np.asarray(pid_pred),
                    fit_latency_us=np.asarray(fit_us),pid_latency_us=np.asarray(pid_us),
                    fit_residual=np.asarray([np.nan if v is None else v for v in residuals]))


def _bench_data(work):
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset
    from odmr_edge_ml.data.loaders import DatasetLoader
    directory=work/'bench_data';recipe=work/'bench_recipe.json'
    if directory.exists():
        if not recipe.is_file() or json.loads(recipe.read_text())!=BENCH_RECIPE:
            raise RuntimeError('existing bench cache lacks identical recipe')
    else:
        generate_dataset(output_dir=str(directory),**BENCH_RECIPE)
        recipe.write_text(json.dumps(BENCH_RECIPE,indent=2)+'\n')
    loader=DatasetLoader(directory,normalize=True)
    data={name:loader.load_split(name) for name in ('train','val','test')}
    raw=DatasetLoader(directory,normalize=False).load_split('test')
    h=hashlib.sha256()
    for split in data.values():
        for a in (split.spectra,split.labels,split.seeds):h.update(np.ascontiguousarray(a).tobytes())
    return data,raw,h.hexdigest()


def _train_mlp(data,work):
    import torch
    from odmr_edge_ml.models.mlp import OdmrMLP
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(MODEL_SEED)
    model=OdmrMLP(input_dim=100,output_dim=1,hidden_dims=[64,64])
    optimizer=torch.optim.Adam(model.parameters(),lr=0.01)
    train=data['train']
    x=torch.from_numpy(train.spectra.astype(np.float32))
    y=torch.from_numpy(np.linalg.norm(train.labels,axis=1).astype(np.float32))*1e6
    model.train();start=time.perf_counter()
    for _ in range(EPOCHS):
        optimizer.zero_grad(set_to_none=True)
        loss=torch.mean((model(x).squeeze(1)-y/50.0)**2)
        loss.backward();optimizer.step()
    model.eval();duration=time.perf_counter()-start
    checkpoint=work/'bench_mlp.pt';torch.save(model.state_dict(),checkpoint)
    return model,dict(seed=MODEL_SEED,epochs=EPOCHS,training_wall_s=duration,
                     checkpoint_sha256=_sha(checkpoint),selection='last epoch, exact fixed benchmark recipe')


def _measure_mlp(model,raw):
    import torch
    pred=[];timing=[]
    with torch.no_grad():
        model(torch.from_numpy(_normalize(raw.spectra[0])[None,:]))
        for row in raw.spectra:
            start=time.perf_counter_ns()
            value=float(model(torch.from_numpy(_normalize(row)[None,:])).item()*50.0)
            timing.append((time.perf_counter_ns()-start)/1000);pred.append(value)
    truth=np.linalg.norm(raw.labels,axis=1)*1e6
    return _statistics(pred,truth,timing),np.asarray(pred),np.asarray(timing)


def _tflite_worker(request_path,output_path):
    sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'experiments'))
    import fcnn_v2_int8_float_equivalence as harness
    from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter
    request=np.load(request_path);spectra=request['spectra'];frequencies=request['frequencies']
    truth=request['truth_uT'];expected_pid=request['expected_pid_uT'];expected_locks=request['expected_locks']
    model=ROOT/'exports/fcnn_v2_residual_dataset_a_int8.tflite'
    interp=Interpreter(model_path=str(model),num_threads=1);interp.allocate_tensors()
    inp=interp.get_input_details()[0];out=interp.get_output_details()[0]
    in_scale,in_zp=inp['quantization'];out_scale,out_zp=out['quantization']
    if inp['dtype']!=np.int8 or out['dtype']!=np.int8 or in_scale<=0 or out_scale<=0:
        raise RuntimeError('unexpected model quantization')
    pid=DerivativeZeroCrossingPID(frequencies)
    def estimate(row):
        p=pid.estimate(row)
        flat=harness.preprocess(row[None,:],np.array([p.lock_bin]),harness.DEFAULT_SIGMA)
        q=harness.quantize_array(harness.flat_to_nhwc(flat),in_scale,int(in_zp),inp['dtype'])
        interp.set_tensor(inp['index'],q);interp.invoke()
        raw=int(interp.get_tensor(out['index']).reshape(-1)[0])
        delta=float(np.float32((raw-int(out_zp))*float(out_scale)))
        return p.b_mag_uT+float(np.clip(delta,-harness.DEFAULT_CLAMP_UT,harness.DEFAULT_CLAMP_UT)),p,raw
    estimate(spectra[0]);pred=[];timings=[];raws=[];pid_values=[];locks=[]
    for row in spectra:
        start=time.perf_counter_ns();value,p,raw=estimate(row)
        timings.append((time.perf_counter_ns()-start)/1000)
        pred.append(value);raws.append(raw);pid_values.append(p.b_mag_uT);locks.append(p.lock_bin)
    if not np.allclose(pid_values,expected_pid,rtol=0,atol=1e-9) or not np.array_equal(locks,expected_locks):
        raise RuntimeError('fresh PID/anchor path differs from saved production labels')
    result=_statistics(pred,truth,timings,tflite_sha256=_sha(model),clamp_uT=harness.DEFAULT_CLAMP_UT,
                       timing_scope='PID + preprocessing + quantization + CPU invocation + dequantization + clamp',
                       single_thread_interpreter=True)
    Path(output_path).write_text(json.dumps(result,indent=2)+'\n')
    np.savez(Path(output_path).with_suffix('.npz'),prediction_uT=pred,raw_int8=np.asarray(raws,dtype=np.int8),latency_us=timings)


def _evaluate(args):
    import h5py
    import scipy
    import torch
    sys.path.insert(0,str(ROOT/'src'))
    work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=True)
    if args.cpu is not None:
        if not hasattr(os,'sched_setaffinity') or args.cpu not in os.sched_getaffinity(0):
            raise RuntimeError('requested CPU affinity unavailable')
        os.sched_setaffinity(0,{args.cpu})
    data,bench,digest=_bench_data(work)
    with h5py.File(args.dataset/'dataset.h5','r') as h:
        group=h['test'];md5=_split_md5(group)
        if md5!=PRODUCTION_TEST_MD5:raise RuntimeError('production test-content MD5 mismatch')
        spectra=group['spectra'][:];frequencies=group['frequencies'][:]
        truth=np.linalg.norm(group['labels'][:]*1e6,axis=1)
    if args.pilot:
        rows=[]
        for name,s,f in [('bench',bench.spectra,bench.frequencies),('production',spectra,frequencies)]:
            times=[];failures=0
            for row in s[:args.pilot]:
                start=time.perf_counter()
                try:fit_field_magnitude(row,f)
                except (RuntimeError,ValueError):failures+=1
                times.append(time.perf_counter()-start)
            rows.append(dict(cohort=name,n=len(times),median_ms=float(np.median(times)*1e3),
                             estimated_full_s=float(np.mean(times)*len(s)),failures=failures))
        print(json.dumps(rows,indent=2));return
    model,training=_train_mlp(data,work)
    bench_truth=np.linalg.norm(bench.labels,axis=1)*1e6
    bench_results,_,arrays=_measure_fit_pid(bench.spectra,bench.frequencies,bench_truth)
    mlp,pred,lat=_measure_mlp(model,bench);bench_results['bench_mlp']=mlp
    arrays.update(mlp_prediction_uT=pred,mlp_latency_us=lat,truth_uT=bench_truth)
    np.savez(work/'bench_predictions.npz',**arrays)
    bench_results['deployed_fcnn_int8']=_not_applicable('FCNN expects 100 samples over 2.82-2.92 GHz; bench covers only 2.866-2.874 GHz. No out-of-range padding.')
    production_results,pid_predictions,arrays=_measure_fit_pid(spectra,frequencies,truth)
    np.savez(work/'production_predictions.npz',truth_uT=truth,**arrays)
    production_results['bench_mlp']=_not_applicable('MLP was trained on 100 samples over 2.866-2.874 GHz; production uses 2.82-2.92 GHz. No unregistered resampling.')
    with np.load(args.dataset/'pid_residuals.npz') as labels:
        if not np.allclose(truth,labels['test_b_mag_uT'],rtol=0,atol=1e-9):raise RuntimeError('production label magnitudes differ')
        if not np.allclose(pid_predictions,labels['test_b_pid_uT'],rtol=0,atol=1e-9):raise RuntimeError('fresh PID differs from saved production PID')
        request=work/'tflite_request.npz'
        np.savez(request,spectra=spectra,frequencies=frequencies,truth_uT=truth,
                 expected_pid_uT=labels['test_b_pid_uT'],expected_locks=labels['test_lock_bins'])
    output=work/'tflite_results.json'
    env={**os.environ,'TF_CPP_MIN_LOG_LEVEL':'3','TF_NUM_INTEROP_THREADS':'1','TF_NUM_INTRAOP_THREADS':'1'}
    subprocess.run([str(args.tf_python),str(Path(__file__).resolve()),'--tflite-worker',str(request),str(output)],check=True,env=env,timeout=300)
    production_results['deployed_fcnn_int8']=json.loads(output.read_text())
    result={'bench_test_200':bench_results,'production_50k_v2_aic_test_5000':production_results,
        'provenance':dict(bench_recipe=BENCH_RECIPE,bench_source_commit=BENCH_SOURCE_COMMIT,
             bench_data_sha256=digest,production_test_md5=md5,script_sha256=_sha(__file__),
             training=training,python=sys.version.split()[0],numpy=np.__version__,scipy=scipy.__version__,
             torch=torch.__version__,platform=platform.platform(),processor=platform.processor(),
             cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
             thread_environment={name:os.environ.get(name) for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
             bench_frequency_hz=[float(bench.frequencies[0]),float(bench.frequencies[-1])],
             production_frequency_hz=[float(frequencies[0]),float(frequencies[-1])],
             artifacts={p.name:_sha(p) for p in [work/'bench_predictions.npz',work/'production_predictions.npz',output.with_suffix('.npz')]},
             fit_configuration='two shared-width Lorentzian dips + affine baseline; max_nfev=200; fixed before cohort scoring',
             scalar_scope='descriptive total-field prediction errors; splitting proxy is not exact for arbitrary orientation; no vector verdict')}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--work-dir',type=Path)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--tf-python',type=Path)
    parser.add_argument('--cpu',type=int)
    parser.add_argument('--pilot',type=int,default=0,help='measure fit runtime only; no cohort accuracy or model training')
    parser.add_argument('--tflite-worker',nargs=2,metavar=('REQUEST','OUTPUT'),help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.tflite_worker:
        _tflite_worker(*args.tflite_worker);return
    if not all((args.dataset,args.work_dir,args.out)) or (not args.pilot and not args.tf_python):
        parser.error('--dataset, --work-dir, --out and (except for --pilot) --tf-python are required')
    if args.pilot<0:parser.error('--pilot must be nonnegative')
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        if os.environ.get(key)!='1':parser.error(f'set {key}=1 before starting Python')
    _evaluate(args)


if __name__=='__main__':main()
