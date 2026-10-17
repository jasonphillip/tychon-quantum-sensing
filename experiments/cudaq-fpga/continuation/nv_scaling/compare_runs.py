"""Compare complete same-host backend receipts; preserve warnings and uncertainty."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import numpy as np


def compare(cpu_dir,gpu_dir,gpu_log):
    cpu=json.loads((cpu_dir/'receipt.json').read_text())
    gpu=json.loads((gpu_dir/'receipt.json').read_text())
    if cpu['status']!='passed' or gpu['status']!='passed':
        raise ValueError('Both numerical receipts must pass')
    if cpu['backend']!='cpu' or gpu['backend']!='cudaq':
        raise ValueError('Expected CPU and CUDA-Q backends')
    if cpu['protocol_sha256']!=gpu['protocol_sha256'] or cpu['platform']!=gpu['platform']:
        raise ValueError('Same protocol and same-host platform are required; Mac timings cannot be compared with Spark GPU')
    c=np.load(cpu_dir/'quantum_dataset.npz'); g=np.load(gpu_dir/'quantum_dataset.npz')
    for field in ['detuning_mhz','delays_us','phases_rad']:
        np.testing.assert_array_equal(c[field],g[field])
    cw=[r['quantum_seconds'] for r in cpu['runs'] if r['kind']=='warm']
    gw=[r['quantum_seconds'] for r in gpu['runs'] if r['kind']=='warm']
    log=gpu_log.read_text(errors='replace')
    warnings=[line for line in log.splitlines() if any(term in line.lower() for term in ['warning','non-batched','not compatible for batching'])]
    fallback=any('non-batched' in x.lower() or 'not compatible for batching' in x.lower() for x in warnings)
    result={'status':'passed','protocol_sha256':cpu['protocol_sha256'],
            'independent_configurations':gpu['independent_configurations'],
            'quantum_probability_count':gpu['quantum_probability_count'],
            'gpu_generated_fraction':gpu['gpu_generated_fraction'],
            'max_complete_probability_difference':float(np.max(np.abs(c['probabilities']-g['probabilities']))),
            'max_complete_density_difference':float(np.max(np.abs(c['density']-g['density']))),
            'cpu_warm_quantum_seconds':{'median':statistics.median(cw),'minimum':min(cw),'maximum':max(cw)},
            'gpu_warm_quantum_seconds':{'median':statistics.median(gw),'minimum':min(gw),'maximum':max(gw)},
            'cpu_seconds_divided_by_gpu_seconds':statistics.median(cw)/statistics.median(gw),
            'ratio_interpretation':'Above one favors GPU; below one favors CPU. No speedup acceptance gate.',
            'first_call_plus_initialization_seconds':{'cpu':cpu['first_call_plus_initialization_seconds'],'gpu':gpu['first_call_plus_initialization_seconds']},
            'process_peak_rss_bytes':{'cpu':cpu['process_peak_rss_bytes'],'gpu':gpu['process_peak_rss_bytes']},
            'gpu_memory':gpu['gpu_memory'],
            'batched_api_used':True,'sequential_fallback_warning_observed':fallback,
            'batch_execution_evidence':'Sequential fallback explicitly reported' if fallback else 'Batched API requested; no fallback warning in retained log. Absence of warnings does not independently prove simultaneous GPU batching.',
            'retained_warnings':warnings,'gpu_log_sha256':hashlib.sha256(gpu_log.read_bytes()).hexdigest(),
            'board_executed':False}
    for name,r in [('cpu',cpu),('gpu',gpu)]:
        result[name+'_single_pipeline_component_sum_seconds']=r['first_call_plus_initialization_seconds']+r['cpu_detector_and_integer_reference_seconds']+r['output_write_seconds']
    result['pipeline_sum_note']='Component sum includes first generation, initialization, CPU detector/integer reference, and writes. It excludes validation and repeated timing passes; it is not a separately measured total.'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu',type=Path,required=True);p.add_argument('--gpu',type=Path,required=True)
    p.add_argument('--gpu-log',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=compare(a.cpu,a.gpu,a.gpu_log)
    with a.output.open('x') as f: f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','quantum_probability_count','max_complete_probability_difference','cpu_seconds_divided_by_gpu_seconds','batch_execution_evidence']}))
