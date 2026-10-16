"""Only ZIP metadata, NPY headers, and existing position hashes; no NumPy."""
import ast
from collections import Counter, defaultdict
import hashlib
import re
import struct
from pathlib import PurePosixPath

PREFIX = "Data availability update 20260220/Fig.S4/Data/"
RAW_PATTERN = re.compile(r"x=([0-9.]+)um, y=([0-9.]+)um raw data\.npy$")
MAX_MEMBER_BYTES = 64 * 1024 * 1024


def coordinate_key(position):
    return hashlib.sha256(("exact_position:" + repr(tuple(float(v) for v in position))).encode()).hexdigest()


def raw_inventory(archive):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("duplicate ZIP member names")
    records = []
    for info in archive.infolist():
        if not info.filename.startswith(PREFIX) or not info.filename.endswith(" raw data.npy"):
            continue
        if ".." in PurePosixPath(info.filename).parts or info.flag_bits & 1:
            raise ValueError("unsafe or encrypted member")
        match = RAW_PATTERN.search(info.filename)
        if not match or not 1 <= info.file_size <= MAX_MEMBER_BYTES:
            raise ValueError("invalid raw metadata")
        position = tuple(map(float, match.groups()))
        records.append({"member": info.filename, "position_um": list(position),
                        "position_hash": coordinate_key(position),
                        "session": str(PurePosixPath(info.filename).parent),
                        "zip_crc32": format(info.CRC, "08x"), "uncompressed_size": info.file_size})
    return records


def select_sample(split, records, count):
    """Round robin across sessions; hash order within each; only small training."""
    if not isinstance(count, int) or count < 1:
        raise ValueError("positive sample count required")
    n = split["n"]
    groups = split["position_groups"]
    if len(groups) != n or len(set(split["train"])) != len(split["train"]):
        raise ValueError("invalid frozen row identity")
    train = set(split["train"])
    if (not train <= set(split["full_train"])
            or train & (set(split["validation"]) | set(split["test"]))
            or any(type(i) is not int or not 0 <= i < n for i in train)):
        raise ValueError("training-only membership required")
    fitted_count = Counter(groups)
    raw_count = Counter(r["position_hash"] for r in records)
    row_for = {groups[i]: i for i in train if fitted_count[groups[i]] == 1}
    sessions = defaultdict(list)
    for row in records:
        key = row["position_hash"]
        if key in row_for and raw_count[key] == 1:
            item = dict(row, fitted_row=row_for[key])
            order = hashlib.sha256(("raw-compatibility-v1:" + key).encode()).hexdigest()
            sessions[row["session"]].append((order, item))
    for rows in sessions.values():
        rows.sort(key=lambda pair: pair[0])
    selected = []
    depth = 0
    while len(selected) < count:
        added = False
        for session in sorted(sessions):
            if depth < len(sessions[session]):
                selected.append(sessions[session][depth][1])
                added = True
                if len(selected) == count:
                    break
        if not added:
            raise ValueError("too few unambiguous small-training raw pairs")
        depth += 1
    return selected


def read_raw_header(stream, expected_size):
    if stream.read(6) != b"\x93NUMPY":
        raise ValueError("ordinary NPY required")
    version = tuple(stream.read(2))
    if version == (1, 0):
        raw = stream.read(2)
        length = struct.unpack("<H", raw)[0]
        encoding = "latin1"
    elif version in ((2, 0), (3, 0)):
        length = struct.unpack("<I", stream.read(4))[0]
        encoding = "utf8" if version == (3, 0) else "latin1"
    else:
        raise ValueError("unsupported NPY version")
    if length > 65536:
        raise ValueError("header too large")
    header = ast.literal_eval(stream.read(length).decode(encoding))
    shape = header.get("shape")
    if (header.get("descr") not in ("<f8", "=f8") or header.get("fortran_order") is not False
            or not isinstance(shape, tuple) or len(shape) != 3
            or any(type(v) is not int for v in shape)
            or not 1 <= shape[0] <= 10000 or shape[1:] != (16, 51)):
        raise ValueError("expected bounded C-order float64 [T,16,51], no objects")
    if stream.tell() + shape[0] * 16 * 51 * 8 != expected_size or expected_size > MAX_MEMBER_BYTES:
        raise ValueError("NPY size/header mismatch")
    return {"shape": list(shape), "dtype": header["descr"], "fortran_order": False}


def bind_custody(sample, custody, archive_sha256, partition_sha256):
    """Exact coordinate-only candidate binding; never claim proven raw lineage."""
    if (custody.get("schema") != 1 or custody.get("signal_decoded") is not False
            or custody.get("archive_sha256") != archive_sha256
            or custody.get("partition_sha256") != partition_sha256):
        raise ValueError("custody scope or pins differ")
    candidates = custody["training_raw_candidates"]
    if candidates["partition_key"] != "full_train":
        raise ValueError("training custody required")
    rows = candidates["candidates"]
    by_row = {r["fitted_row"]: r for r in rows}
    if len(by_row) != len(rows):
        raise ValueError("duplicate custody row")
    for selected in sample:
        row = by_row.get(selected["fitted_row"], {})
        members = row.get("raw_members", [])
        if (row.get("unambiguous") is not True or row.get("raw_member_count") != 1
                or len(members) != 1 or row.get("position_um") != selected["position_um"]):
            raise ValueError("selected row lacks an unambiguous custody candidate")
        raw = members[0]
        if ("Data availability update 20260220/" + raw["member"] != selected["member"]
                or raw["crc32"] != selected["zip_crc32"]
                or raw["size"] != selected["uncompressed_size"]):
            raise ValueError("selected member differs from custody")
