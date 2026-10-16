"""Saved sufficient statistics; no independence claim is inferred from repeat indices."""
import numpy as np
from experiments.widefield_redesign.operators import spectral_contrast,smooth


def sufficient(a,b,groups):
    ca,cb=spectral_contrast(a),spectral_contrast(b)
    result={k:np.zeros((16,168)) for k in ('a','b','aa','bb','ab')}
    result['counts']=np.bincount(groups,minlength=16).astype(np.int64)
    for group in range(16):
        aa,bb=ca[groups==group],cb[groups==group]
        for key,value in [('a',aa),('b',bb),('aa',aa*aa),('bb',bb*bb),('ab',aa*bb)]: result[key][group]=value.sum(axis=0)
    return result


def covariance(stats,indices):
    n=stats['counts'][indices].sum(axis=-1)
    if np.any(n<=0): raise ValueError('Empty resampled spatial coverage')
    totals={k:stats[k][indices].sum(axis=-2)/n[...,None] for k in ('a','b','aa','bb','ab')}
    s=np.mean(totals['ab']-totals['a']*totals['b'],axis=-1)
    nvar=.5*np.mean(totals['aa']+totals['bb']-2*totals['ab']-(totals['a']-totals['b'])**2,axis=-1)
    return s,np.maximum(nvar,0)


def decide(stats,indices,quality):
    occupied=np.flatnonzero(stats['counts'])
    if indices.shape!=(2000,len(occupied)) or indices.dtype.kind not in 'iu' or not np.isin(indices,occupied).all():
        raise ValueError('Wrong resampling indices')
    s,n=covariance(stats,occupied); bs,bn=covariance(stats,indices)
    reliability=float(s/(s+n)) if s+n>0 else None
    valid=(bs+bn)>0
    rlo=float(np.quantile(bs[valid]/(bs[valid]+bn[valid]),.025)) if valid.all() else None
    slo=float(np.quantile(bs,.025))
    checks={'minimum_spots':32<=int(stats['counts'].sum())<=512,'coverage':len(occupied)>=8,
            'positive_covariance':slo>0,'reliability_point':reliability is not None and reliability>=.5,
            'reliability_lower':rlo is not None and rlo>=.25,'clipping':quality['clip_fraction']<=.01,
            'registration':quality['bad_frame_fraction']<=.01}
    return {'signal':float(s),'disagreement':float(n),'reliability':reliability,'signal_ci_lower':slo,
            'reliability_ci_lower':rlo,'spots':int(stats['counts'].sum()),'occupied_superblocks':len(occupied),
            'quality':quality,'conditions':checks,'eligible':all(checks.values())}
