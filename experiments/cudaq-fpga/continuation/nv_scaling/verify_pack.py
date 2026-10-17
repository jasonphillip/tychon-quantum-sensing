"""Verify every full-width expected score/index using the frozen C reference."""
import argparse
import ctypes
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from scaling import ROOT, ROM_SHA


def verify(pack):
    manifest = json.loads((pack/'manifest.json').read_text())
    for name,meta in manifest['files'].items():
        data = (pack/name).read_bytes()
        assert len(data)==meta['bytes'] and hashlib.sha256(data).hexdigest()==meta['sha256']
    rom_bytes = (ROOT/'frozen/templates_i16le.bin').read_bytes()
    assert hashlib.sha256(rom_bytes).hexdigest()==ROM_SHA
    rom = np.frombuffer(rom_bytes,dtype='<i2').astype(np.int16)
    inputs = np.fromfile(pack/'inputs_i16.bin',dtype='<i2').astype(np.int16).reshape(-1,128)
    indices = np.fromfile(pack/'expected_indices_u16.bin',dtype='<u2')
    scores = np.fromfile(pack/'expected_scores_u64.bin',dtype='<u8')
    assert len(inputs)==len(indices)==len(scores)==manifest['count']
    with tempfile.TemporaryDirectory(prefix='nv-reference-') as temp:
        library = Path(temp)/'nv_match.so'
        subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'frozen/nv_match.c'),'-o',str(library)],check=True)
        lib = ctypes.CDLL(str(library))
        ptr = ctypes.POINTER(ctypes.c_int16)
        lib.nv_match.argtypes = [ptr,ptr,ctypes.POINTER(ctypes.c_uint64)]
        lib.nv_match.restype = ctypes.c_uint16
        for row,index,score in zip(inputs,indices,scores):
            actual = ctypes.c_uint64()
            found = lib.nv_match(row.ctypes.data_as(ptr),rom.ctypes.data_as(ptr),ctypes.byref(actual))
            assert found==int(index) and actual.value==int(score), (found,index,actual.value,score)
    return {'status':'passed','records':len(inputs),'all_uint16_indices_exact':True,'all_uint64_scores_exact':True,
            'maximum_expected_score':int(scores.max()),'board_executed':False,'rom_sha256':ROM_SHA}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pack',type=Path,required=True)
    p.add_argument('--output',type=Path)
    a=p.parse_args(); result=verify(a.pack)
    if a.output:
        with a.output.open('x') as f: f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
