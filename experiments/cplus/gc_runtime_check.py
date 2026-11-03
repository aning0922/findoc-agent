"""Real OS fake-child retirement/GC proof in a new synthetic temporary control root."""
import asyncio
import json
from pathlib import Path
import tempfile

from app.demo.config import DemoConfig, password_hash
from app.demo.process import ProcessRuntimeManager, group_alive
from app.demo.seed import build_synthetic_seed, verify_seed


async def main():
    owned = Path(tempfile.mkdtemp(prefix="findoc-cplus-gc-proof-")).resolve()
    seed, control = owned/"seed", owned/"control"
    _, digest = build_synthetic_seed(seed)
    config = DemoConfig(control_root=control, seed_root=seed, username="fixture-only",
                        password_hash=password_hash("fixture-not-used-for-login"),
                        origins=("http://127.0.0.1:14599",), secure_cookie=False)
    manager = ProcessRuntimeManager(config, child_mode="fake", retired_gc=True)
    old_pids = []
    try:
        await manager.recover()
        await manager.reset(1)
        old_pids.append(manager.process.pid)
        await manager.reset(2)
        old_pids.append(manager.process.pid)
        (control/"public-pdf-cache").mkdir()
        (control/"public-pdf-cache"/"preserve").write_text("synthetic public cache sentinel")
        await manager.reset(3)
        assert manager.last_gc_report["deleted"] == [1]
        assert not (control/"active/1").exists()
        assert (control/"active/2").exists() and (control/"active/3").exists()
        assert all(not group_alive(pid) for pid in old_pids)
        dry = await manager.gc_retired_generations(dry_run=True, keep=0)
        assert dry["eligible"] == [2] and dry["deleted"] == []
        assert (control/"active/2").exists()
        assert (control/"public-pdf-cache"/"preserve").is_file()
        assert verify_seed(seed)[1] == digest
        result = dict(tier="REAL_OS_PRIVATE_HTTP_FAKE_CHILD_SYNTHETIC_SEED", owned_root=str(owned),
                      generations_started=[1,2,3], retired_process_groups_exited=True,
                      deleted_generations=[1], kept_retired_generation=2, current_generation=3,
                      dry_run=dry, seed_unchanged=True, public_cache_sentinel_unchanged=True,
                      provider_calls=0, real_pdfs=0, human_financial_approvals=0,
                      limits="Not browser login/takeover or real BGE/cache-import proof; exercised child readiness HTTP and real OS retirement only.")
    finally:
        await manager.close()
    path=Path(__file__).resolve().parents[2]/"docs/cplus/evidence/M1-gc-runtime.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
