"""Temporary fake allowance only; never opens the user's shared ledger."""
from pathlib import Path
import os
import subprocess

import pytest

from app.demo.provider_budget import ProviderBudget
from app.demo.shared_budget import existing_shared_budget
from scripts.run_showcase_local import environments


def repositories(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    subprocess.run(["git", "init", "-q", str(original)], check=True)
    (original / ".gitignore").write_text("data/*\n")
    subprocess.run(["git", "-C", str(original), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(original), "-c", "user.name=Fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
    sibling = tmp_path / "cplus"
    subprocess.run(["git", "-C", str(original), "worktree", "add", "-qb", "cplus", str(sibling)], check=True)
    ledger = original / "data/showcase-cost-control/provider-budget.db"
    return original, sibling, ledger


def test_sibling_reuses_one_existing_allowance_never_initializes(tmp_path):
    _, sibling, ledger = repositories(tmp_path)
    with pytest.raises(ValueError, match="existing_shared_budget"):
        existing_shared_budget(ledger, sibling)
    assert not ledger.exists()
    fake = ProviderBudget(ledger, "5")
    fake.reserve(b"synthetic unknown call", 1)
    before = ledger.read_bytes()
    assert existing_shared_budget(ledger, sibling) == ledger
    assert ledger.read_bytes() == before
    assert fake.summary()["calls"] == 1
    with pytest.raises(ValueError, match="outside_reset"):
        existing_shared_budget(ledger, sibling, forbidden_roots=(ledger.parent,))


def test_other_repo_symlink_hardlink_and_public_modes_rejected(tmp_path):
    original, sibling, ledger = repositories(tmp_path)
    ProviderBudget(ledger, "5")
    unrelated = tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(unrelated)], check=True)
    with pytest.raises(ValueError, match="same_git"):
        existing_shared_budget(ledger, unrelated)
    link = ledger.parent / "link.db"
    link.symlink_to(ledger)
    with pytest.raises(ValueError, match="non_symlink"):
        existing_shared_budget(link, sibling)
    link.unlink()
    os.link(ledger, link)
    with pytest.raises(ValueError, match="private_regular"):
        existing_shared_budget(ledger, sibling)
    link.unlink()
    ledger.chmod(0o644)
    with pytest.raises(ValueError, match="private_regular"):
        existing_shared_budget(ledger, sibling)
    assert (original / "data").is_dir()


def test_cplus_flags_keep_provider_backend_only_and_no_default_mock():
    backend, frontend = environments(
        dict(DEMO_USERNAME="fixture", DEMO_PASSWORD="a", DEMO_OWNER_PASSWORD="b"),
        dict(LLM_API_KEY="synthetic", LLM_MODEL="deepseek-flash"),
        Path("/fake/seed"), Path("/fake/control"), Path("/fake/existing-ledger"),
        "http://127.0.0.1:14540", 12345, "python", False, cplus=True,
    )
    assert backend["FINDOC_CPLUS_ENABLED"] == "1"
    assert backend["FINDOC_PROVIDER_BUDGET_DB"] == "/fake/existing-ledger"
    assert frontend["VITE_FINDOC_CPLUS_MODE"] == "1"
    assert frontend["VITE_FINDOC_SHOWCASE_PREVIEW_CHARTS"] == "0"
    assert not any(k.startswith(("LLM_", "FINDOC_PROVIDER_", "DEMO_")) for k in frontend)
