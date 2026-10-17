#!/usr/bin/env python3
"""Independent saved-artifact acceptance; no CUDA-Q, GPU, or board operations."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

EXPECTED_REGISTRATION_SHA = '096a1f08ca40840502119a4e276a6e45fcafc9f509c1c724744915f12db447c8'
EXPECTED_ROM_SHA = 'b4c8515c0c4842d613a58fc7a23e528c956343bf86ba515cda5715ca57110f8f'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''): digest.update(data)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def checked_path(root, name):
    require(isinstance(name,str) and not Path(name).is_absolute(),'Expected relative registered path')
    path=(root/name).resolve(strict=True)
    require(path.is_relative_to(root.resolve()),'Registered path escapes root')
    require(path.is_file(),'Registered path must be a file')
    return path


def metrics(rho):
    dagger=rho.conj().swapaxes(-2,-1)
    return {'trace_error':float(np.max(np.abs(np.trace(rho,axis1=-2,axis2=-1)-1))),
            'hermiticity_error':float(np.max(np.abs(rho-dagger))),
            'minimum_eigenvalue':float(np.min(np.linalg.eigvalsh((rho+dagger)/2))),
            'purity_error':float(np.max(np.abs(np.trace(rho@rho,axis1=-2,axis2=-1)-.5)))}


def accept(root):
    root=root.resolve(strict=True)
    registration_path=root/'REGISTRATION.json'
    require(sha(registration_path)==EXPECTED_REGISTRATION_SHA,'Registration bytes differ from pre-final freeze')
    registration=read_json(registration_path)
    for name,expected in registration['files'].items():
        require(sha(checked_path(root,name))==expected,f'Registered source/protocol changed: {name}')
    protocol_path=root/'protocol_final.json'
    protocol=read_json(protocol_path)
    require(sha(protocol_path)==registration['protocol_sha256'],'Final protocol hash mismatch')
    require(protocol['split']=='final','Expected registered final split')
    n=protocol['configurations']; phases=4; delays=64
    require(protocol['delay_points']==delays and len(protocol['phases_rad'])==phases,'Frozen FPGA acquisition changed')
    expected_records=n*len(protocol['shots_per_point'])*protocol['noise_realizations']
    tol=protocol['gates']
    receipts={}; datasets={}; physical={}; artifact_hashes={}
    for backend,dirname in [('cpu','final_cpu_linux'),('cudaq','final_gpu')]:
        directory=root/'artifacts'/dirname
        receipt=read_json(directory/'receipt.json')
        require(receipt['status']=='passed' and receipt['backend']==backend,f'{backend} receipt did not pass')
        require(receipt['protocol_sha256']==sha(protocol_path) and receipt['protocol']==protocol,f'{backend} protocol mismatch')
        require(receipt['gpu_generated_fraction']==(1. if backend=='cudaq' else 0.),'Backend provenance mismatch')
        require(receipt['independent_configurations']==n and receipt['quantum_probability_count']==n*phases*delays,'Dataset counts mismatch')
        require(receipt['board_record_count']==expected_records,'Board count mismatch')
        require(len(receipt['runs'])==1+protocol['warm_repetitions'],'Generation repetition count mismatch')
        for run in receipt['runs']:
            require(np.isfinite(run['quantum_seconds']) and run['quantum_seconds']>0,'Invalid quantum timing')
        for name,expected in receipt['source_sha256'].items():
            require(name in registration['files'] and expected==registration['files'][name],f'{backend} source hash mismatch: {name}')
        require(set(receipt['source_sha256'])=={name for name in registration['files'] if name.endswith('.py')},'Incomplete Python provenance')
        require(set(receipt['artifact_sha256'])=={'quantum_dataset.npz','detector_counts.npz'},'Unexpected NPZ artifact contract')
        artifact_hashes[backend]={}
        for name,expected in receipt['artifact_sha256'].items():
            actual=sha(directory/name)
            require(actual==expected,f'{backend} NPZ hash mismatch: {name}')
            artifact_hashes[backend][name]=actual
        # Hashes pass before any array is consumed. No pickle payloads are permitted.
        with np.load(directory/'quantum_dataset.npz',allow_pickle=False) as archive:
            require(set(archive.files)=={'detuning_mhz','delays_us','phases_rad','density','probabilities'},'Unexpected quantum array contract')
            data={key:archive[key] for key in archive.files}
        require(data['density'].shape==(n,phases,delays,4,4),'Density shape mismatch')
        require(data['density'].dtype==np.dtype('complex128'),'Density precision mismatch')
        require(data['probabilities'].shape==(n,phases,delays),'Probability shape mismatch')
        for name,array in data.items(): require(np.all(np.isfinite(array)),f'Nonfinite {backend} {name}')
        expected_detuning=np.random.default_rng(protocol['parameter_seed']).uniform(*protocol['detuning_range_mhz'],n)
        require(np.array_equal(data['detuning_mhz'],expected_detuning),'Fresh parameter seed does not reproduce labels')
        require(np.array_equal(data['delays_us'],np.linspace(0,protocol['maximum_delay_us'],delays)),'Delay labels mismatch')
        require(np.array_equal(data['phases_rad'],np.array(protocol['phases_rad'])),'Phase labels mismatch')
        reconstructed=np.trace(data['density'][...,:2,:2],axis1=-2,axis2=-1).real
        require(np.max(np.abs(reconstructed-data['probabilities']))<=1e-13,'Stored probability differs from stored density')
        require(data['probabilities'].min()>=-tol['probability_atol'] and data['probabilities'].max()<=1+tol['probability_atol'],'Probability range failed')
        physical[backend]=metrics(data['density'])
        m=physical[backend]
        require(m['trace_error']<=tol['trace_atol'],'Trace invariant failed')
        require(m['hermiticity_error']<=tol['hermiticity_atol'],'Hermiticity invariant failed')
        require(m['minimum_eigenvalue']>=tol['minimum_eigenvalue'],'Positivity invariant failed')
        require(m['purity_error']<=tol['purity_atol'],'Purity invariant failed')
        receipts[backend]=receipt; datasets[backend]=data
    cpu=datasets['cpu']; gpu=datasets['cudaq']
    max_probability_error=float(np.max(np.abs(cpu['probabilities']-gpu['probabilities'])))
    max_density_error=float(np.max(np.abs(cpu['density']-gpu['density'])))
    require(max_probability_error<=tol['probability_atol'],'Full probability comparison exceeds registered tolerance')
    require(max_density_error<=tol['density_atol'],'Full density comparison exceeds registered tolerance')
    require(receipts['cpu']['platform']==receipts['cudaq']['platform'],'CPU/GPU platforms differ')
    q=[]
    for d in [cpu,gpu]:
        p=d['probabilities']; feature=np.concatenate([p[:,0]-p[:,2],p[:,1]-p[:,3]],axis=1)
        q.append(np.clip(np.rint(feature*16384),-32768,32767).astype(np.int16))
    q_error=int(np.max(np.abs(q[0].astype(np.int32)-q[1].astype(np.int32))))
    require(q_error<=1,'Noiseless Q14 difference exceeds one LSB')
    pack=root/'artifacts/final_gpu/board_vectors'
    manifest=read_json(pack/'manifest.json')
    require(manifest['count']==expected_records and len(manifest['cases'])==expected_records,'Pack count mismatch')
    require(manifest['abi']['rom_sha256']==EXPECTED_ROM_SHA,'Pack ROM identity changed')
    expected_sizes={'inputs_i16.bin':expected_records*128*2,'expected_indices_u16.bin':expected_records*2,'expected_scores_u64.bin':expected_records*8}
    require(set(manifest['files'])==set(expected_sizes),'Unexpected board binary contract')
    for name,size in expected_sizes.items():
        require((pack/name).stat().st_size==size==manifest['files'][name]['bytes'],f'Pack byte length mismatch: {name}')
        require(sha(pack/name)==manifest['files'][name]['sha256'],f'Pack hash mismatch: {name}')
    inputs=np.fromfile(pack/'inputs_i16.bin',dtype='<i2').reshape(expected_records,128)
    indices=np.fromfile(pack/'expected_indices_u16.bin',dtype='<u2')
    scores=np.fromfile(pack/'expected_scores_u64.bin',dtype='<u8')
    rom_path=root/'frozen/templates_i16le.bin'
    require(sha(rom_path)==EXPECTED_ROM_SHA,'ROM bytes changed')
    rom=np.fromfile(rom_path,dtype='<i2').reshape(121,128).astype(np.int64)
    with np.load(root/'artifacts/final_gpu/detector_counts.npz',allow_pickle=False) as archive:
        require(archive.files==['counts'],'Unexpected detector array contract')
        counts=archive['counts']
    require(counts.shape==(expected_records,phases,delays) and counts.dtype==np.dtype('int32') and counts.min()>=0,'Detector count shape/type/range failed')
    expected_case=0
    for config_id in range(n):
        for shots in protocol['shots_per_point']:
            for replicate in range(protocol['noise_realizations']):
                case=manifest['cases'][expected_case]
                require(case['id']==f'final-{config_id:05d}-r{shots}-n{replicate}','Case identity/order mismatch')
                require(case['configuration']==config_id and case['shots_per_point']==shots and case['replicate']==replicate,'Case metadata mismatch')
                count=counts[expected_case].astype(float)
                scale=shots*(protocol['photons_bright']-protocol['photons_dark'])
                raw=np.rint(np.concatenate([count[0]-count[2],count[1]-count[3]])/scale*16384)
                encoded=np.clip(raw,-32768,32767).astype(np.int16)
                require(np.array_equal(encoded,inputs[expected_case]),'Count-to-FPGA encoding mismatch')
                clipping=int(np.count_nonzero((raw<-32768)|(raw>32767)))
                require(clipping==case['clipped_features'],'Clipping count mismatch')
                distances=np.sum((rom-inputs[expected_case].astype(np.int64))**2,axis=1,dtype=np.int64)
                index=int(np.argmin(distances))
                require(index==int(indices[expected_case]) and int(distances[index])==int(scores[expected_case]),'Full integer result mismatch')
                expected_case+=1
    c_path=root/'artifacts/final_gpu/c_reference_verification.json'
    c=read_json(c_path)
    require(c['status']=='passed' and c['records']==expected_records and c['all_uint16_indices_exact'] is True and c['all_uint64_scores_exact'] is True,'Frozen C verification missing or failed')
    require(c['rom_sha256']==EXPECTED_ROM_SHA,'Frozen C verification ROM mismatch')
    return {'status':'passed','scope':'Saved synthetic data and host integer references; no board execution.',
            'registration_sha256':EXPECTED_REGISTRATION_SHA,'protocol_sha256':sha(protocol_path),
            'registered_source_sha256':registration['files'],
            'receipt_sha256':{b:sha(root/'artifacts'/d/'receipt.json') for b,d in [('cpu','final_cpu_linux'),('cudaq','final_gpu')]},
            'npz_sha256':artifact_hashes,'independent_configurations':n,'quantum_probability_count':n*phases*delays,
            'max_probability_error':max_probability_error,'max_density_error':max_density_error,
            'physical_metrics':physical,'noiseless_max_q14_difference':q_error,'board_record_count':expected_records,
            'manifest_sha256':sha(pack/'manifest.json'),'board_files':manifest['files'],
            'c_verification_sha256':sha(c_path),'all_full_width_integer_results_exact':True,
            'maximum_expected_score':int(scores.max()),'clipped_features':sum(c['clipped_features'] for c in manifest['cases'])}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nv-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    try:
        result=accept(a.nv_root)
    except Exception as exc:
        result={'status':'failed','error':str(exc)}
        a.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),file=sys.stderr)
        return 1
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','quantum_probability_count','max_probability_error','max_density_error','board_record_count','manifest_sha256']}))
    return 0


if __name__=='__main__': raise SystemExit(main())
