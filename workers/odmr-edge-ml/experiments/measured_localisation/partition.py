"""Fixed geometric partition, generated only under numerical approval."""
import hashlib
import math

import numpy as np

from .bundle import arrays


def order_key(salt, value):
    return hashlib.sha256((salt + ":" + str(value)).encode()).hexdigest()


def make_partition(manifest_path, protocol, salt):
    _, y, manifest, metadata = arrays(manifest_path)
    y = np.asarray(y, dtype=float)
    if not np.isfinite(y).all():
        raise ValueError("nonfinite position labels")
    bounds = np.asarray(manifest["operating_bounds_um"], dtype=float)
    if bounds.shape != (2, 2) or (bounds[:, 1] <= bounds[:, 0]).any():
        raise ValueError("custody must declare [xmin,xmax],[ymin,ymax]")
    if ((y < bounds[:, 0]) | (y > bounds[:, 1])).any():
        raise ValueError("position outside declared operating bounds")
    spec = protocol["partition"]
    grid = np.asarray(spec["grid"], dtype=int)
    cell = np.minimum(np.floor((y - bounds[:, 0]) / np.diff(bounds, axis=1).ravel() * grid).astype(int), grid - 1)
    key = [f"{a}:{b}" for a, b in cell]
    test_cells = np.asarray(spec["test_cells"], dtype=int)
    distances = np.max(np.abs(cell[:, None, :] - test_cells[None, :, :]), axis=2)
    is_test = (distances == 0).any(1)
    excluded = (distances <= spec["test_exclusion_chebyshev_cells"]).any(1) & ~is_test
    available = ~(is_test | excluded)
    target_validation = math.ceil(available.sum() * protocol["validation_fraction_of_available_calibration"])
    chosen_cells, validation = [], []
    for group in sorted(set(np.asarray(key)[available]), key=lambda x: order_key(salt, "validation:" + x)):
        selected = np.flatnonzero(available & (np.asarray(key) == group)).tolist()
        validation.extend(selected)
        chosen_cells.append(tuple(map(int, group.split(":"))))
        if len(validation) >= target_validation:
            break
    if not validation:
        raise ValueError("no complete validation cells")
    vd = np.max(np.abs(cell[:, None, :] - np.asarray(chosen_cells)[None, :, :]), axis=2)
    train_eligible = available & ~(vd <= spec["validation_exclusion_chebyshev_cells"]).any(1)
    full_train = np.flatnonzero(train_eligible).tolist()
    # Count all validation labels, including checkpoint selection, in the small budget.
    target_total = math.floor(available.sum() * protocol["calibration_fraction"])
    target_train = target_total - len(validation)
    # Repeated positions stay together. This does not invent independent acquisition groups.
    position_groups = {}
    for i in full_train:
        position_groups.setdefault(tuple(float(v) for v in y[i]), []).append(i)
    train = []
    for position in sorted(position_groups, key=lambda p: order_key(salt, "position:" + repr(p))):
        group = position_groups[position]
        if len(train) + len(group) <= target_train:
            train.extend(group)
    test = np.flatnonzero(is_test).tolist()
    gate = protocol["primary_gate"]
    full_budget = len(full_train) + len(validation)
    small_budget = len(train) + len(validation)
    problems = []
    for label, count, required in (("training", len(train), gate["minimum_training_samples"]),
                                    ("validation", len(validation), gate["minimum_validation_samples"]),
                                    ("test", len(test), gate["minimum_test_samples"]),
                                    ("test blocks", len(set(np.asarray(key)[is_test])), gate["minimum_test_spatial_blocks"])):
        if count < required:
            problems.append(f"{label}: {count} below {required}")
    if len(full_train) > protocol["limits"]["training_samples_maximum"]:
        problems.append("full training pool exceeds registered size cap")
    if not full_budget or small_budget / full_budget > gate["maximum_small_to_full_label_budget_ratio"]:
        problems.append("total calibration label reduction is insufficient")
    return {
        "schema_version": 1, "status": "qualified" if not problems else "qualification_fail",
        "problems": problems, "manifest_sha256": metadata["manifest_sha256"],
        "train": sorted(train), "full_train": sorted(full_train), "validation": sorted(validation),
        "test": sorted(test), "spatial_groups": key, "n": len(y),
        "small_label_budget": small_budget, "full_label_budget": full_budget,
        "test_signal_values_accessed": False,
        "partition_scope": "spatial_holdout_with_test_and_validation_exclusion_gaps",
        "supplied_split_status": "not_used_for_new_test",
        "acquisition_generalization_claim": False,
    }


def validate_partition(split, n, protocol=None):
    sets = []
    for name in ("train", "validation", "test", "full_train"):
        values = split[name]
        if len(set(values)) != len(values) or any(type(i) is not int or not 0 <= i < n for i in values):
            raise ValueError("invalid indices: " + name)
        sets.append(set(values))
    train, validation, test, full = sets
    if train & validation or train & test or validation & test or full & (validation | test) or not train <= full:
        raise ValueError("split overlap or inconsistent full calibration pool")
    if len(split["spatial_groups"]) != n or split["status"] != "qualified":
        raise ValueError("partition did not qualify")
    if split["small_label_budget"] != len(train) + len(validation) or split["full_label_budget"] != len(full) + len(validation):
        raise ValueError("validation labels are missing from calibration accounting")
    if protocol is not None:
        gate = protocol["primary_gate"]
        groups = split["spatial_groups"]
        if (len(train) < gate["minimum_training_samples"] or len(validation) < gate["minimum_validation_samples"]
                or len(test) < gate["minimum_test_samples"]
                or len({groups[i] for i in test}) < gate["minimum_test_spatial_blocks"]
                or len(full) > protocol["limits"]["training_samples_maximum"]
                or split["small_label_budget"] / split["full_label_budget"] > gate["maximum_small_to_full_label_budget_ratio"]):
            raise ValueError("partition no longer meets registered eligibility")
        cells = np.asarray([list(map(int, value.split(":"))) for value in groups])
        for left, right, distance in ((full, test, protocol["partition"]["test_exclusion_chebyshev_cells"]),
                                     (validation, test, protocol["partition"]["test_exclusion_chebyshev_cells"]),
                                     (full, validation, protocol["partition"]["validation_exclusion_chebyshev_cells"])):
            if (np.max(np.abs(cells[list(left), None, :] - cells[None, list(right), :]), axis=2) <= distance).any():
                raise ValueError("spatial partition exclusion gap violated")
