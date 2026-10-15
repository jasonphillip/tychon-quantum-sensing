"""Manufactured archive/partition tests; no downloaded recording is touched."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from experiments.measured_cardiac.access import SignalAccess, authorize
from experiments.measured_cardiac.loader import iter_rows
from experiments.measured_cardiac.metadata import sha256
from experiments.measured_cardiac.tests.test_metadata import manufactured_manifest

class LoaderTests(unittest.TestCase):
    def make_fixture(self, folder, rows):
        archive = folder / "manufactured.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("folder/recording.txt", "time,magnetic,ecg\n" + rows)
        metadata = manufactured_manifest()
        metadata["archive"]["sha256"] = sha256(archive)
        metadata["recordings"][0]["clock"]["sample_rate_hz"] = 1
        manifest = folder / "metadata.json"
        manifest.write_text(json.dumps(metadata))
        permit = SignalAccess(sha256(manifest), frozenset({"manufactured"}),
                              {"manufactured": ((1., 3.),)}, "fixture-not-real-approval", "fixture")
        return archive, manifest, permit

    def test_signal_values_outside_interval_are_not_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest, permit = self.make_fixture(Path(directory),
                "0,not-a-number,not-a-number\n1,10,1\n2,20,2\n3,not-a-number,not-a-number\n")
            with patch("experiments.measured_cardiac.loader.ARCHIVE_BYTES", archive.stat().st_size):
                rows = list(iter_rows(archive, manifest, "manufactured", permit,
                                      max_rows=2, start_seconds=1, stop_seconds=3))
            self.assertEqual([time for time, _ in rows], [1., 2.])
            self.assertEqual(rows[0][1]["magnetic"], 10.)

    def test_partition_crossing_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest, permit = self.make_fixture(Path(directory), "0,1,2\n1,2,3\n")
            with self.assertRaises(PermissionError):
                list(iter_rows(archive, manifest, "manufactured", permit,
                               max_rows=10, start_seconds=0, stop_seconds=2))

    def test_missing_row_is_not_silently_interpolated(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest, permit = self.make_fixture(Path(directory), "0,1,2\n2,2,3\n")
            with patch("experiments.measured_cardiac.loader.ARCHIVE_BYTES", archive.stat().st_size):
                with self.assertRaisesRegex(ValueError, "gap/jitter"):
                    list(iter_rows(archive, manifest, "manufactured", permit,
                                   max_rows=10, start_seconds=1, stop_seconds=3))

    def test_manifest_tampering_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest, permit = self.make_fixture(Path(directory), "0,1,2\n1,2,3\n")
            manifest.write_text(manifest.read_text() + " ")
            with self.assertRaises(PermissionError):
                list(iter_rows(archive, manifest, "manufactured", permit,
                               max_rows=10, start_seconds=1, stop_seconds=3))

    def test_draft_gate_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            gate = folder / "draft.json"
            gate.write_text('{"status":"DRAFT_ROOT_REVIEW"}')
            with self.assertRaises(PermissionError):
                authorize(gate, sha256(gate), folder / "never-read.json")

if __name__ == "__main__":
    unittest.main()
