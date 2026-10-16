"""Bounded qualification only. No descendant processes, training or final-data entrypoint."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from experiments.widefield_redesign.access import gate,sha,write_json


def save_array(path,**arrays):
    import numpy as np
    if Path(path).exists():raise FileExistsError(path)
    np.savez_compressed(path,**arrays)


def qualify(a,args):
    import numpy as np
    from experiments.measured_widefield.io import inspect_header,image_map
    from experiments.widefield_redesign.roi import detect,registration_coordinates,register,integrate
    from experiments.widefield_redesign.qualification import sufficient,decide
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    cp=Path(args.custody).resolve()
    if a['inputs'].get(str(cp))!=sha(cp):raise ValueError('Custody not pinned')
    custody=json.loads(cp.read_text())
    if custody.get('status')!='verified' or custody.get('study')!=a['study']:raise ValueError('Wrong custody certificate')
    rng=np.random.default_rng(a['bootstrap_seed']); reports={}; inventory={}; manifest={}
    for name in a['protocol']['files']['eligibility']:
        entry=custody['files'][name]; raw=Path(args.data)/name
        if raw.is_symlink():raise ValueError('Symlink raw input')
        raw=raw.resolve()
        if entry.get('prior_decoding_status') not in ('no_record_of_decoding','header_only_recorded','no_prior_access_found_in_local_audit') or not entry.get('prior_access_limits') or 'prior_byte_exposure' not in entry:raise ValueError('Known decoding or incomplete prior-access evidence')
        if a['inputs'].get(str(raw))!=entry['sha256']:raise ValueError('Raw hash not bound by supervisor')
        header=inspect_header(raw)
        if not header['complete'] or header['header_sha256']!=entry['header_sha256'] or raw.stat().st_size!=entry['bytes']:raise ValueError('Header/size drift')
        if header['frequency_mhz']!=[2700+1.5*i for i in range(200)]:raise ValueError('Unexpected frequency scale')
        image=image_map(raw,header)
        def frame(repeat,frequency):return np.asarray(image[repeat,frequency,256:768,384:896],float)+32768
        template=sum(frame(0,k) for k in list(range(10))+list(range(190,200)))/20
        scale=float(np.median(template))
        if not np.isfinite(template).all() or scale<=0:raise ValueError('Undefined observed normalization')
        rois,detection=detect(template)
        groups=np.asarray([r['y']//128*4+r['x']//128 for r in rois],dtype=np.int64)
        ids=np.asarray([[i,r['y'],r['x'],int(g)] for i,(r,g) in enumerate(zip(rois,groups))],dtype=np.int64).reshape(-1,4)
        masks=np.stack([r['mask'] for r in rois]) if rois else np.empty((0,9,9),bool)
        filename=name+'.geometry.npz';save_array(out/filename,ids=ids,masks=masks,observed_template=template.astype(np.float32),scale=np.asarray(scale))
        inventory[filename]=sha(out/filename)
        if not 32<=len(rois)<=512 or len(np.unique(groups))<8:
            reports[name]={'eligible':False,'reason':'Observation-only ROI count/coverage gate; no reference signals decoded','spots':len(rois),'occupied_superblocks':len(np.unique(groups)),'detection':detection}
            manifest[name]={'raw_sha256':entry['sha256'],'header_sha256':entry['header_sha256'],'prior_byte_exposure':entry['prior_byte_exposure']}
            del image
            continue
        coordinates=registration_coordinates(rois)
        spectra=np.empty((5,len(rois),200)); clipped=np.zeros((5,len(rois),200),bool)
        shifted=np.empty((4,4,len(rois),200));records=[]
        shifts=[(-1,0),(1,0),(0,-1),(0,1)]
        for repeat in range(5):
            for frequency in range(200):
                values=frame(repeat,frequency)
                translation,bad,record=register(values,template,coordinates)
                v,c=integrate(values,rois,translation);spectra[repeat,:,frequency]=v/scale;clipped[repeat,:,frequency]=c
                records.append(dict(record,repeat=repeat,frequency=frequency,failed=bool(bad)))
                if repeat:
                    for j,(dy,dx) in enumerate(shifts):
                        shifted[j,repeat-1,:,frequency]=integrate(values,rois,(translation[0]+dy,translation[1]+dx))[0]/scale
        if not np.isfinite(spectra).all() or not np.isfinite(shifted).all():raise ValueError('Invalid selected spot; no exclusions')
        aa=spectra[1:3].mean(axis=0);bb=spectra[3:5].mean(axis=0);stats=sufficient(aa,bb,groups)
        occupied=np.flatnonzero(stats['counts']);indices=rng.choice(occupied,size=(2000,len(occupied)),replace=True)
        quality={'clip_fraction':float(clipped.mean()),'bad_frame_fraction':float(np.mean([r['failed'] for r in records])),
            'ambiguous_integer_fraction':float(np.mean([r.get('ambiguous_integer_peak',False) for r in records])),
            'mean_normalized_registration_residual':float(np.mean([r.get('normalized_residual',2) for r in records])),
            'full_repeat_disagreement':float(np.mean((aa-bb)**2)/2)}
        report=decide(stats,indices,quality);sensitivity=[];stats_saved={k:v for k,v in stats.items()};stats_saved['bootstrap_indices']=indices
        for j,opposite in enumerate((1,0,3,2)):
            sa=shifted[j,:2].mean(axis=0);sb=shifted[opposite,2:].mean(axis=0)
            ss=sufficient(sa,sb,groups);sr=decide(ss,indices,quality)
            sensitivity.append({'shift_a':list(shifts[j]),'shift_b':list(shifts[opposite]),'signal_ci_lower':sr['signal_ci_lower'],'reliability':sr['reliability']})
            for key,value in ss.items():stats_saved[f'shift{j}::{key}']=value
        sensitivity_pass=all(r['signal_ci_lower']>0 and r['reliability'] is not None and r['reliability']>=.25 for r in sensitivity)
        report['registration_sensitivity']=sensitivity;report['conditions']['registration_sensitivity']=sensitivity_pass
        report['eligible']=all(report['conditions'].values());reports[name]=report
        for suffix,arrays in [('spectra',{'values':spectra,'clipped':clipped,'ids':ids}),('statistics',stats_saved)]:
            filename=name+'.'+suffix+'.npz';save_array(out/filename,**arrays);inventory[filename]=sha(out/filename)
        for j in range(4):
            filename=name+f'.shift{j}.npz';save_array(out/filename,values=shifted[j],ids=ids);inventory[filename]=sha(out/filename)
        filename=name+'.registration.json';write_json(out/filename,{'records':records,'detection':detection});inventory[filename]=sha(out/filename)
        manifest[name]={'raw_sha256':entry['sha256'],'header_sha256':entry['header_sha256'],'prior_byte_exposure':entry['prior_byte_exposure'],'current_mA':entry['current_mA'],'exposure_ms':header['cards']['EXPOSURE']}
        del image
    report={'study':a['study'],'files':reports,'eligible':all(r['eligible'] for r in reports.values()),'protocol_sha256':a['protocol_sha256'],'scope':'Fixed spot/contrast rule, two training acquisitions, conditional spatial uncertainty; no field truth or general no-signal claim'}
    write_json(out/'report.json',report);inventory['report.json']=sha(out/'report.json')
    write_json(out/'verification-manifest.json',{'files':inventory,'acquisitions':manifest,'bootstrap_seed':a['bootstrap_seed'],'protocol_sha256':a['protocol_sha256'],'source_files':a['source_files']})
    print(json.dumps(report,sort_keys=True));return 0 if report['eligible'] else 2


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['fixtures','qualify']);p.add_argument('--approval',required=True);p.add_argument('--out',required=True);p.add_argument('--data');p.add_argument('--custody');args=p.parse_args()
    output=Path(args.out)
    if not output.is_absolute() or output.resolve().is_relative_to(ROOT) or output.exists():raise ValueError('Output must be new, absolute and outside source')
    a=gate(args.approval,args.command)
    if args.command=='fixtures':
        import os
        os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
        import pytest
        return pytest.main(['-q',str(Path(__file__).with_name('test_redesign.py')),'--basetemp',str(Path(args.out)/'pytest')])
    return qualify(a,args)

if __name__=='__main__':raise SystemExit(main())
