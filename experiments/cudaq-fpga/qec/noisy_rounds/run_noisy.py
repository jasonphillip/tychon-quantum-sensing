"""Frozen repeated-noisy-syndrome benchmark and deterministic FPGA replay export."""
import argparse
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import numpy as np
from noisy_model import (ROOT,QEC,code,fixed_table,sample_histories,syndrome_words,
                         compress,SpaceTimeMatching,failure_flags,wilson)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")


def classify(error,correction):
    unresolved,logical=failure_flags(error,correction)
    n=len(error)
    return {"trials":n,"failure_count":int(np.sum(unresolved|logical)),
            "failure_rate":float(np.mean(unresolved|logical)),
            "failure_rate_wilson_95":wilson(int(np.sum(unresolved|logical)),n),
            "residual_syndrome_count":int(np.sum(unresolved)),
            "codespace_logical_failure_count":int(np.sum(logical))},unresolved|logical


def c_reference(output,syndromes):
    compiler=shutil.which("clang++") or shutil.which("c++")
    if compiler is None: raise RuntimeError("C++ compiler required for exact board export")
    wrapper=output/"reference_wrapper.cpp"
    wrapper.write_text('#include "qec_decoder.h"\nextern "C" uint32_t qec_reference(uint8_t input) { return qec_decode(input); }\n')
    library=output/"qec_reference.so"
    command=[compiler,"-std=c++11","-O2","-Wall","-Wextra","-Werror","-shared","-fPIC","-I",str(QEC),str(QEC/"qec_decoder.cpp"),str(wrapper),"-o",str(library)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    write_json(output/"compile.json",{"command":command,"returncode":compiled.returncode,"stdout":compiled.stdout,"stderr":compiled.stderr})
    compiled.check_returncode()
    lib=ctypes.CDLL(str(library))
    lib.qec_reference.argtypes=[ctypes.c_uint8]
    lib.qec_reference.restype=ctypes.c_uint32
    return np.asarray([lib.qec_reference(int(s)) for s in syndromes],dtype=np.uint32)


def run(output):
    started=time.perf_counter()
    cfg_path=ROOT/"config.json"
    cfg=json.loads(cfg_path.read_text())
    assert sha(QEC/"qec_decoder.cpp")==cfg["fixed_core_sha256"]
    assert sha(QEC/"qec_tables.h")==cfg["fixed_header_sha256"]
    assert sha(QEC/"artifacts/mac_retry/correction_tables.json")==cfg["fixed_tables_json_sha256"]
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/"frozen_config.json",cfg)
    table=fixed_table()
    board_inputs=[]; board_cases=[]
    rows=[]
    try:
        for rounds in cfg["rounds"]:
            for pair_index,(p,q) in enumerate(cfg["noise_pairs"]):
                cell_id=f"r{rounds}_p{p:g}_q{q:g}"
                data_seed=np.random.SeedSequence([cfg["data_seed"],rounds,pair_index])
                measurement_seed=np.random.SeedSequence([cfg["measurement_seed"],rounds,pair_index])
                increments,accumulated,observed,masks=sample_histories(cfg["trials_per_cell"],rounds,p,q,data_seed,measurement_seed)
                final_error=accumulated[:,-1]
                terminal=syndrome_words(final_error)
                last,majority=compress(observed)
                matcher=SpaceTimeMatching(rounds,p,q)
                matched=matcher.decode(observed,terminal)
                corrections={"last_noisy":table[last],"majority_noisy":table[majority],
                             "final_perfect":table[terminal],"spacetime_pymatching":matched}
                row={"cell_id":cell_id,"noisy_rounds":rounds,"data_depolarizing_probability":p,
                     "measurement_flip_probability":q,"initial_syndrome":0,
                     "terminal_measurement":"perfect, no added data noise; offline methods only",
                     "matching_data_marginal":2*p/3,"matching_ignores_Y_sector_correlation":True}
                failures={}
                for name,correction in corrections.items():
                    row[name],failures[name]=classify(final_error,correction)
                if row["spacetime_pymatching"]["residual_syndrome_count"]:
                    raise AssertionError("space-time reference failed perfect terminal syndrome consistency")
                row["paired_offline_comparison"]={
                    "matching_only_failures":int(np.sum(failures["spacetime_pymatching"]&~failures["final_perfect"])),
                    "static_only_failures":int(np.sum(failures["final_perfect"]&~failures["spacetime_pymatching"]))}
                for mode,words in [("last_noisy",last),("majority_noisy",majority),("final_perfect",terminal)]:
                    for trial in range(cfg["board_trials_per_cell"]):
                        board_inputs.append(int(words[trial]))
                        board_cases.append({"case_id":f"{cell_id}/{mode}/trial{trial}","cell_id":cell_id,"mode":mode,
                                            "trial":trial,"observed_noisy_history":observed[trial].tolist(),
                                            "terminal_perfect_syndrome":int(terminal[trial]),
                                            "physical_recovery_failed":bool(failures[mode][trial])})
                np.savez_compressed(output/(cell_id+".npz"),increments=increments,final_error=final_error,
                                    observed=observed,measurement_masks=masks,terminal=terminal,
                                    last_compressed=last,majority_compressed=majority,**corrections)
                rows.append(row)
        for syndrome in range(256):
            board_inputs.append(syndrome)
            board_cases.append({"case_id":f"abi/syndrome{syndrome}","cell_id":None,"mode":"exhaustive_abi",
                                "trial":None,"observed_noisy_history":None,"terminal_perfect_syndrome":None,
                                "physical_recovery_failed":None})
        board_inputs=np.asarray(board_inputs,dtype=np.uint8)
        expected=table[board_inputs]
        c_values=c_reference(output,board_inputs)
        np.testing.assert_array_equal(c_values,expected)
        board=output/"board_vectors"
        board.mkdir()
        board_inputs.tofile(board/"inputs_u8.bin")
        expected.astype("<u4").tofile(board/"expected_corrections_u32.bin")
        manifest={"schema":"qec_noisy_compressed_replay_v1","count":len(board_inputs),"synthetic_history_count":len(board_inputs)-256,
                  "exhaustive_abi_count":256,"evidence":"host C++ and Python reference only; not board execution",
                  "abi":{"input":"uint8 packed syndrome","input_bits":"0..3 Z stabilizers;4..7 X stabilizers, unchanged v1 order",
                         "output":"uint32 little-endian Pauli correction","output_bits":"0..8 X frame;9..17 Z frame;18..31 zero",
                         "compression_location":"host; FPGA sees only the compressed eight-bit word",
                         "warning":"Matching the reference correction does not establish physical recovery success"},
                  "fixed_core_sha256":sha(QEC/"qec_decoder.cpp"),"fixed_header_sha256":sha(QEC/"qec_tables.h"),
                  "config_sha256":sha(cfg_path),"c_reference_exact_cases":len(board_inputs),
                  "files":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in board.iterdir() if p.is_file()},
                  "cases":board_cases}
        write_json(board/"manifest.json",manifest)
        result={"status":"completed","schema":cfg["schema"],"final_streams_consumed":True,
                "config_sha256":sha(cfg_path),"total_trials":cfg["trials_per_cell"]*len(rows),
                "cells":rows,"board_vectors":len(board_inputs),"compiled_reference_exact":True,
                "matching_terminal_consistency":True,"wall_seconds":time.perf_counter()-started,
                "versions":{k:importlib.metadata.version(k) for k in ["numpy","scipy","stim","pymatching"]},
                "python":sys.version,"platform":platform.platform(),
                "source_sha256":{p.name:sha(p) for p in [ROOT/"noisy_model.py",ROOT/"run_noisy.py",ROOT/"test_noisy.py",QEC/"qec_model.py",QEC/"qec_decoder.cpp"]},
                "artifact_sha256":{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.suffix!=".so"},
                "limits":["Phenomenological, not gate-level circuit noise", "Online methods lack perfect terminal information",
                          "Separate-sector MWPM ignores Y correlation", "Static LUT remains a one-round core",
                          "History compression runs on host", "No threshold, novel decoder, GPU or quantum-hardware result"]}
        write_json(output/"metrics.json",result)
        print(json.dumps({"status":"completed","total_trials":result["total_trials"],"board_vectors":len(board_inputs),
                          "wall_seconds":result["wall_seconds"],"cells":[{"id":r["cell_id"],
                             "last_noisy_failure":r["last_noisy"]["failure_rate"],
                             "majority_noisy_failure":r["majority_noisy"]["failure_rate"],
                             "perfect_terminal_lut_failure":r["final_perfect"]["failure_rate"],
                             "spacetime_matching_failure":r["spacetime_pymatching"]["failure_rate"]} for r in rows]},indent=2))
    except Exception as exc:
        write_json(output/"failure.json",{"error":repr(exc),"completed_cells":rows,"wall_seconds":time.perf_counter()-started})
        raise
    assert sha(QEC/"qec_decoder.cpp")==cfg["fixed_core_sha256"]
    assert sha(QEC/"qec_tables.h")==cfg["fixed_header_sha256"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    run(args.output.resolve())
