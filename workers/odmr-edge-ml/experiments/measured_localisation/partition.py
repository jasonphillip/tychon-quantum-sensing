"""Fixed geometric partition, generated only under numerical approval."""
import hashlib
import math

import numpy as np

from .bundle import positions_only, possible_sessions, supplied_position_summary


def order_key(salt, value):
    return hashlib.sha256((salt + ":" + str(value)).encode()).hexdigest()


def make_partition(manifest_path, protocol, salt):
    y, manifest, metadata = positions_only(manifest_path)
    y = np.asarray(y, dtype=float)
    if not np.isfinite(y).all():
        raise ValueError("nonfinite position labels")
    bounds = np.asarray(manifest["operating_bounds_um"], dtype=float)
    if bounds.shape != (2, 2) or (bounds[:, 1] <= bounds[:, 0]).any():
        raise ValueError("custody must declare [xmin,xmax],[ymin,ymax]")
    if ((y < bounds[:, 0]) | (y > bounds[:, 1])).any():
        raise ValueError("position outside declared operating bounds")
    spec = protocol["partition"]
    if spec.get("acquisition_policy") != "spatial_within_represented_sessions_disclose_possible_overlap":
        raise ValueError("root must choose and freeze the acquisition-generalization scope")
    memberships = possible_sessions(manifest_path, y)
    position_keys = [repr(tuple(float(v) for v in row)) for row in y]
    def unique_count(indices):
        return len({position_keys[i] for i in indices})
    grid = np.asarray(spec["grid"], dtype=int)
    cell = np.minimum(np.floor((y - bounds[:, 0]) / np.diff(bounds, axis=1).ravel() * grid).astype(int), grid - 1)
    key = [f"{a}:{b}" for a, b in cell]
    test_cells = np.asarray(spec["test_cells"], dtype=int)
    distances = np.max(np.abs(cell[:, None, :] - test_cells[None, :, :]), axis=2)
    is_test = (distances == 0).any(1)
    excluded = (distances <= spec["test_exclusion_chebyshev_cells"]).any(1) & ~is_test
    available = ~(is_test | excluded)
    available_unique = unique_count(np.flatnonzero(available))
    target_validation = math.ceil(available_unique * protocol["validation_fraction_of_available_calibration"])
    chosen_cells, validation = [], []
    for group in sorted(set(np.asarray(key)[available]), key=lambda x: order_key(salt, "validation:" + x)):
        selected = np.flatnonzero(available & (np.asarray(key) == group)).tolist()
        validation.extend(selected)
        chosen_cells.append(tuple(map(int, group.split(":"))))
        if unique_count(validation) >= target_validation:
            break
    if not validation:
        raise ValueError("no complete validation cells")
    vd = np.max(np.abs(cell[:, None, :] - np.asarray(chosen_cells)[None, :, :]), axis=2)
    train_eligible = available & ~(vd <= spec["validation_exclusion_chebyshev_cells"]).any(1)
    full_train = np.flatnonzero(train_eligible).tolist()
    # Count all validation labels, including checkpoint selection, in the small budget.
    target_total = math.floor(available_unique * protocol["calibration_fraction"])
    target_train = target_total - unique_count(validation)
    # Repeated positions stay together. This does not invent independent acquisition groups.
    position_groups = {}
    for i in full_train:
        position_groups.setdefault(tuple(float(v) for v in y[i]), []).append(i)
    train = []
    for position in sorted(position_groups, key=lambda p: order_key(salt, "position:" + repr(p))):
        group = position_groups[position]
        if unique_count(train) < target_train:
            train.extend(group)
    test = np.flatnonzero(is_test).tolist()
    gate = protocol["primary_gate"]
    full_budget = unique_count(full_train + validation)
    small_budget = unique_count(train + validation)
    problems = []
    for label, count, required in (("training unique positions", unique_count(train), gate["minimum_training_samples"]),
                                    ("validation unique positions", unique_count(validation), gate["minimum_validation_samples"]),
                                    ("test unique positions", unique_count(test), gate["minimum_test_samples"]),
                                    ("test blocks", len(set(np.asarray(key)[is_test])), gate["minimum_test_spatial_blocks"])):
        if count < required:
            problems.append(f"{label}: {count} below {required}")
    if len(full_train) > protocol["limits"]["training_samples_maximum"]:
        problems.append("full training pool exceeds registered size cap")
    if not full_budget or small_budget / full_budget > gate["maximum_small_to_full_label_budget_ratio"]:
        problems.append("total calibration label reduction is insufficient")
    partitions = {"train": sorted(train), "full_train": sorted(full_train), "validation": sorted(validation), "test": sorted(test)}
    session_counts = {name: {s: sum(s in memberships[i] for i in rows)
                             for s in sorted({s for i in rows for s in memberships[i]})}
                      for name, rows in partitions.items()}
    overlaps = {a + "__" + b: sorted(set(session_counts[a]) & set(session_counts[b]))
                for a, b in (("full_train", "validation"), ("full_train", "test"), ("validation", "test"))}
    return {
        "schema_version": 2, "status": "qualified" if not problems else "qualification_fail",
        "problems": problems, "manifest_sha256": metadata["manifest_sha256"],
        "train": sorted(train), "full_train": sorted(full_train), "validation": sorted(validation),
        "test": sorted(test), "spatial_groups": key, "n": len(y),
        "small_label_budget": small_budget, "full_label_budget": full_budget,
        "label_budget_unit": "unique_stage_xy_positions_including_validation",
        "small_measurement_rows": len(train) + len(validation),
        "full_measurement_rows": len(full_train) + len(validation),
        "partition_unique_positions": {name: unique_count(rows) for name, rows in partitions.items()},
        "position_groups": [order_key("exact_position", key) for key in position_keys],
        "possible_acquisition_groups": memberships,
        "possible_session_row_counts": session_counts,
        "possible_session_overlap": overlaps,
        "rows_with_ambiguous_session_identity": sum(len(group) > 1 for group in memberships),
        "session_assignment_status": "coordinate_catalog_memberships_only_version_A_raw_lineage_unresolved",
        "supplied_split_geometry": supplied_position_summary(manifest_path, y),
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
    positions = split["position_groups"]
    if len(positions) != n or split.get("label_budget_unit") != "unique_stage_xy_positions_including_validation":
        raise ValueError("unique-position calibration accounting required")
    def unique_count(indices):
        return len({positions[i] for i in indices})
    for left, right in ((train, validation), (train, test), (validation, test), (full, test), (full, validation)):
        if {positions[i] for i in left} & {positions[i] for i in right}:
            raise ValueError("repeated stage position crosses partitions")
    for rows in (train, validation, test, full):
        groups = {positions[i] for i in rows}
        if any(group in groups and i not in rows for i, group in enumerate(positions)):
            raise ValueError("a repeated position was only partly selected")
    if split["small_label_budget"] != unique_count(train | validation) or split["full_label_budget"] != unique_count(full | validation):
        raise ValueError("validation labels are missing from calibration accounting")
    if split["small_measurement_rows"] != len(train | validation) or split["full_measurement_rows"] != len(full | validation):
        raise ValueError("measurement-row accounting mismatch")
    if protocol is not None:
        gate = protocol["primary_gate"]
        groups = split["spatial_groups"]
        if (unique_count(train) < gate["minimum_training_samples"] or unique_count(validation) < gate["minimum_validation_samples"]
                or unique_count(test) < gate["minimum_test_samples"]
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
