"""Offline public bundle acceptance and corruption checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "docs/scalar_repair_cycle_2026-10"
CHECKER = ROOT / "scripts/recompute_published_scalar_validation.py"
SPEC = importlib.util.spec_from_file_location("public_scalar_checker", CHECKER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublicScalarValidationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        shutil.copytree(BUNDLE, self.bundle)

    def run_checker(self):
        env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        out = self.root / "receipt.json"
        proc = subprocess.run([sys.executable, str(CHECKER), "--bundle", str(self.bundle),
                               "--no-network", "--cross-check-truth", "--out", str(out)],
                              capture_output=True, text=True, env=env)
        return proc, json.loads(out.read_text())

    def update_bundle_hash(self, relative):
        manifest_path = self.bundle / "BUNDLE.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        path = self.bundle / relative
        manifest["files"][relative]["sha256"] = sha(path)
        manifest["files"][relative]["size_bytes"] = path.stat().st_size
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    def test_bundle_passes(self):
        proc, result = self.run_checker()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["selection"]["can_proceed"])
        self.assertTrue(all(cell["bootstrap_checked"] for cell in result["cells"].values()))

    def test_prediction_byte_tamper_fails(self):
        path = self.bundle / "results-val/clean_predictions.npz"
        with path.open("r+b") as stream:
            stream.seek(10)
            byte = stream.read(1)
            stream.seek(10)
            stream.write(bytes([byte[0] ^ 1]))
        proc, result = self.run_checker()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("bundle SHA256", result["error"])

    def test_metrics_value_tamper_fails(self):
        relative = "results-val/clean_metrics.json"
        path = self.bundle / relative
        obj = json.loads(path.read_text())
        obj["metrics"]["training_mean"]["mae_uT"] += 1
        path.write_text(json.dumps(obj, indent=2) + "\n")
        self.update_bundle_hash(relative)
        proc, result = self.run_checker()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duplicate metric JSON equality", result["error"])
        arrays = MODULE.load_arrays(self.bundle / "results-val/clean_predictions.npz", 512)
        quant = json.loads((self.bundle / "QUANTIZATION.manifest.json").read_text())
        with self.assertRaisesRegex(AssertionError, "clean.metrics"):
            MODULE.verify_cell("clean", arrays, obj, 512, quant)

    def test_derivative_public_hash_tamper_fails(self):
        relative = "freeze1.public.json"
        path = self.bundle / relative
        path.write_text(path.read_text().replace("private-path/", "masked-path/", 1))
        self.update_bundle_hash(relative)
        proc, result = self.run_checker()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("sanitization public SHA256", result["error"])

    def test_output_endpoint_count_tamper_fails(self):
        relative = "results-val/clean_metrics.json"
        path = self.bundle / relative
        obj = json.loads(path.read_text())
        obj["quantization"]["identity"]["C_direct_seed42"]["output_at_max"] += 1
        path.write_text(json.dumps(obj, indent=2) + "\n")
        self.update_bundle_hash(relative)
        proc, result = self.run_checker()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duplicate metric JSON equality", result["error"])
        arrays = MODULE.load_arrays(self.bundle / "results-val/clean_predictions.npz", 512)
        quant = json.loads((self.bundle / "QUANTIZATION.manifest.json").read_text())
        with self.assertRaisesRegex(AssertionError, "output_at_max"):
            MODULE.check_output_occupancy("clean", arrays, obj, quant, 512)


if __name__ == "__main__":
    unittest.main()
