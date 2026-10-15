"""Strict primary-HDU FITS reader and spatial partitions for Zenodo 7233869."""
import hashlib
import math
from pathlib import Path


def inspect_header(path):
    """Read complete header blocks only. Never inspect an image value."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("FITS input must not be a symlink")
    cards, raw, ended = {}, bytearray(), False
    with path.open("rb") as stream:
        for _ in range(32):
            block = stream.read(2880)
            if len(block) != 2880:
                raise ValueError("Incomplete FITS header")
            raw.extend(block)
            for offset in range(0, 2880, 80):
                card = block[offset:offset + 80].decode("ascii")
                key = card[:8].strip()
                if key == "END":
                    ended = True
                    break
                if card[8:10] != "= ":
                    continue
                if key in cards:
                    raise ValueError("Duplicate FITS keyword: " + key)
                value = card[10:].split("/", 1)[0].strip()
                if value in ("T", "F"):
                    value = value == "T"
                elif value.startswith("'"):
                    value = value.strip("' ")
                else:
                    value = float(value.replace("D", "E")) if any(c in value for c in ".ED") else int(value)
                cards[key] = value
            if ended:
                break
    if not ended:
        raise ValueError("Header exceeds bounded reader")
    shape = tuple(cards.get("NAXIS" + str(i)) for i in (4, 3, 2, 1))
    if cards.get("SIMPLE") is not True or cards.get("NAXIS") != 4 or shape != (5, 200, 1024, 1280):
        raise ValueError("Unexpected primary FITS shape; do not guess axes")
    if cards.get("BITPIX") != 16 or cards.get("BSCALE", 1) != 1 or cards.get("BZERO", 0) != 32768:
        raise ValueError("Unexpected storage convention")
    if cards.get("NSCANS") != shape[0]:
        raise ValueError("Repeat count does not match outer axis")
    start, step, stop = (float(cards[k]) for k in ("STARFREQ", "STEPSIZE", "STOPFREQ"))
    if step <= 0 or not math.isclose(start + shape[1] * step, stop, abs_tol=1e-9):
        raise ValueError("Frequency metadata does not define a stop-exclusive grid")
    data_bytes = math.prod(shape) * 2
    expected_bytes = len(raw) + ((data_bytes + 2879) // 2880) * 2880
    return {"cards": cards, "shape": list(shape), "offset": len(raw),
            "header_sha256": hashlib.sha256(raw).hexdigest(), "expected_bytes": expected_bytes,
            "actual_bytes": path.stat().st_size, "complete": path.stat().st_size == expected_bytes,
            "axis_order": ["repeat_ordinal", "frequency", "y", "x"],
            "temporal_order": "No per-frame timestamps; repeat ordinal is not verified chronological time.",
            "frequency_mhz": [start + i * step for i in range(shape[1])]}


def blocks(split):
    """Central 512-square crop; whole block columns define disjoint regions."""
    columns = {"train": range(4), "development": range(4, 6), "final": range(6, 8)}[split]
    for row in range(8):
        for column in columns:
            yield row * 8 + column, 256 + row * 64, 384 + column * 64


def image_map(path, metadata):
    import numpy as np
    if not metadata["complete"]:
        raise ValueError("Incomplete FITS download")
    return np.memmap(path, mode="r", dtype=">i2", offset=metadata["offset"], shape=tuple(metadata["shape"]))


def validate_rows(rows, split):
    """Reject partial groups, duplicates, bad indices, or cross-partition patches."""
    import numpy as np
    expected = {group: (y, x) for group, y, x in blocks(split)}
    if rows.dtype.kind not in "iu" or rows.shape != (len(expected) * 3 * 8, 5):
        raise ValueError("Incomplete or invalid partition row keys")
    expected_keys = [(f, g, p) for f in range(3) for g in expected for p in range(8)]
    if list(map(tuple, rows[:, :3])) != expected_keys:
        raise ValueError("Unexpected partition row order or duplicate rows")
    for file_index in range(3):
        for group, (y, x) in expected.items():
            coordinates = rows[(rows[:, 0] == file_index) & (rows[:, 1] == group), 3:]
            relative = coordinates - [y + 8, x + 8]
            if np.any(relative < 0) or np.any(relative > 44) or np.any(relative % 4):
                raise ValueError("Patch outside registered guarded grid")
            distance = np.max(np.abs(coordinates[:, None] - coordinates[None, :]), axis=2)
            if np.any(distance[np.triu_indices(8, 1)] < 8):
                raise ValueError("Patch separation differs from registered selection")


def patch_spectrum(image, repeat, y, x):
    import numpy as np
    if repeat not in range(5) or not (0 <= y <= 1020 and 0 <= x <= 1276):
        raise ValueError("Patch outside FITS dimensions")
    values = np.asarray(image[repeat, :, y:y + 4, x:x + 4], dtype=np.float64) + 32768.0
    return values.mean(axis=(1, 2)), bool(np.any((values == 0) | (values == 65535)))


def select_patches(image, y, x):
    """Read repeat0 within one guarded block, then select eight separated patches."""
    import numpy as np
    crop = np.asarray(image[0, :, y + 8:y + 56, x + 8:x + 56], dtype=np.float64) + 32768.0
    brightness = crop.mean(axis=0).reshape(12, 4, 12, 4).mean(axis=(1, 3))
    ranked = sorted(((float(brightness[i, j]), i, j) for i in range(12) for j in range(12)),
                    key=lambda item: (-item[0], item[1], item[2]))
    chosen = []
    for _, row, column in ranked:
        if all(max(abs(row - r), abs(column - c)) >= 2 for r, c in chosen):
            chosen.append((row, column))
        if len(chosen) == 8:
            break
    if len(chosen) != 8:
        raise ValueError("Insufficient separated patches")
    return [(y + 8 + row * 4, x + 8 + column * 4) for row, column in chosen]


def normalize(values):
    import numpy as np
    scale = float(np.median(np.r_[values[:10], values[-10:]]))
    if not np.isfinite(values).all() or not math.isfinite(scale) or scale <= 0:
        raise ValueError("Undefined endpoint normalization; stop rather than remove outcome-dependent rows")
    return values / scale, scale
