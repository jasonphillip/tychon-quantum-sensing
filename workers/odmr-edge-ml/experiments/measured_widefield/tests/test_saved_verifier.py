"""Manufactured saved-output verification fixtures; no measured-data access."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from experiments.measured_widefield.io import blocks
from experiments.measured_widefield.metrics import compare
from experiments.measured_widefield.verify_saved import CLASSICAL, publication_manifest, sha, verify


class SavedVerifierTests(unittest.TestCase):
    def test_round_trip_rejects_rehashed_metric_and_array_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def save(path, value):
                path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")

            def bundle(name, data, metadata):
                path = root / name
                path.mkdir()
                np.savez_compressed(path / "arrays.npz", **data)
                save(path / "manifest.json", dict(metadata, arrays_sha256=sha(path / "arrays.npz")))
                return path

            rows = np.asarray([(f, g, p, y + 8 + (p // 4) * 8, x + 8 + (p % 4) * 8)
                               for f in range(3) for g, y, x in blocks("development") for p in range(8)], dtype=np.int64)
            count = len(rows)
            target = np.ones((count, 9, 200)); target[:, :, 50:55] = 0.98
            targets = bundle("targets", {"targets": target, "row_key": rows,
                "repeat_difference": np.zeros((count, 200)), "target_storage_extrema": np.zeros(count, dtype=bool)},
                {"kind": "targets", "split": "development", "rows": count, "repeats": [3],
                 "shifts_yx": [[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1], [-2, 0], [2, 0], [0, -2], [0, 2]],
                 "inputs_manifest_sha256": "a" * 64})
            mask = np.arange(50)
            model = bundle("model", {"shape_edges": mask, "shape_edge_training_energy": np.zeros(199)},
                           {"kind": "classical_model", "training_only": True})
            saved = {}
            for index, method in enumerate(sorted(CLASSICAL)):
                saved.update({method + "__prediction": target[:, 0] + 0.001 * (index + 1),
                    method + "__failed": np.zeros(count, dtype=bool), method + "__fit_reliable": np.zeros(count, dtype=bool),
                    method + "__seconds": np.full(count, 0.001)})
            predictions = bundle("predictions", dict(saved, row_key=rows), {"kind": "predictions", "split": "development",
                "inputs_manifest_sha256": "a" * 64, "methods": sorted(CLASSICAL), "label_values_read": False})
            report, indices = compare(target, rows, saved, 123456, shape_edges=mask)
            bootstrap = root / "bootstrap.npz"
            np.savez_compressed(bootstrap, groups=indices)
            report.update(split="development", target_manifest_sha256=sha(targets / "manifest.json"),
                prediction_manifest_sha256=[sha(predictions / "manifest.json")],
                classical_model_manifest_sha256=sha(model / "manifest.json"), shape_edges=mask.tolist(),
                approval_sha256="b" * 64, accounting_run_id="manufactured-fixture", bootstrap_sha256=sha(bootstrap))
            metrics = root / "metrics.json"
            save(metrics, report)
            manifest = root / "verification-manifest.json"

            def inventory():
                save(manifest, publication_manifest(targets, [predictions], model, metrics, bootstrap, 123456))
                return dict(targets=targets, predictions=[predictions], model=model, metrics=metrics,
                            bootstrap=bootstrap, manifest=manifest, expected_manifest_sha256=sha(manifest))

            arguments = inventory()
            self.assertEqual(verify(**arguments)["status"], "PASS")
            report["methods"][report["reference"]]["mse"] += 0.01
            save(metrics, report)
            arguments = inventory()  # Even a refreshed hash cannot hide a wrong reported metric.
            with self.assertRaisesRegex(ValueError, "metric differs"):
                verify(**arguments)
            with (predictions / "arrays.npz").open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "Artifact hash differs"):
                verify(**arguments)


if __name__ == "__main__":
    unittest.main()
