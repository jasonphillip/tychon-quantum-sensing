"""Local Fisher information with explicit scaled coordinates and null tests."""
from dataclasses import replace
import numpy as np
from forward import forward, field_vector

PARAMETERS=("field_uT","center_mhz","width_mhz","contrast","slope","theta","phi")
SCALES=np.array([45.,1.,5.,.015,.02,1.,1.])
CART_SCALES=np.array([45.,45.,45.,1.,5.,.015,.02])
STEPS=(1e-4,3e-5,1e-5)
LADDERS={"fixed":[0],"center":[0,1],"shape":[0,1,2,3,4],
         "direction_shape":[0,1,2,3,4,5,6]}
CUTOFFS=(1e-8,1e-10,1e-12)

def symmetry_zeros(p,cartesian=False):
    """Exact registered-coordinate predicates; no numerical closeness tolerance."""
    rules={}
    if cartesian:
        if p.theta==0.:rules[0]="Bx=0: Rz(pi)K reverses Bx; squared Sx strength unchanged"
        if p.theta==0. or p.phi==0.:rules[1]="By=0: complex conjugation reverses By"
        if p.bias_uT==0. and p.theta==np.pi/2:
            rules[2]="Bz=0: Rx(pi)K reverses Bz"
    else:
        if p.theta==0.:rules[5]="theta=0: Rz(pi) makes theta+h and theta-h equivalent"
        if p.bias_uT==0. and p.theta==np.pi/2:
            rules[5]="bias=0, theta=pi/2: Rx(pi)K makes theta+h and theta-h equivalent"
        if p.theta==0.:rules[6]="theta=0: field vector is independent of phi"
        elif p.phi==0.:rules[6]="phi=0: complex conjugation makes phi+h and phi-h equivalent"
    return rules

def finite_jacobian(p,normalization,factor,cartesian=False):
    mu,base=forward(p,normalization,factor)
    all_j=[];events=[[] for _ in range(7)]
    vector=field_vector(p)
    names=("bx","by","bz","center_mhz","width_mhz","contrast","slope") if cartesian else PARAMETERS
    scales=CART_SCALES if cartesian else SCALES
    for step in STEPS:
        columns=[]
        for k,name in enumerate(names):
            h=step*scales[k]
            if cartesian and k<3:
                plus=vector.copy();minus=vector.copy()
                plus[k]+=h;minus[k]-=h
                yp,dp=forward(p,normalization,factor,plus)
                ym,dm=forward(p,normalization,factor,minus)
            else:
                yp,dp=forward(replace(p,**{name:getattr(p,name)+h}),normalization,factor)
                ym,dm=forward(replace(p,**{name:getattr(p,name)-h}),normalization,factor)
            for side,diagnostic in (("plus",dp),("minus",dm)):
                for key,kind in (("allowed_transitions","transition_selection"),
                                 ("ms0_index","ms0_assignment"),
                                 ("max_bin","sampled_max")):
                    if kind=="sampled_max" and normalization!="historical":continue
                    if diagnostic[key]!=base[key]:
                        events[k].append({"step":step,"side":side,"kind":kind,
                            "base":base[key],"perturbed":diagnostic[key]})
            if name=="center_mhz":
                spacing=100/99
                # Interpolation changes slope at integer sample spacings, including zero.
                if np.floor((p.center_mhz-h)/spacing)!=np.floor((p.center_mhz+h)/spacing):
                    events[k].append({"step":step,"kind":"interpolation_knot"})
            columns.append((yp-ym)/(2*step)) # derivative with respect to scaled coordinates
        all_j.append(np.column_stack(columns))
    errors=[];differences=[];norms=[np.linalg.norm(a,axis=0).tolist() for a in all_j]
    for older,newer in zip(all_j[:-1],all_j[1:]):
        difference=np.linalg.norm(newer-older,axis=0)
        norm=np.maximum(np.linalg.norm(newer,axis=0),np.linalg.norm(older,axis=0))
        errors.append(difference/np.maximum(norm,1e-8))
        differences.append(difference.tolist())
    error=np.maximum(*errors)
    branches=[bool(e) for e in events]
    rules=symmetry_zeros(p,cartesian)
    zero=[k in rules for k in range(7)]
    valid=[bool((e<=.02 or z) and not b) for e,b,z in zip(error,branches,zero)]
    unexplained=[n for n,e,b,z in zip(names,error,branches,zero) if e>.02 and not b and not z]
    jacobian=all_j[-1].copy()
    for k in rules:jacobian[:,k]=0.
    return mu,jacobian,{"parameter_names":list(names),
        "derivative_relative_error":error.tolist(),
        "raw_derivative_column_norms":norms,"raw_pair_difference_norms":differences,
        "symmetry_zero_columns":zero,"symmetry_rules":{names[k]:v for k,v in rules.items()},
        "derivative_max_relative_error":float(error.max()),
        "derivative_stable":all(valid),"column_valid":valid,
        "column_branch_crossed":branches,"branch_events":dict(zip(names,events)),
        "unexplained_nonconvergent_columns":unexplained,
        "branch_crossed":any(branches),
        "coordinate_singularity":bool(not cartesian and abs(np.sin(p.theta))<1e-8),
        **base}

def ladder_validity(diagnostics,indices,coordinate_system):
    reasons=[]
    for i in indices:
        name=diagnostics["parameter_names"][i]
        if diagnostics["column_branch_crossed"][i]:
            reasons.append(name+":branch")
        if diagnostics["derivative_relative_error"][i]>.02 and not diagnostics.get("symmetry_zero_columns",[False]*7)[i]:
            reasons.append(name+":nonconvergent")
    if coordinate_system=="spherical" and diagnostics["coordinate_singularity"] and any(i>=5 for i in indices):
        reasons.append("spherical_polar_coordinate_singularity")
    return not reasons,reasons

def unavailable_bound(dimension,cutoff,reasons):
    return {"std_bound_uT":None,"identifiable":None,"rank":None,
        "dimension":dimension,"singular_values":None,"svd_relative_cutoff":cutoff,
        "null_target_fraction":None,"condition_retained":None,
        "validity":"unavailable","unavailable_reasons":reasons}

def masked_bound(mu,jacobian,photons,target_gradient,cutoff,diagnostics,indices,coordinates):
    valid,reasons=ladder_validity(diagnostics,indices,coordinates)
    if not valid:return unavailable_bound(len(target_gradient),cutoff,reasons)
    result=fisher_bound(mu,jacobian,photons,target_gradient,cutoff)
    result.update({"validity":"regular","unavailable_reasons":[]})
    return result

def fisher_bound(mu,jacobian,photons,target_gradient,cutoff):
    weight=np.sqrt(photons/mu + .5/mu**2)
    weighted=weight[:,None]*jacobian
    _,singular,vt=np.linalg.svd(weighted,full_matrices=False)
    threshold=cutoff*singular[0] if len(singular) and singular[0]>0 else 0.
    keep=singular>threshold
    g=np.asarray(target_gradient,float)
    coordinates=vt@g
    null_fraction=float(np.linalg.norm(coordinates[~keep])/max(np.linalg.norm(g),1e-300))
    identifiable=bool(null_fraction<=1e-7 and np.any(keep))
    bound=float(np.sqrt(np.sum((coordinates[keep]/singular[keep])**2))) if identifiable else None
    return {"std_bound_uT":bound,"identifiable":identifiable,
        "rank":int(keep.sum()),"dimension":len(g),
        "singular_values":singular.tolist(),"svd_relative_cutoff":cutoff,
        "null_target_fraction":null_fraction,
        "condition_retained":float(singular[0]/singular[keep][-1]) if keep.any() else None}

def point_information(p,normalization,factor,snr):
    mu,jac,diagnostics=finite_jacobian(p,normalization,factor)
    photons=(snr/(.30*.015))**2
    rows=[]
    for name,indices in LADDERS.items():
        j=jac[:,indices];g=np.zeros(len(indices));g[0]=45.
        for cutoff in CUTOFFS:
            r=masked_bound(mu,j,photons,g,cutoff,diagnostics,indices,"spherical")
            r.update({"ladder":name,"coordinate_system":"spherical",**diagnostics})
            rows.append(r)
    cmu,cjac,cdiag=finite_jacobian(p,normalization,factor,cartesian=True)
    target=np.zeros(7);target[:3]=45*field_vector(p)/p.field_uT
    for cutoff in CUTOFFS:
        r=masked_bound(cmu,cjac,photons,target,cutoff,cdiag,list(range(7)),"cartesian")
        r.update({"ladder":"direction_shape","coordinate_system":"cartesian",**cdiag})
        rows.append(r)
    return rows

def lorentzian_profile(x,p):
    b,s,c,d,a,e,h=p
    u=(x-c+d/2)/h;v=(x-c-d/2)/h
    return b+s*x-a/(1+u*u)-e/(1+v*v)

def lorentzian_jacobian(x,p):
    b,s,c,d,a,e,h=p
    u=(x-c+d/2)/h;v=(x-c-d/2)/h
    l,r=1+u*u,1+v*v
    dc1=-2*a*u/(h*l*l);dc2=-2*e*v/(h*r*r)
    return np.column_stack([np.ones_like(x),x,dc1+dc2,(-dc1+dc2)/2,
        -1/l,-1/r,-2*(a*u*u/(l*l)+e*v*v/(r*r))/h])
