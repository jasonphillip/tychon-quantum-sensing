"""Temporary fake custody only. No production secret or scientific computation."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
MODULE = Path(__file__).resolve().parents[1] / "experiments/scalar_bias_design/custody.py"
spec = importlib.util.spec_from_file_location("bias_custody", MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = Path(self.tmp.name).resolve()
        self.protocol = self.p / "protocol.md"
        self.protocol.write_text("registered fixture\n")
        self.reg = self.p / "registration.json"
        self.reg.write_text(json.dumps({"stage": "stage2", "approved": True, "protocol_sha256": c.sha(self.protocol)}))
        self.source = self.p / "fixture.py"
        self.source.write_text("fixture = True\n")
        self.manifest = self.p / "code.json"
        self.manifest.write_text(json.dumps({"files": {"fixture.py": c.sha(self.source)}}))
        self.a = SimpleNamespace(command="create", custody_root=self.p / "private", public_root=self.p / "public",
            protocol=self.protocol, registration=self.reg, code_root=self.p, code_manifest=self.manifest)
        with patch.object(c.secrets, "token_bytes", return_value=b"x" * 32):
            c.create(self.a)
    def freeze(self):
        self.a.command = "freeze"
        self.a.freeze_sha256 = c.advance(self.a)["freeze_sha256"]
    def test_normal_and_failed_retirement(self, status="failed"):
        self.freeze()
        self.a.output_root = self.p / "generated"
        entropy = {k: getattr(self.a, k) for k in ("custody_root", "protocol", "registration", "code_root", "code_manifest", "freeze_sha256", "output_root")}
        self.assertEqual(c.consume_entropy(**entropy), int.from_bytes(b"x" * 32, "big"))
        with self.assertRaises(FileExistsError): c.consume_entropy(**entropy)
        self.a.output_root.mkdir()
        self.a.data_manifest = self.a.output_root / "manifest.json"
        self.a.data_manifest.write_text(json.dumps({"status": "complete", "freeze_sha256": self.a.freeze_sha256,
            "commitment_sha256": c.sha(self.a.custody_root / "secret.bin")}))
        self.a.data_manifest_sha256 = c.sha(self.a.data_manifest)
        self.a.data_manifest.chmod(0o444); self.a.output_root.chmod(0o555)
        self.addCleanup(self.a.output_root.chmod, 0o755)
        self.a.command = "access"
        access = c.advance(self.a)["access_sha256"]
        public = c.verify_access(protocol=self.protocol, registration=self.reg, freeze=self.a.public_root / "freeze.json", access=self.a.public_root / "access.json", code_root=self.p, data_manifest=self.a.data_manifest)
        self.assertEqual(public["freeze_sha256"], self.a.freeze_sha256)
        with self.assertRaises(ValueError): c.advance(self.a)
        self.a.command = "reveal"
        self.a.result = self.p / "result.bin"
        self.a.result.write_bytes(b"saved failure evidence")
        self.a.result_sha256 = c.sha(self.a.result)
        binding = {"freeze_sha256": self.a.freeze_sha256, "access_sha256": access}
        for name, obj in (("result_manifest", {**binding, "result_sha256": self.a.result_sha256}),
                          ("report", {**binding, "status": status})):
            path = self.p / (name + ".json")
            path.write_text(json.dumps(obj)); setattr(self.a, name, path); setattr(self.a, name + "_sha256", c.sha(path))
        result = c.advance(self.a)
        self.assertEqual(result["report_status"], status)
        self.assertNotIn("secret_hex", result)
        self.assertEqual(c.read(self.a.public_root / "reveal.json")["secret_hex"], (b"x" * 32).hex())
        with self.assertRaises(ValueError): c.advance(self.a)
    def test_complete_retirement(self):
        self.test_normal_and_failed_retirement("complete")
    def test_duplicate_and_code_drift(self):
        with self.assertRaises(ValueError): c.create(self.a)
        self.freeze()
        with self.assertRaises(ValueError): c.advance(self.a)
        self.source.write_text("changed\n")
        self.a.command = "access"
        with self.assertRaises(ValueError): c.advance(self.a)
    def test_replaced_secret_and_symlink(self):
        self.freeze()
        secret = self.a.custody_root / "secret.bin"
        secret.unlink(); secret.write_bytes(b"x" * 32); secret.chmod(0o400)
        self.a.command = "access"
        with self.assertRaises(ValueError): c.advance(self.a)
        link = self.p / "link"; link.symlink_to(self.protocol)
        with self.assertRaises(ValueError): c.sha(link)
    def test_protocol_drift_and_missing_result(self):
        self.protocol.write_text("unregistered change\n")
        with self.assertRaises(ValueError): self.freeze()
        with self.assertRaises(ValueError): c.file_bytes(self.p / "missing")
