"""Verify existing measured-data receipts and integer bytes; no evaluation rerun."""
import csv,hashlib,json,math,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/frozen_v1'
def check(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    reg=json.loads((ROOT/'registration.json').read_text())
    for name,digest in reg['sha256'].items():check(sha(ROOT/name)==digest,'registered hash: '+name)
    r=json.loads((OUT/'metrics.json').read_text())
    for name,digest in r['output_hashes'].items():check(sha(OUT/name)==digest,'output hash: '+name)
    p=OUT/'candidate_integer_pack';m=json.loads((p/'manifest.json').read_text())
    for name,digest in m['sha256'].items():check(sha(p/name)==digest,'pack hash: '+name)
    inputs=(p/'inputs_i16.bin').read_bytes();scores=(p/'expected_scores_i64.bin').read_bytes();labels=(p/'labels_u8.bin').read_bytes()
    n=m['records'];check(len(inputs)==n*256 and len(scores)==n*8 and len(labels)==n,'pack lengths')
    w=m['weights_i32'];bias=m['bias_i64'];correct=0
    for i,(row,(expected,),label) in enumerate(zip(struct.iter_unpack('<128h',inputs),struct.iter_unpack('<q',scores),labels)):
        actual=bias+sum(row[j]*w[j%2] for j in range(128))
        check(actual==expected,'integer score mismatch');correct+=int((actual>=0)==label)
    check(correct/n==m['preparation_accuracy'],'integer accuracy')
    with (OUT/'final_predictions.csv').open() as f:rows=list(csv.DictReader(f))
    check(len(rows)==n,'prediction rows')
    for name,metric in r['final'].items():
        if not metric['coverage']:continue
        conf=[[0,0],[0,0]]
        for i,row in enumerate(rows):
            label=int(row['preparation']);check(label==labels[i] and int(row['shot_index'])==500+i%500,'record provenance')
            conf[label][int(row[name])]+=1
        check(conf==metric['confusion_preparation_by_assignment'],'prediction counts: '+name)
    better=worse=0
    for row in rows:
        label=row['preparation'];a=row['affine_reference_boxcar']==label;b=row['reference_boxcar_uncalibrated']==label
        better+=a and not b;worse+=b and not a
    d=better+worse
    pvalue=min(1.,2*sum(math.comb(d,k) for k in range(min(better,worse)+1))/2**d) if d else 1.
    result={'status':'PASS','registered_hashes':len(reg['sha256']),'exact_integer_records':n,
            'affine_paired_better':better,'affine_paired_worse':worse,'exact_discordant_binomial_two_sided_p':pvalue,
            'uncertainty_scope':'conditional independent-discordant-shot assumption; no acquisition-level inference',
            'scope':'saved receipt verification only; final outcomes not regenerated'}
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
