"""New exact spin-matrix checks for the recorded symmetry-only correction."""
import argparse,json
from pathlib import Path
import numpy as np
from configuration import sha
from forward import Point,SX,SY,SZ
from information import symmetry_zeros,ladder_validity
def run(correction,remaining,out):
    out.mkdir(parents=True,exist_ok=False)
    report={"status":"running","correction_sha256":sha(correction),"remaining_checks_sha256":sha(remaining),
        "implementation_sha256":{p.name:sha(p) for p in Path(__file__).parent.glob("*.py")},"checks":[]}
    try:
        if json.loads(remaining.read_text())["status"]!="pass":raise AssertionError("earlier invariant evidence")
        ux=np.eye(3)-2*(SX@SX);uz=np.diag([-1.,1.,-1.]);identity=np.eye(3)
        residuals=[]
        for label,u,conjugate,signs in [
            ("Bz reversal Rx(pi)K",ux,True,[1,1,-1]),
            ("By reversal K",identity,True,[1,-1,1]),
            ("Bx reversal Rz(pi)K",uz,True,[-1,1,1]),
            ("theta reversal at pole Rz(pi)",uz,False,[-1,-1,1])]:
            for op,sign in zip((SX,SY,SZ),signs):
                actual=u@(op.conj() if conjugate else op)@u.conj().T
                residuals.append(float(np.linalg.norm(actual-sign*op)))
            z2=SZ@SZ
            residuals.append(float(np.linalg.norm(u@z2@u.conj().T-z2)))
            zero=np.diag([0.,1.,0.])
            residuals.append(float(np.linalg.norm(u@zero@u.conj().T-zero)))
            if max(residuals)>1e-14:raise AssertionError("exact spin-matrix symmetry")
            report["checks"].append(label+": Hamiltonian operators, ms0 projector and squared Sx invariance")
        p=Point(field_uT=45,theta=np.pi/2,phi=np.pi/4)
        if set(symmetry_zeros(p))!={5}:raise AssertionError("perpendicular theta rule")
        if set(symmetry_zeros(p,True))!={2}:raise AssertionError("perpendicular Bz rule")
        if 5 in symmetry_zeros(Point(theta=np.pi/2,phi=np.pi/4,bias_uT=250)):
            raise AssertionError("bias breaks reversal around original Bz=0")
        if symmetry_zeros(Point(theta=np.pi/3,phi=np.pi/4)):
            raise AssertionError("no unproved generic zero")
        d={"parameter_names":["B","center","width","contrast","slope","theta","phi"],
           "column_branch_crossed":[False]*7,"derivative_relative_error":[0]*5+[.03,0],
           "symmetry_zero_columns":[False]*5+[True,False],"coordinate_singularity":False}
        if not ladder_validity(d,list(range(7)),"spherical")[0]:raise AssertionError("proved zero accepted")
        d["column_branch_crossed"][5]=True
        if ladder_validity(d,list(range(7)),"spherical")[0]:raise AssertionError("branch still unavailable")
        report["checks"].append("exact predicates and branch precedence")
        report["maximum_operator_residual"]=max(residuals);report["status"]="pass"
    except Exception as exc:
        report["status"]="fail";report["error"]=type(exc).__name__+": "+str(exc);raise
    finally:(out/"checks.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("correction","remaining","out"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();run(a.correction,a.remaining,a.out)
