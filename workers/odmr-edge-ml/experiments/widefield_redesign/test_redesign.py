"""Manufactured checks only. This file has not been executed during preparation."""
import json
import numpy as np
import pytest
from experiments.widefield_redesign.access import validate_protocol,gate,sha,write_json
from experiments.widefield_redesign.operators import spectral_contrast
from experiments.widefield_redesign.qualification import sufficient,decide
from experiments.widefield_redesign.roi import register,registration_coordinates,integrate
from experiments.widefield_redesign.verify_saved import verify


def test_linear_background_is_removed():
    x=np.linspace(2.,7.,200)
    assert np.max(np.abs(spectral_contrast(x)))<1e-12


def manufactured():
    f=2700+1.5*np.arange(200);line=16**2/(4*(f-2850)**2+16**2)
    v=1-np.linspace(.01,.1,32)[:,None]*line
    groups=np.arange(32)%8;stats=sufficient(v,v,groups)
    indices=np.tile(np.arange(8),(2000,1))
    quality={'clip_fraction':0.,'bad_frame_fraction':0.}
    return stats,indices,quality


def test_identical_reproducible_contrast_passes():
    stats,indices,quality=manufactured();assert decide(stats,indices,quality)['eligible']


def test_mean_spectrum_has_no_spatial_signal():
    v=np.ones((32,200));stats=sufficient(v,v,np.arange(32)%8)
    result=decide(stats,np.tile(np.arange(8),(2000,1)),{'clip_fraction':0.,'bad_frame_fraction':0.})
    assert not result['eligible'] and result['reliability'] is None


def test_registration_flags_cannot_be_discarded():
    stats,indices,q=manufactured();q['bad_frame_fraction']=.02
    assert not decide(stats,indices,q)['eligible']


def test_half_pixel_registration_uses_brightness():
    from scipy.ndimage import shift
    yy,xx=np.mgrid[:512,:512];template=np.full((512,512),100.)
    rois=[]
    for cy,cx in [(100,100),(200,250),(350,150),(400,400)]:
        template+=200*np.exp(-((yy-cy)**2+(xx-cx)**2)/4)
        rois.append({'y':cy,'x':cx,'mask':np.ones((9,9),bool)})
    moved=shift(template,(.5,-.5),order=1,mode='nearest')
    delta,bad,record=register(moved,template,registration_coordinates(rois))
    assert not bad
    assert np.max(np.abs(np.asarray(delta)-[.5,-.5]))<.25
    assert record['ambiguous_integer_peak']


def test_outside_declared_drift_is_flagged():
    from scipy.ndimage import shift
    yy,xx=np.mgrid[:512,:512];template=100+200*np.exp(-((yy-200)**2+(xx-250)**2)/4)
    rois=[{'y':200,'x':250,'mask':np.ones((9,9),bool)}]
    _,bad,_=register(shift(template,(3.,0.),order=1),template,registration_coordinates(rois))
    assert bad


def test_unfrozen_or_changed_protocol_rejected(tmp_path):
    from pathlib import Path
    original=json.loads(Path(__file__).with_name('protocol.json').read_text());original['status']='FROZEN'
    path=tmp_path/'protocol.json';path.write_text(json.dumps(original));validate_protocol(path)
    original['roi']['minimum_spots_per_file']=1;path.write_text(json.dumps(original))
    with pytest.raises(ValueError):validate_protocol(path)


def test_environment_alone_is_not_authorization(tmp_path,monkeypatch):
    p=tmp_path/'approval.json';p.write_text(json.dumps({'status':'approved','study':'widefield-redesign-2026-10-15','phases':['qualify'],'allowed_run_ids':['spoof']}))
    monkeypatch.setenv('TYCHON_NUMERICAL_APPROVAL_SHA256',sha(p));monkeypatch.setenv('TYCHON_NUMERICAL_RUN_ID','spoof');monkeypatch.delenv('TYCHON_ACTIVE_NUMERICAL_CONTEXT',raising=False)
    with pytest.raises(ValueError):gate(p,'qualify')


def test_saved_geometry_stop_roundtrip_and_tamper(tmp_path):
    files={};reports={}
    for name in ('f1.fits','f4.fits'):
        p=tmp_path/(name+'.geometry.npz');np.savez_compressed(p,ids=np.empty((0,4),np.int64),masks=np.empty((0,9,9),bool));files[p.name]=sha(p)
        reports[name]={'eligible':False,'reason':'Insufficient geometry','spots':0,'occupied_superblocks':0}
    write_json(tmp_path/'report.json',{'files':reports,'eligible':False});files['report.json']=sha(tmp_path/'report.json')
    write_json(tmp_path/'verification-manifest.json',{'files':files});digest=sha(tmp_path/'verification-manifest.json')
    assert verify(tmp_path,digest)['status']=='PASS'
    with (tmp_path/'f1.fits.geometry.npz').open('ab') as f:f.write(b'tamper')
    with pytest.raises(ValueError):verify(tmp_path,digest)


def test_fixed_roi_rule_finds_manufactured_sparse_spots():
    from experiments.widefield_redesign.roi import detect
    yy,xx=np.mgrid[:512,:512]
    template=100+3*np.sin(.9*xx)+2*np.cos(.7*yy)
    for cy in range(63,448,64):
        for cx in range(63,448,64):
            template+=60*np.exp(-((yy-cy)**2+(xx-cx)**2)/(2*1.2**2))
    rois,record=detect(template)
    assert 32<=len(rois)<=512
    assert len({r['y']//128*4+r['x']//128 for r in rois})>=8
    assert all(r['mask'].shape==(9,9) for r in rois)


def test_bootstrap_recenters_each_resampled_region_set():
    from experiments.widefield_redesign.qualification import covariance
    f=np.arange(200); a=(1+np.arange(32)[:,None]*np.cos(f/10)/100)
    b=a+np.sin(np.arange(32)[:,None]+f/12)/1000
    groups=np.arange(32)%8; stats=sufficient(a,b,groups)
    selection=np.asarray([0,0,1,3,3,4,6,7])
    s,n=covariance(stats,selection)
    aa=np.concatenate([spectral_contrast(a[groups==g]) for g in selection]);bb=np.concatenate([spectral_contrast(b[groups==g]) for g in selection])
    aa-=aa.mean(axis=0);bb-=bb.mean(axis=0)
    assert np.isclose(s,np.mean(aa*bb),atol=1e-15)
    assert np.isclose(n,np.mean((aa-bb)**2)/2,atol=1e-15)


def positive_saved_bundle(root):
    from experiments.widefield_redesign.qualification import sufficient
    files={};reports={}
    f=2700+1.5*np.arange(200);line=16**2/(4*(f-2850)**2+16**2)
    v=1-np.linspace(.01,.1,32)[:,None]*line
    ids=np.asarray([[i,32+128*((i%8)//4)+16*(i//16),32+128*((i%8)%4)+16*((i//8)%2),i%8] for i in range(32)],np.int64)
    indices=np.tile(np.arange(8),(2000,1));directions=[(-1,0),(1,0),(0,-1),(0,1)]
    quality={'clip_fraction':0.,'bad_frame_fraction':0.,'ambiguous_integer_fraction':0.,'mean_normalized_registration_residual':0.,'full_repeat_disagreement':0.}
    for name in ('f1.fits','f4.fits'):
        stats=sufficient(v,v,ids[:,3]);result=decide(stats,indices,quality)
        sensitivity=[{'shift_a':list(directions[j]),'shift_b':list(directions[o]),'signal_ci_lower':result['signal_ci_lower'],'reliability':result['reliability']} for j,o in enumerate((1,0,3,2))]
        result['registration_sensitivity']=sensitivity;result['conditions']['registration_sensitivity']=True;result['eligible']=all(result['conditions'].values());reports[name]=result
        saved=dict(stats,bootstrap_indices=indices)
        for j in range(4):
            for k,value in stats.items():saved[f'shift{j}::{k}']=value
        payloads=[('geometry',{'ids':ids,'masks':np.ones((32,9,9),bool)}),
                  ('spectra',{'ids':ids,'values':np.stack([v]*5),'clipped':np.zeros((5,32,200),bool)}),('statistics',saved)]
        payloads +=[(f'shift{j}',{'ids':ids,'values':np.stack([v]*4)}) for j in range(4)]
        for suffix,arrays in payloads:
            p=root/(name+'.'+suffix+'.npz');np.savez_compressed(p,**arrays);files[p.name]=sha(p)
        records=[{'repeat':r,'frequency':f,'failed':False,'correlation':1.,'margin':.5,'ambiguous_integer_peak':False,'normalized_residual':0.,'best_shift':[0,0],'refined_shift':[0.,0.]} for r in range(5) for f in range(200)]
        p=root/(name+'.registration.json');write_json(p,{'records':records});files[p.name]=sha(p)
    p=root/'report.json';write_json(p,{'files':reports,'eligible':all(r['eligible'] for r in reports.values())});files[p.name]=sha(p)
    write_json(root/'verification-manifest.json',{'files':files})
    return sha(root/'verification-manifest.json')


def test_positive_saved_spectrum_roundtrip_all_shifts(tmp_path):
    digest=positive_saved_bundle(tmp_path)
    result=verify(tmp_path,digest)
    assert result['status']=='PASS' and result['scientific_eligible']


def test_consistently_hashed_mismatched_spot_ids_rejected(tmp_path):
    positive_saved_bundle(tmp_path)
    p=tmp_path/'f1.fits.spectra.npz'
    with np.load(p,allow_pickle=False) as z:values={k:z[k] for k in z.files}
    values['ids']=values['ids'].copy();values['ids'][0,1]+=1
    np.savez_compressed(p,**values)
    mp=tmp_path/'verification-manifest.json';m=json.loads(mp.read_text());m['files'][p.name]=sha(p);mp.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='spectra/flags'):verify(tmp_path,sha(mp))
