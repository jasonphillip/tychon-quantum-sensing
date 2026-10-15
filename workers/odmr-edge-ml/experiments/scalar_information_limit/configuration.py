"""Reject registration drift; formulas remain bound to recorded source hashes."""
import ast,hashlib,json
from dataclasses import asdict
from pathlib import Path
from forward import Point,D_HZ,ELECTRON_GAMMA,NV_GAMMA,FREQUENCIES_MHZ
from information import STEPS
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def function_source(path,name):
    text=Path(path).read_text()
    node=next(x for x in ast.parse(text).body if isinstance(x,ast.FunctionDef) and x.name==name)
    return ast.get_source_segment(text,node)
def validate_registration(r):
    expected={"electron_gamma_rad_per_s_T":ELECTRON_GAMMA,
        "nv_gamma_multiplier":1.000357,"D_Hz":D_HZ,"temperature_slope_Hz_per_K":-74200,
        "frequency_Hz":{"start":int(FREQUENCIES_MHZ[0]*1e6),
            "stop":int(FREQUENCIES_MHZ[-1]*1e6),"count":len(FREQUENCIES_MHZ)},
        "fixed":{"temperature_K":293.15,"contrast":.015,"mw_scale":1.,
            "mw_gradient":.196875,"spatial_bins":10,"background_slope":.02,"frequency_offset_MHz":.3},
        "grid":{"field_uT":[20,45,70],"cos_theta":[0,.5,1],
            "azimuth_rad":[0,0.7853981633974483],"bias_uT":[0,250,500,1000],
            "linewidth_FWHM_MHz":[1.5,5,7],"reference_SNR":[3,10]},
        "analytic_prior":{"magnitude_uniform_uT":[20,70],"cos_theta_uniform":[-1,1]},
        "global_amplitude_reference":{"field_uT":45,"bias_uT":1000,"theta":0,"phi":0,
            "linewidth_FWHM_MHz":5,"temperature_K":293.15,"mw_scale":1,
            "gradient":.196875,"before_interpolation":True}}
    for key,value in expected.items():
        actual=r[key]
        if key=="analytic_prior":actual={k:actual[k] for k in value}
        if actual!=value:raise ValueError("registration mismatch: "+key)
    if r["jacobian_steps"]["relative"]!=list(STEPS):raise ValueError("step mismatch")
    p=asdict(Point())
    for key,value in {"temperature_K":293.15,"contrast":.015,"mw_scale":1.,
                     "gradient":.196875,"slope":.02,"center_mhz":.3}.items():
        if p[key]!=value:raise ValueError("Point fixed value mismatch: "+key)
    if NV_GAMMA!=ELECTRON_GAMMA*1.000357:raise ValueError("gamma mismatch")
    return expected
def bind_preflight(preflight,original_information,clarification):
    previous=json.loads(Path(preflight).read_text())
    amendment=json.loads(Path(clarification).read_text())
    if previous["status"]!="fail" or previous["error"]!="AssertionError: forward derivative stability":
        raise ValueError("unexpected historical preflight result")
    if amendment["diagnostic_retry_sha256"]!=sha(preflight):raise ValueError("clarification/preflight hash mismatch")
    expected_checks=["12 manufactured forward parity cases","analytic Lorentzian Jacobian at three steps"]
    if previous["checks"]!=expected_checks:raise ValueError("historical passing evidence absent")
    here=Path(__file__).parent
    if sha(here/"forward.py")!=previous["implementation_sha256"]["forward.py"]:
        raise ValueError("forward changed after parity")
    if sha(original_information)!=previous["implementation_sha256"]["information.py"]:
        raise ValueError("original derivative/Fisher source receipt mismatch")
    for name in ("lorentzian_profile","lorentzian_jacobian","fisher_bound"):
        if function_source(original_information,name)!=function_source(here/"information.py",name):
            raise ValueError("previously checked function changed: "+name)
    return {"preflight_sha256":sha(preflight),"clarification_sha256":sha(clarification),
        "forward_sha256":sha(here/"forward.py"),
        "original_information_sha256":sha(original_information),
        "original_status":"fail: branch classification; passing checks retained"}
