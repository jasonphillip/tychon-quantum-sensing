"""Saved prediction arithmetic only; all invalid cases remain in denominators."""
import numpy as np
from experiments.localisation_redesign.metrics import errors, summary, ratio


def resampling_bounds(a,b,groups,seed,replicates,quantiles):
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        return {str(q):{"ratio":None,"absolute_mean_um":None} for q in quantiles}
    unique=np.unique(groups)
    totals_a=np.array([a[groups==g].sum() for g in unique])
    totals_b=np.array([b[groups==g].sum() for g in unique])
    counts=np.array([(groups==g).sum() for g in unique])
    choices=np.random.default_rng(np.random.SeedSequence(seed)).integers(0,len(unique),size=(replicates,len(unique)))
    da,db,n=totals_a[choices].sum(1),totals_b[choices].sum(1),counts[choices].sum(1)
    return {str(q):{"ratio":float(np.quantile(da/db,q)) if (db>0).all() else None,
                   "absolute_mean_um":float(np.quantile(da/n,q))} for q in quantiles}


def evaluate(labels,small,full,groups,protocol,seed):
    a,b=errors(small,labels),errors(full,labels)
    sa,sb=summary(a),summary(b)
    uncertainty=protocol["uncertainty"]
    bounds=resampling_bounds(a,b,groups,seed,uncertainty["bootstrap_replicates"],
                             [uncertainty["primary_quantile"],uncertainty["additional_search_adjusted_quantile"]])
    mean_ratio=ratio(sa["mean_error_um"],sb["mean_error_um"])
    tail_ratio=ratio(sa["p95_error_um"],sb["p95_error_um"])
    g=protocol["gates"];cal=protocol["calibration"]
    under=lambda value,limit:value is not None and value<=limit
    criteria={"all25_cases":len(labels)==25 and len(np.unique(labels,axis=0))==25,
              "five_whole_spatial_groups":len(np.unique(groups))==5,
              "full_coverage":sa["coverage"]==1.0 and sb["coverage"]==1.0,
              "half_unique_calibration":cal["small_unique_positions"]/cal["full_unique_positions"]<=g["maximum_calibration_ratio"],
              "mean_ratio":under(mean_ratio,g["maximum_mean_ratio"]),
              "p95_ratio":under(tail_ratio,g["maximum_p95_ratio"]),
              "absolute_mean":under(sa["mean_error_um"],g["maximum_mean_error_um"]),
              "absolute_p95":under(sa["p95_error_um"],g["maximum_p95_error_um"])}
    required={str(uncertainty["primary_quantile"])}
    if uncertainty["additional_is_required"]:
        required.add(str(uncertainty["additional_search_adjusted_quantile"]))
    for quantile,upper in bounds.items():
        if quantile not in required:
            continue
        criteria["ratio_upper_"+quantile]=under(upper["ratio"],g["maximum_conditional_upper_mean_ratio"])
        criteria["absolute_upper_"+quantile]=under(upper["absolute_mean_um"],g["maximum_conditional_upper_mean_error_um"])
    stripe_results=[]
    for group in np.unique(groups):
        chosen=groups==group
        stripe_results.append({"group_id":str(group),"small":summary(a[chosen]),"full":summary(b[chosen]),
                               "case_indices":np.flatnonzero(chosen).tolist()})
    return {"status":"PASS" if all(criteria.values()) else "FAIL","criteria":criteria,
            "small":sa,"full":sb,"mean_ratio":mean_ratio,"p95_ratio":tail_ratio,
            "conditional_whole_stripe_upper_bounds":bounds,
            "required_uncertainty_quantiles":sorted(required),
            "sensitivity_only_quantiles":[q for q in bounds if q not in required],
            "stripes":stripe_results,"subgroup_selection":False,
            "per_case_small_error_um":[float(v) if np.isfinite(v) else None for v in a],
            "per_case_full_error_um":[float(v) if np.isfinite(v) else None for v in b],
            "invalid_error_semantics":"infinite_error;aggregate_null;automatic_failure",
            "scope":protocol["scope"],"independent_acquisitions":1,
            "population_day_uncertainty_estimated":False,"original_spatial_verdict":"FAIL"}
