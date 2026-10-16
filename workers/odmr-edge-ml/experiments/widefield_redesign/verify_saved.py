"""Public NumPy-only saved-statistic check. No FITS, inference, private gate or Torch."""
from pathlib import Path
import argparse,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.widefield_redesign.access import sha,write_json
from experiments.widefield_redesign.qualification import decide,sufficient


def equal(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,bool) or a is None or isinstance(a,str):return a==b and type(a)==type(b)
    return np.isclose(a,b,rtol=1e-10,atol=1e-15)


def verify(directory,expected):
    root=Path(directory).resolve();mp=root/'verification-manifest.json'
    if sha(mp)!=expected:raise ValueError('Independent manifest pin differs')
    manifest=json.loads(mp.read_text())
    for relative,digest in manifest['files'].items():
        p=root/relative
        if p.is_symlink() or not p.resolve().is_relative_to(root) or sha(p)!=digest:raise ValueError('Artifact integrity failure')
    report=json.loads((root/'report.json').read_text());checks=0
    if list(report['files'])!=['f1.fits','f4.fits']:raise ValueError('Wrong acquisition identities')
    for name,saved in report['files'].items():
        with np.load(root/(name+'.geometry.npz'),allow_pickle=False) as z:
            ids=z['ids'];masks=z['masks']
            if ids.dtype.kind not in 'iu' or ids.shape!=(len(masks),4) or masks.dtype!=bool or masks.shape[1:]!=(9,9):raise ValueError('Invalid spot identity or masks')
            if not np.array_equal(ids[:,0],np.arange(len(ids))) or len(set(map(tuple,ids[:,1:3])))!=len(ids):raise ValueError('Duplicate spot identity')
            if not np.array_equal(ids[:,3],ids[:,1]//128*4+ids[:,2]//128):raise ValueError('Wrong spatial grouping')
        if 'reason' in saved:
            if saved['eligible'] or (32<=len(ids)<=512 and len(set(ids[:,3]))>=8):raise ValueError('Geometry stop inconsistent')
            checks+=1;continue
        with np.load(root/(name+'.statistics.npz'),allow_pickle=False) as z:stats={k:z[k] for k in z.files}
        with np.load(root/(name+'.spectra.npz'),allow_pickle=False) as z:
            v=z['values'];clips=z['clipped']
            if not np.array_equal(z['ids'],ids) or v.shape!=(5,len(ids),200) or clips.shape!=v.shape or clips.dtype!=bool or not np.isfinite(v).all():raise ValueError('Wrong saved spectra/flags')
            aa=v[1:3].mean(axis=0);bb=v[3:5].mean(axis=0)
        fresh=sufficient(aa,bb,ids[:,3])
        for key,value in fresh.items():
            if not np.allclose(value,stats[key],rtol=1e-10,atol=1e-15):raise ValueError('Sufficient statistics disagree with published spectra')
        rr=json.loads((root/(name+'.registration.json')).read_text())['records']
        if [(r['repeat'],r['frequency']) for r in rr]!=[(r,f) for r in range(5) for f in range(200)]:raise ValueError('Incomplete frame identity')
        quality={'clip_fraction':float(clips.mean()),'bad_frame_fraction':float(np.mean([r['failed'] for r in rr])),
            'ambiguous_integer_fraction':float(np.mean([r.get('ambiguous_integer_peak',False) for r in rr])),
            'mean_normalized_registration_residual':float(np.mean([r.get('normalized_residual',2) for r in rr])),
            'full_repeat_disagreement':float(np.mean((aa-bb)**2)/2)}
        result=decide(fresh,stats['bootstrap_indices'],quality);sens=[]
        shifted=[]
        for j in range(4):
            with np.load(root/(name+f'.shift{j}.npz'),allow_pickle=False) as z:
                if not np.array_equal(z['ids'],ids):raise ValueError('Shifted identity differs')
                shifted.append(z['values'])
        directions=[(-1,0),(1,0),(0,-1),(0,1)]
        for j,opposite in enumerate((1,0,3,2)):
            ss=sufficient(shifted[j][:2].mean(axis=0),shifted[opposite][2:].mean(axis=0),ids[:,3])
            for key,value in ss.items():
                if not np.allclose(value,stats[f'shift{j}::{key}'],rtol=1e-10,atol=1e-15):raise ValueError('Shift statistic mismatch')
            r=decide(ss,stats['bootstrap_indices'],quality)
            sens.append({'shift_a':list(directions[j]),'shift_b':list(directions[opposite]),'signal_ci_lower':r['signal_ci_lower'],'reliability':r['reliability']})
        result['registration_sensitivity']=sens
        result['conditions']['registration_sensitivity']=all(r['signal_ci_lower']>0 and r['reliability'] is not None and r['reliability']>=.25 for r in sens)
        result['eligible']=all(result['conditions'].values())
        if not equal(result,saved):raise ValueError('Reported metric/condition differs')
        checks+=len(fresh)+len(result)
    if report['eligible']!=all(r['eligible'] for r in report['files'].values()):raise ValueError('Whole-stage decision differs')
    return {'status':'PASS','checks':checks,'scientific_eligible':report['eligible'],'manifest_sha256':expected}


def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out)
    if not out.is_absolute() or out.resolve().is_relative_to(ROOT) or out.resolve().is_relative_to(Path(a.bundle).resolve()) or out.exists():raise ValueError('Output must be new, absolute and outside source/bundle')
    result=verify(a.bundle,a.manifest_sha256);out.mkdir(parents=True,exist_ok=False);write_json(out/'verification.json',result);print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
