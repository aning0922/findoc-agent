import socket
import stat
import subprocess

import pytest

from scripts.run_showcase_local import (
    environments,
    init_config,
    port_available,
    private_values,
    provider_values,
)


def repo(root):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("data/*\n")
    (root / "data").mkdir()
    return root / "data/local.env"


def test_private_init_ignored_no_overwrite_no_symlink(tmp_path):
    path = repo(tmp_path)
    init_config(path, tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    original = path.read_bytes()
    values = private_values(path, tmp_path)
    assert values["DEMO_PASSWORD"] != values["DEMO_OWNER_PASSWORD"]
    with pytest.raises(FileExistsError):
        init_config(path, tmp_path)
    assert path.read_bytes() == original
    link = tmp_path / "data/link.env"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symlink"):
        init_config(link, tmp_path)
    with pytest.raises(ValueError, match="ignored"):
        init_config(tmp_path / "public.env", tmp_path)


def test_provider_whitelist_and_frontend_secret_isolation(tmp_path, monkeypatch):
    path = repo(tmp_path)
    path.write_text(
        "LLM_API_KEY=${DO_NOT_INTERPOLATE}\nLLM_MODEL=deepseek-flash\nLLM_BASE_URL=https://api.deepseek.com/v1\nLLM_TIMEOUT_SECONDS=60\nOTHER_SECRET=hidden\n"
    )
    path.chmod(0o600)
    provider = provider_values(path, tmp_path)
    assert provider["LLM_API_KEY"] == "${DO_NOT_INTERPOLATE}"
    assert "OTHER_SECRET" not in provider
    for name in [
        "LLM_API_KEY",
        "DEMO_PASSWORD",
        "OPENAI_API_KEY",
        "VITE_BAD_SECRET",
        "FINDOC_PROVIDER_CAP_CNY",
    ]:
        monkeypatch.setenv(name, "ambient-secret")
    backend, frontend = environments(
        dict(DEMO_USERNAME="local", DEMO_PASSWORD="private-a", DEMO_OWNER_PASSWORD="private-b"),
        provider,
        tmp_path / "seed",
        tmp_path / "control",
        tmp_path / "ledger.db",
        "http://127.0.0.1:14530",
        12345,
        "python",
        False,
    )
    assert backend["DEMO_CONFLICT_POLICY"] == "wait_only"
    assert backend["FINDOC_PROVIDER_CAP_CNY"] == "5"
    assert not any(k.startswith(("LLM_", "DEMO_", "OPENAI_", "FINDOC_PROVIDER_")) for k in frontend)
    assert frontend["VITE_FINDOC_DEMO_MODE"] == "1"
    assert "private-a" not in str(frontend)
    path.write_text(path.read_text().replace("deepseek-flash", "unverified-model"))
    with pytest.raises(ValueError, match="unsupported"):
        provider_values(path, tmp_path)


def test_occupied_port_is_rejected_without_signals():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        with pytest.raises(OSError):
            port_available(sock.getsockname()[1])


def test_check_uses_temporary_seed_without_spawning(tmp_path, monkeypatch, capsys):
    import sys
    from app.demo.seed import build_synthetic_seed
    import scripts.run_showcase_local as launcher

    path = repo(tmp_path)
    init_config(path, tmp_path)
    seed = tmp_path / "data/showcase-seed-v1"
    build_synthetic_seed(seed)
    vite = tmp_path / "frontend/node_modules/vite/bin/vite.js"
    vite.parent.mkdir(parents=True)
    vite.write_text("// never executed")
    monkeypatch.setattr(launcher, "PROJECT", tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    launcher.main(
        [
            "--check",
            "--config",
            str(path),
            "--seed",
            str(seed),
            "--control",
            str(tmp_path / "data/showcase-local-controller-v1"),
            "--python",
            sys.executable,
            "--node",
            sys.executable,
            "--port",
            str(port),
        ]
    )
    output = capsys.readouterr().out
    assert '"llm": "disabled"' in output
    assert "DEMO_PASSWORD" not in output
    assert not (tmp_path / "data/showcase-local-controller-v1").exists()


def test_provider_config_from_same_common_worktree_only(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    path = repo(original)
    subprocess.run(["git", "-C", str(original), "add", ".gitignore"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(original),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    worktree = tmp_path / "integration"
    subprocess.run(
        ["git", "-C", str(original), "worktree", "add", "-qb", "integration", str(worktree)],
        check=True,
    )
    path.write_text(
        "LLM_API_KEY=offline-fixture\nLLM_MODEL=deepseek-flash\nLLM_BASE_URL=https://api.deepseek.com/v1\nLLM_TIMEOUT_SECONDS=30\n"
    )
    path.chmod(0o600)
    assert provider_values(path, worktree)["LLM_API_KEY"] == "offline-fixture"
    # The primary DEMO config helper remains restricted to its checkout.
    with pytest.raises(ValueError, match="in_checkout"):
        private_values(path, worktree)
    other = tmp_path / "unrelated"
    other.mkdir()
    unrelated = repo(other)
    unrelated.write_bytes(path.read_bytes())
    unrelated.chmod(0o600)
    with pytest.raises(ValueError, match="same_git_common_dir"):
        provider_values(unrelated, worktree)
    public = original / "not-ignored.env"
    public.write_bytes(path.read_bytes())
    public.chmod(0o600)
    with pytest.raises(ValueError, match="ignored"):
        provider_values(public, worktree)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="600"):
        provider_values(path, worktree)
