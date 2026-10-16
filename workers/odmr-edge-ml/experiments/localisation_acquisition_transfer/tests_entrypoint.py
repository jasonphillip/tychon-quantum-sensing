"""In-process fixture entrypoint for the descendant-free numerical supervisor."""
import argparse
from pathlib import Path
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "experiments.localisation_acquisition_transfer"
from .guard import authorize, PACKAGE

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", required=True)
    args = parser.parse_args()
    authorize(args.approval, "manufactured")
    import pytest
    raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", str(PACKAGE/"tests")]))
