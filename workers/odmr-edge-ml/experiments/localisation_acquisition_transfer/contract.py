"""Metadata-only contracts and exact stage-label identity."""
import hashlib
from pathlib import PurePosixPath
import re

ROOT = "Data availability update 20260220/"
DAY = "Fig.3 and ML model and data/Fig. 3b and Fig. 3c/2025-08-04 175200chip15 45mW/"
LABEL = re.compile(r"x=([0-9.]+)um, y=([0-9.]+)um raw data\.npy$")


def position_hash(position):
    return hashlib.sha256(("exact_position:" + repr(tuple(float(v) for v in position))).encode()).hexdigest()


def check_geometry(geometry, custody):
    rows=geometry["members"]
    originals=sorted(custody["august4"]["members"],key=lambda r:tuple(r["position_um"]))
    if len(rows)!=25 or len(originals)!=25 or geometry["count"]!=25:
        raise ValueError("exactly all 25 cases required")
    positions=[tuple(row["position_um"]) for row in rows]
    xs,ys=sorted({p[0] for p in positions}),sorted({p[1] for p in positions})
    if len(set(positions))!=25 or len(xs)!=5 or len(ys)!=5 or set(positions)!={(x,y) for x in xs for y in ys}:
        raise ValueError("complete unique 5x5 geometry required")
    for row,original in zip(rows, originals):
        if {k:v for k,v in row.items() if k not in ("group_id","position_sha256")}!=original:
            raise ValueError("member differs from custody")
        name=row["member"]
        if not name.startswith(DAY) or ".." in PurePosixPath(name).parts:
            raise ValueError("only exact separate-day members allowed")
        match=LABEL.search(name)
        if not match or tuple(map(float,match.groups()))!=tuple(row["position_um"]):
            raise ValueError("filename stage-label mismatch")
        if row["position_sha256"]!=position_hash(row["position_um"]):
            raise ValueError("stage-label identity mismatch")
        if row["group_id"]!="y_stripe_"+str(ys.index(row["position_um"][1])):
            raise ValueError("prospective whole-stripe grouping changed")
    return rows


def check_saved_labels(labels, geometry):
    if len(labels)!=25:
        raise ValueError("label count mismatch")
    for row,reference in zip(labels,geometry["members"]):
        if len(row)!=2 or position_hash(row)!=reference["position_sha256"]:
            raise ValueError("saved stage-label identity mismatch")


def decode_seed_bytes(payload, expected_sha256):
    if len(payload)!=32 or hashlib.sha256(payload).hexdigest()!=expected_sha256:
        raise ValueError("released seed does not match 256-bit commitment")
    return int.from_bytes(payload,"big")
