"""Raw-compatibility saved-output check (public copy); no fitting, inference, or raw data.

Derived unchanged in arithmetic from the independent verifier used before publication
(root_raw_compatibility_saved_check_v1.py, sha256 29ee3cbaeb688e3d56a9926bf86f759741633fdbf1fcd115410f91d60f151342); only this docstring differs.
Recomputes the 192 feature comparisons and the maximum differences from the saved arrays.
Run without python -O (checks use assert). --out must be a new directory.
Usage: python3 check_raw_compatibility.py --bundle <localisation-raw-compatibility dir>
       --protocol <workers/odmr-edge-ml/experiments/localisation_raw_compatibility/protocol.json> --out <new dir>
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
a=argparse.ArgumentParser();a.add_argument('--bundle',type=Path,required=True);a.add_argument('--protocol',type=Path,required=True);a.add_argument('--out',type=Path,required=True);x=a.parse_args()
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((x.bundle/'manifest.json').read_text());p=json.loads(x.protocol.read_text())
assert h(x.protocol)==m['protocol_sha256'] and p['status']=='FROZEN'
for name,digest in m['files'].items():assert h(x.bundle/name)==digest
actual=np.load(x.bundle/'extracted_features_MHz.npy',allow_pickle=False)
expected=np.load(x.bundle/'reference_A_features_MHz.npy',allow_pickle=False)
params=np.load(x.bundle/'raw_fit_parameters.npy',allow_pickle=False)
std=np.load(x.bundle/'raw_fit_std.npy',allow_pickle=False)
assert actual.shape==expected.shape==(8,24) and params.shape==std.shape==(8,8,6)
derived=np.stack((np.abs(params[:,:,1]-params[:,:,4]),std[:,:,1],std[:,:,4]),axis=2).reshape(8,24)*1000.
np.testing.assert_array_equal(actual,derived)
t=p['matching_tolerances'];at=np.tile([t['splitting_atol_MHz'],t['standard_error_atol_MHz'],t['standard_error_atol_MHz']],8);rt=np.tile([t['splitting_rtol'],t['standard_error_rtol'],t['standard_error_rtol']],8)
error=np.abs(actual-expected);limit=at+rt*np.abs(expected)
flags=json.loads((x.bundle/'fit_flags.json').read_text());sample=json.loads((x.bundle/'sample.json').read_text());receipts=json.loads((x.bundle/'member_receipts.json').read_text())
assert len(flags)==len(receipts)==len(sample['members'])==8
for i,row in enumerate(flags):
 assert row['fitted_row']==sample['members'][i]['fitted_row']==receipts[i]['fitted_row']
 assert len(row['channels'])==8 and [z['channel'] for z in row['channels']]==p['model_channel_order']
 assert all(z['valid'] and z['reason'] is None for z in row['channels'])
 assert receipts[i]['member']==sample['members'][i]['member'] and receipts[i]['zip_crc32']==sample['members'][i]['zip_crc32']
valid=np.isfinite(actual)&np.isfinite(expected)&(actual>0)&(expected>0)
passed=bool((valid&(error<=limit)).all())
report=json.loads((x.bundle/'qualification.json').read_text())
assert passed and report['status']=='PASS' and report['comparison']['passed_elements']==192
out={'status':'PASS','comparisons':192,'valid_channel_fits':64,'max_splitting_absolute_difference_MHz':float(error[:,::3].max()),'max_standard_error_absolute_difference_MHz':float(error.reshape(8,8,3)[:,:,1:].max()),'max_tolerance_fraction':float((error/limit).max()),'manifest_sha256':h(x.bundle/'manifest.json'),'scope':'Training-only numerical compatibility; no acquisition transfer or performance claim'}
x.out.mkdir(parents=True,exist_ok=False);(x.out/'result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
