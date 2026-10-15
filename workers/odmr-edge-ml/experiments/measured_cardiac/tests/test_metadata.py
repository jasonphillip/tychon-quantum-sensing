"""Prepared metadata tests; execute only inside the approved accounting stage."""
import copy
import unittest
from experiments.measured_cardiac.metadata import ARCHIVE_BYTES, ARCHIVE_MD5, eligibility, safe_member

def manufactured_manifest():
    return {
        "schema_version": 1, "record_id": "20703822", "license": "CC-BY-4.0",
        "archive": {"bytes": ARCHIVE_BYTES, "md5": ARCHIVE_MD5, "sha256": "a"*64, "custody_verified": True},
        "recordings": [{
            "id": "manufactured", "member": "folder/recording.txt", "experiment_kind": "human_cardiac",
            "participant_id": "manufactured-participant", "session_id": "manufactured-session",
            "acquisition_evidence": "manufactured fixture", "channel_evidence": "manufactured fixture",
            "group_evidence": "manufactured fixture", "duration_seconds": 3600,
            "acquisition_filters": {"known": True, "evidence": "manufactured fixture"},
            "clock": {"sample_rate_hz": 1000, "timestamp_seconds_per_unit": 1, "shared_clock": True,
                      "evidence": "manufactured fixture"},
            "format": {"header_lines": 1, "delimiter": ",", "timestamp_column": 0},
            "channels": [
                {"id": "magnetic", "column": 1, "role": "primary_magnetic", "role_evidence": "manufactured fixture",
                 "calibration": {"tesla_per_unit": 1e-9, "offset_raw": 0, "relative_uncertainty": 0.01,
                                 "applies_to_recording": "manufactured", "evidence": "manufactured fixture"}},
                {"id": "ecg", "column": 2, "role": "ecg_trigger", "role_evidence": "manufactured fixture"}
            ]
        }]
    }

class MetadataTests(unittest.TestCase):
    def test_valid_proxy_is_not_clean_truth(self):
        result = eligibility(manufactured_manifest())
        self.assertTrue(result["eligible"])
        self.assertFalse(result["clean_mcg_target"])
        self.assertFalse(result["clinical_accuracy_supported"])
        self.assertFalse(any(x["operation"] == "causal_reference_cancellation" for x in result["capabilities"]))

    def test_separate_opm_is_not_primary(self):
        manifest = manufactured_manifest()
        manifest["recordings"][0]["channels"][0]["role"] = "separate_opm"
        self.assertFalse(eligibility(manifest)["eligible"])

    def test_missing_calibration_blocks(self):
        manifest = manufactured_manifest()
        manifest["recordings"][0]["channels"][0]["calibration"]["evidence"] = ""
        self.assertFalse(eligibility(manifest)["eligible"])

    def test_noise_reference_requires_cardiac_leakage_evidence(self):
        manifest = manufactured_manifest()
        ref = {"id": "noise", "column": 3, "role": "reference_noise", "role_evidence": "fixture",
               "synchronous": True, "reference_evidence": "fixture", "cardiac_leakage_bound_verified": False}
        manifest["recordings"][0]["channels"].append(ref)
        result = eligibility(manifest)
        self.assertFalse(any(x["operation"] == "causal_reference_cancellation" for x in result["capabilities"]))
        ref["cardiac_leakage_bound_verified"] = True
        self.assertTrue(any(x["operation"] == "causal_reference_cancellation" for x in eligibility(manifest)["capabilities"]))

    def test_unknown_participant_limits_claim(self):
        manifest = manufactured_manifest()
        manifest["recordings"][0]["participant_id"] = None
        result = eligibility(manifest)
        self.assertTrue(result["eligible"])
        self.assertTrue(any("participant_unknown" in x for x in result["warnings"]))

    def test_wrong_version_and_incomplete_custody(self):
        manifest = manufactured_manifest()
        manifest["record_id"] = "20703821"
        manifest["archive"]["custody_verified"] = False
        self.assertFalse(eligibility(manifest)["eligible"])

    def test_unsafe_members(self):
        for name in ("../escape", "/absolute", "C:/absolute", "folder\\bad", "folder/../escape"):
            self.assertFalse(safe_member(name))
        self.assertTrue(safe_member("folder/data.txt"))

    def test_unknown_acquisition_filters_block(self):
        manifest = manufactured_manifest()
        manifest["recordings"][0]["acquisition_filters"]["known"] = False
        self.assertFalse(eligibility(manifest)["eligible"])

    def test_column_collision_blocks(self):
        manifest = manufactured_manifest()
        manifest["recordings"][0]["channels"][1]["column"] = 1
        self.assertFalse(eligibility(manifest)["eligible"])

if __name__ == "__main__":
    unittest.main()
