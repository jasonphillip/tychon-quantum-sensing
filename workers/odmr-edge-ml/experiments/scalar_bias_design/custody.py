"""One-shot Stage 2 custody. Stdlib only; never print secret material.
create: --custody-root NEW --public-root NEW --protocol FILE --registration JSON
freeze/access/reveal: --custody-root ROOT --protocol FILE --registration JSON
  --code-root DIR --code-manifest JSON; access/reveal also --freeze-sha256 HASH
access: --data-manifest JSON --data-manifest-sha256 HASH
reveal: additionally --result FILE --result-manifest JSON --report JSON
  --result-sha256 HASH --result-manifest-sha256 HASH --report-sha256 HASH
Registration: {stage: "stage2", approved: true, protocol_sha256: SHA256}.
Code manifest: {files: {relative_path: SHA256}}. Paths cannot contain '..'.
Result manifest: {freeze_sha256, access_sha256, result_sha256}.
Report: {freeze_sha256, access_sha256, status: "complete" or "failed"}.
Both roots must remain outside Syncthing. Public metadata are exclusive 0444 files.
After reveal, publish reveal.json and retired.json through the publication owner.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
def check(ok, message):
    if not ok:
        raise ValueError(message)
def safe(value):
    p = Path(value).absolute()
    check(not any(x.is_symlink() for x in (p, *p.parents)), "symlink path refused")
    check(".." not in p.parts, "parent traversal refused")
    return p
def file_bytes(value):
    p = safe(value)
    check(p.is_file(), "regular file required")
    return p.read_bytes()
def sha(value):
    return hashlib.sha256(file_bytes(value)).hexdigest()
def read(value):
    return json.loads(file_bytes(value))
def identity(path):
    s = safe(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
def immutable(path, content, mode=0o444):
    p = safe(path)
    data = content if isinstance(content, bytes) else (json.dumps(content, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        os.fchmod(f.fileno(), mode)
def root_path(value):
    p = safe(value)
    check(not any(x.name.casefold() in ("shared", "syncthing", "sync") for x in (p, *p.parents)),
          "custody/public root cannot be in a sync folder")
    return p
def context(a):
    root = root_path(a.custody_root)
    check(stat.S_IMODE(root.stat().st_mode) == 0o700, "private root must be 0700")
    state = read(root / "state.json")
    public = root_path(state["public_root"])
    check(identity(public)[:2] == state["public_identity"], "public directory replaced")
    for name in ("protocol", "registration"):
        p = safe(getattr(a, name))
        check(identity(p) == state[name + "_identity"] and sha(p) == state[name + "_sha256"], name + " drift")
    secret = root / "secret.bin"
    check(stat.S_IMODE(safe(secret).stat().st_mode) == 0o400, "secret must be 0400")
    check(identity(secret) == state["secret_identity"], "secret file replaced or changed")
    check(len(file_bytes(secret)) == 32 and sha(secret) == state["commitment_sha256"], "secret commitment mismatch")
    check(sha(public / "commitment.json") == state["commitment_record_sha256"], "commitment record drift")
    check(not (root / "retired.json").exists() and not (public / "retired.json").exists(), "custody retired")
    return root, public, state
@contextmanager
def locked(root):
    lock = safe(root) / "operation.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink()
def code(a):
    base = safe(a.code_root)
    manifest = read(a.code_manifest)
    check(isinstance(manifest.get("files"), dict) and manifest["files"], "nonempty code manifest required")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        check(not relative.is_absolute() and ".." not in relative.parts and relative.parts, "unsafe code path")
        check(sha(base / relative) == expected, "code hash drift: " + name)
    return {"code_manifest_sha256": sha(a.code_manifest), "files": manifest["files"]}
def create(a):
    root, public = root_path(a.custody_root), root_path(a.public_root)
    check(root != public and root not in public.parents and public not in root.parents, "roots must be disjoint")
    check(not root.exists() and not public.exists(), "custody/public root already exists")
    protocol, registration = sha(a.protocol), read(a.registration)
    check(registration.get("stage") == "stage2" and registration.get("approved") is True
          and registration.get("protocol_sha256") == protocol, "registered Stage 2 approval required")
    root.mkdir(mode=0o700)
    public.mkdir(mode=0o755)
    immutable(root / "secret.bin", secrets.token_bytes(32), 0o400)
    record = {"schema": 1, "protocol_sha256": protocol, "registration_sha256": sha(a.registration),
              "commitment_sha256": sha(root / "secret.bin"), "created_utc": datetime.now(timezone.utc).isoformat()}
    immutable(public / "commitment.json", record)
    immutable(root / "state.json", {**record, "public_root": str(public), "public_identity": identity(public)[:2],
        "secret_identity": identity(root / "secret.bin"), "protocol_identity": identity(a.protocol),
        "registration_identity": identity(a.registration), "commitment_record_sha256": sha(public / "commitment.json")}, 0o400)
    return record
def frozen(a, root, public, state):
    check(sha(public / "freeze.json") == a.freeze_sha256, "freeze hash mismatch")
    inputs = read(root / "freeze-inputs.json")
    check(identity(public / "freeze.json") == inputs["freeze_identity"], "freeze file replaced")
    check(identity(a.code_manifest) == inputs["manifest_identity"], "code manifest replaced")
    freeze = read(public / "freeze.json")
    check(freeze["protocol_sha256"] == state["protocol_sha256"]
          and freeze["commitment_sha256"] == state["commitment_sha256"], "freeze binding mismatch")
    check(code(a) == {k: freeze[k] for k in ("files", "code_manifest_sha256")}, "frozen code drift")
    return freeze
def consume_entropy(*, custody_root, protocol, registration, code_root, code_manifest, freeze_sha256, output_root):
    """Generator-only in-memory entropy handoff; never expose through CLI/stdout."""
    a = argparse.Namespace(**locals())
    with locked(root_path(a.custody_root)):
        root, public, state = context(a)
        frozen(a, root, public, state)
        output = safe(a.output_root)
        check(not output.exists(), "generation output already exists")
        immutable(root / "generation.used", {"freeze_sha256": a.freeze_sha256, "output_root": str(output)}, 0o400)
        return int.from_bytes(file_bytes(root / "secret.bin"), "big")
def verify_access(*, protocol, registration, freeze, access, code_root, data_manifest):
    """Public metadata/code checks only. Caller owns exclusive evaluation phases."""
    f, r, a, m = map(read, (freeze, registration, access, data_manifest))
    check(r.get("approved") is True and r.get("stage") == "stage2", "registration required")
    check(f["registration_sha256"] == sha(registration), "public registration drift")
    check(r["protocol_sha256"] == f["protocol_sha256"] == sha(protocol), "public protocol drift")
    check(a["freeze_sha256"] == m["freeze_sha256"] == sha(freeze), "public freeze drift")
    check(a["data_manifest_sha256"] == sha(data_manifest) and a["commitment_sha256"] == m["commitment_sha256"], "public manifest drift")
    check(f["commitment_sha256"] == a["commitment_sha256"], "public commitment drift")
    check(a["status"] == "authorized_once" and m.get("status") == "complete", "incomplete authorization")
    for name, expected in f["files"].items():
        check(not Path(name).is_absolute() and ".." not in Path(name).parts, "unsafe public code path")
        check(sha(safe(code_root) / name) == expected, "public code drift")
    return a
def advance(a):
    root = root_path(a.custody_root)
    with locked(root):
        root, public, state = context(a)
        if a.command == "freeze":
            check(not (root / "freeze-inputs.json").exists(), "already frozen")
            record = {**code(a), "schema": 1, "protocol_sha256": state["protocol_sha256"],
                      "registration_sha256": state["registration_sha256"],
                      "commitment_sha256": state["commitment_sha256"]}
            immutable(public / "freeze.json", record)
            immutable(root / "freeze-inputs.json", {"manifest_identity": identity(a.code_manifest),
                      "freeze_identity": identity(public / "freeze.json")}, 0o400)
            return {"freeze_sha256": sha(public / "freeze.json"), **record}
        frozen(a, root, public, state)
        if a.command == "access":
            check(not (root / "access.used").exists(), "evaluation already consumed")
            generation = read(root / "generation.used")
            check(generation["freeze_sha256"] == a.freeze_sha256, "generation authorization missing")
            check(safe(a.data_manifest).parent == safe(generation["output_root"]), "generation output root mismatch")
            check(not (safe(a.data_manifest).stat().st_mode | safe(generation["output_root"]).stat().st_mode) & 0o222, "generated manifest/root not sealed")
            check(sha(a.data_manifest) == a.data_manifest_sha256, "generated manifest hash mismatch")
            generated = read(a.data_manifest)
            check(generated.get("status") == "complete" and generated.get("freeze_sha256") == a.freeze_sha256
                  and generated.get("commitment_sha256") == state["commitment_sha256"], "generated manifest binding mismatch")
            record = {"schema": 1, "status": "authorized_once", "freeze_sha256": a.freeze_sha256,
                      "data_manifest_sha256": a.data_manifest_sha256,
                      "commitment_sha256": state["commitment_sha256"], "protocol_sha256": state["protocol_sha256"],
                      "accessed_utc": datetime.now(timezone.utc).isoformat()}
            immutable(root / "access.used", record, 0o400)
            immutable(public / "access.json", record)
            return {"access_sha256": sha(public / "access.json"), **record}
        check(sha(root / "access.used") == sha(public / "access.json"), "access receipt drift")
        access = sha(public / "access.json")
        for name in ("result", "result_manifest", "report"):
            check(sha(getattr(a, name)) == getattr(a, name + "_sha256"), name + " hash mismatch")
        manifest, report = read(a.result_manifest), read(a.report)
        for obj in (manifest, report):
            check(obj.get("freeze_sha256") == a.freeze_sha256 and obj.get("access_sha256") == access,
                  "result/report custody binding mismatch")
        check(manifest.get("result_sha256") == a.result_sha256, "result manifest payload mismatch")
        check(report.get("status") in ("complete", "failed"), "saved terminal report required")
        record = {"schema": 1, "commitment_sha256": state["commitment_sha256"], "freeze_sha256": a.freeze_sha256,
                  "access_sha256": access, "result_sha256": a.result_sha256,
                  "result_manifest_sha256": a.result_manifest_sha256, "report_sha256": a.report_sha256,
                  "report_status": report["status"], "retired_utc": datetime.now(timezone.utc).isoformat()}
        immutable(root / "retired.json", record, 0o400)
        immutable(public / "reveal.json", {**record, "secret_hex": file_bytes(root / "secret.bin").hex()})
        immutable(public / "retired.json", record)
        return {**record, "reveal_sha256": sha(public / "reveal.json")}
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("create", "freeze", "access", "reveal"):
        cmd = sub.add_parser(name)
        for key in ("custody-root", "protocol", "registration"):
            cmd.add_argument("--" + key, required=True)
        if name == "create":
            cmd.add_argument("--public-root", required=True)
        else:
            for key in ("code-root", "code-manifest"):
                cmd.add_argument("--" + key, required=True)
        if name in ("access", "reveal"):
            cmd.add_argument("--freeze-sha256", required=True)
        if name == "access":
            cmd.add_argument("--data-manifest", required=True)
            cmd.add_argument("--data-manifest-sha256", required=True)
        if name == "reveal":
            for key in ("result", "result-manifest", "report"):
                cmd.add_argument("--" + key, required=True)
                cmd.add_argument("--" + key + "-sha256", required=True)
    a = p.parse_args()
    print(json.dumps(create(a) if a.command == "create" else advance(a), sort_keys=True))
if __name__ == "__main__":
    main()
