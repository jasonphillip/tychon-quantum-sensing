"""Metadata/header-only preparation; never read a raw signal payload."""
import argparse
from pathlib import Path
import sys
import zipfile
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "experiments.localisation_raw_compatibility"
from .guard import read_json, write_json, sha256, PACKAGE
from .metadata import raw_inventory, select_sample, read_raw_header, bind_custody


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--custody", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    protocol = read_json(PACKAGE / "protocol.json")
    if sha256(args.partition) != protocol["partition_sha256"]:
        raise ValueError("partition changed")
    if sha256(args.custody) != protocol["custody_sha256"]:
        raise ValueError("custody changed")
    custody = read_json(args.custody)
    split = read_json(args.partition)
    with zipfile.ZipFile(args.archive) as archive:
        sample = select_sample(split, raw_inventory(archive), protocol["sample_count"])
        bind_custody(sample, custody, protocol["archive_sha256"], protocol["partition_sha256"])
        for row in sample:
            with archive.open(row["member"]) as stream:
                row["header"] = read_raw_header(stream, row["uncompressed_size"])
    result = {"schema_version": 1, "purpose": "training_only_raw_compatibility",
              "selection": protocol["sample_selection"], "count": len(sample),
              "partition_sha256": sha256(args.partition),
              "custody_sha256": sha256(args.custody),
              "archive_sha256": protocol["archive_sha256"],
              "archive_hash_status": "custody_pin_recheck_required_by_qualified_job",
              "signal_payloads_decoded": False, "members": sample}
    write_json(args.output, result)
    print(str(Path(args.output).resolve()), sha256(args.output))


if __name__ == "__main__":
    main()
