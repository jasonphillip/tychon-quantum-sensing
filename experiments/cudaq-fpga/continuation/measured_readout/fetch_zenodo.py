"""Bounded range retrieval; never downloads the entire 923 MB archive implicitly."""
import argparse, hashlib, io, json, re, urllib.request, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CAP=250_000_000
class Remote(io.RawIOBase):
    def __init__(self, metadata):
        f=metadata['files'][0];self.url=f['links']['self'];self.size=f['size'];self.pos=0
        self.ledger=ROOT/'retrieval.json'
        self.log=json.loads(self.ledger.read_text()) if self.ledger.exists() else {'downloaded_bytes':0,'requests':[],'members':{}}
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=(0 if whence==0 else self.pos if whence==1 else self.size)+offset
        if not 0<=self.pos<=self.size:raise ValueError('seek outside archive')
        return self.pos
    def read(self,n=-1):
        n=min(self.size-self.pos,n if n>=0 else self.size)
        if not n:return b''
        if self.log['downloaded_bytes']+n>CAP:raise ValueError('250 MB cumulative retrieval cap')
        start=self.pos;req=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{start+n-1}'})
        with urllib.request.urlopen(req,timeout=60) as r:
            if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{start+n-1}/{self.size}':
                raise ValueError('Server did not honor exact bounded range; body not downloaded')
            data=r.read(n+1)
        self.log['downloaded_bytes']+=len(data)
        self.log['requests'].append({'start':start,'requested':n,'received':len(data)})
        self.ledger.write_text(json.dumps(self.log,indent=2)+'\n')
        if len(data)!=n:raise ValueError('truncated range')
        self.pos+=n
        return data

def main():
    a=argparse.ArgumentParser();a.add_argument('--member',action='append',default=[]);args=a.parse_args()
    remote=Remote(json.loads((ROOT/'zenodo_10000511_metadata.json').read_text()))
    with zipfile.ZipFile(remote) as z:
        entries=[{'name':x.filename,'bytes':x.file_size,'compressed_bytes':x.compress_size,'crc32':f'{x.CRC:08x}'} for x in z.infolist()]
        index=ROOT/'archive_index.json'
        if not index.exists():index.write_text(json.dumps(entries,indent=2)+'\n')
        print(json.dumps(entries if not args.member else {'members_requested':args.member},indent=2))
        for name in args.member:
            rel=Path(name)
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe member')
            info=z.getinfo(name)
            if info.file_size>CAP:raise ValueError('member decompression exceeds cap')
            out=ROOT/'inputs'/rel
            if out.exists():raise ValueError('immutable input already exists')
            data=z.read(info)  # ZipFile checks each member CRC.
            out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);out.chmod(0o444)
            remote.log['members'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'crc32':f'{info.CRC:08x}'}
            remote.ledger.write_text(json.dumps(remote.log,indent=2)+'\n')
            print('saved',name,len(data))
    print('cumulative downloaded bytes',remote.log['downloaded_bytes'])
if __name__=='__main__':main()
