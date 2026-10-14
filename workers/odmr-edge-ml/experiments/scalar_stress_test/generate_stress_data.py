#!/usr/bin/env python3
"""Generate and seal fixed scalar stress partitions. No model inference."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, subprocess, sys, time, warnings
from pathlib import Path
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
os.environ.setdefault('OMP_NUM_THREADS', '2')
import numpy as np

CELLS = {
    'clean': (1.5, .030, None, 0., 0.),
    'realistic_anchor': (5., .015, 10., .02, .3),
    'wide_lines': (7., .015, 10., .02, .3),
    'low_snr': (5., .015, 3., .02, .3),
    'negative_slope': (5., .015, 10., -.02, .3),
    'negative_offset': (5., .015, 10., .02, -.3),
    'higher_contrast': (5., .030, 10., .02, .3),
}
PARTITIONS = {'dev': (16, 202610140), 'val': (128, 202610141), 'final': (256, 202610142)}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sim-repo', type=Path, required=True)
    p.add_argument('--original-manifest', type=Path, required=True)
    p.add_argument('--prior-predictions', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--partition', choices=PARTITIONS, required=True)
    a=p.parse_args(); started=time.monotonic()
    if a.out.is_symlink(): raise RuntimeError('Symlinked output root refused')
    a.out.mkdir(parents=True,exist_ok=True)
    dest=a.out/a.partition
    if dest.exists(): raise RuntimeError('Partition already exists; no overwrite')
    ledger=a.out/'generation-ledger.json'
    previous=json.loads(ledger.read_text()) if ledger.exists() else []
    spent=sum(x['seconds'] for x in previous)
    if spent>=1200: raise RuntimeError('Generation cap reached')
    original=json.loads(a.original_manifest.read_text())
    forbidden=set()
    for key in ('train_seeds','val_seeds','test_seeds'):
        forbidden.update(int(x) for x in original[key])
    with np.load(a.prior_predictions, allow_pickle=False) as z:
        forbidden.update(int(x) for x in z['sample_seeds'])
    for part in PARTITIONS:
        manifest=a.out/part/'manifest.json'
        if manifest.exists(): forbidden.update(json.loads(manifest.read_text())['sample_seeds'])
    rows,master=PARTITIONS[a.partition]
    rng=np.random.default_rng(master); seeds=[]
    while len(seeds)<rows:
        seed=int(rng.integers(0,2**31))
        if seed not in forbidden:
            seeds.append(seed); forbidden.add(seed)
    noise_seeds=np.random.SeedSequence([master,811]).generate_state(rows).astype(np.uint64)
    ou_seed=int(np.random.SeedSequence([master,812]).generate_state(1)[0])
    sys.path.insert(0,str(a.sim_repo/'src'))
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
    from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig
    from nv_sensor_sim.pipelines.batch_generate import _generate_split_stochastic
    from nv_sensor_sim.physics.parameters import compute_linewidth
    from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr
    dest.mkdir()
    write_json(dest/'INCOMPLETE.json',{'partition':a.partition,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    base={}; reference_labels=None; rendered={}
    for width in sorted({x[0] for x in CELLS.values()}):
        if spent+time.monotonic()-started>=1200: raise RuntimeError('Generation cap reached')
        p1=(np.pi*width*1e6-1/1.48e-6)*9.9e-6
        if not np.isclose(compute_linewidth(p1),width*1e6): raise RuntimeError('Linewidth inversion mismatch')
        config=SimulationConfig(random_seed=master,use_optics=False,include_nitrogen=False,n_freq_points=100,mw_freq_range_Hz=(2.82e9,2.92e9))
        adapter=SimOSAdapter(config)
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            x,b,params,seed_arr,freq=_generate_split_stochastic(adapter,config,seeds,
                ou_noise_config=OUNoiseConfig(**original['ou_params']),ou_trajectory_seed=ou_seed,
                p1_range_ppm=(p1,p1),b1_gradient_range=tuple(original['test_b1_gradient_range']),
                b_perp_range_T=(0.,0.),bz_range_T=(.005,.015),n_freq_points=100,split_name=a.partition,
                field_sampling='spherical',b_mag_range_T=(20e-6,70e-6))
        if reference_labels is None: reference_labels=b.copy()
        else: np.testing.assert_array_equal(b,reference_labels)
        np.testing.assert_array_equal(seed_arr,np.asarray(seeds))
        if not np.isfinite(x).all(): raise RuntimeError('Nonfinite generated spectra')
        factors=params[:,4,None]*(1+params[:,2,None]*np.linspace(-.5,.5,10))
        widths=width*1e6*np.sqrt(1+getattr(config,'base_saturation_s0',.1)*factors**2)
        rendered[str(width)]={'intrinsic_fwhm_hz':width*1e6,'p1_ppm':p1,
            'rendered_component_fwhm_hz_range':[float(widths.min()),float(widths.max())],
            'aliasing_warning_count':sum('aliasing' in str(w.message).lower() for w in ws)}
        base[width]=(x,b,params,seed_arr,freq)
        print(json.dumps({'event':'rendered','partition':a.partition,'intrinsic_mhz':width,'rows':rows}),flush=True)
    records={}
    for name,(width,contrast,snr,slope,offset_mhz) in CELLS.items():
        x,b,params,seeds_arr,freq=base[width]
        depth=np.max(1-x,axis=1,keepdims=True)
        if np.any(depth<=0): raise RuntimeError('Nonpositive dip depth')
        scaled=1-(1-x)*(contrast/depth)
        shifted=np.array([np.interp(freq-offset_mhz*1e6,freq,row,left=row[0],right=row[-1]) for row in scaled])
        signal=shifted+slope*(freq-(freq[0]+freq[-1])/2)/(freq[-1]-freq[0])
        photons=None if snr is None else photons_for_dip_snr(.30*contrast,snr)
        if photons is not None:
            signal=np.array([apply_shot_noise(row,photons,int(seed)) for row,seed in zip(signal,noise_seeds)])
        path=dest/(name+'.npz')
        np.savez_compressed(path,spectra=signal,truth_vectors_T=b,frequencies_hz=freq,sample_seeds=seeds_arr,
            nuisance_params=params,noise_seeds=noise_seeds)
        records[name]={'file':path.name,'sha256':sha(path),'rows':rows,'intrinsic_fwhm_mhz':width,
            'contrast':contrast,'reference_snr':snr,'slope':slope,'frequency_offset_hz':offset_mhz*1e6,
            'photons_per_point':photons}
    elapsed=time.monotonic()-started
    if spent+elapsed>1200: raise RuntimeError('Generation cap exceeded; partition remains incomplete')
    source_files=['adapters/simos_adapter.py','pipelines/batch_generate.py','physics/lineshape.py','physics/parameters.py','physics/shot_noise.py']
    manifest={'schema':1,'partition':a.partition,'rows_per_cell':rows,'master_seed':master,'ou_seed':ou_seed,
        'sample_seeds':seeds,'prior_seed_overlap':0,'single_orientation':True,'frequency_points':100,
        'frequency_range_hz':[2.82e9,2.92e9],'magnitude_prior_uT':[20,70],'direction_prior':'isotropic',
        'cells':records,'rendered_linewidths':rendered,'noise_reference_fraction':.30,
        'source_parameters':{'ou':original['ou_params'],'b1_gradient_range':original['test_b1_gradient_range']},
        'generator_sha256':sha(__file__),'protocol_sha256':sha(a.protocol),'generation_seconds':elapsed,
        'simulator_commit':subprocess.check_output(['git','-C',str(a.sim_repo),'rev-parse','HEAD'],text=True).strip(),
        'source_sha256':{f:sha(a.sim_repo/'src/nv_sensor_sim'/f) for f in source_files},
        'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'label_or_baseline_summary_disclosed':False}
    write_json(dest/'manifest.json',manifest)
    (dest/'INCOMPLETE.json').unlink()
    for path in dest.iterdir(): path.chmod(0o444)
    dest.chmod(0o555)
    previous.append({'partition':a.partition,'seconds':elapsed,'manifest_sha256':sha(dest/'manifest.json')})
    write_json(ledger,previous)
    print(json.dumps({'event':'sealed','partition':a.partition,'rows_per_cell':rows,'cells':len(records),
        'seconds':elapsed,'manifest_sha256':sha(dest/'manifest.json')}),flush=True)

if __name__=='__main__':main()
