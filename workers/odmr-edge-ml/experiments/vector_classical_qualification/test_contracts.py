"""Manufactured contract tests. Execute only through a registered fixtures job."""
import ast
import copy
import inspect
import unittest
from unittest.mock import patch
import numpy as np
from experiments.vector_direct_screen import baseline as frozen
from experiments.vector_direct_screen.physics import CFG
from experiments.vector_classical_qualification import adapter, access


class FakeEngine:
    backend = "numpy"
    xp = np
    def array(self, value): return np.asarray(value)
    def numpy(self, value): return np.asarray(value)
    def sync(self): pass


def initialize(engine, counts, mode):
    return np.repeat(counts[:, :1], 8, axis=1)


def observed_check(engine, counts, params):
    return (counts[:, 0].astype(int) % 2 == 0), np.arange(len(counts), dtype=float)*0


def full_fallback(engine, counts):
    n = len(counts)
    return {"parameters": np.repeat(counts[:, :1]+1000, 8, axis=1),
            "accepted": np.ones(n, dtype=bool), "reduced_deviance": np.zeros(n)}


class NormalizeChunk(ast.NodeTransformer):
    def visit_Name(self, node):
        if node.id == "chunk_size":
            return ast.Subscript(value=ast.Name(id="CFG", ctx=ast.Load()),
                                 slice=ast.Constant(value="chunk_size"), ctx=ast.Load())
        return node


class ContractTests(unittest.TestCase):
    def test_policy_body_differs_only_by_outer_chunk_parameter(self):
        old = ast.parse(inspect.getsource(frozen.policy_device)).body[0]
        new = ast.parse(inspect.getsource(adapter._chunked_policy)).body[0]
        new = NormalizeChunk().visit(new)
        self.assertEqual(ast.dump(ast.Module(body=old.body, type_ignores=[])),
                         ast.dump(ast.Module(body=new.body, type_ignores=[])))

    def test_solver_functions_are_same_objects(self):
        self.assertIs(adapter.initialize, frozen.initialize)
        self.assertIs(adapter.observed_check, frozen.observed_check)
        self.assertIs(adapter.full_fallback, frozen.full_fallback)

    def test_cfg_is_not_mutated(self):
        before = copy.deepcopy(CFG)
        self.assertEqual(adapter.CHUNKS, (256, 1024, 4096))
        with patch.multiple(adapter, initialize=initialize, observed_check=observed_check,
                            full_fallback=full_fallback):
            adapter.policy_device(FakeEngine(), np.zeros((2, 512)), chunk_size=1024)
        self.assertEqual(CFG, before)

    def test_fallback_mask_and_original_order_survive_chunk_boundaries(self):
        counts = np.zeros((1030, 512)); counts[:, 0] = np.arange(1030)
        replacements = dict(initialize=initialize, observed_check=observed_check,
                            full_fallback=full_fallback)
        with patch.multiple(frozen, **replacements), patch.multiple(adapter, **replacements):
            expected = frozen.policy_device(FakeEngine(), counts, "affine")
            for chunk in adapter.CHUNKS:
                actual = adapter.policy_device(FakeEngine(), counts, "affine", chunk_size=chunk)
                for key in expected:
                    np.testing.assert_array_equal(actual[key], expected[key])
                np.testing.assert_array_equal(actual["fallback"], np.arange(1030) % 2 == 1)
                self.assertTrue(actual["accepted"].all())

    def test_all_four_variants_keep_original_dispatch(self):
        counts = np.zeros((257, 512)); counts[:, 0] = np.arange(257)
        replacements = dict(initialize=initialize, observed_check=observed_check,
                            full_fallback=full_fallback)
        with patch.multiple(frozen, **replacements), patch.multiple(adapter, **replacements):
            for variant in ("affine", "peaks", "calibrated", "lm"):
                expected = frozen.policy_device(FakeEngine(), counts, variant)
                actual = adapter.policy_device(FakeEngine(), counts, variant, chunk_size=4096)
                for key in expected:
                    np.testing.assert_array_equal(actual[key], expected[key])

    def test_invalid_chunks_are_rejected(self):
        for chunk in (True, 0, 128, 2048, 8192, 256.0):
            with self.assertRaises(ValueError):
                adapter.policy_device(FakeEngine(), np.zeros((1, 512)), chunk_size=chunk)

    def test_empty_inputs_and_unknown_policy_are_rejected(self):
        for counts, variant in ((np.zeros((0, 512)), "affine"),
                                (np.zeros((1, 512)), "unknown")):
            with self.assertRaises(ValueError):
                adapter.policy_device(FakeEngine(), counts, variant)

    def test_host_interface_validates_count_values_and_shape(self):
        for counts in (np.zeros((1, 511)), np.full((1, 512), -1.),
                       np.full((1, 512), np.nan)):
            with self.assertRaises(ValueError):
                adapter.fit_counts(counts)

    def test_additive_guard_rejects_missing_or_changed_source_pins(self):
        gate = {"frozen_source_commit": "f5032fa3461aba2d2395bd1313c25fd9a8f98220"}
        with patch.object(access, "frozen_authorize", return_value=(gate, {})):
            with self.assertRaises(PermissionError): access.authorize("unused", "unused", "fixtures")
        gate["additive_source_sha256"] = {"wrong": "wrong"}
        with patch.object(access, "frozen_authorize", return_value=(gate, {})):
            with self.assertRaises(PermissionError): access.authorize("unused", "unused", "fixtures")

    def test_additive_guard_rejects_wrong_frozen_commit(self):
        gate = {"additive_source_sha256": access.source_pins(), "frozen_source_commit": "wrong"}
        with patch.object(access, "frozen_authorize", return_value=(gate, {})):
            with self.assertRaises(PermissionError): access.authorize("unused", "unused", "fixtures")
