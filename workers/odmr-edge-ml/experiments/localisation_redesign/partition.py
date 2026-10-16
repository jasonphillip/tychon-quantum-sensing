"""Geometry-only coverage selection; preserve every original held partition."""
import copy
import hashlib
import numpy as np
from .bundle import positions_only
from .guard import read_json, sha256


def coverage_positions(points, count):
    """Farthest-point selection in physical micrometres; lexicographic ties."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError("finite two-dimensional positions required")
    points = np.unique(points, axis=0)  # lexicographic ordering fixes every tie
    if not 1 <= count <= len(points):
        raise ValueError("invalid coverage budget")
    first = int(np.argmin(np.sum((points - points.mean(axis=0)) ** 2, axis=1)))
    selected = [first]
    distances = np.sum((points - points[first]) ** 2, axis=1)
    distances[first] = -np.inf
    while len(selected) < count:
        index = int(np.argmax(distances))
        selected.append(index)
        distances = np.minimum(distances, np.sum((points - points[index]) ** 2, axis=1))
        distances[selected] = -np.inf
    return points[selected]


def make_partition(bundle, parent_path, protocol):
    if sha256(parent_path) != protocol["parent_partition_sha256"]:
        raise ValueError("original partition hash differs")
    parent = read_json(parent_path)
    y, _, metadata = positions_only(bundle)
    validate_partition(parent, metadata["n"])
    if parent["manifest_sha256"] != metadata["manifest_sha256"]:
        raise ValueError("parent partition used a different bundle")
    # Recheck original coordinate identities without reading any measured features.
    keys = [hashlib.sha256(("exact_position:" + repr(tuple(float(v) for v in row))).encode()).hexdigest() for row in y]
    if keys != parent["position_groups"]:
        raise ValueError("parent coordinate identities changed")
    selected = coverage_positions(y[parent["full_train"]], protocol["calibration"]["training_unique_positions"])
    selected_set = set(map(tuple, selected))
    split = copy.deepcopy(parent)
    split["train"] = [i for i in parent["full_train"] if tuple(y[i]) in selected_set]
    split["parent_partition_sha256"] = sha256(parent_path)
    split["coverage_selection_order_um"] = selected.tolist()
    split["selection_method"] = "centroid_start_farthest_point_physical_um_lexicographic_ties"
    split["small_label_budget"] = len(selected) + parent["partition_unique_positions"]["validation"]
    split["small_measurement_rows"] = len(split["train"]) + len(split["validation"])
    split["partition_unique_positions"]["train"] = len(selected)
    memberships = split["possible_acquisition_groups"]
    split["possible_session_row_counts"]["train"] = {
        s: sum(s in memberships[i] for i in split["train"])
        for s in sorted({s for i in split["train"] for s in memberships[i]})}
    split["old_small_budget_failure_reopened"] = False
    split["status"] = "qualified"
    validate_redesign(split, protocol)
    # These fields are exactly inherited, not regenerated around observed errors.
    for key in ("test", "validation", "full_train", "spatial_groups", "position_groups",
                "possible_session_overlap", "session_assignment_status"):
        if split[key] != parent[key]:
            raise ValueError("preserved parent partition field changed: " + key)
    return split


def validate_redesign(split, protocol):
    validate_partition(split, split["n"], protocol)
    expected = {"train": 90, "validation": 34, "test": 36, "full_train": 214}
    actual = {key: len({split["position_groups"][i] for i in split[key]}) for key in expected}
    if actual != expected or actual != split["partition_unique_positions"]:
        raise ValueError("registered unique-position counts changed")
    if (split.get("parent_partition_sha256") != protocol["parent_partition_sha256"]
            or split["small_label_budget"] != 124 or split["full_label_budget"] != 248
            or split.get("selection_method") != "centroid_start_farthest_point_physical_um_lexicographic_ties"):
        raise ValueError("new calibration contract changed")


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
