"""Run only through a root-approved reservation; no position model is imported."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "experiments.localisation_raw_compatibility"
from .guard import authorize, bind, read_json, write_json, sha256, PACKAGE
from .metadata import raw_inventory, select_sample, read_raw_header, bind_custody


def checked_bundle_file(root, item):
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("invalid bundle path")
    path = (root/relative).resolve(strict=True)
    path.relative_to(root.resolve())
    if sha256(path) != item["sha256"]:
        raise ValueError("version-A payload drift")
    return path


def main():
    parser = argparse.ArgumentParser()
    for name in ("approval", "archive", "bundle", "partition", "sample", "custody", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    approval = authorize(args.approval, "qualify")
    if (approval.get("signal_values_authorized") != "selected_unambiguous_small_training_raw_and_A_rows_only"
            or approval.get("separate_day_access_authorized") is not False):
        raise RuntimeError("training-only signal approval required")
    for name in ("archive", "bundle", "partition", "sample", "custody"):
        bind(approval, name, getattr(args, name))
    protocol = read_json(PACKAGE/"protocol.json")
    if (sha256(args.archive) != protocol["archive_sha256"]
            or sha256(args.partition) != protocol["partition_sha256"]):
        raise ValueError("protocol input pins changed")
    split, sample = read_json(args.partition), read_json(args.sample)
    if (sample.get("schema_version") != 1 or sample.get("count") != protocol["sample_count"]
            or not isinstance(sample.get("members"), list)
            or len(sample["members"]) != protocol["sample_count"]
            or sample.get("purpose") != "training_only_raw_compatibility"
            or sample.get("partition_sha256") != protocol["partition_sha256"]
            or sample.get("archive_sha256") != protocol["archive_sha256"]
            or sample.get("custody_sha256") != protocol["custody_sha256"]
            or sha256(args.custody) != protocol["custody_sha256"]):
        raise ValueError("invalid sample declaration")
    root = Path(args.bundle).resolve().parent
    bundle = read_json(args.bundle)
    if (bundle.get("fit_version") != "A_model_loaded"
            or bundle.get("archive_sha256") != protocol["archive_sha256"]
            or bundle["fit_parameters"]["sha256"] != protocol["version_A_parameters_sha256"]
            or bundle["fit_standard_deviations"]["sha256"] != protocol["version_A_std_sha256"]):
        raise ValueError("declared version-A pair required")
    import numpy as np
    from .extract import extract_payload, compare_features
    destination = Path(args.output).resolve()
    if (destination == root or root in destination.parents
            or destination == PACKAGE.parents[1] or PACKAGE.parents[1] in destination.parents):
        raise ValueError("outputs must be outside source and custody")
    destination.mkdir(parents=True, exist_ok=False)
    rows = [row["fitted_row"] for row in sample["members"]]
    # Indexed mmap access only: no validation or consumed test rows are loaded.
    parameter_path = checked_bundle_file(root, bundle["fit_parameters"])
    std_path = checked_bundle_file(root, bundle["fit_standard_deviations"])
    full_parameters = np.load(parameter_path, allow_pickle=False, mmap_mode="r")
    full_deviations = np.load(std_path, allow_pickle=False, mmap_mode="r")
    if (full_parameters.shape != (split["n"],8,6) or full_deviations.shape != full_parameters.shape
            or full_parameters.dtype != np.dtype("<f8") or full_deviations.dtype != np.dtype("<f8")):
        raise ValueError("unexpected version-A shape/dtype")
    # Validate sample membership before any fitted feature indexing or raw decoding.
    with zipfile.ZipFile(args.archive) as archive:
        expected = select_sample(split, raw_inventory(archive), protocol["sample_count"])
        bind_custody(expected, read_json(args.custody), protocol["archive_sha256"], protocol["partition_sha256"])
        for selected, declared in zip(expected, sample["members"]):
            if selected != {k: v for k, v in declared.items() if k != "header"}:
                raise ValueError("sample differs from deterministic training-only selection")
            with archive.open(selected["member"]) as stream:
                if read_raw_header(stream, selected["uncompressed_size"]) != declared["header"]:
                    raise ValueError("selected raw header drift")
        p, s = full_parameters[rows], full_deviations[rows]
        reference = np.stack((np.abs(p[:,:,1]-p[:,:,4]), s[:,:,1], s[:,:,4]), axis=2).reshape(len(rows),24)*1000.
        all_parameters, all_deviations, features, flags, receipts = [], [], [], [], []
        for selected in sample["members"]:
            payload = archive.read(selected["member"])
            # ZIP verifies CRC; the full archive SHA also binds member bytes.
            params, deviations, extracted, channel_flags = extract_payload(payload)
            all_parameters.append(params); all_deviations.append(deviations); features.append(extracted)
            flags.append({"fitted_row": selected["fitted_row"], "channels": channel_flags})
            receipts.append({"member": selected["member"], "payload_sha256": hashlib.sha256(payload).hexdigest(),
                             "zip_crc32": selected["zip_crc32"], "fitted_row": selected["fitted_row"]})
    actual = np.asarray(features)
    match = compare_features(actual, reference, protocol["matching_tolerances"])
    all_valid = all(flag["valid"] for row in flags for flag in row["channels"])
    passed = all_valid and match["all_features_match"]
    report = {"status": "PASS" if passed else "FAIL", "claim_scope": approval["claim_scope"],
              "all_fits_valid": all_valid, "comparison": match, "samples": len(rows),
              "raw_day_accessed": False, "position_models_executed": False,
              "raw_to_A_lineage_proved": False,
              "meaning": "bounded numerical compatibility only; not full raw lineage or acquisition transfer",
              "next_action": "root_review_only" if passed else "STOP_no_unchanged_model_transfer_no_tolerance_tuning"}
    for name, values in [("raw_fit_parameters.npy", all_parameters), ("raw_fit_std.npy", all_deviations),
                         ("extracted_features_MHz.npy", actual), ("reference_A_features_MHz.npy", reference)]:
        np.save(destination/name, np.asarray(values), allow_pickle=False)
    for name, value in [("qualification.json",report),("fit_flags.json",flags),("member_receipts.json",receipts),
                        ("sample.json",sample)]:
        write_json(destination/name,value)
    manifest = {"schema_version":1,"approval_sha256":sha256(args.approval),
                "protocol_sha256":sha256(PACKAGE/"protocol.json"),
                "source_sha256":approval["source_sha256"],
                "inputs":{name:sha256(getattr(args,name)) for name in ("archive","bundle","partition","sample")},
                "files":{p.name:sha256(p) for p in sorted(destination.iterdir())}}
    write_json(destination/"manifest.json",manifest)
    print(report["status"], match)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
