"""Phenomenological repeated syndromes around the unchanged d3 lookup table."""
from pathlib import Path
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parent
QEC=ROOT.parent
sys.path.insert(0,str(QEC))
import qec_model as code


def fixed_table():
    return np.array(json.loads((QEC/"artifacts/mac_retry/correction_tables.json").read_text())["fixed_ml"],dtype=np.uint32)


def syndrome_words(errors):
    errors=np.asarray(errors,dtype=np.uint32)
    result=np.zeros(errors.shape,dtype=np.uint8)
    for index,support in enumerate(code.Z_SUPPORTS+code.X_SUPPORTS):
        bit=np.zeros(errors.shape,dtype=np.uint8)
        shift=0 if index<4 else 9
        for qubit in support:
            bit ^= ((errors>>(qubit+shift))&1).astype(np.uint8)
        result |= bit << index
    return result


def words_to_bits(words):
    return ((np.asarray(words)[...,None]>>np.arange(8))&1).astype(np.uint8)


def bits_to_words(bits):
    return np.sum(np.asarray(bits,dtype=np.uint32)*(1<<np.arange(bits.shape[-1])),axis=-1,dtype=np.uint32)


def sample_histories(trials,rounds,p,q,data_seed,measurement_seed):
    data_rng=np.random.default_rng(data_seed)
    occur=data_rng.random((trials,rounds,9))<p
    pauli=data_rng.integers(1,4,size=(trials,rounds,9),dtype=np.uint8)*occur
    x=bits_to_words(pauli&1)
    z=bits_to_words(pauli>>1)
    increments=x|(z<<9)
    accumulated=np.bitwise_xor.accumulate(increments,axis=1)
    true_syndrome=syndrome_words(accumulated)
    measurement_rng=np.random.default_rng(measurement_seed)
    measurement_masks=bits_to_words(measurement_rng.random((trials,rounds,8))<q).astype(np.uint8)
    observed=true_syndrome^measurement_masks
    return increments,accumulated,observed,measurement_masks


def compress(observed):
    rounds=observed.shape[1]
    if rounds%2!=1:
        raise ValueError("odd number of rounds required")
    majority=bits_to_words(words_to_bits(observed).sum(axis=1)>rounds//2).astype(np.uint8)
    return observed[:,-1].copy(),majority


def detection_events(observed,terminal):
    complete=np.concatenate([observed,np.asarray(terminal)[:,None]],axis=1)
    difference=complete.copy()
    difference[:,1:] ^= complete[:,:-1]
    return words_to_bits(difference)


def graph_matrix(supports,rounds,p,q):
    """Exact space-time parity map; no extra data interval before terminal closure."""
    rows=4*(rounds+1)
    columns=[]; faults=[]; weights=[]; labels=[]
    data_probability=2*p/3
    if data_probability>0:
        for t in range(rounds):
            for qubit in range(9):
                column=np.zeros(rows,dtype=np.uint8)
                for check,support in enumerate(supports):
                    if qubit in support:
                        column[4*t+check]=1
                fault=np.zeros(9,dtype=np.uint8); fault[qubit]=1
                columns.append(column); faults.append(fault)
                weights.append(float(np.log((1-data_probability)/data_probability)))
                labels.append(("data",t,qubit))
    if q>0:
        for t in range(rounds):
            for check in range(4):
                column=np.zeros(rows,dtype=np.uint8)
                column[4*t+check]=1; column[4*(t+1)+check]=1
                columns.append(column); faults.append(np.zeros(9,dtype=np.uint8))
                weights.append(float(np.log((1-q)/q)))
                labels.append(("measurement",t,check))
    if not columns:
        return np.zeros((rows,0),dtype=np.uint8),np.zeros((9,0),dtype=np.uint8),np.array([]),labels
    return np.array(columns,dtype=np.uint8).T,np.array(faults,dtype=np.uint8).T,np.asarray(weights),labels


class SpaceTimeMatching:
    def __init__(self,rounds,p,q):
        import pymatching
        from scipy.sparse import csc_matrix
        self.rounds=rounds
        self.matchers=[]
        self.graphs=[]
        for supports in (code.Z_SUPPORTS,code.X_SUPPORTS):
            h,f,w,labels=graph_matrix(supports,rounds,p,q)
            if h.shape[1]:
                matcher=pymatching.Matching.from_check_matrix(csc_matrix(h),weights=w,faults_matrix=csc_matrix(f))
            else:
                matcher=None
            self.matchers.append(matcher)
            self.graphs.append((h,f,w,labels))

    def decode(self,observed,terminal):
        events=detection_events(observed,terminal)
        correction=[]
        for sector,matcher in enumerate(self.matchers):
            if matcher is None:
                result=np.zeros((len(observed),9),dtype=np.uint8)
                if np.any(events[:,:,4*sector:4*(sector+1)]):
                    raise ValueError("nonzero events in noiseless graph")
            else:
                result=matcher.decode_batch(np.ascontiguousarray(events[:,:,4*sector:4*(sector+1)].reshape(len(observed),-1)))
                if result.shape!=(len(observed),9):
                    raise AssertionError(f"Unexpected PyMatching correction shape {result.shape}")
            correction.append(bits_to_words(result))
        return correction[0]|(correction[1]<<9)


def failure_flags(final_error,correction):
    residual=np.asarray(final_error,dtype=np.uint32)^np.asarray(correction,dtype=np.uint32)
    syndrome_nonzero=syndrome_words(residual)!=0
    logical_x=np.zeros(residual.shape,dtype=np.uint8)
    logical_z=np.zeros(residual.shape,dtype=np.uint8)
    for qubit in (0,1,2):
        logical_x ^= ((residual>>qubit)&1).astype(np.uint8)
    for qubit in (0,3,6):
        logical_z ^= ((residual>>(qubit+9))&1).astype(np.uint8)
    logical_failure=(~syndrome_nonzero)&((logical_x|logical_z)!=0)
    return syndrome_nonzero,logical_failure


def wilson(failures,trials):
    z=1.959963984540054
    p=failures/trials
    denominator=1+z*z/trials
    center=(p+z*z/(2*trials))/denominator
    radius=z*np.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/denominator
    return [float(max(0,center-radius)),float(min(1,center+radius))]
