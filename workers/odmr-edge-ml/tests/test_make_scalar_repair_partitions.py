"""Sealing and seed invariants for the scalar repair data custodian."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/make_scalar_repair_partitions.py"
SPEC = importlib.util.spec_from_file_location("scalar_repair_partitions", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_disjoint_partition_seed_streams():
    used, _ = module.scan_used_seeds()
    streams = {}
    for partition, (rows, _) in module.PARTITIONS.items():
        streams[partition] = set(module.reserve_seeds(partition, used.copy(), rows)[0])
        assert len(streams[partition]) == rows
        assert not streams[partition] & used
    assert not streams["dev"] & streams["val"]
    assert not streams["dev"] & streams["final"]
    assert not streams["val"] & streams["final"]


def test_tiny_partition_determinism_read_only_and_modified_byte(tmp_path):
    roots = [tmp_path / "first", tmp_path / "second"]
    results = [module.generate(root, "dev", rows_override=2) for root in roots]
    for result in results:
        assert result["rows_per_cell"] == 2
        assert result["total_rows"] == 14
    a = roots[0] / "dev"
    b = roots[1] / "dev"
    assert not a.stat().st_mode & 0o222
    for name in module.CELLS:
        first = a / f"{name}.npz"
        second = b / f"{name}.npz"
        assert not first.stat().st_mode & 0o222
        with np.load(first, allow_pickle=False) as left, np.load(second, allow_pickle=False) as right:
            for key in left.files:
                np.testing.assert_array_equal(left[key], right[key])
    assert module.verify(roots[0], "dev")["total_rows"] == 14
    altered = a / "clean.npz"
    altered.chmod(0o644)
    with altered.open("r+b") as stream:
        stream.seek(100)
        byte = stream.read(1)
        stream.seek(100)
        stream.write(bytes([byte[0] ^ 1]))
    altered.chmod(0o444)
    with pytest.raises(RuntimeError, match="Hash or read-only mismatch"):
        module.verify(roots[0], "dev")
