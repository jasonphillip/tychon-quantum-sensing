"""Stage entrypoints. Every signal/numerical command requires a pinned approval."""
import argparse
import json
import os
from pathlib import Path

from .access import gate, save, sha, verified_manifest
from .io import inspect_header

FILES = ("f0.fits", "f8.fits", "f24.fits")
SHIFTS = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2))


def output_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def arrays(path, approval):
    import numpy as np
    path = Path(path)
    expected = approval["artifacts"][str((path / "manifest.json").resolve())]
    record = verified_manifest(path / "manifest.json", expected)
    if sha(path / "arrays.npz") != record["arrays_sha256"]:
        raise ValueError("Array artifact changed")
    with np.load(path / "arrays.npz", allow_pickle=False) as saved:
        return record, {key: saved[key] for key in saved.files}


def write_arrays(output, values, record):
    import numpy as np
    output = output_directory(output)
    np.savez_compressed(output / "arrays.npz", **values)
    record = dict(record, arrays_sha256=sha(output / "arrays.npz"),
                  approval_sha256=os.environ["TYCHON_NUMERICAL_APPROVAL_SHA256"],
                  accounting_run_id=os.environ["TYCHON_NUMERICAL_RUN_ID"])
    save(output / "manifest.json", record)
    return record


def custody(args, approval):
    manifest = verified_manifest(args.custody, approval["data_manifest_sha256"])
    if manifest.get("status") != "verified" or manifest.get("record_id") != "7233869":
        raise ValueError("Verified widefield custody manifest required")
    paths = {}
    for name in FILES:
        entry = manifest["files"][name]
        path = Path(args.data_root) / name
        header = inspect_header(path)
        if not header["complete"] or header["actual_bytes"] != entry["bytes"] or header["header_sha256"] != entry["header_sha256"]:
            raise ValueError("FITS metadata differs from custody")
        if entry.get("axis_order_confirmed") is not True or sha(path) != entry["sha256"]:
            raise ValueError("FITS bytes or axis provenance are not verified")
        paths[name] = (path, header)
    return manifest, paths


def extract_inputs(args, approval):
    import numpy as np
    from .io import blocks, image_map, normalize, patch_spectrum, select_patches
    _, paths = custody(args, approval)
    spectra, scales, quality, rows = [], [], [], []
    for file_index, name in enumerate(FILES):
        path, header = paths[name]
        image = image_map(path, header)
        for group, y, x in blocks(args.split):
            for patch, (py, px) in enumerate(select_patches(image, y, x)):
                values, flag = patch_spectrum(image, 0, py, px)
                normalized, scale = normalize(values)
                spectra.append(normalized); scales.append(scale); quality.append(flag)
                rows.append((file_index, group, patch, py, px))
        del image
    write_arrays(args.out, {"inputs": np.asarray(spectra), "input_scale": np.asarray(scales),
                 "storage_extrema": np.asarray(quality), "row_key": np.asarray(rows, dtype=np.int64),
                 "frequency_mhz": np.asarray(header["frequency_mhz"])},
                 {"kind": "inputs", "split": args.split, "files": list(FILES), "repeat": 0,
                  "custody_sha256": sha(args.custody), "rows": len(rows), "target_values_read": False})


def extract_targets(args, approval):
    import numpy as np
    from .io import image_map, normalize, patch_spectrum
    record, source = arrays(args.inputs, approval)
    if record["kind"] != "inputs" or record["split"] != args.split:
        raise ValueError("Input split mismatch")
    if args.split == "final":
        if not args.predictions or sha(Path(args.predictions) / "manifest.json") != approval["prediction_manifest_sha256"]:
            raise ValueError("Final prediction commitment required before reading final references")
    _, paths = custody(args, approval)
    repeats = {"train": (1, 2), "development": (3,), "final": (4,)}[args.split]
    targets, differences, extrema = [], [], []
    active, image = None, None
    for file_index, group, patch, y, x in source["row_key"]:
        if active != int(file_index):
            active = int(file_index)
            path, header = paths[FILES[active]]
            image = image_map(path, header)
        shifted, flags, centered = [], [], []
        for dy, dx in SHIFTS:
            values = []
            for repeat in repeats:
                raw, flag = patch_spectrum(image, repeat, int(y) + dy, int(x) + dx)
                values.append(normalize(raw)[0]); flags.append(flag)
            shifted.append(np.mean(values, axis=0))
            if (dy, dx) == (0, 0):
                centered = values
        targets.append(shifted)
        differences.append(centered[0] - centered[1] if len(centered) == 2 else np.zeros(200))
        extrema.append(any(flags))
    write_arrays(args.out, {"targets": np.asarray(targets), "repeat_difference": np.asarray(differences),
                 "target_storage_extrema": np.asarray(extrema), "row_key": source["row_key"]},
                 {"kind": "targets", "split": args.split, "repeats": list(repeats),
                  "shifts_yx": list(SHIFTS), "inputs_manifest_sha256": sha(Path(args.inputs) / "manifest.json"),
                  "custody_sha256": sha(args.custody), "rows": len(targets)})


def train_models(args, approval):
    import numpy as np
    first, inputs = arrays(args.inputs, approval)
    second, targets = arrays(args.targets, approval)
    if first["split"] != "train" or second["split"] != "train" or not np.array_equal(inputs["row_key"], targets["row_key"]):
        raise ValueError("Training rows must match and remain in train groups")
    if args.action == "fit-classical":
        from .baselines import fit_linear_models
        fitted = fit_linear_models(inputs["inputs"], targets["targets"][:, 0], targets["repeat_difference"])
        metadata = {"kind": "classical_model", "training_only": True}
    else:
        from .candidate import train
        if approval.get("classical_development_gate_pass") is not True:
            raise ValueError("Classical qualification must precede learned training")
        seed = approval["training_seed"]
        if type(seed) is not int or not (0 <= seed < 2 ** 63):
            raise ValueError("Audited Torch-compatible seed required")
        fitted, losses = train(inputs["inputs"], targets["targets"][:, 0], seed)
        metadata = {"kind": "candidate_model", "epochs": 20, "parameters": 6616, "seed": seed, "training_losses": losses}
    metadata.update(inputs_manifest_sha256=sha(Path(args.inputs) / "manifest.json"),
                    targets_manifest_sha256=sha(Path(args.targets) / "manifest.json"))
    write_arrays(args.out, fitted, metadata)


def predict(args, approval):
    import numpy as np
    from . import baselines
    record, data = arrays(args.inputs, approval)
    if record["kind"] != "inputs" or record["split"] != args.split:
        raise ValueError("Input kind/split mismatch")
    methods = tuple(args.methods.split(","))
    if list(methods) != approval["methods"] or len(set(methods)) != len(methods):
        raise ValueError("Prediction methods must match frozen approval")
    model, weights = {}, {}
    if any(method in ("ridge", "pca_wiener") for method in methods):
        model_record, model = arrays(args.model, approval)
        if model_record["kind"] != "classical_model":
            raise ValueError("Wrong classical model")
    if "candidate" in methods:
        candidate_record, weights = arrays(args.weights, approval)
        if candidate_record["kind"] != "candidate_model":
            raise ValueError("Wrong candidate model")
    values = {"row_key": data["row_key"]}
    for method in methods:
        if method == "candidate":
            from .candidate import predict as candidate_predict
            prediction, failed, seconds = candidate_predict(data["inputs"], weights)
            reliable = np.zeros(len(failed), dtype=bool)
        else:
            prediction, failed, reliable, seconds = baselines.predict(method, data["inputs"], data["frequency_mhz"], model)
        values[method + "__prediction"] = prediction
        values[method + "__failed"] = failed
        values[method + "__fit_reliable"] = reliable
        values[method + "__seconds"] = seconds
    write_arrays(args.out, values, {"kind": "predictions", "split": args.split, "methods": list(methods),
                 "inputs_manifest_sha256": sha(Path(args.inputs) / "manifest.json"),
                 "label_values_read": False, "timing_scope": "Batch-1 normalized-spectrum processing including fallback; excludes file I/O and ROI extraction."})


def score(args, approval):
    import numpy as np
    from .metrics import compare
    record, target = arrays(args.targets, approval)
    if record["split"] != args.split or record["kind"] != "targets":
        raise ValueError("Target split mismatch")
    if args.split == "final" and not approval.get("reference_method"):
        raise ValueError("Final scoring requires the development-frozen classical reference")
    combined, manifests = {}, []
    for directory in args.prediction_bundles:
        prediction_record, saved = arrays(directory, approval)
        if prediction_record["kind"] != "predictions" or prediction_record["split"] != args.split:
            raise ValueError("Prediction split mismatch")
        if not np.array_equal(saved.pop("row_key"), target["row_key"]):
            raise ValueError("Prediction/reference row mismatch")
        if set(combined) & set(saved):
            raise ValueError("Duplicate method predictions; preserve original runs")
        combined.update(saved); manifests.append(sha(Path(directory) / "manifest.json"))
    result, bootstrap = compare(target["targets"], target["row_key"], combined,
                 approval["bootstrap_seed"], approval.get("reference_method"))
    result.update(split=args.split, target_manifest_sha256=sha(Path(args.targets) / "manifest.json"),
                  prediction_manifest_sha256=manifests,
                  approval_sha256=os.environ["TYCHON_NUMERICAL_APPROVAL_SHA256"],
                  accounting_run_id=os.environ["TYCHON_NUMERICAL_RUN_ID"])
    output = output_directory(args.out)
    np.savez_compressed(output / "bootstrap.npz", groups=bootstrap)
    result["bootstrap_sha256"] = sha(output / "bootstrap.npz")
    save(output / "metrics.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "extract-inputs", "extract-targets", "fit-classical", "train-candidate", "predict", "score"))
    for flag in ("approval", "data-root", "custody", "inputs", "targets", "model", "weights", "predictions", "out"):
        parser.add_argument("--" + flag)
    parser.add_argument("--fits", nargs="+")
    parser.add_argument("--split", choices=("train", "development", "final"))
    parser.add_argument("--methods")
    parser.add_argument("--prediction-bundles", nargs="+")
    args = parser.parse_args()
    if args.action == "inspect":
        if not args.fits:
            parser.error("inspect requires --fits")
        print(json.dumps({str(Path(path).resolve()): inspect_header(path) for path in args.fits}, indent=2))
        return
    if not args.approval or not args.out:
        parser.error("Numerical phases require --approval and exclusive --out")
    phase = args.action + (":" + args.split if args.split else "")
    approval = gate(args.approval, phase)
    if args.action == "extract-inputs":
        extract_inputs(args, approval)
    elif args.action == "extract-targets":
        extract_targets(args, approval)
    elif args.action in ("fit-classical", "train-candidate"):
        train_models(args, approval)
    elif args.action == "predict":
        predict(args, approval)
    else:
        score(args, approval)


if __name__ == "__main__":
    main()
