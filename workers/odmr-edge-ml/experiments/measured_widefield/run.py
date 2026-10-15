"""Absolute-path entrypoint for the coordinator's existing accounting adapter."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "tests":
        from experiments.measured_widefield.access import gate
        parser = argparse.ArgumentParser()
        parser.add_argument("action", choices=("tests",))
        parser.add_argument("--approval", required=True)
        args = parser.parse_args()
        gate(args.approval, "tests")
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / "tests"), pattern="test_*.py")
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    from experiments.measured_widefield.pipeline import main as pipeline_main
    pipeline_main()


if __name__ == "__main__":
    main()
