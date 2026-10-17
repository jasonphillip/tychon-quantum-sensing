"""Bounded immutable NPY range retrieval and explicit source-test release gate."""
import hashlib,json,os,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CAP=400_000_000
# Conservative allowance includes already retrieved thermal ranges, train labels, and metadata.
PRIOR_RESERVED=8_934_736+7_200_128+2_000_000
CODE_FILES=('processor_io.py','processor_eval.py','test_processor.py')

def check(ok,message):
    if not ok:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def rows(ranges,limit):
    result=[]
    for a,b in ranges:
        check(type(a) is int and type(b) is int and 0<=a<b<=limit,'invalid row range')
        result.extend(range(a,b))
    check(len(result)==len(set(result)),'duplicate row range');return result

def validate_protocol(p):
    seen=set()
    for ranges in p['source_train'].values():
        ids=set(rows(ranges,900000));check(not seen&ids,'source-train split overlap');seen|=ids
    test=rows(p['source_test']['final'],100000)
    check(len(seen)==16384 and len(test)==8192,'approved row counts changed')
    check(p['candidate_windows']==[[0,770],[100,500]],'approved windows changed')
    check((len(seen)+len(test))*1540*8==p['download_budget_bytes']['remaining_signal_ranges'],'signal byte budget')
    check(PRIOR_RESERVED+(len(seen)+len(test))*1540*8+len(test)*8+1024<CAP,'lane cap')

def range_bytes(header,a,b):
    shape=header['header']['shape'];check(header['header']['descr']=='<f8' and header['header']['fortran_order'] is False,'unsupported NPY schema')
    check(header['data_offset']==128 and len(shape) in (1,2),'unsupported NPY offset/shape')
    rows([[a,b]],shape[0]);width=1 if len(shape)==1 else shape[1]
    check(width in (1,1540) and header['file_bytes']==128+shape[0]*width*8,'NPY length/layout mismatch')
    return 128+a*width*8,(b-a)*width*8

def check_registered(root,receipt):
    for relative,digest in receipt['sha256'].items():check(sha(root/relative)==digest,'registered file changed: '+relative)

def release_gate(root,release):
    check(release is not None and Path(release).is_file(),'source-test is sealed: release missing')
    approval=load(release);receipt_path=root/'train_frozen/receipt.json';receipt=load(receipt_path)
    check(approval.get('schema')=='processor_readout_test_release_v1' and approval.get('approved') is True,'source-test release invalid')
    check(isinstance(approval.get('reviewer'),str) and bool(approval['reviewer'].strip()),'reviewer missing')
    check(approval.get('training_receipt_sha256')==sha(receipt_path),'release does not bind training receipt')
    check_registered(root,receipt['registration'])
    for name,digest in receipt['artifacts'].items():check(sha(root/'train_frozen'/name)==digest,'frozen training artifact changed: '+name)
    return approval

class RangeStore:
    def __init__(self,root=ROOT,release=None):
        self.root=Path(root);self.headers=load(self.root/'headers.json');self.release=release
        self.ledger_path=self.root/'range_ledger.json'
        self.ledger=load(self.ledger_path) if self.ledger_path.exists() else {'schema':'immutable_npy_ranges_v1','prior_reserved_bytes':PRIOR_RESERVED,'received_bytes':0,'ranges':{},'failures':[]}
    def save(self):write(self.ledger_path,self.ledger)
    def request(self,url,start,n,total,path):
        check(self.ledger['prior_reserved_bytes']+self.ledger['received_bytes']+n+1<=CAP,'400 MB lane cap')
        part=path.with_name(path.name+'.partial');check(not part.exists(),'partial range requires changed-approach recovery')
        received=0
        try:
            req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{start+n-1}'})
            with urllib.request.urlopen(req,timeout=120) as response:
                check(response.status==206 and response.headers.get('Content-Range')==f'bytes {start}-{start+n-1}/{total}','server ignored exact Range; body not read')
                path.parent.mkdir(parents=True,exist_ok=True)
                with part.open('xb') as out:
                    while received<n:
                        block=response.read(min(1024*1024,n-received))
                        if not block:break
                        received+=len(block);out.write(block)
                check(received==n,'truncated HTTP range')
            os.replace(part,path);path.chmod(0o444)
        except Exception as error:
            self.ledger['failures'].append({'url':url,'start':start,'requested':n,'received':received,'error':str(error),'partial':str(part.relative_to(self.root))})
            raise
        finally:
            self.ledger['received_bytes']+=received;self.save()
    def verify_header(self,name):
        if '_test_' in name:release_gate(self.root,self.release)
        h=self.headers[name];path=self.root/'inputs/ranges'/('checked_'+name+'.header')
        if not path.exists():self.request(h['url'],0,128,h['file_bytes'],path)
        check(sha(path)==h['header_sha256'],'remote NPY header changed')
    def get(self,name,a,b):
        if '_test_' in name:release_gate(self.root,self.release)
        h=self.headers[name];start,n=range_bytes(h,a,b);key=f'{name}:{a}:{b}'
        path=self.root/'inputs/ranges'/f'{name}.{a}-{b}.bin'
        if path.exists():
            check(key in self.ledger['ranges'],'unregistered existing range')
            entry=self.ledger['ranges'][key]
            check(path.stat().st_size==n and sha(path)==entry['sha256'],'immutable range changed')
            return path
        self.verify_header(name);self.request(h['url'],start,n,h['file_bytes'],path)
        self.ledger['ranges'][key]={'file':str(path.relative_to(self.root)),'source_file':name,'rows':[a,b],'byte_start':start,'bytes':n,'sha256':sha(path),'url':h['url']}
        self.save();print(f'FETCHED {name} rows[{a}:{b}] {n} bytes',flush=True);return path
