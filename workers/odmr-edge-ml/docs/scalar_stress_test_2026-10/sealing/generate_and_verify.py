#!/usr/bin/env python3
"""Metadata-only generator wrapper and private sealing verification."""
import argparse,datetime,hashlib,json,os,stat,subprocess,time
from pathlib import Path
import numpy as np
ROOT=Path("<path>")
SEAL=ROOT/"sealing"
PYTHON="<path>"
SIM=Path("<path>")
ORIGINAL=Path("<data-root>/production_50k_v2_aic/manifest.json")
PRIOR=Path("<path>")
PROTOCOL_SHA="39cde896ef333889806d176e3e162af645608de9c02a59310b9884925f746072"
GENERATOR_SHA="44ff2d0fca79fb1ca32fa6124006eb788fd8d3e735bb2aa1b417cfbb24a590e4"
ROWS={"dev":16,"val":128,"final":256}
CELLS=["clean","realistic_anchor","wide_lines","low_snr","negative_slope","negative_offset","higher_contrast"]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+"\n")
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
 p=argparse.ArgumentParser();p.add_argument("--partition",choices=ROWS,required=True);a=p.parse_args()
 SEAL.mkdir(exist_ok=True)
 attempts=SEAL/"attempts.json";history=json.loads(attempts.read_text()) if attempts.exists() else []
 assert not any(x["partition"]==a.partition for x in history),"Prior attempt exists; no silent retry or overwrite"
 assert sha(ROOT/"PROTOCOL.md")==PROTOCOL_SHA and sha(ROOT/"generate_stress_data.py")==GENERATOR_SHA
 prior_elapsed=sum(x.get("elapsed_seconds",0) for x in history)
 remaining=1200-prior_elapsed
 if remaining<=0:raise RuntimeError("Cumulative generation cap reached")
 command=[PYTHON,str(ROOT/"generate_stress_data.py"),"--sim-repo",str(SIM),"--original-manifest",str(ORIGINAL),
  "--prior-predictions",str(PRIOR),"--protocol",str(ROOT/"PROTOCOL.md"),"--out",str(ROOT/"data"),"--partition",a.partition]
 receipt={"partition":a.partition,"command":command,"started_utc":utc(),"status":"running"}
 history.append(receipt);dump(attempts,history)
 log=SEAL/(a.partition+"-generation.log")
 start=time.monotonic()
 try:
  with log.open("x") as f:
   proc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=remaining,env={**os.environ,"OPENBLAS_NUM_THREADS":"2","OMP_NUM_THREADS":"2"})
  receipt["returncode"]=proc.returncode
  receipt["status"]="generated" if proc.returncode==0 else "generation_failed"
 except subprocess.TimeoutExpired:
  receipt["status"]="timeout";receipt["returncode"]=None
 finally:
  receipt["elapsed_seconds"]=time.monotonic()-start;receipt["ended_utc"]=utc();receipt["log_path"]=str(log);dump(attempts,history)
 if receipt["status"]!="generated":
  print(json.dumps({"partition":a.partition,"failure":receipt["status"],"seconds":receipt["elapsed_seconds"],"log":str(log)}),flush=True)
  raise SystemExit(1)
 verification_start=time.monotonic()
 dest=ROOT/"data"/a.partition;manifest_path=dest/"manifest.json";manifest=json.loads(manifest_path.read_text())
 assert manifest["protocol_sha256"]==PROTOCOL_SHA and manifest["generator_sha256"]==GENERATOR_SHA
 assert manifest["rows_per_cell"]==ROWS[a.partition] and set(manifest["cells"])==set(CELLS)
 assert not (dest/"INCOMPLETE.json").exists()
 original=json.loads(ORIGINAL.read_text())
 forbidden=set()
 for key in ["train_seeds","val_seeds","test_seeds"]:forbidden.update(map(int,original[key]))
 with np.load(PRIOR,allow_pickle=False) as z:prior_seeds=z["sample_seeds"]
 forbidden.update(map(int,prior_seeds))
 for other in ROWS:
  other_manifest=ROOT/"data"/other/"manifest.json"
  if other!=a.partition and other_manifest.exists():forbidden.update(json.loads(other_manifest.read_text())["sample_seeds"])
 expected_seeds=np.asarray(manifest["sample_seeds"])
 assert len(expected_seeds)==ROWS[a.partition] and len(set(expected_seeds.tolist()))==len(expected_seeds)
 assert not (set(map(int,expected_seeds))&forbidden)
 shapes={"spectra":(ROWS[a.partition],100),"truth_vectors_T":(ROWS[a.partition],3),"frequencies_hz":(100,),
         "sample_seeds":(ROWS[a.partition],),"nuisance_params":(ROWS[a.partition],5),"noise_seeds":(ROWS[a.partition],)}
 first=None;file_records=[]
 for cell in CELLS:
  path=dest/manifest["cells"][cell]["file"]
  assert path.parent==dest and not path.is_symlink()
  file_sha=sha(path);assert file_sha==manifest["cells"][cell]["sha256"]
  assert stat.S_IMODE(path.stat().st_mode)&0o222==0
  with np.load(path,allow_pickle=False) as z:
   assert set(z.files)==set(shapes)
   arrays={k:z[k] for k in shapes}
   for k,value in arrays.items():
    assert value.shape==shapes[k],(cell,k,value.shape)
    assert np.isfinite(value).all(),(cell,k)
   np.testing.assert_array_equal(arrays["sample_seeds"],expected_seeds)
   np.testing.assert_allclose(arrays["frequencies_hz"],np.linspace(2.82e9,2.92e9,100),rtol=0,atol=0)
   if first is None:first={k:v.copy() for k,v in arrays.items() if k!="spectra"}
   else:
    for k in ["truth_vectors_T","frequencies_hz","sample_seeds","noise_seeds"]:
     np.testing.assert_array_equal(arrays[k],first[k])
    np.testing.assert_array_equal(arrays["nuisance_params"][:,1:],first["nuisance_params"][:,1:])
  file_records.append({"path":str(path),"sha256":file_sha,"rows":ROWS[a.partition],"array_count":len(shapes),"shape_failures":0,"finiteness_failures":0,"write_bit_count":0})
 assert stat.S_IMODE(manifest_path.stat().st_mode)&0o222==0
 assert stat.S_IMODE(dest.stat().st_mode)&0o222==0
 assert set(p.name for p in dest.iterdir())==set([x+".npz" for x in CELLS]+["manifest.json"])
 result={"partition":a.partition,"path":str(dest),"rows_per_cell":ROWS[a.partition],"cell_count":len(CELLS),
  "total_cell_rows":ROWS[a.partition]*len(CELLS),"unique_sample_seed_count":len(expected_seeds),"seed_overlap_count":0,
  "cross_cell_vector_mismatch_count":0,"cross_cell_nuisance_trajectory_mismatch_count":0,"cross_cell_noise_seed_mismatch_count":0,
  "writable_file_or_directory_count":0,"failures":[],"manifest_sha256":sha(manifest_path),
  "protocol_sha256":PROTOCOL_SHA,"generator_sha256":GENERATOR_SHA,
  "source_file_count":len(manifest["source_sha256"]),
  "generation_seconds":receipt["elapsed_seconds"],"generator_reported_seconds":manifest["generation_seconds"],
  "verification_seconds":time.monotonic()-verification_start,"files":file_records}
 dump(SEAL/(a.partition+"-verification.json"),result)
 receipt["status"]="sealed_and_verified";receipt["manifest_sha256"]=result["manifest_sha256"];dump(attempts,history)
 print(json.dumps({k:result[k] for k in ["partition","path","rows_per_cell","cell_count","total_cell_rows","unique_sample_seed_count","seed_overlap_count","writable_file_or_directory_count","failures","manifest_sha256","generation_seconds","verification_seconds"]}),flush=True)
if __name__=="__main__":main()
