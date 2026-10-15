"""Frozen causal trigger and completed-beat voltage estimators; no clean target."""
from __future__ import annotations
import numpy as np
from scipy.signal import butter, sosfilt, lfilter
from .causal import CausalFilter

GRID = np.arange(-400, 800, dtype=float)/2000.
DURATIONS = (30, 60, 120)
FLOORS = (0.1, 0.25, 0.5)
BASELINES = ("raw_mean", "raw_median", "raw_trimmed", "notch_mean", "notch_median", "notch_trimmed")

def triggers(ecg, fs):
    """Threshold learns only from the first ten seconds of this same block."""
    filtered = sosfilt(butter(2, [5.,25.], btype="bandpass", fs=fs, output="sos"), ecg)
    n = max(1, int(round(.05*fs)))
    energy = lfilter(np.ones(n)/n, [1.], filtered**2)
    warm = int(np.ceil(10*fs))
    initial = energy[:warm]
    median = float(np.median(initial))
    threshold = median + 6*float(np.median(np.abs(initial-median)))
    if not np.isfinite(threshold) or threshold <= 0:
        return np.empty(0,dtype=int), np.empty(0,dtype=int), threshold
    confirm, refractory = max(1,int(np.ceil(.05*fs))), int(np.ceil(.3*fs))
    peaks, decisions = [], []
    i = max(warm,1)
    while i + confirm < len(energy):
        if energy[i] > threshold and energy[i-1] <= threshold:
            end = i+confirm
            peak = i+int(np.argmax(energy[i:end+1]))
            peaks.append(peak)
            decisions.append(end)
            i = max(end+1,peak+refractory)
        else:
            i += 1
    return np.asarray(peaks,dtype=int), np.asarray(decisions,dtype=int), threshold

def completed_beats(window, fs, duration):
    time = window["time"]-window["time"][0]
    # Prefix truncation prevents the 30-second method observing 60/120-second samples.
    stop = int(np.searchsorted(time,duration,side="left"))
    time, ecg, raw = time[:stop], window["ecg"][:stop], window["nv"][:stop]
    notch = CausalFilter(fs, notch_hz=(50.,60.), quality=30).process(raw)
    peaks, decisions, threshold = triggers(ecg,fs)
    matrices = {"raw":[], "notch":[]}
    quality, accepted, completed = [],[],[]
    prior_stop = -np.inf
    for p,d in zip(peaks,decisions):
        center = time[p]
        start, end = center-.2, center+.4
        if start < 10 or end > time[-1] or start < prior_stop or time[d] > end:
            continue
        for key, values in (("raw",raw),("notch",notch)):
            beat = np.interp(center+GRID,time,values)
            matrices[key].append(beat-float(np.mean(beat)))
        a,b=np.searchsorted(time,[center-.1,center],side="left")
        quality.append(float(np.var(notch[a:b])))
        accepted.append(center)
        completed.append(end)
        prior_stop=end
    # A deterministic calibration scale from the first ten seconds, shared by all methods.
    warm=notch[time<10]
    segment=max(2,int(round(.1*fs)))
    variances=[float(np.var(warm[i:i+segment])) for i in range(0,len(warm)-segment+1,segment)]
    scale=float(np.median(variances)) if variances else 0.
    return {**{k:np.asarray(v,dtype=float).reshape(-1,len(GRID)) for k,v in matrices.items()},
            "quality":np.asarray(quality), "quality_scale":scale, "warm_variances":np.asarray(variances),
            "trigger_times":time[peaks], "decision_times":time[decisions],
            "accepted_times":np.asarray(accepted), "completion_times":np.asarray(completed),
            "threshold":threshold, "trigger_count":len(peaks), "beat_count":len(accepted),
            "yield":len(accepted)/len(peaks) if len(peaks) else 0., "duration_seconds":duration}

def aggregate(beats, method):
    if len(beats)==0:
        return np.zeros(len(GRID))
    if method=="mean": return np.mean(beats,axis=0)
    if method=="median": return np.median(beats,axis=0)
    if method=="trimmed":
        n=len(beats)//10
        return np.mean(np.sort(beats,axis=0)[n:len(beats)-n],axis=0)
    raise ValueError("Unknown aggregate.")

def candidate(beats, quality, scale, floor):
    if len(beats)==0 or scale<=0:
        return np.zeros(len(GRID)), np.zeros(len(beats))
    weights=np.clip(1/(quality/scale+floor),1/(4*floor),1/floor)
    return np.average(beats,axis=0,weights=weights),weights

def template_null(templates, candidate_mean):
    if not len(templates):
        return np.zeros(len(GRID)), -1
    outputs=[]
    for t in templates:
        power=float(np.dot(t,t))
        outputs.append(t*(float(np.dot(t,candidate_mean))/power) if power>0 else np.zeros(len(GRID)))
    best=int(np.argmin([np.mean((p-candidate_mean)**2) for p in outputs]))
    return outputs[best],best

def metrics(prediction, reference):
    power=float(np.mean(reference**2))
    if power<=0: return {"nrmse":None,"correlation":None,"amplitude_ratio":None,"same_polarity":False,"peak_shift_seconds":None,"width_ratio":None,"preserves":False}
    p,q=int(np.argmax(np.abs(prediction))),int(np.argmax(np.abs(reference)))
    amp=float(abs(prediction[p])/abs(reference[q]))
    polarity=bool(prediction[p]*reference[q]>0)
    shift=float(abs(GRID[p]-GRID[q]))
    def spread(x):
        w=x*x; s=float(np.sum(w))
        if s<=0:return 0.
        center=float(np.dot(GRID,w)/s)
        return float(np.sqrt(np.dot((GRID-center)**2,w)/s))
    refwidth=spread(reference)
    width=spread(prediction)/refwidth if refwidth>0 else 0.
    norm=float(np.linalg.norm(prediction)*np.linalg.norm(reference))
    corr=float(np.dot(prediction,reference)/norm) if norm>0 else 0.
    return {"nrmse":float(np.sqrt(np.mean((prediction-reference)**2)/power)),"correlation":corr,
            "amplitude_ratio":amp,"same_polarity":polarity,"peak_shift_seconds":shift,"width_ratio":width,
            "preserves":bool(polarity and .8<=amp<=1.2 and shift<=.020000000001 and .8<=width<=1.25)}

def score(prediction,a,b,threshold):
    ma,mb=metrics(prediction,a),metrics(prediction,b)
    usable=ma["nrmse"] is not None and mb["nrmse"] is not None
    error=max(ma["nrmse"],mb["nrmse"]) if usable else None
    return {"reference_a":ma,"reference_b":mb,"error":error,
            "passes":bool(usable and error<=threshold and ma["preserves"] and mb["preserves"])}

def reference_gate(a,b,counts,yields):
    ab,ba=metrics(a,b),metrics(b,a)
    error=max(ab["nrmse"],ba["nrmse"]) if ab["nrmse"] is not None and ba["nrmse"] is not None else None
    passed=bool(error is not None and error<=.5 and ab["correlation"]>=.8 and ab["preserves"] and ba["preserves"] and min(counts)>=100 and min(yields)>=.9)
    return {"passes":passed,"error":error,"a_against_b":ab,"b_against_a":ba,"counts":list(counts),"yields":list(yields)}
