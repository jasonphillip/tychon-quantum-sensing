"""Only checks not reached in the failed preflights; no spectrum generation."""
import argparse,json
from pathlib import Path
import numpy as np
from scipy.integrate import quad
from configuration import validate_registration,bind_preflight,sha
from information import fisher_bound,ladder_validity,masked_bound
def check(condition,label):
    if not condition:raise AssertionError(label)
def run(registration,preflight,original,clarification,out):
    out.mkdir(parents=True,exist_ok=False)
    r={"status":"running","checks":[],"implementation_sha256":
        {p.name:sha(p) for p in Path(__file__).parent.glob("*.py")}}
    try:
        reg=json.loads(registration.read_text())
        validate_registration(reg)
        r["binding"]=bind_preflight(preflight,original,clarification)
        r["checks"].append("registration and retained parity/analytic source binding")
        # Algebra-only branch masks. No forward-model evaluations.
        d={"parameter_names":["B","center","width","contrast","slope","theta","phi"],
           "column_branch_crossed":[False]*5+[True,False],
           "derivative_relative_error":[0.]*7,"coordinate_singularity":False}
        check(ladder_validity(d,[0,1,2,3,4],"spherical")[0],"unneeded branch must not invalidate shape")
        check(not ladder_validity(d,list(range(7)),"spherical")[0],"required branch invalid")
        mu=np.ones(100);j=np.column_stack((np.sin(np.linspace(0,3,100)),np.ones(100)))
        blocked=masked_bound(mu,j,1e6,[1,0],1e-10,d,[0,5],"spherical")
        check(blocked["std_bound_uT"] is None and blocked["rank"] is None,"no bound at branch")
        d["column_branch_crossed"]=[False]*7;d["coordinate_singularity"]=True
        check(ladder_validity(d,[0,1,2,3,4],"spherical")[0],"known direction at pole")
        check(not ladder_validity(d,list(range(7)),"spherical")[0],"polar unknown direction invalid")
        check(ladder_validity(d,list(range(7)),"cartesian")[0],"Cartesian chart avoids polar flag")
        d["derivative_relative_error"][2]=.02001
        check(not ladder_validity(d,[0,1,2],"cartesian")[0],"unchanged convergence tolerance")
        r["checks"].append("synthetic per-ladder validity algebra")
        a,b=20.,70.
        closed=(b*b/6+a*a/2-(2/3)*a*np.sqrt(a*b))/(b-a)
        numeric=quad(lambda q:(np.sqrt(b)-np.sqrt(max(a,q)))**2/(b-a),
                     0,b,points=[a],epsabs=1e-11,epsrel=1e-11)[0]
        check(abs(numeric-closed)<1e-9,"projection Bayes oracle quadrature")
        r["analytic_prior"]={"projection_only_bayes_MAE_uT":closed,
            "quadrature_MAE_uT":numeric,"constant_MAE_uT":(b-a)/4,
            "constant_RMSE_uT":(b-a)/np.sqrt(12),
            "warning":"Reduced projection model only; not a full-physics lower bound."}
        r["checks"].append("projection-only oracle integral")
        fixed=fisher_bound(mu,j[:,:1],1e6,[1],1e-10)
        nuisance=fisher_bound(mu,j,1e6,[1,0],1e-10)
        check(nuisance["std_bound_uT"]>=fixed["std_bound_uT"],"nuisance monotonicity")
        lower_photons=fisher_bound(mu,j,1e5,[1,0],1e-10)
        check(lower_photons["std_bound_uT"]>=nuisance["std_bound_uT"],"noise monotonicity")
        repeat=fisher_bound(np.r_[mu,mu],np.vstack([j,j]),1e6,[1,0],1e-10)
        check(abs(repeat["std_bound_uT"]*np.sqrt(2)/nuisance["std_bound_uT"]-1)<1e-12,"replicate additivity")
        null=fisher_bound(mu,np.ones((100,2)),1e6,[1,0],1e-10)
        check(null["std_bound_uT"] is None and not null["identifiable"],"null target not pseudoinverse")
        check(abs(np.sqrt(1e6/(1e6+.5))-1)<1e-6,"Gaussian/Poisson high-count limit")
        r["fisher_invariants"]={"fixed":fixed,"nuisance":nuisance,"replicate":repeat,"null":null,"lower_photons":lower_photons}
        r["checks"].append("nuisance, noise, replicate, nullspace and high-count Fisher checks")
        r["status"]="pass"
    except Exception as exc:
        r["status"]="fail";r["error"]=type(exc).__name__+": "+str(exc);raise
    finally:(out/"checks.json").write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    print(json.dumps(r,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("registration","preflight","original","clarification","out"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();run(a.registration,a.preflight,a.original,a.clarification,a.out)
