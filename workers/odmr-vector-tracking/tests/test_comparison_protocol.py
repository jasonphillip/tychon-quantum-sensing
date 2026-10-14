#!/usr/bin/env python3
"""Focused Task 3 regressions. Set COMPARISON_GENERATOR to the generator path.

Example: COMPARISON_GENERATOR=/absolute/repo/experiments/make_comparison_test_set.py
python3 /absolute/path/test_comparison_protocol.py
HDF5 integration tests skip when h5py is unavailable; no renderer is imported.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "work/task3/repo/experiments/make_comparison_test_set.py"
SOURCE = Path(os.environ.get("COMPARISON_GENERATOR", DEFAULT_SOURCE))
spec = importlib.util.spec_from_file_location("comparison_generator", SOURCE)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
try:
    import h5py
except ImportError:
    h5py = None


def partition_record(partition="final", version=1):
    n = g.PER_REPLICATE[partition]
    master = g.master_seed(partition, version)
    result = {"master_seed": master, "cell_count": 14, "sequences_per_cell_seed": n,
              "total_sequences": 14 * 3 * n, "generation_wall_s": g.LEGACY_SECONDS if version == 1 and partition == "final" else 0.0,
              "array_hash_rule": g.HASH_RULE, "cells": []}
    for cell in g.cells():
        reps = [{"index": i, "seed": g._seed(cell["name"], i, master), "n_sequences": n,
                 "n_frames": 256, "lineage": {}, "augmentation": {}} for i in range(3)]
        result["cells"].append({**cell, "replicates": reps, "seed": [r["seed"] for r in reps],
                                "n_sequences": n * 3, "n_frames": 256, "data_md5": "0" * 32})
    return result


def make_rep(path, n):
    path.mkdir(parents=True)
    with h5py.File(path / "dataset.h5", "w") as handle:
        handle.create_dataset("test/spectra", shape=(n, 256, 1), dtype="f4")
    (path / "manifest.json").write_text('{"fixture": true}\n')


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.patch = mock.patch.object(g, "ROOT", self.root)
        self.patch.start()
        (self.root / "docs").mkdir()

    def tearDown(self):
        self.patch.stop()
        for path in [self.root, *self.root.rglob("*")]:
            if not path.is_symlink():
                path.chmod(stat.S_IMODE(path.stat().st_mode) | (0o700 if path.is_dir() else 0o600))
        self.temp.cleanup()


class MetadataTests(WorkspaceCase):
    def test_master_schedule_and_pairing(self):
        self.assertEqual([g.master_seed(p, 1) for p in g.PARTITIONS], [20261014, 20261114, 20261214])
        self.assertEqual([g.master_seed(p, 2) for p in g.PARTITIONS], [20270114, 20270214, 20270314])
        self.assertEqual(g._seed("clean", 0), g._seed("realistic", 0))
        self.assertNotEqual(g._seed("clean", 0), g._seed("extrapolation", 0))
        used = set()
        for version in (1, 2, 3, 4):
            for name in g.PARTITIONS:
                seeds = g._seed_values(version, name)
                self.assertFalse(seeds & used)
                used.update(seeds)
        with self.assertRaises(ValueError):
            g.master_seed("final", 0)

    def test_cross_partition_collision_rejected(self):
        with mock.patch.object(g, "_seed_values", return_value={10}):
            with self.assertRaisesRegex(RuntimeError, "cross-partition"):
                g._preflight_seeds(2)

    def test_seed_stream_collision_rejected(self):
        with mock.patch.object(g, "_seed", return_value=10):
            with self.assertRaisesRegex(RuntimeError, "within a partition"):
                g._seed_values(2, "dev")

    def test_registered_grid_and_malformed_hash_rejected(self):
        valid = partition_record()
        g._validate_partition(valid, "final", 1)
        changes = [lambda p: p["cells"][0].update(data_md5="wrong"),
                   lambda p: p["cells"][0]["config"].update(snr=99),
                   lambda p: p["cells"][0]["replicates"][0].update(seed=1),
                   lambda p: p["cells"].reverse(),
                   lambda p: p.update(total_sequences=588)]
        for change in changes:
            with self.subTest(change=change):
                bad = copy.deepcopy(valid)
                change(bad)
                with self.assertRaises(RuntimeError):
                    g._validate_partition(bad, "final", 1)

    def test_cumulative_time_and_sequence_caps(self):
        record = g._new_manifest(2)
        record.update(total_sequences=1680, generation_wall_s=g.LEGACY_SECONDS)
        self.assertAlmostEqual(g._generation_budget(record, "dev"), 3600 - g.LEGACY_SECONDS)
        record["generation_wall_s"] = 3600
        with self.assertRaisesRegex(RuntimeError, "time budget"):
            g._generation_budget(record, "dev")
        record.update(total_sequences=2500, generation_wall_s=0)
        with self.assertRaisesRegex(RuntimeError, "sequence budget"):
            g._generation_budget(record, "dev")
        record = g._new_manifest(2)
        record["partitions"]["final"] = partition_record("final", 2)
        record["partitions"]["final"]["generation_wall_s"] = 3601
        g._update_totals(record)
        with self.assertRaisesRegex(RuntimeError, "budget exceeded"):
            g._validate_manifest(record, 2, complete=False)

    def test_failed_attempt_and_bad_aggregate_rejected(self):
        record = g._new_manifest(2)
        record["attempts"] = [{"partition": "dev", "status": "failed", "generation_wall_s": 12}]
        g._update_totals(record)
        self.assertEqual(record["generation_wall_s"], 12)
        with self.assertRaisesRegex(RuntimeError, "incomplete generation"):
            g._validate_manifest(record, 2, complete=False)
        record = g._new_manifest(2)
        record["total_sequences"] = 1
        with self.assertRaisesRegex(RuntimeError, "accounting mismatch"):
            g._validate_manifest(record, 2, complete=False)

    def test_duplicate_json_and_symlinks_rejected(self):
        path = self.root / "docs/duplicate.json"
        path.write_text('{"schema": 2, "schema": 1}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            g._read_json(path)
        link = self.root / "data"
        link.symlink_to(self.root / "docs", target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            g._safe_path(link / "comparison_test_v1")

    def test_final_overwrite_refused_before_import_or_write(self):
        data, manifest = g.paths(2)
        (data / "final").mkdir(parents=True)
        sentinel = data / "final/sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaisesRegex(FileExistsError, "overwrite or regenerate"):
            g.generate("final", 2, None)
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertFalse(manifest.exists())

    def test_partial_output_and_v1_regeneration_refused(self):
        data, _ = g.paths(2)
        data.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "without its manifest"):
            g.generate("dev", 2, None)
        with self.assertRaisesRegex(RuntimeError, "legacy-only"):
            g.generate("final", 1, None)

    def test_help_without_renderer_or_hdf5_import(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                g.main(["--help"])
        self.assertEqual(result.exception.code, 0)
        self.assertIn("20270114", output.getvalue())
        self.assertNotIn("--force", output.getvalue())


@unittest.skipIf(h5py is None, "h5py unavailable; run these integration tests in the simulator environment")
class HDF5Tests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.data, self.manifest = g.paths(1)
        self.legacy = {"schema": 1, **partition_record()}
        for cell in self.legacy["cells"]:
            directory = self.data / cell["name"]
            for rep in cell["replicates"]:
                make_rep(directory / f"seed_{rep['index']}", 40)
            cell["data_md5"] = g.data_md5(directory)
        self.raw = (json.dumps(self.legacy, indent=2) + "\n").encode()
        self.manifest.write_bytes(self.raw)
        self.sha_patch = mock.patch.object(g, "LEGACY_SHA256", hashlib.sha256(self.raw).hexdigest())
        self.sha_patch.start()
        self.before = {p.relative_to(self.data): p.read_bytes() for p in self.data.rglob("*") if p.is_file()}

    def tearDown(self):
        self.sha_patch.stop()
        super().tearDown()

    def adopt(self):
        with contextlib.redirect_stdout(io.StringIO()):
            g.adopt_legacy()
        return g._read_json(self.manifest)

    def test_adoption_preserves_all_bytes_hashes_and_provenance(self):
        record = self.adopt()
        self.assertEqual(record["legacy_manifest_utf8"].encode(), self.raw)
        self.assertEqual(record["legacy_manifest_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(record["partitions"]["final"]["cells"], self.legacy["cells"])
        for rel, before in self.before.items():
            self.assertEqual((self.data / "final" / rel).read_bytes(), before)
        g._verify_existing(record, 1)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(g.verify(1), 0)
        self.assertIn("INCOMPLETE, 1/3 partitions", output.getvalue())
        with self.assertRaises(FileExistsError):
            g.generate("final", 1, None)

    def test_adoption_handles_original_readonly_root_and_children(self):
        for path in [*self.data.rglob("*"), self.data]:
            path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
        record = self.adopt()
        self.assertTrue(self.data.stat().st_mode & stat.S_IWUSR)
        g._verify_existing(record, 1)
        for rel, before in self.before.items():
            path = self.data / "final" / rel
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.stat().st_mode & 0o222)

    def test_migration_rolls_back_on_manifest_failure(self):
        for path in [*self.data.rglob("*"), self.data]:
            path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
        before_modes = {p.relative_to(self.data): stat.S_IMODE(p.stat().st_mode)
                        for p in [self.data, *self.data.rglob("*")]}
        with mock.patch.object(g, "_write_manifest", side_effect=OSError("injected disk error")):
            with self.assertRaises(OSError):
                g.adopt_legacy()
        self.assertEqual(self.manifest.read_bytes(), self.raw)
        self.assertFalse((self.data / "final").exists())
        self.assertEqual(stat.S_IMODE(self.data.stat().st_mode), 0o555)
        self.assertEqual(before_modes, {p.relative_to(self.data): stat.S_IMODE(p.stat().st_mode)
                                       for p in [self.data, *self.data.rglob("*")]})
        for rel, before in self.before.items():
            self.assertEqual((self.data / rel).read_bytes(), before)
        g._verify_tree(self.data, self.legacy)

    def test_malformed_hash_or_legacy_provenance_rejected(self):
        record = self.adopt()
        record["partitions"]["final"]["cells"][0]["data_md5"] = "f" * 32
        with self.assertRaisesRegex(RuntimeError, "differs from original"):
            g._verify_existing(record, 1)
        record = g._read_json(self.manifest)
        record["legacy_manifest_utf8"] += " "
        with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
            g._verify_existing(record, 1)

    def test_mutable_final_rejected(self):
        record = self.adopt()
        path = self.data / "final/clean/seed_0/dataset.h5"
        path.chmod(path.stat().st_mode | 0o200)
        with self.assertRaisesRegex(RuntimeError, "FINAL is writable"):
            g._verify_existing(record, 1)

    def test_changed_hdf5_and_unexpected_file_rejected(self):
        record = self.adopt()
        path = self.data / "final/clean/seed_0/dataset.h5"
        path.chmod(path.stat().st_mode | 0o200)
        with h5py.File(path, "r+") as handle:
            handle["test/spectra"][0, 0, 0] = 0.5
        path.chmod(path.stat().st_mode & ~0o222)
        with self.assertRaisesRegex(RuntimeError, "data_md5 mismatch"):
            g._verify_existing(record, 1)
        (self.data / "extra").write_text("unexpected")
        with self.assertRaisesRegex(RuntimeError, "unexpected or incomplete"):
            g._verify_existing(record, 1)

    def test_legacy_symlink_rejected_without_moving(self):
        path = self.data / "clean/seed_0/manifest.json"
        path.unlink()
        path.symlink_to(self.manifest)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            g.adopt_legacy()
        self.assertFalse((self.data / "final").exists())
        self.assertEqual(self.manifest.read_bytes(), self.raw)

    def fake_generator(self, output, cell, seed, n_seq):
        make_rep(output, n_seq)
        return {"fixture_seed": seed}

    def test_generate_dev_val_and_verify_all_2856(self):
        self.adopt()
        with mock.patch.object(g, "_resolve_sim_root", return_value=self.root), \
                mock.patch.object(g, "_call_generator", side_effect=self.fake_generator), \
                mock.patch.object(g, "_augment", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()):
            g.generate("dev", 1, None)
            g.generate("val", 1, None)
            self.assertEqual(g.verify(1), 0)
        record = g._read_json(self.manifest)
        self.assertEqual(record["total_sequences"], 2856)
        self.assertGreater(record["generation_wall_s"], g.LEGACY_SECONDS)
        for name in ("dev", "val"):
            self.assertEqual(record["partitions"][name]["total_sequences"], 588)
        for rel, before in self.before.items():
            self.assertEqual((self.data / "final" / rel).read_bytes(), before)

    def test_failed_generation_records_time_and_blocks_retry(self):
        self.adopt()
        with mock.patch.object(g, "_resolve_sim_root", return_value=self.root), \
                mock.patch.object(g, "_call_generator", side_effect=RuntimeError("injected render failure")):
            with self.assertRaisesRegex(RuntimeError, "injected render"):
                g.generate("dev", 1, None)
        record = g._read_json(self.manifest)
        self.assertEqual(record["attempts"][0]["status"], "failed")
        self.assertGreater(record["generation_wall_s"], g.LEGACY_SECONDS)
        (self.data / "dev").rmdir()
        with self.assertRaisesRegex(RuntimeError, "incomplete generation"):
            g.generate("dev", 1, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
