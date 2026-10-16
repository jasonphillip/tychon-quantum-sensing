"""Failure contracts: missing or changed evidence must never produce aggregate PASS."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/verify_evidence.py"


class ReproductionFailureTests(unittest.TestCase):
    def run_wrapper(self, *arguments, optimize=False):
        command = [sys.executable, "-B"]
        if optimize:
            command.append("-O")
        return subprocess.run([*command, str(WRAPPER), *map(str, arguments)],
                              text=True, capture_output=True, timeout=30)

    def assert_failed(self, result, message):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stdout + result.stderr)
        self.assertNotIn("RESULT: PASS", result.stdout)

    def test_missing_kit_stops_before_any_numeric_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report"
            result = self.run_wrapper("--kit-evidence-dir", Path(tmp) / "missing", "--out", out)
            self.assert_failed(result, "KIT_EVIDENCE_DIR does not exist")
            self.assertFalse(out.exists())

    def test_changed_kit_bytes_rejected_before_any_numeric_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "kit"
            kit.mkdir()
            subprocess.run(["git", "init", "--quiet", str(kit)], check=True)
            # Correct filename and size, deliberately wrong bytes. Hashes must be checked.
            (kit / "hw.bin").write_bytes(bytes(512))
            out = Path(tmp) / "report"
            result = self.run_wrapper("--kit-evidence-dir", kit, "--out", out)
            self.assert_failed(result, "SHA256 mismatch")
            self.assertFalse(out.exists())

    def test_output_inside_source_is_rejected(self):
        result = self.run_wrapper("--kit-evidence-dir", "/nonexistent-kit",
                                  "--out", ROOT / "must-not-create-evidence-test")
        self.assert_failed(result, "outside both checkouts")

    def test_relative_output_is_rejected(self):
        result = self.run_wrapper("--kit-evidence-dir", "/nonexistent-kit", "--out", "relative-report")
        self.assert_failed(result, "absolute path")

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_wrapper("--kit-evidence-dir", "/nonexistent-kit", "--out", tmp)
            self.assert_failed(result, "new directory")

    def test_no_kit_path_does_not_mean_current_directory(self):
        result = self.run_wrapper("--kit-evidence-dir", "")
        self.assert_failed(result, "Set KIT_EVIDENCE_DIR")

    def test_optimized_python_cannot_disable_evidence_assertions(self):
        result = self.run_wrapper("--kit-evidence-dir", "/nonexistent-kit", optimize=True)
        self.assert_failed(result, "requires assertions")


if __name__ == "__main__":
    unittest.main()
