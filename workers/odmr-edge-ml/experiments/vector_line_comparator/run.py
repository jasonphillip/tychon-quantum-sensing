"""In-process manufactured checks only. No population execution entrypoint yet."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.vector_line_comparator.access import authorize,source_pins


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--gate",type=Path,required=True)
    parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    gate,context=authorize(args.gate,args.approval_sha256,"fixtures")
    if gate.get("execution")!={"phase":"fixtures","backend":"torch","device":"cpu","dtype":"float64"}:
        raise PermissionError("Exact manufactured execution required")
    args.out.mkdir(parents=True,exist_ok=False)
    import unittest
    from experiments.vector_line_comparator import test_manufactured
    with (args.out/"fixtures.txt").open("x") as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(test_manufactured))
    record={"passed":result.wasSuccessful(),"tests":result.testsRun,
        "failures":len(result.failures),"errors":len(result.errors),
        "scope":"manufactured fixtures only; no population evidence",
        "source_sha256":source_pins(),"approval_sha256":args.approval_sha256,
        "reservation_id":context["central_reservation_id"]}
    (args.out/"result.json").write_text(json.dumps(record,indent=2)+"\n")
    return 0 if result.wasSuccessful() else 2


if __name__=="__main__":
    raise SystemExit(main())
