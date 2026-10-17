"""Measured preparation-label classification. No GPU or hardware access."""
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):os.environ[k]='4'
import argparse, datetime, hashlib, json, math, platform, resource, time
from pathlib import Path
import h5py
import numpy as np
ROOT=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def check(ok,message):
    if not ok:raise ValueError(message)
def qualification(path):
    with h5py.File(path,'r') as h:
        d=h['readout_meta_CH0_re'];im=h['readout_meta_CH0_im']
        coord=h['qubit_pi_pulse_amplitude'][:];ts=h['readout_meta_time'][:]
        check(d.shape==im.shape==(2,1000,781),'unexpected measured shape')
        check(np.array_equal(coord,[0.,1.]),'unexpected preparation labels')
        check(d.attrs['units']==b'V' and h['readout_meta_time'].attrs['units']==b's','unexpected units')
        check(np.all(np.diff(ts)>0),'time order')
        return {'shape':list(d.shape),'preparation_values':coord.tolist(),'signal_units':'V','time_units':'s',
                'sample_start_s':float(ts[0]),'sample_end_s':float(ts[-1]),
                'sample_interval_s':float(ts[1]-ts[0]),
                **{k:d.attrs[k].decode() for k in ('guid','run_timestamp','completed_timestamp','sample_name','exp_name')},
                'measured_raw_records':True,'compatible_independent_acquisitions':1,'within_acquisition_eligible':True,
                'drift_transfer_eligible':False,'label_scope':'intended preparation, not verified true-state labels'}

def validate_splits(splits,n):
    used=set()
    for name,(lo,hi) in splits.items():
        check(type(lo) is int and type(hi) is int and 0<=lo<hi<=n,'invalid split')
        ids=set(range(lo,hi));check(not used&ids,'overlapping split');used|=ids

def load_block(h,bounds,bins):
    lo,hi=bounds
    # Read only the named shot block. Qualification never accesses signal values.
    x=np.stack((h['readout_meta_CH0_re'][:,lo:hi,:],h['readout_meta_CH0_im'][:,lo:hi,:]),axis=-1)
    check(np.all(np.isfinite(x)),'nonfinite input; no silent record removal')
    binned=np.stack([x[:,:,idx,:].mean(axis=2) for idx in np.array_split(np.arange(x.shape[2]),bins)],axis=2)
    return binned.reshape(-1,bins,2),np.repeat([0,1],hi-lo).astype(np.int64)

def linear(x,y,kind,shrink=.2):
    z=x.mean(axis=1) if kind=='boxcar' else x.reshape(len(x),-1)
    means=np.stack([z[y==j].mean(0) for j in (0,1)])
    w=means[1]-means[0]
    if kind=='lda':
        r=z-means[y];cov=r.T@r/(len(y)-2)
        cov=(1-shrink)*cov+shrink*np.trace(cov)/z.shape[1]*np.eye(z.shape[1])
        w=np.linalg.solve(cov,w)
    check(np.all(np.isfinite(w)) and np.any(w!=0),'degenerate classifier')
    return {'kind':kind,'w':w,'b':-float(w@means.mean(0))}

def score(x,model):
    z=x.mean(axis=1) if model['kind']=='boxcar' else x.reshape(len(x),-1)
    return z@model['w']+model['b']

def fit_affine(reference,ry,calibration,cy,c):
    nominal=np.stack([reference[ry==j].mean(0) for j in (0,1)]).reshape(-1,2)
    observed=np.stack([calibration[cy==j].mean(0) for j in (0,1)]).reshape(-1,2)
    design=np.column_stack((nominal,np.ones(len(nominal))))
    fitted,_,rank,_=np.linalg.lstsq(design,observed,rcond=None)
    matrix,offset=fitted[:2],fitted[2];sv=np.linalg.svd(matrix,compute_uv=False)
    cond=float(sv[0]/sv[-1]) if sv[-1] else None
    valid=bool(rank==3 and sv[-1]>=c['affine_minimum_singular_value'] and cond is not None and cond<=c['affine_maximum_condition_number'])
    return {'matrix':matrix.tolist(),'offset':offset.tolist(),'rank':int(rank),'singular_values':sv.tolist(),'condition':cond,'valid':valid}

def apply_affine(x,fit):
    check(fit['valid'],'invalid affine calibration')
    return ((x.reshape(-1,2)-fit['offset'])@np.linalg.inv(fit['matrix'])).reshape(x.shape)

def wilson(k,n):
    z=1.959963984540054;p=k/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [mid-half,mid+half]

def metrics(y,s):
    if s is None:return {'coverage':0.,'balanced_accuracy':None,'reason':'invalid affine calibration'}
    pred=(s>=0).astype(int);conf=np.array([[np.sum((y==i)&(pred==j)) for j in (0,1)] for i in (0,1)])
    return {'coverage':1.,'balanced_accuracy':float(np.mean(np.diag(conf)/conf.sum(axis=1))),
            'confusion_preparation_by_assignment':conf.tolist(),
            'per_preparation_error':(1-np.diag(conf)/conf.sum(axis=1)).tolist(),
            'correct':int(np.sum(pred==y)),'records':len(y),'conditional_iid_wilson95':wilson(int(np.sum(pred==y)),len(y))}

def integer_pack(out,x,y,training,model):
    # Boxcar host model only. New coefficients are not the currently deployed model.
    scale=float(np.max(np.abs(training))/4);check(scale>0,'invalid training scale')
    w=model['w'];norm=float(np.max(np.abs(w)))
    wn=w/norm;bn=model['b']/(scale*norm)*x.shape[1]
    qw=np.rint(wn*2**14).astype(np.int64);qb=int(np.rint(bn*2**25))
    pre=np.rint(x/scale*2**11);clipped=int(np.sum((pre<-32768)|(pre>32767)))
    q=np.clip(pre,-32768,32767).astype('<i2')
    bound=int(x.shape[1]*32768*sum(abs(int(v)) for v in qw)+abs(qb))
    check(bound<2**63,'int64 score overflow')
    sums=q.astype(np.int64).sum(axis=1);scores=(sums@qw+qb).astype('<i8')
    exact=[sum(int(a)*int(b) for a,b in zip(row,qw))+qb for row in sums]
    check(all(int(a)==b for a,b in zip(scores,exact)),'integer parity')
    folder=out/'candidate_integer_pack';folder.mkdir()
    for name,data in [('inputs_i16.bin',q.reshape(len(q),128).tobytes()),('expected_scores_i64.bin',scores.tobytes()),('labels_u8.bin',y.astype('u1').tobytes())]:
        (folder/name).write_bytes(data)
    receipt={'records':len(y),'input_shape':[len(y),128],'byte_order':'little','input_fraction_bits':11,
             'score_fraction_bits':25,'volts_per_normalized_unit':scale,'weights_i32':qw.tolist(),'bias_i64':qb,
             'full_int16_score_abs_bound':bound,'clipped_values':clipped,'python_bigint_scores_exact':True,
             'float_decision_disagreements':int(np.sum((scores>=0)!=(score(x,model)>=0))),
             'preparation_accuracy':float(np.mean((scores>=0)==y)),
             'scope':'candidate coefficients and host arithmetic only; requires new build; no board replay',
             'sha256':{f.name:sha(f) for f in folder.iterdir()}}
    write(folder/'manifest.json',receipt);return receipt

def register():
    c=json.loads((ROOT/'protocol.json').read_text());validate_splits(c['split_per_preparation'],1000)
    receipt=ROOT/'registration.json';check(not receipt.exists(),'registration exists')
    paths=['protocol.json','PROTOCOL.md','evaluate.py','test_evaluate.py',c['dataset'],'zenodo_10000511_metadata.json']
    write(receipt,{'registered_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'scope':'before any final signal read','sha256':{p:sha(ROOT/p) for p in paths},'qualification':qualification(ROOT/c['dataset'])})
    print('REGISTERED',sha(receipt))

def run(out):
    reg=json.loads((ROOT/'registration.json').read_text())
    for path,digest in reg['sha256'].items():check(sha(ROOT/path)==digest,'registered file changed: '+path)
    check(not out.exists(),'output must be new');check(not (ROOT/'consumed.json').exists(),'final set already consumed')
    out.mkdir(parents=True);start=time.perf_counter();c=json.loads((ROOT/'protocol.json').read_text())
    write(out/'registration.json',reg)
    with h5py.File(ROOT/c['dataset'],'r') as h:
        blocks={k:load_block(h,c['split_per_preparation'][k],c['bin_count']) for k in ('reference','calibration','validation')}
        ref,ry=blocks['reference'];cal,cy=blocks['calibration'];vx,vy=blocks['validation']
        tx=np.concatenate((ref,cal));ty=np.concatenate((ry,cy))
        models={name:linear(tx,ty,kind,c['lda_shrinkage']) for name,kind in [('pooled_boxcar','boxcar'),('pooled_matched_filter','matched'),('pooled_lda','lda')]}
        reference=linear(ref,ry,'boxcar');affine=fit_affine(ref,ry,cal,cy,c)
        def all_scores(x):
            result={k:score(x,m) for k,m in models.items()}
            result['affine_reference_boxcar']=score(apply_affine(x,affine),reference) if affine['valid'] else None
            return result
        val={k:metrics(vy,s) for k,s in all_scores(vx).items()}
        selected=max(c['baseline_methods'],key=lambda k:val[k]['balanced_accuracy'] if val[k]['coverage'] else -1)
        selection={'selected':selected,'validation':val,'affine':affine,'final_read_started':False,
                   'model_parameters':{k:{'kind':m['kind'],'w':m['w'].tolist(),'b':m['b']} for k,m in {**models,'reference_boxcar':reference}.items()}}
        write(out/'selection_before_final.json',selection)
        write(ROOT/'consumed.json',{'output':str(out.relative_to(ROOT)),'selection_sha256':sha(out/'selection_before_final.json'),
                                   'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'final_set_consumed':True})
        fx,fy=load_block(h,c['split_per_preparation']['final'],c['bin_count'])
    final_scores=all_scores(fx);result={k:metrics(fy,s) for k,s in final_scores.items()}
    result['reference_boxcar_uncalibrated']=metrics(fy,score(fx,reference))
    gain=(result['affine_reference_boxcar']['balanced_accuracy']-result['reference_boxcar_uncalibrated']['balanced_accuracy']) if affine['valid'] else None
    pack=integer_pack(out,fx,fy,tx,models['pooled_boxcar'])
    rowfile=out/'final_predictions.csv'
    with rowfile.open('w') as f:
        names=list(final_scores)+['reference_boxcar_uncalibrated'];f.write('preparation,shot_index,'+','.join(names)+'\n')
        final_scores['reference_boxcar_uncalibrated']=score(fx,reference)
        for i,label in enumerate(fy):f.write(f'{label},{500+i%500},'+','.join(str(int(final_scores[k][i]>=0)) if final_scores[k] is not None else '' for k in names)+'\n')
    mem=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    receipt={'schema':'measured_readout_result_v1','qualification':reg['qualification'],'selected':selected,'final':result,
             'calibration_gain_over_reference':gain,'calibration_gain_nonnegative':bool(gain is not None and gain>=0),
             'utility_acceptance_pass':result[selected]['balanced_accuracy']>=c['utility_acceptance']['selected_final_balanced_accuracy_min'],
             'drift_transfer_eligible':False,'candidate_integer_pack':pack,'elapsed_seconds':time.perf_counter()-start,
             'peak_rss_bytes':int(mem if platform.system()=='Darwin' else mem*1024),'memory_method':'getrusage RUSAGE_SELF ru_maxrss',
             'python':platform.python_version(),'numpy':np.__version__,'h5py':h5py.__version__,
             'scope':'within-acquisition preparation-label agreement; no physical true-state fidelity or drift-transfer claim; no FPGA run',
             'output_hashes':{'final_predictions.csv':sha(rowfile),'selection_before_final.json':sha(out/'selection_before_final.json')}}
    write(out/'metrics.json',receipt);print(json.dumps(receipt,indent=2))

def main():
    a=argparse.ArgumentParser();a.add_argument('command',choices=['qualify','register','run']);a.add_argument('--output',type=Path);args=a.parse_args()
    if args.command=='qualify':print(json.dumps(qualification(ROOT/json.loads((ROOT/'protocol.json').read_text())['dataset']),indent=2))
    elif args.command=='register':register()
    else:
        check(args.output is not None,'--output required');run(args.output.resolve())
if __name__=='__main__':main()
