"""Execute the registered deterministic grid once, preserving nonregular cases."""
import argparse,csv,itertools,json
from pathlib import Path
import numpy as np
from forward import Point,field_vector,fixed_amplitude_factor,photon_budget
from information import finite_jacobian,masked_bound,LADDERS,CUTOFFS
from configuration import sha,validate_registration,bind_preflight
def run(registration,preflight,original,clarification,remaining,out,symmetry_checks=None,symmetry_correction=None):
    reg=json.loads(registration.read_text())
    validate_registration(reg)
    binding=bind_preflight(preflight,original,clarification)
    prior=json.loads(remaining.read_text())
    if prior["status"]!="pass":raise RuntimeError("remaining checks failed")
    current={p.name:sha(p) for p in Path(__file__).parent.glob("*.py")}
    if symmetry_checks is None:
        if current!=prior["implementation_sha256"]:raise RuntimeError("implementation changed after remaining checks")
    else:
        sc=json.loads(symmetry_checks.read_text())
        if sc["status"]!="pass":raise RuntimeError("symmetry checks failed")
        if sc["remaining_checks_sha256"]!=sha(remaining):raise RuntimeError("remaining evidence drift")
        if sc["correction_sha256"]!=sha(symmetry_correction):raise RuntimeError("correction evidence drift")
        if current!=sc["implementation_sha256"]:raise RuntimeError("implementation changed after symmetry checks")
    out.mkdir(parents=True,exist_ok=False)
    factor=fixed_amplitude_factor()
    summary={"status":"running","registration_sha256":sha(registration),
        "binding":binding,"remaining_checks_sha256":sha(remaining),
        "implementation_sha256":current,"global_amplitude_factor":factor,
        "global_amplitude_reference":reg["global_amplitude_reference"],
        "analytic_prior":prior["analytic_prior"],"rows":0,"points":0,
        "warning":"Local variance diagnostics, not a lower bound for all estimators under MAE.",
        "symmetry_checks_sha256":sha(symmetry_checks) if symmetry_checks else None,
        "symmetry_correction_sha256":sha(symmetry_correction) if symmetry_correction else None}
    records=[];points=[];matrices=[]
    try:
        g=reg["grid"]
        for B,costheta,phi,bias,width,mode in itertools.product(g["field_uT"],g["cos_theta"],
                g["azimuth_rad"],g["bias_uT"],g["linewidth_FWHM_MHz"],
                ("historical","fixed_amplitude")):
            p=Point(field_uT=B,theta=float(np.arccos(costheta)),phi=phi,bias_uT=bias,width_mhz=width)
            mu,j,d=finite_jacobian(p,mode,factor)
            cmu,cj,cd=finite_jacobian(p,mode,factor,cartesian=True)
            key={"point_index":len(points),"field_uT":B,"cos_theta":costheta,"azimuth_rad":phi,"bias_uT":bias,
                   "linewidth_FWHM_MHz":width,"normalization":mode}
            points.append({**key,"spherical":d,"cartesian":cd})
            matrices.append((mu,j,cmu,cj))
            for snr in g["reference_SNR"]:
                photons=photon_budget(snr)
                common={**key,"reference_SNR":snr,"photons_per_bin":photons}
                for ladder,indices in LADDERS.items():
                    target=np.zeros(len(indices));target[0]=45.
                    for cutoff in CUTOFFS:
                        r=masked_bound(mu,j[:,indices],photons,target,cutoff,d,indices,"spherical")
                        records.append({**common,"ladder":ladder,"coordinate_system":"spherical",
                            "coordinate_singularity":d["coordinate_singularity"],**r})
                target=np.zeros(7);target[:3]=45*field_vector(p)/p.field_uT
                for cutoff in CUTOFFS:
                    r=masked_bound(cmu,cj,photons,target,cutoff,cd,list(range(7)),"cartesian")
                    records.append({**common,"ladder":"direction_shape","coordinate_system":"cartesian",
                        "coordinate_singularity":False,**r})
            if d["unexplained_nonconvergent_columns"] or cd["unexplained_nonconvergent_columns"]:
                raise RuntimeError("unexplained derivative convergence failure; no grid retry")
        summary["status"]="complete"
    except Exception as exc:
        summary["status"]="stopped";summary["error"]=type(exc).__name__+": "+str(exc);raise
    finally:
        summary["rows"]=len(records);summary["points"]=len(points)
        summary["unidentifiable_rows"]=sum(x["identifiable"] is False for x in records)
        summary["unavailable_rows"]=sum(x["validity"]=="unavailable" for x in records)
        summary["rank_cutoffs"]=list(CUTOFFS)
        for name,obj in [("points.json",points),("information.json",records),("summary.json",summary)]:
            (out/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
        if matrices:
            np.savez_compressed(out/"derivatives.npz",
                point_keys=np.array([json.dumps({k:v for k,v in p.items() if k not in ("spherical","cartesian")},sort_keys=True) for p in points]),
                spherical_mean=np.stack([m[0] for m in matrices]),
                spherical_jacobian=np.stack([m[1] for m in matrices]),
                cartesian_mean=np.stack([m[2] for m in matrices]),
                cartesian_jacobian=np.stack([m[3] for m in matrices]))
        if records:
            with (out/"information.csv").open("x",newline="") as stream:
                fields=list(records[0]);writer=csv.DictWriter(stream,fields);writer.writeheader()
                for row in records:writer.writerow({k:json.dumps(v) if isinstance(v,list) else v for k,v in row.items()})
    print(json.dumps(summary,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("registration","preflight","original","clarification","remaining","out"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--symmetry-checks",type=Path);p.add_argument("--symmetry-correction",type=Path)
    a=p.parse_args();run(a.registration,a.preflight,a.original,a.clarification,a.remaining,a.out,a.symmetry_checks,a.symmetry_correction)
