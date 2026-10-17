"""Verify public saved evidence only. No downloads, fitting, GPU, or hardware."""
from pathlib import Path
import csv,hashlib,json,struct,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parent

def check(condition,message):
    if not condition: raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def read(path):return json.loads(path.read_text())
def verify_inventory(root):
    manifest=read(root/'SOURCE_MAP.json')
    for entry in manifest['files']:
        path=(root/entry['public_relative_path']).resolve()
        check(path.is_relative_to(root.resolve()),'Inventory path escape')
        check(sha(path)==entry['public_sha256'],'Publication hash: '+entry['public_relative_path'])
    return len(manifest['files'])
def compare_quantum(cpu,gpu,cfg):
    for key in ['detuning_mhz','delays_us','phases_rad']:
        check(np.array_equal(cpu[key],gpu[key]),'Saved CPU/GPU labels differ')
    n=cfg['configurations'];tol=cfg['gates']
    for data in [cpu,gpu]:
        rho=data['density'];p=data['probabilities']
        check(rho.shape==(n,4,64,4,4) and p.shape==(n,4,64),'Quantum shape')
        check(rho.dtype==np.dtype('complex128'),'Density precision')
        check(np.all(np.isfinite(rho)) and np.all(np.isfinite(p)),'Nonfinite quantum data')
        dagger=rho.conj().swapaxes(-1,-2)
        check(np.max(np.abs(np.trace(rho,axis1=-2,axis2=-1)-1))<=tol['trace_atol'],'Trace invariant')
        check(np.max(np.abs(rho-dagger))<=tol['hermiticity_atol'],'Hermiticity invariant')
        check(np.linalg.eigvalsh((rho+dagger)/2).min()>=tol['minimum_eigenvalue'],'Positivity invariant')
        check(np.max(np.abs(np.trace(rho@rho,axis1=-2,axis2=-1)-.5))<=tol['purity_atol'],'Purity invariant')
        check(p.min()>=-tol['probability_atol'] and p.max()<=1+tol['probability_atol'],'Probability bounds')
        check(np.max(np.abs(p-np.trace(rho[...,:2,:2],axis1=-2,axis2=-1).real))<=1e-13,'Stored probability versus density')
    pe=float(np.max(np.abs(cpu['probabilities']-gpu['probabilities'])))
    de=float(np.max(np.abs(cpu['density']-gpu['density'])))
    check(pe<=tol['probability_atol'],'Probability tolerance')
    check(de<=tol['density_atol'],'Density tolerance')
    return pe,de

def verify_integer(inputs,indices,scores,rom):
    check(inputs.ndim==2 and inputs.shape[1]==128,'Input shape')
    check(len(inputs)==len(indices)==len(scores),'Integer lengths')
    for row,index,score in zip(inputs,indices,scores):
        distances=np.sum((rom.astype(np.int64)-row.astype(np.int64))**2,axis=1,dtype=np.int64)
        k=int(np.argmin(distances))
        check(k==int(index) and int(distances[k])==int(score),'Full-width integer result')
    return len(inputs)

def main():
    count=verify_inventory(ROOT)
    nv=ROOT/'nv_scaling';cfg=read(nv/'protocol_final.json')
    data=[]
    for folder in ['final_cpu_linux','final_gpu']:
        directory=nv/'artifacts'/folder;r=read(directory/'receipt.json')
        for name,digest in r['artifact_sha256'].items():check(sha(directory/name)==digest,'NPZ receipt hash')
        check(r['status']=='passed','Recorded numerical acceptance')
        with np.load(directory/'quantum_dataset.npz',allow_pickle=False) as z:data.append({k:z[k] for k in z.files})
    pe,de=compare_quantum(*data,cfg)
    pack=nv/'artifacts/final_gpu/board_vectors'
    inputs=np.fromfile(pack/'inputs_i16.bin',dtype='<i2').reshape(-1,128)
    indices=np.fromfile(pack/'expected_indices_u16.bin',dtype='<u2');scores=np.fromfile(pack/'expected_scores_u64.bin',dtype='<u8')
    rom=np.fromfile(nv/'frozen/templates_i16le.bin',dtype='<i2').reshape(121,128)
    n=verify_integer(inputs,indices,scores,rom)
    with (ROOT/'board/execution/nv-replay.csv').open() as f:rows=list(csv.DictReader(f))
    check(len(rows)==n,'Board row count')
    for i,row in enumerate(rows):
        check(int(row['record'])==i and int(row['match'])==1 and int(row['error'])==0,'Board record status')
        check(int(row['result_hex'],16)==int(indices[i])==int(row['expected_hex'],16),'Board full index')
        check(int(row['score_hex'],16)==int(scores[i])==int(row['expected_score_hex'],16),'Board full score')
        check(int(row['completed_after'])==int(row['completed_before'])+1,'Board counter')
        check(int(row['fabric_cycles'])==23479,'Board cycles')
        if i:check(int(row['completed_before'])==int(rows[i-1]['completed_after']),'Board counter continuity')
    checks=[['measured_readout/verify_saved.py'],['measured_readout/processor_readout/verify_saved_processor.py','--pack-only'],['demo/show_evidence.py','--root',str(ROOT),'--manifest','demo/evidence_manifest.json']]
    for args in checks:subprocess.run([sys.executable,str(ROOT/args[0]),*args[1:]],check=True)
    print(json.dumps({'status':'PASS','publication_files':count,'quantum_probabilities':cfg['configurations']*256,'max_probability_error':pe,'max_density_error':de,'exact_nv_integer_records':n,'exact_saved_board_records':len(rows),'scope':'Saved evidence only; no new scientific or hardware run'},indent=2))
if __name__=='__main__':main()
