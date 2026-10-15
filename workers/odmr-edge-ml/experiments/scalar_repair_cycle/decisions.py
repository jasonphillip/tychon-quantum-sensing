"""Frozen validation selection and conjunctive primary-condition decisions."""
import numpy as np
from estimators import paired_ci
PRIMARY=("clean","realistic_anchor")
SEEDS=(42,20261014,20261015)
def prediction_gate(summary,label):
    checks={}
    for cell in PRIMARY:
        x=summary[cell]
        checks[cell]=bool(x["decision_metrics"][label]["p90_abs_uT"]<=25 and
            all(x["paired_comparisons"][label+"_minus_"+b]["ci95_uT"][1]<-.5
                for b in ("training_mean","training_median")))
    return dict(passed=all(checks.values()),conditions=checks)
def rank(summary,labels):
    cell=summary["realistic_anchor"]
    best=min(cell["decision_metrics"][k]["mae_uT"] for k in labels)
    tied=[k for k in labels if cell["decision_metrics"][k]["mae_uT"]<best+.1]
    return min(tied,key=lambda k:(cell["decision_metrics"][k]["hard_invalid_fraction"],
        cell["decision_metrics"][k]["median_pipeline_seconds"],k))
def decide(summary):
    gates={k:prediction_gate(summary,k) for k in
        ("robust_prior_fit","conditional_likelihood","edge_ols__int8","joint_fit__int8")}
    classical_labels=["robust_prior_fit","conditional_likelihood"]
    neural_labels=["edge_ols__int8","joint_fit__int8"]
    classical=rank(summary,[k for k in classical_labels if gates[k]["passed"]] or classical_labels)
    neural=rank(summary,[k for k in neural_labels if gates[k]["passed"]] or neural_labels)
    return dict(classical=classical,neural=neural,primary_implementation="int8",claim_route="accuracy",
        gates=gates,can_proceed=any(g["passed"] for g in gates.values()))
def final_decision(summary,selection):
    classical,neural=selection["classical"],selection["neural"]
    neural_gate=prediction_gate(summary,neural)
    classical_gate=prediction_gate(summary,classical)
    advantage=neural_gate["passed"] and all(
        summary[c]["paired_comparisons"][neural+"_minus_"+classical]["ci95_uT"][1]<-.5 for c in PRIMARY)
    neural_reliable=neural_gate["passed"] and all(
        summary[c]["decision_metrics"][neural]["all_seeds_reliable"] for c in PRIMARY)
    classical_reliable=classical_gate["passed"] and all(
        summary[c]["decision_metrics"][classical]["valid_fraction"]>=.95 for c in PRIMARY)
    if advantage:outcome="neural_accuracy_advantage"
    elif classical_gate["passed"]:outcome="classical_reference"
    elif neural_gate["passed"]:outcome="prior_aided_prediction_without_confirmed_neural_advantage"
    else:outcome="neither_selected_method_passed"
    policy=neural.removesuffix("__int8")
    quantization={}
    for seed in SEEDS:
        key=f"{policy}_seed{seed}_int8_minus_fp32"
        quantization[str(seed)]=all(summary[c]["paired_comparisons"].get(key,{"ci95_uT":[0,float("inf")]})["ci95_uT"][1]<=.5 for c in PRIMARY)
    mean_quant=all(summary[c]["paired_comparisons"].get(policy+"_mean_int8_minus_fp32",{"ci95_uT":[0,float("inf")]})["ci95_uT"][1]<=.5 for c in PRIMARY)
    uncertain=any(summary[c]["paired_comparisons"][neural+"_minus_"+classical]["ci95_uT"][0]<-.5<=
        summary[c]["paired_comparisons"][neural+"_minus_"+classical]["ci95_uT"][1] for c in PRIMARY)
    return dict(outcome=outcome,neural_accuracy_advantage=bool(advantage),
        neural_advantage_status="confirmed" if advantage else ("inconclusive" if uncertain else "not_established"),
        int8_preserves_mean=bool(mean_quant),int8_preserves_per_seed=quantization,
        neural_prediction_gate=neural_gate,classical_prediction_gate=classical_gate,
        neural_reliable=bool(neural_reliable),classical_reliable=bool(classical_reliable),
        scope="synthetic prior-aided magnitude prediction; ambiguity retained")
