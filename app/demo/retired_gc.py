"""Bounded cleanup of this controller's positively retired generation directories."""
import json
from pathlib import Path
import shutil
import time

from app.demo.seed import sha256


def remember_retired(control: Path, record: dict, manifest_sha: str) -> None:
    generation = record.get("generation")
    if type(generation) is not int or generation < 1:
        raise ValueError("invalid_retired_generation")
    directory = control / "retirements"
    directory.mkdir(exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise ValueError("retirement_directory_symlink")
    value = {**record, "seed_manifest_sha256": manifest_sha,
             "retirement_proof": "verified_process_group_exited", "retired_at": time.time()}
    target = directory / f"{generation}.json"
    if target.is_symlink():
        raise ValueError("retirement_marker_symlink")
    temporary = directory / f"{generation}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("unexpected_retirement_temporary")
    with temporary.open("x") as stream:
        temporary.chmod(0o600)
        json.dump(value, stream)
    temporary.replace(target)


def collect_retired(control: Path, seed: Path, current: Path | None, *,
                    process_birth, group_alive, dry_run=True, keep=1) -> dict:
    if type(keep) is not int or not 0 <= keep <= 10:
        raise ValueError("invalid_retired_keep_count")
    if not control.is_absolute() or any(x.is_symlink() for x in (control, *control.parents)):
        raise ValueError("unsafe_gc_control_root")
    active, markers = control / "active", control / "retirements"
    if active.is_symlink() or markers.is_symlink() or active.resolve() == seed.resolve():
        raise ValueError("unsafe_gc_active_root")
    result = {"dry_run": dry_run, "kept_retired_count": keep,
              "eligible": [], "deleted": [], "skipped": []}
    if not markers.exists():
        return result
    candidates = []
    for marker in markers.glob("*.json"):
        if marker.is_symlink() or not marker.stem.isdecimal():
            result["skipped"].append({"name": marker.name, "reason": "invalid_marker"})
            continue
        try:
            record = json.loads(marker.read_text())
            generation = record["generation"]
            if (type(generation) is not int or str(generation) != marker.stem
                    or record["retirement_proof"] != "verified_process_group_exited"):
                raise ValueError()
            candidates.append((generation, marker, record))
        except (ValueError, KeyError, TypeError):
            result["skipped"].append({"name": marker.name, "reason": "invalid_marker"})
    candidates.sort(reverse=True, key=lambda item: item[0])
    for n, (generation, marker, record) in enumerate(candidates):
        root = active / str(generation)
        reason = None
        if n < keep:
            reason = "retained_for_diagnostics"
        elif not root.exists() or root.is_symlink() or not root.is_dir():
            reason = "missing_or_symlink_generation"
        elif root.resolve().parent != active.resolve() or root.resolve() == seed.resolve():
            reason = "outside_owned_active_root"
        elif current is not None and root.resolve() == current.resolve():
            reason = "current_generation"
        elif any(x.is_symlink() for x in root.rglob("*")):
            reason = "nested_symlink"
        else:
            manifest = root / ".demo-manifest.json"
            if not manifest.is_file() or sha256(manifest) != record.get("seed_manifest_sha256"):
                reason = "unverified_materialization"
            elif (type(record.get("pid")) is not int or record["pid"] <= 1
                  or record.get("pgid") != record["pid"] or not record.get("birth")):
                reason = "invalid_process_identity"
            elif process_birth(record["pid"]) is not None or group_alive(record["pgid"]):
                reason = "process_identity_not_quiescent"
        if reason:
            result["skipped"].append({"generation": generation, "reason": reason})
            continue
        result["eligible"].append(generation)
        if not dry_run:
            # No runtime writer remains; rmtree never follows directory symlinks.
            try:
                shutil.rmtree(root)
                marker.unlink()
                result["deleted"].append(generation)
            except OSError:
                result["skipped"].append({"generation": generation, "reason": "filesystem_cleanup_failed"})
    return result
