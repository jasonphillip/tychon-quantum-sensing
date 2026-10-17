"""Read-only byte, CSV, and integer checks. Does not fit or reevaluate models."""
import argparse,csv,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def check(ok,message):
    if not ok:raise ValueError(message)
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def verify_train(root):
    folder=root/'train_frozen';receipt=read(folder/'receipt.json')
    for name,digest in receipt['registration']['sha256'].items():check(sha(root/name)==digest,'registered hash '+name)
    for name,digest in receipt['artifacts'].items():check(sha(folder/name)==digest,'frozen artifact '+name)
    ranges=read(folder/'train_ranges.json')
    for name,digest in ranges.items():check(sha(root/name)==digest,'training range '+name)
    selection=read(folder/'selection.json');check(selection['source_test_values_read']==0,'training used test')
    source=read(folder/'source_train_rows.json');used=set()
    for row in source:
        identity=row['source_row'];check(identity not in used,'training partition row overlap');used.add(identity)
    return {'frozen_training_rows':len(used),'frozen_training_ranges':len(ranges),'selected':selection['selected']}
def verify_pack(root,out):
    r=read(out/'metrics.json');folder=out/'candidate_integer_pack';m=read(folder/'manifest.json')
    for name,digest in m['sha256'].items():check(sha(folder/name)==digest,'pack hash '+name)
    n=m['records'];data=(folder/'inputs_i16.bin').read_bytes();score=(folder/'expected_scores_i64.bin').read_bytes()
    y=(folder/'labels_u8.bin').read_bytes();rowbytes=(folder/'source_rows_u32.bin').read_bytes()
    check(len(data)==n*256 and len(score)==n*8 and len(y)==n and len(rowbytes)==n*4,'pack length')
    rowids=[x[0] for x in struct.iter_unpack('<I',rowbytes)];conf=[[0,0],[0,0]]
    for row,(expected,),label in zip(struct.iter_unpack('<128h',data),struct.iter_unpack('<q',score),y):
        check(label in (0,1),'unknown label')
        actual=m['bias_i64']+sum(int(v)*m['weights_i32'][i%2] for i,v in enumerate(row))
        check(actual==expected,'full-width integer mismatch');conf[label][int(actual>=0)]+=1
    check(conf==m['metrics']['confusion_preparation_by_assignment'],'integer confusion matrix')
    check(sha(out/'predictions.csv')==r['predictions_sha256'],'prediction hash')
    with (out/'predictions.csv').open() as f:pred=list(csv.DictReader(f))
    check(len(pred)==n,'prediction count')
    for i,row in enumerate(pred):check(int(row['source_test_row'])==rowids[i] and int(row['preparation'])==y[i],'source row/label mapping')
    checked=0
    for candidate in pred[0]:
        if candidate in ('source_test_row','preparation'):continue
        expected=r['final'][candidate]
        if not expected['coverage']:
            check(all(row[candidate]=='' for row in pred),'invalid calibration predictions present');continue
        cm=[[0,0],[0,0]]
        for row,label in zip(pred,y):
            v=int(row[candidate]);check(v in (0,1),'nonbinary prediction');cm[label][v]+=1
        check(cm==expected['confusion_preparation_by_assignment'],'candidate confusion '+candidate);checked+=1
    return {'exact_integer_records':n,'prediction_candidates_checked':checked,'selected':r['selected'],
            'selected_balanced_accuracy':r['final'][r['selected']]['balanced_accuracy'],
            'scope':'saved integer/CSV checks only; no model fitting, new scientific evaluation, or hardware execution'}
def main():
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,default=ROOT);a.add_argument('--train-only',action='store_true');a.add_argument('--pack-only',action='store_true');a.add_argument('--output',type=Path);args=a.parse_args()
    result={'status':'PASS'}
    if not args.pack_only:result.update(verify_train(args.root))
    if not args.train_only:result.update(verify_pack(args.root,args.output or args.root/'test_frozen'))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
