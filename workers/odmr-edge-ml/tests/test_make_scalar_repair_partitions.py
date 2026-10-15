"""Sealing and seed invariants for the scalar repair data custodian."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/make_scalar_repair_partitions.py"
SPEC = importlib.util.spec_from_file_location("scalar_repair_partitions", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


OWN_PUBLISHED_BUNDLE = module.REPO / "docs" / "scalar_repair_cycle_2026-10"


@pytest.fixture(autouse=True)
def _exclude_own_published_bundle(monkeypatch):
    """The cycle's own published bundle holds this generator's outputs (dev r1, dev-r2, val
    manifests); they are not earlier consumed sets, so the seed scan in these tests ignores them."""
    original = module.manifest_paths

    def without_own_bundle(roots):
        return [item for item in original(roots) if OWN_PUBLISHED_BUNDLE not in item[2].parents]

    monkeypatch.setattr(module, "manifest_paths", without_own_bundle)


def test_disjoint_partition_seed_streams():
    used, _ = module.scan_used_seeds()
    streams = {}
    for partition, (rows, _) in module.PARTITIONS.items():
        streams[partition] = set(module.reserve_seeds(partition, used.copy(), rows)[0])
        assert len(streams[partition]) == rows
        assert not streams[partition] & used
    assert not streams["dev-r2"] & streams["val"]
    assert not streams["dev-r2"] & streams["final"]
    assert not streams["val"] & streams["final"]


def test_tiny_partition_determinism_read_only_and_modified_byte(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger.jsonl")
    roots = [tmp_path / "first", tmp_path / "second"]
    results = [module.generate(root, "dev-r2", rows_override=2) for root in roots]
    for result in results:
        assert result["rows_per_cell"] == 2
        assert result["total_rows"] == 14
    a = roots[0] / "dev-r2"
    b = roots[1] / "dev-r2"
    assert not a.stat().st_mode & 0o222
    for name in module.CELLS:
        first = a / f"{name}.npz"
        second = b / f"{name}.npz"
        assert not first.stat().st_mode & 0o222
        with np.load(first, allow_pickle=False) as left, np.load(second, allow_pickle=False) as right:
            for key in left.files:
                np.testing.assert_array_equal(left[key], right[key])
    assert module.verify(roots[0], "dev-r2")["total_rows"] == 14
    altered = a / "clean.npz"
    altered.chmod(0o644)
    with altered.open("r+b") as stream:
        stream.seek(100)
        byte = stream.read(1)
        stream.seek(100)
        stream.write(bytes([byte[0] ^ 1]))
    altered.chmod(0o444)
    with pytest.raises(RuntimeError, match="Hash or read-only mismatch"):
        module.verify(roots[0], "dev-r2")


def test_budget_aborts_incomplete_and_ledgers_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.delenv("SCALAR_REPAIR_PARENT_JOB", raising=False)
    module.LEDGER.write_text(json.dumps({"job": "scalar_repair_generation", "wall_seconds": 1199.999}) + "\n")
    with pytest.raises(RuntimeError, match="Cumulative generation cap"):
        module.generate(tmp_path / "data", "dev-r2", rows_override=1)
    assert (tmp_path / "data/dev-r2/INCOMPLETE.json").exists()
    entries = [json.loads(line) for line in module.LEDGER.read_text().splitlines()]
    assert entries[-1]["job"] == "scalar_repair_generation"
    assert entries[-1]["success"] is False
    assert entries[-1]["wall_seconds"] > 0


def test_unexpected_generation_failure_is_ledgered(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.delenv("SCALAR_REPAIR_PARENT_JOB", raising=False)
    def fail(*args, **kwargs):
        raise RuntimeError("forced generator failure")
    monkeypatch.setattr(module, "_generate", fail)
    with pytest.raises(RuntimeError, match="forced generator failure"):
        module.generate(tmp_path / "data", "dev-r2", rows_override=1)
    entry = json.loads(module.LEDGER.read_text().splitlines()[0])
    assert entry["job"] == "scalar_repair_generation"
    assert entry["success"] is False
    assert entry["wall_seconds"] >= 0


def test_seeds_unique_across_kinds_and_partitions():
    used = set(module.EXCLUDED)
    for partition, (rows, _) in module.PARTITIONS.items():
        three = module.reserve_seeds(partition, used, rows)
        merged = [seed for stream in three for seed in stream]
        assert len(set(merged)) == 3 * rows
        assert not set(merged) & used
        used.update(merged)


def test_nominal_at_zero():
    _, OUNoiseConfig, _, _, _, trajectory, *_ = module._source_imports()
    recipe = json.loads(module.RECIPE.read_text())["config"]
    config = OUNoiseConfig(**recipe["ou_noise"])
    T, B1 = trajectory(config, 1, seed=123)
    assert T[0] == config.T_mean_C + 273.15
    assert B1[0] == config.B1_nominal


def test_render_parity_with_first_sealed_dev_rows():
    sealed = module.REPO / ".scratch/scalar_repair_2026-10/dev"
    if not sealed.is_dir():
        pytest.skip("Local sealed development r1 absent")
    manifest = json.loads((sealed / "manifest.json").read_text())
    recipe = json.loads(module.RECIPE.read_text())["config"]
    SimOSAdapter, OUNoiseConfig, SimulationConfig, sphere, corrupt, trajectory, *_ = module._source_imports()
    from nv_sensor_sim.pipelines.batch_generate import _generate_split_stochastic
    width, contrast, _, slope, offset = module.CELLS["clean"]
    p1 = (np.pi * width * 1e6 - 1 / 1.48e-6) * 9.9e-6
    config = SimulationConfig(random_seed=manifest["master_seed"], use_optics=False,
                              include_nitrogen=False, n_freq_points=100,
                              mw_freq_range_Hz=(2.82e9, 2.92e9))
    adapter = SimOSAdapter(config)
    with np.load(sealed / "clean.npz", allow_pickle=False) as saved:
        for i in range(8):
            seed = manifest["sample_seeds"][i]
            nuisance_seed = manifest["nuisance_seeds"][i]
            old_x, old_b, old_p, _, freq = _generate_split_stochastic(
                adapter, config, [seed, seed], OUNoiseConfig(**recipe["ou_noise"]),
                nuisance_seed, (p1, p1), tuple(recipe["test_b1_gradient_range"]),
                (0., 0.), (.005, .015), 100, "parity", field_sampling="spherical",
                b_mag_range_T=(20e-6, 70e-6))
            rendered, b, p, f = module.render_field(adapter, seed, old_p[1, 1], old_p[1, 4],
                                                      p1, tuple(recipe["test_b1_gradient_range"]),
                                                      sphere, corrupt)
            np.testing.assert_array_equal(rendered, old_x[1])
            np.testing.assert_array_equal(b, old_b[1])
            np.testing.assert_array_equal(p, old_p[1])
            np.testing.assert_array_equal(f, freq)
            depth = np.max(1 - rendered)
            scaled = 1 - (1 - rendered) * (contrast / depth)
            shifted = np.interp(f - offset * 1e6, f, scaled, left=scaled[0], right=scaled[-1])
            signal = shifted + slope * (f - (f[0] + f[-1]) / 2) / (f[-1] - f[0])
            np.testing.assert_array_equal(signal, saved["spectra"][i])


def test_time_uniform_nuisance_marginal_against_long_trajectories():
    from scipy.stats import ks_2samp
    _, OUNoiseConfig, _, _, _, trajectory, *_ = module._source_imports()
    recipe = json.loads(module.RECIPE.read_text())["config"]
    config = OUNoiseConfig(**recipe["ou_noise"])
    horizon = recipe["splits"]["train"]
    rng = np.random.default_rng(31827)
    indices = rng.integers(0, horizon, size=4096)
    sampled = np.array([(lambda T, B1: (T[-1], B1[-1]))(
        *trajectory(config, int(k) + 1, seed=int(seed)))
        for k, seed in zip(indices, range(100000, 104096))])
    reference = []
    for seed in range(200000, 200128):
        T, B1 = trajectory(config, horizon, seed=seed)
        index = rng.integers(0, horizon, size=32)
        reference.extend(zip(T[index], B1[index]))
    reference = np.asarray(reference)
    for column, tolerance in ((0, .5), (1, .005)):
        assert ks_2samp(sampled[:, column], reference[:, column]).pvalue > .01
        assert np.max(np.abs(np.quantile(sampled[:, column], [.05, .5, .95]) -
                             np.quantile(reference[:, column], [.05, .5, .95]))) < tolerance
