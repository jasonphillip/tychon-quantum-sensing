"""Manufactured inputs only. Execution requires a registered root test job."""
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from scipy.interpolate import RBFInterpolator
from experiments.localisation_redesign.metrics import errors, summary, ratio, evaluate_saved
from experiments.localisation_redesign.models import (Scaling, representation, gp_objective, fit_classical,
                                                      predict_classical, training_loss)
from experiments.localisation_redesign.partition import coverage_positions
from experiments.localisation_redesign.guard import PACKAGE


class Contracts(unittest.TestCase):
    def test_coverage_ties_and_no_duplicate_budget(self):
        points = np.array([[0., 0.], [2., 0.], [0., 2.], [2., 2.], [1., 1.], [0., 0.]])
        actual = coverage_positions(points, 3)
        np.testing.assert_array_equal(actual, [[1., 1.], [0., 0.], [0., 2.]])
        np.testing.assert_array_equal(actual, coverage_positions(points[::-1], 3))

    def test_coverage_limits(self):
        with self.assertRaises(ValueError):
            coverage_positions([[1., 1.], [1., 1.]], 2)

    def test_scaling_training_only_and_inverse(self):
        x = np.exp(np.arange(96).reshape(4, 24) / 100)
        y = np.array([[0., 10.], [1., 20.], [2., 30.], [3., 40.]])
        scale = Scaling().fit(x, y)
        np.testing.assert_allclose(scale.inverse(scale.y(y)), y, atol=1e-12)
        before = scale.x_mean.copy()
        scale.x(x * 10000)
        np.testing.assert_array_equal(before, scale.x_mean)

    def test_channel_order_and_weighting(self):
        x = np.arange(48).reshape(2, 24)
        np.testing.assert_array_equal(representation(x, 0), x[:, ::3])
        np.testing.assert_array_equal(representation(x, .25)[:, 1::3], x[:, 1::3] / 4)

    def test_invalid_rows_stay(self):
        labels = np.zeros((3, 2))
        prediction = np.array([[1., 1.], [np.nan, 0.], [0., 0.]])
        result = summary(errors(prediction, labels))
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['invalid_rows'], 1)
        self.assertIsNone(result['mean_error_um'])
        self.assertEqual(result['coverage'], 2 / 3)

    def test_zero_denominator_is_not_win(self):
        self.assertIsNone(ratio(0, 0))
        self.assertIsNone(ratio(1, 0))

    def test_rbf_matches_scipy_reference(self):
        x = np.sin(np.arange(240).reshape(10, 24) / 13)
        y = np.column_stack((np.arange(10), np.arange(10) ** 2)) / 10
        q = x[:3] + .01
        config = dict(family='rbf', quality_weight=.25, smoothing=.1)
        state, _ = fit_classical(config, x, y)
        expected = RBFInterpolator(representation(x, .25), y, kernel='inverse_multiquadric',
                                  epsilon=1 / np.sqrt(24), degree=0, smoothing=.1)(representation(q, .25))
        np.testing.assert_allclose(predict_classical(config, state, q), expected, atol=1e-9, rtol=1e-9)

    def test_knn_duplicates_are_finite(self):
        x = np.zeros((3, 24)); y = np.array([[1., 2.], [3., 4.], [5., 6.]])
        config = dict(family='knn', quality_weight=0., k=3)
        state, _ = fit_classical(config, x, y)
        np.testing.assert_allclose(predict_classical(config, state, x[:1]), [[3., 4.]])

    def test_ard_analytic_gradients(self):
        x = np.array([[0., 0.], [1., .1], [.2, 1.], [.5, .8]])
        y = np.array([.1, .2, -.4, .3])
        theta = np.log([1.2, .9, 1.1, .08])
        for family in ('se', 'matern32'):
            _, gradient = gp_objective(theta, x, y, family)
            numeric = []
            for i in range(len(theta)):
                delta = np.zeros_like(theta); delta[i] = 1e-5
                numeric.append((gp_objective(theta + delta, x, y, family)[0] - gp_objective(theta - delta, x, y, family)[0]) / 2e-5)
            np.testing.assert_allclose(gradient, numeric, rtol=2e-4, atol=2e-5)

    def test_physical_loss_uses_units(self):
        import torch
        prediction = torch.tensor([[1., 1.]])
        target = torch.zeros_like(prediction)
        scale = torch.tensor([3., 4.])
        physical = training_loss(prediction, target, scale, 'physical_euclidean')
        self.assertAlmostEqual(float(physical), np.sqrt(26) - 1, places=6)
        self.assertEqual(float(training_loss(prediction, target, scale, 'standardized_mse_control')), 1.)

    def test_protocol_counts_and_scope(self):
        protocol = json.loads((PACKAGE / 'protocol.json').read_text())
        self.assertEqual(len(protocol['classical_grid']), 38)
        self.assertEqual((24 + 1) * 96 + (96 + 1) * 2, protocol['candidate']['parameters'])
        self.assertEqual(protocol['calibration']['total_small'] * 2, protocol['calibration']['total_full'])
        self.assertEqual(protocol['candidate']['registered_training_seeds'], 1)

    def test_gates_include_full_budget_and_invalids(self):
        protocol = json.loads((PACKAGE / 'protocol.json').read_text())
        y = np.column_stack((np.arange(40), np.arange(40)))
        groups = np.repeat(np.arange(8), 5)
        result = evaluate_saved(y, y + 1., y + 2., y + 3., y + .5, groups, protocol, 124, 248, 17, False, True)
        self.assertFalse(result['gate_passed'])
        self.assertFalse(result['neural_criteria']['matched_full_pool_quality'])
        self.assertTrue(result['neural_criteria']['same_budget_useful_advantage'])
        perfect = evaluate_saved(y, y, y, y, y, groups, protocol, 124, 248, 17, True, True, 'NEURAL_CALIBRATION_EFFICIENCY')
        self.assertFalse(perfect['gate_passed'])

    def test_complete_saved_only_verification_and_tampered_metric(self):
        import tempfile
        from experiments.localisation_redesign.guard import sha256
        from experiments.localisation_redesign.verify_saved import verify
        protocol = json.loads((PACKAGE / 'protocol.json').read_text())
        n = 284
        split = {'n': n, 'status': 'qualified', 'train': list(range(90)), 'full_train': list(range(214)),
                 'validation': list(range(214, 248)), 'test': list(range(248, 284)),
                 'position_groups': [hashlib.sha256(('exact_position:' + repr((float(i), float(i)))).encode()).hexdigest() for i in range(n)],
                 'spatial_groups': ['0:0'] * 214 + ['3:3'] * 34 + [cell for cell in ['7:7','7:9','9:7','9:9','7:11','11:7'] for _ in range(6)],
                 'small_label_budget': 124, 'full_label_budget': 248,
                 'small_measurement_rows': 124, 'full_measurement_rows': 248,
                 'label_budget_unit': 'unique_stage_xy_positions_including_validation',
                 'partition_unique_positions': {'train': 90, 'validation': 34, 'test': 36, 'full_train': 214},
                 'parent_partition_sha256': protocol['parent_partition_sha256'],
                 'selection_method': 'centroid_start_farthest_point_physical_um_lexicographic_ties'}
        rows = split['test']; labels = np.column_stack((rows, rows))
        groups = np.asarray(split['spatial_groups'])[rows]
        predictions = {'candidate': labels + .1, 'small': labels + 1., 'full': labels + 1.}
        result = evaluate_saved(labels, predictions['candidate'], None, predictions['small'], predictions['full'],
                                groups, protocol, 124, 248, 19, True, True, 'NEURAL_CALIBRATION_EFFICIENCY')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {'labels_um': labels, 'row_indices': np.asarray(rows), 'spatial_groups': groups}
            for name, values in predictions.items():
                payload[name + '_um'] = values; payload[name + '_valid'] = np.ones(36, dtype=bool)
            np.savez(root / 'predictions.npz', **payload)
            documents = {'protocol.json': protocol, 'partition.json': split, 'metrics.json': result,
                         'selection.json': {'stage': 'held_group', 'selected_path': 'NEURAL_CALIBRATION_EFFICIENCY'},
                         'verification.json': {'stage': 'held_group', 'confidence': True, 'expected_row_indices': rows,
                                               'small_label_budget': 124, 'full_label_budget': 248,
                                               'benchmark_complete': True, 'bootstrap_seed': 19, 'selected_path': 'NEURAL_CALIBRATION_EFFICIENCY'}}
            for name, value in documents.items():
                (root / name).write_text(json.dumps(value))
            manifest = {'source_sha256': {str(f.relative_to(PACKAGE)): sha256(f) for f in PACKAGE.rglob('*.py')},
                        'files': {f.name: sha256(f) for f in root.iterdir()}}
            manifest['source_sha256']['protocol.json'] = sha256(PACKAGE / 'protocol.json')
            (root / 'artifact_manifest.json').write_text(json.dumps(manifest))
            self.assertTrue(verify(root)['gate_passed'])
            result['candidate']['mean_error_um'] += 1
            (root / 'metrics.json').write_text(json.dumps(result))
            manifest['files']['metrics.json'] = sha256(root / 'metrics.json')
            (root / 'artifact_manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'saved metrics differ'):
                verify(root)

    def test_registered_classical_route_and_no_held_switch(self):
        protocol = json.loads((PACKAGE / 'protocol.json').read_text())
        y = np.column_stack((np.arange(36), np.arange(36)))
        groups = np.repeat(np.arange(6), 6)
        development = evaluate_saved(y, y + 2, y + 1, y + 1, y + 1, groups, protocol, 124, 248, 3, False, True)
        self.assertFalse(development['neural_gate_passed'])
        self.assertTrue(development['classical_gate_passed'])
        self.assertEqual(development['selected_path'], 'CLASSICAL_CALIBRATION_EFFICIENCY')
        held = evaluate_saved(y, None, None, y + 1, y + 1, groups, protocol, 124, 248, 3, True, True, 'CLASSICAL_CALIBRATION_EFFICIENCY')
        self.assertTrue(held['gate_passed'])
        self.assertFalse(held['neural_gate_passed'])
        failed_neural = evaluate_saved(y, y + 2, None, y + 1, y + 1, groups, protocol, 124, 248, 3, True, True, 'NEURAL_CALIBRATION_EFFICIENCY')
        self.assertFalse(failed_neural['gate_passed'])
        self.assertEqual(failed_neural['selected_path'], 'NEURAL_CALIBRATION_EFFICIENCY')


    def label_identity_fixture(self):
        labels = np.array([[1.25, 3.5], [4.75, 8.0], [2.0, 9.25]])
        hashes = [hashlib.sha256(('exact_position:' + repr(tuple(float(v) for v in row))).encode()).hexdigest() for row in labels]
        return labels, [0, 1, 2], {'position_groups': hashes}

    def test_saved_identity_rejects_shifted_labels(self):
        from experiments.localisation_redesign.verify_saved import validate_label_identity
        labels, rows, split = self.label_identity_fixture()
        validate_label_identity(labels, rows, split)
        with self.assertRaisesRegex(ValueError, 'saved label coordinates'):
            validate_label_identity(labels + [0.25, 0.0], rows, split)

    def test_saved_identity_rejects_permuted_labels(self):
        from experiments.localisation_redesign.verify_saved import validate_label_identity
        labels, rows, split = self.label_identity_fixture()
        with self.assertRaisesRegex(ValueError, 'saved label coordinates'):
            validate_label_identity(labels[[1, 0, 2]], rows, split)

    def test_saved_identity_rejects_truncated_labels(self):
        from experiments.localisation_redesign.verify_saved import validate_label_identity
        labels, rows, split = self.label_identity_fixture()
        with self.assertRaisesRegex(ValueError, 'saved label count/shape'):
            validate_label_identity(labels[:-1], rows, split)


if __name__ == '__main__':
    unittest.main()
