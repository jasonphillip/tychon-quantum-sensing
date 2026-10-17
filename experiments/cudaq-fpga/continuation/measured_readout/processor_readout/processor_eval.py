"""Frozen classical preparation-readout study; separate train and released test commands."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):os.environ[name]='4'
import argparse,csv,datetime,hashlib,json,math,platform,resource,signal,time
from pathlib import Path
import numpy as np
from processor_io import ROOT,CODE_FILES,RangeStore,check,sha,load,write,rows,validate_protocol,check_registered,release_gate

METHODS=['pooled_boxcar','pooled_matched_filter','pooled_lda_shrinkage_0.2','affine_reference_boxcar']
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def memory_bytes():
    n=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;return int(n if platform.system()=='Darwin' else n*1024)
def bin_weights(length,bins=64):
    check(type(length) is int and length>=bins>0,'invalid bin dimensions')
    edges=np.linspace(0.,float(length),bins+1);i=np.arange(length)
    overlap=np.maximum(0,np.minimum(edges[1:,None],i+1)-np.maximum(edges[:-1,None],i))
    return overlap/(length/bins)
def bin_trace(x,window):
    a,b=window;check(x.ndim==3 and x.shape[1:]==(770,2) and 0<=a<b<=770,'unexpected trace shape/window')
    return np.einsum('nti,bt->nbi',x[:,a:b,:],bin_weights(b-a),optimize=True)
def fit(x,y,kind):
    z=x.mean(1) if kind=='boxcar' else x.reshape(len(x),-1)
    m=np.stack([z[y==k].mean(0) for k in (0,1)]);w=m[1]-m[0]
    if kind=='lda':
        residual=z-m[y];cov=residual.T@residual/(len(y)-2)
        cov=.8*cov+.2*np.trace(cov)/len(w)*np.eye(len(w));w=np.linalg.solve(cov,w)
    check(np.isfinite(w).all() and np.any(w!=0),'degenerate classifier')
    return {'kind':kind,'w':w.tolist(),'b':-float(w@m.mean(0))}
def score(x,m):
    z=x.mean(1) if m['kind']=='boxcar' else x.reshape(len(x),-1)
    return z@np.asarray(m['w'])+m['b']
def affine_fit(ref,ry,cal,cy):
    nominal=np.stack([ref[ry==k].mean(0) for k in (0,1)]).reshape(-1,2)
    observed=np.stack([cal[cy==k].mean(0) for k in (0,1)]).reshape(-1,2)
    design=np.column_stack((nominal,np.ones(len(nominal))));f,_,rank,_=np.linalg.lstsq(design,observed,rcond=None)
    sv=np.linalg.svd(f[:2],compute_uv=False);cond=float(sv[0]/sv[-1]) if sv[-1] else None
    valid=bool(rank==3 and sv[-1]>=.15 and cond is not None and cond<=10.)
    return {'matrix':f[:2].tolist(),'offset':f[2].tolist(),'rank':int(rank),'singular_values':sv.tolist(),'condition':cond,'valid':valid}
def affine_apply(x,a):
    check(a['valid'],'invalid affine calibration')
    return ((x.reshape(-1,2)-a['offset'])@np.linalg.inv(a['matrix'])).reshape(x.shape)
def wilson(k,n):
    check(n>0,'empty preparation class');z=1.959963984540054;p=k/n;d=1+z*z/n
    mid=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [mid-half,mid+half]
def metrics(y,s):
    if s is None:return {'coverage':0.,'balanced_accuracy':None,'reason':'invalid affine calibration'}
    pred=(s>=0).astype(np.int64);conf=np.array([[np.sum((y==i)&(pred==j)) for j in (0,1)] for i in (0,1)])
    counts=conf.sum(1);check(np.all(counts>0),'missing preparation')
    return {'coverage':1.,'balanced_accuracy':float(np.mean(np.diag(conf)/counts)),
            'pooled_accuracy':float(np.trace(conf)/len(y)),'confusion_preparation_by_assignment':conf.tolist(),
            'per_preparation_counts':counts.tolist(),'per_preparation_error':(1-np.diag(conf)/counts).tolist(),
            'per_preparation_accuracy_wilson95':[wilson(int(conf[k,k]),int(counts[k])) for k in (0,1)],
            'pooled_accuracy_wilson95':wilson(int(np.trace(conf)),len(y)),
            'interval_scope':'conditional IID shot assumptions; pooled interval is not a balanced-accuracy interval'}
def select(candidates):
    viable=[c for c in candidates if c['validation']['coverage']]
    check(bool(viable),'no eligible candidate')
    return min(viable,key=lambda c:(-c['validation']['balanced_accuracy'],METHODS.index(c['method']),c['window'][1]-c['window'][0]))['id']
def candidate_scores(x,model,method):
    if method=='affine_reference_boxcar':return score(affine_apply(x,model['affine']),model['reference']) if model['affine']['valid'] else None
    return score(x,model[method])
def arrays(store,source,ranges):
    name=f'0528_X_{source}_0_770.npy';chunks=[];ids=[]
    for a,b in ranges:
        path=store.get(name,a,b);v=np.fromfile(path,dtype='<f8').reshape(b-a,770,2)
        check(np.isfinite(v).all(),'nonfinite signal; no filtering');chunks.append(v);ids.extend(range(a,b))
    if source=='train':
        y=np.load(ROOT/'inputs/0528_y_train_0_770.npy',allow_pickle=False)[ids]
    else:
        y=np.concatenate([np.fromfile(store.get('0528_y_test_0_770.npy',a,b),dtype='<f8') for a,b in ranges])
    check(np.isin(y,[0.,1.]).all(),'unknown preparation label')
    return np.concatenate(chunks),y.astype(np.int64),np.asarray(ids,dtype=np.int64)
def register():
    p=load(ROOT/'PROPOSED_PROTOCOL.json');validate_protocol(p)
    out=ROOT/'train_registration.json';check(not out.exists(),'registration exists')
    files=list(CODE_FILES)+['PROPOSED_PROTOCOL.json','headers.json','inputs/0528_y_train_0_770.npy','train_label_qualification.json']
    r={'registered_utc':now(),'scope':'train-only pipeline before signal retrieval; test requires independent release',
       'sha256':{name:sha(ROOT/name) for name in files}}
    write(out,r);print('REGISTERED',sha(out))
def train():
    reg=load(ROOT/'train_registration.json');check_registered(ROOT,reg)
    out=ROOT/'train_frozen';check(not out.exists(),'training output exists');out.mkdir()
    begin=time.perf_counter();p=load(ROOT/'PROPOSED_PROTOCOL.json');store=RangeStore()
    blocks={k:arrays(store,'train',v) for k,v in p['source_train'].items()}
    retrieval_elapsed=time.perf_counter()-begin;fit_start=time.perf_counter()
    models={};candidates=[];row_hashes=[]
    for part,(x,y,ids) in blocks.items():
        for row,label,index in zip(x,y,ids):row_hashes.append({'partition':part,'source_row':int(index),'label':int(label),'signal_sha256':hashlib.sha256(row.tobytes()).hexdigest()})
    for window in p['candidate_windows']:
        key=f'{window[0]}:{window[1]}'
        b={k:(bin_trace(v[0],window),v[1]) for k,v in blocks.items()}
        ref,ry=b['reference'];cal,cy=b['calibration'];vx,vy=b['validation'];tx=np.concatenate((ref,cal));ty=np.concatenate((ry,cy))
        m={name:fit(tx,ty,kind) for name,kind in zip(METHODS[:3],('boxcar','matched','lda'))}
        m.update(reference=fit(ref,ry,'boxcar'),affine=affine_fit(ref,ry,cal,cy),integer_input_scale=float(np.max(np.abs(tx))/4))
        models[key]=m
        for method in METHODS:candidates.append({'id':method+'@'+key,'method':method,'window':window,'validation':metrics(vy,candidate_scores(vx,m,method))})
    selected=select(candidates);boxcar=select([c for c in candidates if c['method']=='pooled_boxcar'])
    write(out/'models.json',models);write(out/'source_train_rows.json',row_hashes)
    selection={'selected':selected,'boxcar_pack_candidate':boxcar,'candidates':candidates,'frozen_before_test_download':True,'source_test_values_read':0}
    write(out/'selection.json',selection)
    # Bind immutable ranges independently of the ledger, which will grow during released test retrieval.
    ranges={entry['file']:entry['sha256'] for entry in store.ledger['ranges'].values()}
    write(out/'train_ranges.json',ranges)
    receipt={'schema':'processor_readout_train_receipt_v1','frozen_utc':now(),'registration':reg,
             'artifacts':{name:sha(out/name) for name in ('models.json','source_train_rows.json','selection.json','train_ranges.json')},
             'source_test_values_read':0,'training_rows':{k:len(v[1]) for k,v in blocks.items()},
             'training_signal_checks':{k:{'shape':list(v[0].shape),'minimum':float(v[0].min()),'maximum':float(v[0].max()),'all_integer_valued':bool(np.equal(v[0],np.rint(v[0])).all()),'preparation_counts':[int(np.sum(v[1]==j)) for j in (0,1)]} for k,v in blocks.items()},
             'retrieval_seconds':retrieval_elapsed,'fit_selection_seconds':time.perf_counter()-fit_start,
             'elapsed_seconds':time.perf_counter()-begin,'peak_rss_bytes':memory_bytes(),'memory_method':'getrusage RUSAGE_SELF ru_maxrss',
             'numpy':np.__version__,'python':platform.python_version(),'source_scope':'native digital values; preparation labels; acquisition grouping unverified'}
    write(out/'receipt.json',receipt)
    print(json.dumps({'selected':selected,'boxcar_pack_candidate':boxcar,'candidates':candidates,'receipt_sha256':sha(out/'receipt.json'),'resources':receipt},indent=2))
def integer_pack(out,x,y,ids,m,scale,candidate):
    w=np.asarray(m['w']);norm=float(np.max(np.abs(w)));check(scale>0 and norm>0,'invalid integer scale');qw=np.rint(w/norm*2**14).astype(np.int64)
    qb=int(np.rint(m['b']/(scale*norm)*64*2**25));pre=np.rint(x/scale*2**11)
    clipped=int(np.sum((pre<-32768)|(pre>32767)));q=np.clip(pre,-32768,32767).astype('<i2')
    bound=64*32768*sum(abs(int(t)) for t in qw)+abs(qb);check(bound<2**63,'score int64 bound')
    scores=(q.astype(np.int64).sum(axis=1)@qw+qb).astype('<i8')
    exact=[sum(int(pair[0])*int(qw[0])+int(pair[1])*int(qw[1]) for pair in row)+qb for row in q]
    check(all(int(a)==b for a,b in zip(scores,exact)),'integer parity')
    folder=out/'candidate_integer_pack';folder.mkdir()
    for name,data in [('inputs_i16.bin',q.reshape(len(q),128).tobytes()),('expected_scores_i64.bin',scores.tobytes()),('labels_u8.bin',y.astype('u1').tobytes()),('source_rows_u32.bin',ids.astype('<u4').tobytes())]:(folder/name).write_bytes(data)
    r={'candidate':candidate,'records':len(y),'input_pairs':64,'input_dtype':'little-endian int16','score_dtype':'little-endian int64',
       'input_fraction_bits':11,'score_fraction_bits':25,'native_units_per_normalized_unit':scale,'weights_i32':qw.tolist(),'bias_i64':qb,
       'full_int16_abs_score_bound':bound,'clipped_values':clipped,'python_bigint_scores_exact':True,
       'float_decision_disagreements':int(np.sum((scores>=0)!=(score(x,m)>=0))),'metrics':metrics(y,scores),
       'scope':'new host coefficients; requires future FPGA image; no hardware execution','sha256':{f.name:sha(f) for f in folder.iterdir()}}
    write(folder/'manifest.json',r);return r

def test(release,out):
    approval=release_gate(ROOT,release);check(not (ROOT/'test_consumed.json').exists(),'source-test already consumed')
    check(not out.exists(),'test output exists');out.mkdir(parents=True)
    train=load(ROOT/'train_frozen/receipt.json');selection=load(ROOT/'train_frozen/selection.json');models=load(ROOT/'train_frozen/models.json')
    for name,digest in load(ROOT/'train_frozen/train_ranges.json').items():check(sha(ROOT/name)==digest,'frozen range changed')
    write(out/'release.json',approval);write(out/'train_receipt.json',train)
    write(ROOT/'test_consumed.json',{'started_utc':now(),'output':str(out.relative_to(ROOT)),'training_receipt_sha256':sha(ROOT/'train_frozen/receipt.json'),'status':'consumed before first test-label/signal retrieval'})
    begin=time.perf_counter();p=load(ROOT/'PROPOSED_PROTOCOL.json');store=RangeStore(release=release)
    x,y,ids=arrays(store,'test',p['source_test']['final'])
    check(all(np.sum(y==j)>=1024 for j in (0,1)),'insufficient final preparation class; no resampling')
    train_hashes={v['signal_sha256'] for v in load(ROOT/'train_frozen/source_train_rows.json')}
    duplicates=[int(i) for row,i in zip(x,ids) if hashlib.sha256(row.tobytes()).hexdigest() in train_hashes]
    write(out/'duplicate_check.json',{'exact_signal_duplicates_vs_source_train':duplicates})
    check(not duplicates,'exact signal duplicate across source partitions; no filtering')
    retrieval=time.perf_counter()-begin;eval_start=time.perf_counter();scores={};result={};paired={}
    binned={f'{a}:{b}':bin_trace(x,[a,b]) for a,b in p['candidate_windows']}
    for c in selection['candidates']:
        key=f'{c["window"][0]}:{c["window"][1]}';s=candidate_scores(binned[key],models[key],c['method'])
        scores[c['id']]=s;result[c['id']]=metrics(y,s)
    for key,m in models.items():
        raw=score(binned[key],m['reference']);cal=scores['affine_reference_boxcar@'+key]
        result['reference_boxcar@'+key]=metrics(y,raw)
        if cal is not None:
            a=(cal>=0)==y;b=(raw>=0)==y;better=int(np.sum(a&~b));worse=int(np.sum(b&~a))
            paired[key]={'calibration_minus_reference_balanced_accuracy':metrics(y,cal)['balanced_accuracy']-metrics(y,raw)['balanced_accuracy'],
                         'corrected_records':better,'regressed_records':worse}
    names=list(scores)
    with (out/'predictions.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['source_test_row','preparation']+names)
        for i,label in enumerate(y):writer.writerow([int(ids[i]),int(label)]+[int(scores[k][i]>=0) if scores[k] is not None else '' for k in names])
    key=selection['boxcar_pack_candidate'].split('@')[1]
    pack=integer_pack(out,binned[key],y,ids,models[key]['pooled_boxcar'],models[key]['integer_input_scale'],selection['boxcar_pack_candidate'])
    final=selection['selected'];receipt={'schema':'processor_readout_final_v1','selected':final,'final':result,'paired_calibration':paired,
             'utility_acceptance_pass':result[final]['balanced_accuracy']>=.90,'drift_transfer_eligible':False,
             'source_test_records':len(y),'source_test_preparation_counts':[int(np.sum(y==j)) for j in (0,1)],
             'candidate_integer_pack':pack,'retrieval_seconds':retrieval,'evaluation_export_seconds':time.perf_counter()-eval_start,
             'elapsed_seconds':time.perf_counter()-begin,'peak_rss_bytes':memory_bytes(),'memory_method':'getrusage RUSAGE_SELF ru_maxrss',
             'source_train_test_exact_duplicates':0,'training_receipt_sha256':sha(ROOT/'train_frozen/receipt.json'),
             'predictions_sha256':sha(out/'predictions.csv'),'source_test_ranges':{k:v for k,v in store.ledger['ranges'].items() if '_test_' in k},
             'scope':'held-out source-test preparation-label classification; acquisition identities unverified; no drift, true-state certification, or FPGA execution'}
    write(out/'metrics.json',receipt);print(json.dumps(receipt,indent=2))
def main():
    signal.signal(signal.SIGALRM,lambda a,b:(_ for _ in ()).throw(TimeoutError('1800 second registered run cap')));signal.alarm(1800)
    a=argparse.ArgumentParser();a.add_argument('command',choices=['register','train','test']);a.add_argument('--release',type=Path);a.add_argument('--output',type=Path);args=a.parse_args()
    if args.command=='register':register()
    elif args.command=='train':train()
    else:
        check(args.output is not None,'test output required');test(args.release,args.output.resolve())
if __name__=='__main__':main()
