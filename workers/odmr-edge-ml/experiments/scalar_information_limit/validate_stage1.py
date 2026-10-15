"""Manufactured checks only; invoke through the accounted stage runner."""
import argparse,hashlib,importlib.metadata,json,sys
from dataclasses import asdict,replace
from pathlib import Path
import numpy as np
from scipy.integrate import quad
from forward import Point,forward,field_vector,fixed_amplitude_factor,photon_budget
from information import (lorentzian_profile,lorentzian_jacobian,finite_jacobian,
                         fisher_bound)

PINNED={
"adapters/simos_adapter.py":"d5985c3920fbe6334d9bb70210e21711e2d0cda14e63308df37cf126aa46e431",
"pipelines/batch_generate.py":"ba9365e55bbbbc0c7b2465539104461512a9c0a4c0be4dd57c35b70d8275c5db",
"physics/lineshape.py":"f0d2797b88556d25534872cf05a7cf2fae2c2f03c29c03080671dd07f4f63a28",
"physics/parameters.py":"3ad33dfb5d64e606b828173b12b372b3c7df7464d96824ad0c34ba494be01410",
"physics/shot_noise.py":"c3b602bb5dab7c227d9485b8145fb995d544df5e533c59a1d571621557d44c73",
"physics/noise_injection.py":"f8270506ba7b05063cb7fc6e548456e2339f903de110066fc2767808e275b778"}
EXTRAS=("physics/hamiltonian.py","config.py")
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(condition,label):
    if not condition:raise AssertionError(label)
def validate(sim_source,out):
    out.mkdir(parents=True,exist_ok=False)
    results={"status":"running","checks":[],"implementation_sha256":{p.name:digest(p) for p in Path(__file__).parent.glob("*.py")}}
    try:
        source=Path(sim_source).resolve()
        pin={key:digest(source/"nv_sensor_sim"/key) for key in PINNED}
        check(pin==PINNED,"simulator source hash drift")
        sys.path.insert(0,str(source))
        from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
        from nv_sensor_sim.config import SimulationConfig
        from nv_sensor_sim.physics.lineshape import corrupt_spectrum
        from simos.systems import NV
        import simos.constants as constants
        from forward import ELECTRON_GAMMA,NV_GAMMA
        check(constants.ye==ELECTRON_GAMMA,"electron gamma")
        check(NV.yNV==NV_GAMMA,"NV gamma")
        package_source=Path(NV.__file__)
        private={"sim_source":str(source),"files":{key:str(source/"nv_sensor_sim"/key) for key in (*PINNED,*EXTRAS)},
                 "SimOS_NV_source":str(package_source),"SimOS_constants_source":str(Path(constants.__file__))}
        (out/"private-provenance.json").write_text(json.dumps(private,indent=2)+"\n")
        results["provenance"]={"pinned_simulator_sha256":pin,
            "extra_simulator_sha256":{key:digest(source/"nv_sensor_sim"/key) for key in EXTRAS},
            "simos_NV_sha256":digest(package_source),"simos_constants_sha256":digest(constants.__file__),
            "versions":{p:importlib.metadata.version(p) for p in ("numpy","scipy","simos","qutip")}}
        factor=fixed_amplitude_factor()
        results["global_amplitude_factor"]=factor
        cases=[
            Point(field_uT=45,theta=0,bias_uT=0),
            Point(field_uT=45,theta=0,bias_uT=1000),
            Point(field_uT=20,theta=np.pi/2,phi=0,width_mhz=1.5),
            Point(field_uT=70,theta=np.pi/2,phi=np.pi/4,bias_uT=250,width_mhz=7),
            Point(field_uT=45,theta=np.pi/3,phi=np.pi/4,bias_uT=500),
            Point(field_uT=20,theta=np.pi/3,phi=0,bias_uT=1000,width_mhz=1.5),
        ]
        parity=[]
        for p in cases:
            config=SimulationConfig(use_optics=False,include_nitrogen=False,
                n_freq_points=100,mw_freq_range_Hz=(2.82e9,2.92e9))
            config.temperature_K=p.temperature_K
            config.B_field_T=(field_vector(p)+[0,0,p.bias_uT])*1e-6
            p1=(np.pi*p.width_mhz*1e6-1/1.48e-6)*9.9e-6
            config.p1_concentration_ppm=p1
            f,raw,_=corrupt_spectrum(SimOSAdapter(config),config,p.gradient,0.,
                                    p1_ppm=p1,mw_power_scale=p.mw_scale)
            for mode in ("historical","fixed_amplitude"):
                dep=1-raw
                scale=p.contrast/dep.max() if mode=="historical" else factor*(p.contrast/.015)
                ref=1-dep*scale
                ref=np.interp(f-p.center_mhz*1e6,f,ref,left=ref[0],right=ref[-1])
                ref+=p.slope*(f-(f[0]+f[-1])/2)/(f[-1]-f[0])
                actual,_=forward(p,mode,factor)
                err=float(np.max(abs(actual-ref)))
                check(err<=1e-8,"forward parity")
                parity.append({"point":asdict(p),"normalization":mode,"max_abs_error":err})
        results["parity"]=parity;results["checks"].append("12 manufactured forward parity cases")
        x=np.linspace(-50,50,100);derivatives=[]
        for par in ([1,.0002,.3,1.5,.01,.014,2.5],[1,-.0002,-1,3,.005,.02,.8]):
            par=np.array(par,float);analytic=lorentzian_jacobian(x,par)
            for step in (1e-4,3e-5,1e-5):
                numeric=[]
                for j in range(7):
                    h=step*max(abs(par[j]),1e-2)
                    hi=par.copy();lo=par.copy();hi[j]+=h;lo[j]-=h
                    numeric.append((lorentzian_profile(x,hi)-lorentzian_profile(x,lo))/(2*h))
                numeric=np.column_stack(numeric)
                error=np.linalg.norm(numeric-analytic,axis=0)/np.maximum(np.linalg.norm(analytic,axis=0),1e-7)
                check(float(error.max())<1e-5,"Lorentzian analytic derivative")
                derivatives.append(float(error.max()))
        results["analytic_derivative_max_relative_error"]=max(derivatives)
        results["checks"].append("analytic Lorentzian Jacobian at three steps")
        preflight=[]
        results["preflight_derivatives"]=preflight
        for p in cases:
            for mode in ("historical","fixed_amplitude"):
                for cart in (False,True):
                    _,_,d=finite_jacobian(p,mode,factor,cart)
                    preflight.append({"point":asdict(p),"normalization":mode,"cartesian":cart,**d})
                    check(d["derivative_stable"],"forward derivative stability")
        results["preflight_derivatives"]=preflight
        results["checks"].append("24 manufactured finite-difference convergence checks")
        a,b=20.,70.
        closed=(b*b/6+a*a/2-(2/3)*a*np.sqrt(a*b))/(b-a)
        numeric=quad(lambda q:(np.sqrt(b)-np.sqrt(max(a,q)))**2/(b-a),
                     0,b,points=[a],epsabs=1e-11,epsrel=1e-11)[0]
        check(abs(numeric-closed)<1e-9,"projection Bayes oracle quadrature")
        results["analytic_prior"]={"projection_only_bayes_MAE_uT":closed,
            "quadrature_MAE_uT":numeric,"constant_MAE_uT":(b-a)/4,
            "constant_RMSE_uT":(b-a)/np.sqrt(12),
            "warning":"Reduced projection model only; not a full-physics lower bound."}
        results["checks"].append("projection-only oracle integral")
        mu=np.ones(100);j=np.column_stack((np.sin(np.linspace(0,3,100)),np.ones(100)))
        fixed=fisher_bound(mu,j[:,:1],1e6,[1],1e-10)
        nuisance=fisher_bound(mu,j,1e6,[1,0],1e-10)
        check(nuisance["std_bound_uT"]>=fixed["std_bound_uT"],"nuisance monotonicity")
        repeat=fisher_bound(np.r_[mu,mu],np.vstack([j,j]),1e6,[1,0],1e-10)
        check(abs(repeat["std_bound_uT"]*np.sqrt(2)/nuisance["std_bound_uT"]-1)<1e-12,"replicate additivity")
        null=fisher_bound(mu,np.ones((100,2)),1e6,[1,0],1e-10)
        check(null["std_bound_uT"] is None and not null["identifiable"],"null target not pseudoinverse")
        check(abs(np.sqrt(1e6/(1e6+.5))-1)<1e-6,"Gaussian/Poisson high-count limit")
        results["checks"].append("nuisance, replicate, nullspace and high-count Fisher checks")
        results["status"]="pass"
    except Exception as exc:
        results["status"]="fail";results["error"]=type(exc).__name__+": "+str(exc)
        raise
    finally:
        (out/"validation.json").write_text(json.dumps(results,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":results["status"],"checks":results["checks"],
                      "max_parity":max(x["max_abs_error"] for x in results["parity"])},indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--sim-source",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();validate(a.sim_source,a.out)
