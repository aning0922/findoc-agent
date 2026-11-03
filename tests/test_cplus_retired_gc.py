"""Owned synthetic temporary generation directories; no developer runtime deletion."""
import json

from app.demo.retired_gc import collect_retired, remember_retired
from app.demo.seed import build_synthetic_seed, materialize, verify_seed


def fixture(tmp_path):
    seed = tmp_path / "seed"
    _, digest = build_synthetic_seed(seed)
    control = tmp_path / "control"
    active = control / "active"
    active.mkdir(parents=True)
    for generation in (1, 2, 3):
        materialize(seed, active / str(generation), digest)
    for generation in (1, 2):
        remember_retired(control, dict(pid=1000000000+generation, pgid=1000000000+generation,
                                     birth="synthetic", instance_id=f"fixture-{generation}", generation=generation), digest)
    return seed, digest, control, active


def test_gc_dry_run_then_deletes_only_retired_keeping_recent_and_seed(tmp_path):
    seed, digest, control, active = fixture(tmp_path)
    for name in ("public-pdf-cache", "budget", "foreign"):
        (control/name).mkdir()
        (control/name/"keep").write_text("preserve")
    (active/"999").mkdir()  # No controller retirement proof: never a deletion candidate.
    args = dict(process_birth=lambda _: None, group_alive=lambda _: False)
    dry = collect_retired(control, seed, active/"3", **args)
    assert dry["eligible"] == [1] and dry["deleted"] == [] and (active/"1").exists()
    real = collect_retired(control, seed, active/"3", dry_run=False, **args)
    assert real["deleted"] == [1] and not (active/"1").exists()
    assert all((active/str(g)).exists() for g in (2, 3, 999))
    assert all((control/name/"keep").read_text()=="preserve" for name in ("public-pdf-cache", "budget", "foreign"))
    assert verify_seed(seed)[1] == digest


def test_gc_refuses_current_live_identity_and_nested_symlink(tmp_path):
    seed, _, control, active = fixture(tmp_path)
    (active/"1"/"outside").symlink_to(tmp_path, target_is_directory=True)
    report = collect_retired(control, seed, active/"2", keep=0, dry_run=False,
                             process_birth=lambda _: None, group_alive=lambda _: False)
    assert report["deleted"] == []
    assert {r["reason"] for r in report["skipped"]} == {"current_generation", "nested_symlink"}
    (active/"1"/"outside").unlink()
    report = collect_retired(control, seed, active/"3", keep=0, dry_run=False,
                             process_birth=lambda _: "different-live-process", group_alive=lambda _: False)
    assert report["deleted"] == []
    assert all(r["reason"] == "process_identity_not_quiescent" for r in report["skipped"])


def test_modified_manifest_does_not_authorize_gc(tmp_path):
    seed, _, control, active = fixture(tmp_path)
    marker = control/"retirements/1.json"
    value=json.loads(marker.read_text())
    value['seed_manifest_sha256']='0'*64
    marker.write_text(json.dumps(value))
    report=collect_retired(control,seed,active/"3",dry_run=False,
                           process_birth=lambda _:None,group_alive=lambda _:False)
    assert report['deleted']==[] and (active/'1').exists()
    assert any(r['reason']=='unverified_materialization' for r in report['skipped'])
