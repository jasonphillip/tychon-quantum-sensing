#!/usr/bin/env python3
"""Independent arithmetic verification. Never reads raw final data or runs inference."""
import os
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
import datetime
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch

ROOT = Path('<path>')
OUT = ROOT/'independent-verification'
RESULTS = ROOT/'results-final'
EXPECTED_FREEZE = '5e54c8f9fe223217cdd8e5566f0665724c3fa230395092b733f1a6b79f63790f'
SEEDS = [42, 20261014, 20261015]
issues = []
comparisons = 0
largest_difference = 0.0

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def check(condition, label):
    if not condition:
        issues.append(label)

def compare(actual, expected, label):
    global comparisons, largest_difference
    comparisons += 1
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        issues.append(label+' shape/nonfinite mismatch')
        return
    difference = float(np.max(np.abs(a-b)))
    largest_difference = max(largest_difference, difference)
    if difference > 1e-10:
        issues.append(label+f' difference={difference:.12g}')

def metrics(prediction, truth):
    error = np.asarray(prediction, dtype=np.float64)-np.asarray(truth, dtype=np.float64)
    absolute = np.abs(error)
    return dict(n=len(error), mae_uT=float(absolute.mean()), rmse_uT=float(np.sqrt(np.mean(error*error))),
                median_abs_uT=float(np.median(absolute)), p90_abs_uT=float(np.quantile(absolute,.9)),
                bias_uT=float(error.mean()))

def compare_metrics(actual, expected, label):
    for key in actual:
        compare(actual[key], expected[key], label+'/'+key)

def main():
    start = time.monotonic()
    OUT.mkdir(exist_ok=True)
    summary = read(RESULTS/'SUMMARY.json')
    access = read(ROOT/'FINAL_ACCESS.json')
    freeze = read(ROOT/'FROZEN_CHOICES.json')
    check(sha(ROOT/'FROZEN_CHOICES.json') == EXPECTED_FREEZE, 'freeze file hash')
    check(access['freeze_sha256'] == EXPECTED_FREEZE, 'receipt freeze hash')
    check(sha(RESULTS/'SUMMARY.json') == access['summary_sha256'], 'receipt summary hash')
    check(access['status'] == summary['status'] == 'complete', 'completion state')
    check(access['candidates'] == freeze['candidates'], 'candidate manifests differ')
    check(access['data_manifest_sha256'] == freeze['final_manifest_sha256'], 'manifest hash receipts differ')
    check(sha(ROOT/'evaluate_stress.py') == access['evaluator_sha256'] == freeze['source_hashes'][str(ROOT/'evaluate_stress.py')], 'evaluator hash')
    check(access['protocol_sha256'] == freeze['source_hashes'][str(ROOT/'PROTOCOL.md')], 'protocol receipt hash')
    check(freeze['created_utc'] < access['first_read_utc'] < access['completed_utc'], 'freeze/access timestamp ordering')
    candidates = {}
    for item in freeze['candidates']:
        check(sha(item['checkpoint']) == item['checkpoint_sha256'], item['name']+' checkpoint hash')
        check(sha(item['export']) == item['export_sha256'], item['name']+' export hash')
        state = torch.load(item['checkpoint'], map_location='cpu', weights_only=True)['state_dict']
        sigma = float(state['sigma'])
        check(np.isfinite(sigma) and sigma >= .1, item['name']+' sigma contract')
        candidates[item['name']] = dict(sigma=sigma, checkpoint_sha256=item['checkpoint_sha256'], export_sha256=item['export_sha256'])
        del state
    cells = {}
    model_count = interval_count = disagreement_count = failure_count = 0
    for cell, stored in summary['cells'].items():
        separate = read(RESULTS/(cell+'_metrics.json'))
        check(separate == stored, cell+' separate metrics versus summary')
        path = RESULTS/stored['prediction_file']
        check(path.parent == RESULTS and path.name == cell+'_predictions.npz', cell+' prediction path')
        check(sha(path) == stored['prediction_sha256'], cell+' prediction hash')
        with np.load(path, allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        truth = arrays['truth_uT']
        check(truth.shape == (256,), cell+' row count')
        recomputed = {}
        for name, expected in stored['models'].items():
            actual = metrics(arrays['pred__'+name], truth)
            compare_metrics(actual, expected, cell+'/'+name)
            recomputed[name] = actual
            model_count += 1
        errors = {}
        for arm in ['B_full_residual','C_direct']:
            for precision in ['fp32','int8']:
                names = [f'{arm}_seed{s}__{precision}' for s in SEEDS]
                error_rows = np.stack([np.abs(arrays['pred__'+name]-truth) for name in names])
                errors[arm+'__'+precision] = error_rows.mean(axis=0)
                expected = stored['arm_summary'][arm+'__'+precision]
                compare(error_rows.mean(axis=1), expected['seed_mae_uT'], cell+'/'+arm+'/'+precision+'/seed_mae')
                compare(error_rows.mean(), expected['mean_seed_mae_uT'], cell+'/'+arm+'/'+precision+'/mean_seed_mae')
        c = errors['C_direct__int8']
        differences = {
            'C_minus_mean': c-np.abs(arrays['pred__training_mean']-truth),
            'C_minus_prior_fit': c-np.abs(arrays['pred__prior_fit']-truth),
            'C_minus_prior_PID': c-np.abs(arrays['pred__prior_PID']-truth),
            'C_minus_repaired_B': c-errors['B_full_residual__int8'],
        }
        # Draw once in a single block, independently of evaluator's chunked implementation.
        indices = np.random.default_rng(202610143).integers(0,len(truth),size=(10000,len(truth)))
        intervals = {}
        for name, difference in differences.items():
            sampled = difference[indices].mean(axis=1)
            bounds = np.quantile(sampled,[.025,.975])
            expected = stored['paired_comparisons'][name]
            compare(difference.mean(), expected['mean_difference_uT'], cell+'/'+name+'/mean')
            compare(bounds, expected['ci95_uT'], cell+'/'+name+'/interval')
            check(expected['resamples']==10000 and expected['bootstrap_seed']==202610143, cell+'/'+name+'/bootstrap configuration')
            intervals[name] = {'mean_difference_uT':float(difference.mean()),'ci95_uT':bounds.tolist()}
            interval_count += 1
        failures = {}
        for name in ['prior_fit','prior_PID']:
            failed = arrays['failed__'+name].astype(bool)
            outside = arrays['outside__'+name].astype(bool)
            projection = arrays['raw_projection__'+name]
            expected = stored['failures'][name]
            values = dict(failed=int(failed.sum()),out_of_support=int(outside.sum()),n=len(failed),failure_fraction=float(failed.mean()))
            for key,value in values.items():compare(value,expected[key],cell+'/'+name+'/'+key)
            magnitude = np.sqrt(70*np.maximum(20,np.clip(np.abs(projection),0,70)))
            fallback = np.where(failed,freeze['training_mean_uT'],magnitude)
            compare(fallback,arrays['pred__'+name],cell+'/'+name+'/prior mapping and fallback')
            check(np.array_equal(outside,np.isfinite(projection)&(np.abs(projection)>70)),cell+'/'+name+'/support mask')
            if name=='prior_fit':compare(np.where(failed,freeze['training_mean_uT'],projection),arrays['pred__two_line_projection'],cell+'/two_line fallback')
            failures[name]=values
            failure_count += 1
        for name,quant in stored['quantization'].items():
            fp,qi=arrays['pred__'+name+'__fp32'],arrays['pred__'+name+'__int8']
            compare_metrics(metrics(qi,fp),quant['int8_vs_fp32'],cell+'/'+name+'/quantization disagreement')
            output = qi-arrays['pred__PID'] if name.startswith('B_full_residual') else qi
            codes = np.rint(output/quant['output_scale']+quant['output_zero_point']).astype(np.int64)
            check(np.all((codes>=-128)&(codes<=127)),cell+'/'+name+'/output codes')
            compare(int(np.sum(codes==-128)),quant['output_at_min'],cell+'/'+name+'/endpoint min')
            compare(int(np.sum(codes==127)),quant['output_at_max'],cell+'/'+name+'/endpoint max')
            compare(float(np.mean((codes==-128)|(codes==127))),quant['output_saturation_fraction'],cell+'/'+name+'/endpoint fraction')
            disagreement_count += 1
        cells[cell]={'C_int8_mean_seed_mae_uT':float(c.mean()),'training_mean_mae_uT':recomputed['training_mean']['mae_uT'],
                     'prior_fit_mae_uT':recomputed['prior_fit']['mae_uT'],'paired_comparisons':intervals,'failures':failures,
                     'prediction_sha256':sha(path)}
    checks = {cell:{name:(cells[cell]['paired_comparisons'][name]['mean_difference_uT']<0 and
                          cells[cell]['paired_comparisons'][name]['ci95_uT'][1]<0)
                   for name in ['C_minus_mean','C_minus_prior_fit']} for cell in freeze['primary_cells']}
    criterion = all(value for cell in checks.values() for value in cell.values())
    check(criterion == summary['primary_criterion_passed'],'primary criterion')
    calibration_path=ROOT.parent/'scalar-calibration-repair/run-1/validation_predictions.npz'
    calibration={}
    with np.load(calibration_path,allow_pickle=False) as p:
        for representation in ['float','prefix_int8','rank_int8']:
            seed_metrics=[metrics(p[f'B_full_residual_seed{s}__{representation}_field_uT'],p['truth_uT']) for s in SEEDS]
            calibration[representation]={name:float(np.mean([m[name] for m in seed_metrics])) for name in ['mae_uT','rmse_uT','p90_abs_uT']}
        for representation in ['prefix_int8','rank_int8']:
            calibration[representation]['quantization_mae_uT']=float(np.mean([np.mean(np.abs(p[f'B_full_residual_seed{s}__{representation}_field_uT']-p[f'B_full_residual_seed{s}__float_field_uT'])) for s in SEEDS]))
            calibration[representation]['endpoint_fraction']=float(np.mean([np.mean(np.isin(p[f'B_full_residual_seed{s}__{representation}_codes'],[-128,127])) for s in SEEDS]))
    for name,value in [('float',10.805220418246849),('prefix_int8',13.833197497996858),('rank_int8',10.823257085395163)]:
        compare(calibration[name]['mae_uT'],value,'calibration prior headline/'+name)
    report={'status':'passed' if not issues else 'discrepancies','discrepancies':issues,'numerical_comparison_count':comparisons,
            'max_numeric_difference':largest_difference,'model_metric_sets':model_count,'paired_intervals':interval_count,
            'disagreement_metric_sets':disagreement_count,'failure_support_count_sets':failure_count,
            'primary_criterion_passed':criterion,'primary_checks':checks,'cells':cells,'candidate_sigma_and_hashes':candidates,
            'freeze_sha256':EXPECTED_FREEZE,'summary_sha256':sha(RESULTS/'SUMMARY.json'),
            'calibration_saved_validation_recomputed':calibration,'calibration_prediction_sha256':sha(calibration_path),
            'raw_final_access_count':0,'inference_count':0,'elapsed_seconds':time.monotonic()-start,
            'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'limits':['Failure counts verify saved masks; optimizer failure causes cannot be independently established without rerunning fits.',
                      'Input endpoint counts and measured inference timings cannot be recomputed from saved predictions.',
                      'Calibration headline comparison uses the prior verification handoff values, without opening another result file.']}
    (OUT/'VERIFICATION.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    lines=['# Independent saved-output verification','',f"Status: {report['status']}. Discrepancies: {len(issues)}.",
           f"Recomputed {model_count} model metric sets, {interval_count} paired intervals, {disagreement_count} FP32/INT8 disagreement sets, and {failure_count} failure/support sets.",
           f"Largest numeric difference: {largest_difference:.3g}. Primary criterion: {criterion}.",'',
           '| Primary cell | C INT8 MAE | Training mean MAE | Prior fit MAE |','|---|---:|---:|---:|']
    for name in freeze['primary_cells']:
        x=cells[name];lines.append(f"| {name} | {x['C_int8_mean_seed_mae_uT']:.8f} | {x['training_mean_mae_uT']:.8f} | {x['prior_fit_mae_uT']:.8f} |")
    lines+=['','All six checkpoints were loaded with weights_only=True for sigma metadata. Candidate file hashes were checked. No model was constructed.','',
            'Calibration validation mean MAE: '+json.dumps({k:v['mae_uT'] for k,v in calibration.items()}),'',
            'Raw final accesses: 0. Inference calls: 0.','', 'Limits:']+['- '+s for s in report['limits']]
    if issues:lines+=['','Discrepancies:']+['- '+s for s in issues]
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:report[k] for k in ['status','discrepancies','numerical_comparison_count','max_numeric_difference','model_metric_sets','paired_intervals','disagreement_metric_sets','failure_support_count_sets','primary_criterion_passed','primary_checks','calibration_saved_validation_recomputed','elapsed_seconds']},indent=2))

if __name__=='__main__':main()
