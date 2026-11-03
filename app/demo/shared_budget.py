"""Read-only admission of an existing allowance shared by sibling worktrees."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat
import subprocess


def git_identity(directory: Path) -> tuple[Path, Path]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def read(*args):
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", *args],
            env=env, capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip()).resolve()

    return read("--show-toplevel"), read("--path-format=absolute", "--git-common-dir")


def existing_shared_budget(path: Path, project: Path, *, forbidden_roots=()) -> Path:
    """Never initialize, copy, chmod, replenish or change the ledger in this check."""
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("shared_budget_requires_absolute_non_symlink_path")
    if not path.is_file():
        raise ValueError("existing_shared_budget_required")
    info = path.stat()
    if info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("shared_budget_requires_private_regular_file")
    owner, common = git_identity(path.parent)
    _, project_common = git_identity(project)
    if common != project_common or path != owner / "data/showcase-cost-control/provider-budget.db":
        raise ValueError("shared_budget_requires_same_git_canonical_location")
    if any(path.is_relative_to(Path(root).resolve()) for root in forbidden_roots):
        raise ValueError("shared_budget_must_be_outside_reset_cache_and_seed")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("SELECT cap FROM config WHERE id=1").fetchone() != ("5",):
                raise ValueError("shared_budget_cap_mismatch")
            db.execute("SELECT id,reserved,state,input_tokens,output_tokens FROM calls LIMIT 0")
    except sqlite3.Error as exc:
        raise ValueError("shared_budget_schema_invalid") from exc
    return path
