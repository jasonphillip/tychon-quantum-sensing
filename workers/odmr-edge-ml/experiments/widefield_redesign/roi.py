"""Observation-only ROI geometry and bounded global per-frame registration."""
import numpy as np
from scipy.ndimage import gaussian_filter,median_filter,label,binary_dilation,map_coordinates


def detect(template):
    if template.shape!=(512,512) or not np.isfinite(template).all(): raise ValueError('Invalid observation template')
    blurred=gaussian_filter(template,.8,mode='reflect')
    residual=blurred-median_filter(blurred,size=31,mode='reflect')
    median=float(np.median(residual)); mad=float(1.4826*np.median(np.abs(residual-median)))
    if mad<=0: raise ValueError('Zero fluorescence noise scale; qualification undefined')
    labels,count=label(residual>median+6*mad,structure=np.ones((3,3),int))
    candidates=[]; rejected=[]
    for k in range(1,count+1):
        yy,xx=np.where(labels==k); area=len(yy)
        if not (3<=area<=49) or np.ptp(yy)>6 or np.ptp(xx)>6:
            rejected.append({'component':k,'reason':'observed_size'}); continue
        weight=np.maximum(residual[yy,xx]-median,0)
        cy,cx=[int(np.rint(np.sum(v*weight)/weight.sum())) for v in (yy,xx)]
        if min(cy,cx,511-cy,511-cx)<8 or np.max(np.abs(yy-cy))>3 or np.max(np.abs(xx-cx))>3:
            rejected.append({'component':k,'reason':'observed_boundary'}); continue
        footprint=binary_dilation(labels[cy-4:cy+5,cx-4:cx+5]==k,structure=np.ones((3,3),bool))
        candidates.append({'component':k,'y':cy,'x':cx,'mask':footprint})
    accepted=[]
    for c in candidates:
        crowded=any(d is not c and max(abs(d['y']-c['y']),abs(d['x']-c['x']))<12 for d in candidates)
        if crowded: rejected.append({'component':c['component'],'reason':'observed_crowding'})
        else: accepted.append(c)
    accepted.sort(key=lambda c:(c['y'],c['x']))
    return accepted,{'detected_components':count,'mad':mad,'threshold':median+6*mad,'rejected':rejected}


def registration_coordinates(rois):
    dy,dx=np.meshgrid(np.arange(-4,5),np.arange(-4,5),indexing='ij')
    y=np.concatenate([r['y']+dy.ravel() for r in rois]); x=np.concatenate([r['x']+dx.ravel() for r in rois])
    return y,x


def register(frame,template,coordinates):
    y,x=coordinates; ref=template[y,x]; ref=ref-ref.mean(); refnorm=np.linalg.norm(ref)
    shifts=[(dy,dx) for dy in range(-3,4) for dx in range(-3,4)]
    if refnorm<=0: return (0,0),True,{'correlation':None,'margin':None,'best_shift':[0,0]}
    scores=[]
    for dy,dx in shifts:
        sample=np.asarray(frame[y+dy,x+dx],float); sample-=sample.mean(); denom=np.linalg.norm(sample)*refnorm
        scores.append(float(sample@ref/denom) if denom>0 else -1.)
    order=sorted(range(49),key=lambda i:(-scores[i],shifts[i]))
    best=shifts[order[0]]; corr=scores[order[0]]; margin=corr-scores[order[1]]
    refined=list(map(float,best))
    if max(abs(v) for v in best)<=2:
        grid=np.asarray(scores).reshape(7,7); iy,ix=best[0]+3,best[1]+3
        for axis,neighbours in enumerate(((grid[iy-1,ix],grid[iy,ix],grid[iy+1,ix]),(grid[iy,ix-1],grid[iy,ix],grid[iy,ix+1]))):
            left,middle,right=neighbours; curvature=left-2*middle+right
            refined[axis]+=float(np.clip(.5*(left-right)/curvature,-.5,.5)) if curvature < -1e-12 else 0.
        sample=map_coordinates(np.asarray(frame,float),[y+refined[0],x+refined[1]],order=1,mode='constant',cval=np.nan)
        sample-=sample.mean(); denom=np.linalg.norm(sample)*refnorm
        corr=float(sample@ref/denom) if denom>0 else -1.
    bad=not np.isfinite(corr) or corr<.9 or max(abs(v) for v in refined)>2
    return ((0.,0.) if bad else tuple(refined)),bad,{'correlation':corr,'margin':margin,'ambiguous_integer_peak':margin<.002,'best_shift':list(best),'refined_shift':refined,'normalized_residual':2*(1-corr)}


def integrate(frame,rois,shift):
    dy,dx=shift; values=[]; clipped=[]
    for r in rois:
        yy,xx=np.meshgrid(np.arange(-4,5)+r['y']+dy,np.arange(-4,5)+r['x']+dx,indexing='ij')
        patch=map_coordinates(np.asarray(frame,float),[yy,xx],order=1,mode='constant',cval=np.nan)
        values.append(float(patch[r['mask']].mean()))
        fy,fx=np.floor(yy).astype(int),np.floor(xx).astype(int); wy,wx=yy-fy,xx-fx
        bad=False
        for sy,sx,weight in [(0,0,(1-wy)*(1-wx)),(1,0,wy*(1-wx)),(0,1,(1-wy)*wx),(1,1,wy*wx)]:
            sample=frame[fy+sy,fx+sx]; support=r['mask'] & (weight>0)
            bad |= bool(np.any(((sample==0)|(sample==65535)) & support))
        clipped.append(bad)
    return np.asarray(values),np.asarray(clipped,bool)
