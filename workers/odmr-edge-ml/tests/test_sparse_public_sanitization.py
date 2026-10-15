"""Manufactured file-hash tests only; no qualification arithmetic or dataset reads."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.sparse_acquisition_screen import verify_public as verifier


class PublicationSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.relative = "experiments/sparse_acquisition_screen/README.md"
        self.document = self.root / self.relative
        self.document.parent.mkdir(parents=True)
        self.document.write_text("Original documentation.\n")
        self.original = verifier.sha(self.document)
        self.sources = {self.relative: self.original}
        self.manifest = self.root / "sanitization.json"
        self.root_patch = patch.object(verifier, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def binding(self):
        return {"path": self.relative, "source_sha256": self.original,
                "public_sha256": verifier.sha(self.document)}

    def declare(self, bindings):
        self.manifest.write_text(json.dumps({"schema": 1, "files": bindings}))
        return self.manifest

    def test_exact_sources_without_manifest(self):
        actual, provenance = verifier.verify_source_files(self.sources)
        self.assertEqual(actual, self.sources)
        self.assertIsNone(provenance["manifest_sha256"])
        self.assertEqual(provenance["accepted_markdown_variants"], [])

    def test_changed_document_requires_manifest(self):
        self.document.write_text("Published documentation.\n")
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            verifier.verify_source_files(self.sources)

    def test_explicit_allowed_document_variant(self):
        self.document.write_text("Published documentation.\n")
        item = self.binding()
        actual, provenance = verifier.verify_source_files(self.sources, self.declare([item]))
        self.assertEqual(actual[self.relative], item["public_sha256"])
        self.assertEqual(provenance["accepted_markdown_variants"], [item])
        self.assertEqual(provenance["manifest_sha256"], verifier.sha(self.manifest))

    def test_wrong_original_or_public_digest_fails(self):
        self.document.write_text("Published documentation.\n")
        for key, message in (("source_sha256", "original hash mismatch"),
                             ("public_sha256", "public hash mismatch")):
            item = self.binding()
            item[key] = "0" * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                verifier.verify_source_files(self.sources, self.declare([item]))

    def test_code_data_protocol_and_other_markdown_are_never_allowed(self):
        paths = ("experiments/sparse_acquisition_screen/physics.py",
                 "experiments/sparse_acquisition_screen/qualification_spec.json",
                 "experiments/sparse_acquisition_screen/PROTOCOL.md",
                 "results/data.json", "elsewhere/README.md")
        for relative in paths:
            item = self.binding()
            item["path"] = relative
            with self.subTest(path=relative), self.assertRaisesRegex(ValueError, "not allowed"):
                verifier.verify_source_files({relative: self.original}, self.declare([item]))

    def test_unlisted_and_duplicate_bindings_fail(self):
        item = self.binding()
        with self.assertRaisesRegex(ValueError, "absent from original"):
            verifier.verify_source_files({}, self.declare([item]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            verifier.verify_source_files(self.sources, self.declare([item, item]))

    def test_code_change_still_fails_with_valid_document_binding(self):
        relative = "experiments/sparse_acquisition_screen/physics.py"
        code = self.root / relative
        code.write_text("ORIGINAL = True\n")
        expected = verifier.sha(code)
        code.write_text("ORIGINAL = False\n")
        self.document.write_text("Published documentation.\n")
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            verifier.verify_source_files({**self.sources, relative: expected},
                                         self.declare([self.binding()]))

    def test_noncanonical_and_symlink_document_bindings_fail(self):
        item = self.binding()
        item["path"] = "experiments/sparse_acquisition_screen/../sparse_acquisition_screen/README.md"
        with self.assertRaisesRegex(ValueError, "not allowed"):
            verifier.verify_source_files(self.sources, self.declare([item]))
        target = self.document.with_name("redirect.md")
        target.write_text("Published documentation.\n")
        self.document.unlink()
        self.document.symlink_to(target.name)
        with self.assertRaisesRegex(ValueError, "symlink"):
            verifier.verify_source_files(self.sources, self.declare([self.binding()]))

    def test_malformed_declarations_fail(self):
        malformed = ({"schema": True, "files": []}, {"schema": 1, "files": {}},
                     {"schema": 1, "files": [], "skip_hashes": True})
        for value in malformed:
            self.manifest.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier.verify_source_files(self.sources, self.manifest)


if __name__ == "__main__":
    unittest.main()
