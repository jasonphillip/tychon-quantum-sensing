"""Prepared manufactured timestamps; no measured data or waveform decoding."""
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from experiments.measured_cardiac.qualify_timestamps import qualify_recording

class TimestampOnlyTests(unittest.TestCase):
    def fixture(self, directory, first, second):
        path = Path(directory) / "manufactured.zip"
        name = "neutral-recording.txt"
        header = b"% header\n" * 7
        rows = lambda times: b"".join((str(t) + ";NOT_A_NUMBER_DO_NOT_DECODE\n").encode() for t in times)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, header + rows(first) + rows(second))
        archive = zipfile.ZipFile(path)
        info = archive.getinfo(name)
        record = {"id": "P1-S01", "participant_id": "P1", "session_id": "P1-S01",
                  "split": "development", "member_name_sha256": hashlib.sha256(name.encode()).hexdigest(),
                  "member_bytes": info.file_size, "member_crc32": format(info.CRC, "08x"), "header_sha256": None}
        return archive, record

    def test_matching_time_arrays_ignore_nonnumeric_signal_column(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, record = self.fixture(directory, range(601), range(601))
            with archive:
                result = qualify_recording(archive, record)
            self.assertTrue(result["timestamp_only_eligible"])
            self.assertEqual(result["waveform_values_decoded"], 0)
            self.assertEqual(result["rows_per_channel"], 601)
            self.assertEqual(result["exact_windows"][1]["first_sample"], 180)

    def test_shifted_second_origin_is_not_aligned_by_waveform(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, record = self.fixture(directory, range(601), [x + .001 for x in range(601)])
            with archive, self.assertRaisesRegex(ValueError, "origin"):
                qualify_recording(archive, record)

    def test_missing_second_channel_sample_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, record = self.fixture(directory, range(601), [x for x in range(601) if x != 100])
            with archive, self.assertRaisesRegex(ValueError, "arrays differ"):
                qualify_recording(archive, record)

    def test_matching_but_irregular_sampling_fails(self):
        times = [x for x in range(601) if x != 100]
        with tempfile.TemporaryDirectory() as directory:
            archive, record = self.fixture(directory, times, times)
            with archive:
                result = qualify_recording(archive, record)
            self.assertFalse(result["timestamp_only_eligible"])
            self.assertIn("sampling_interval_variation_exceeds_2_percent", result["errors"])

if __name__ == "__main__":
    unittest.main()
