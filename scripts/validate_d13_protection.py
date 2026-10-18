"""D13 local isolation/protection evidence; run from the product worktree."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

product = Path.cwd()
if product.resolve() != Path(__file__).resolve().parent.parent:
    raise RuntimeError("Run D13 validation from the product worktree cwd")
baseline = json.loads((product / "product/validation/git-baseline.json").read_text())
source = Path(baseline["source_root"])
backup = Path(baseline["backup_path"])
env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


def git(*args):
    return subprocess.check_output(["git", "-C", str(source), *args], env=env)


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def state():
    paths = {
        p.decode()
        for p in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
        if p
    }
    files = {p: digest(source / p) for p in sorted(paths) if (source / p).is_file()}
    data = {
        str(p.relative_to(source)): digest(p)
        for p in sorted((source / "data").rglob("*"))
        if p.is_file()
    }
    other = product.parent / "findoc-v1-product-design"

    def other_git(*args):
        return subprocess.check_output(["git", "-C", str(other), *args], env=env)

    other_paths = {
        p.decode()
        for p in other_git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(
            b"\0"
        )
        if p
    }
    protected_product = dict(
        head=other_git("rev-parse", "HEAD").decode().strip(),
        branch=other_git("branch", "--show-current").decode().strip(),
        status=other_git("status", "--porcelain=v1").decode(),
        origin=other_git("remote", "get-url", "origin").decode().strip(),
        index_sha256=digest(
            Path(
                other_git("rev-parse", "--path-format=absolute", "--git-path", "index")
                .decode()
                .strip()
            )
        ),
        files={p: digest(other / p) for p in sorted(other_paths) if (other / p).is_file()},
        data={
            str(p.relative_to(other)): digest(p)
            for p in sorted((other / "data").rglob("*"))
            if p.is_file()
        },
    )
    default_runtime = {
        str(p.relative_to(product)): digest(p)
        for p in sorted((product / "data/runtime").rglob("*"))
        if p.is_file()
    }
    return dict(
        protected_product=protected_product,
        analyst_default_runtime=default_runtime,
        head=git("rev-parse", "HEAD").decode().strip(),
        branch=git("branch", "--show-current").decode().strip(),
        status=git("status", "--porcelain=v1").decode(),
        index_sha256=digest(
            Path(git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
        ),
        files=files,
        data=data,
        diff_sha256=hashlib.sha256(git("diff", "--binary")).hexdigest(),
        staged_diff_sha256=hashlib.sha256(git("diff", "--cached", "--binary")).hexdigest(),
        backup_files={p: digest(backup / "files" / p) for p in baseline["files"]},
        patch_sha256=digest(backup / "tracked.patch"),
    )


current = state()
checks = {k: current[k] == baseline[k] for k in ("head", "branch", "status", "index_sha256")}
checks.update(
    day76_files=all(current["files"].get(p) == h for p, h in baseline["files"].items()),
    baseline_databases=all(current["data"].get(p) == h for p, h in baseline["databases"].items()),
    frozen_files=current["backup_files"] == baseline["files"],
    patch_matches_source=current["diff_sha256"] == current["patch_sha256"],
)
if sys.argv[1] == "before":
    assert all(checks.values()), checks
    (product / "data/30d-foundation/d13-source-before.json").write_text(
        json.dumps(current, indent=2) + "\n"
    )
    output = dict(
        stage="before",
        checks=checks,
        source_file_count=len(current["files"]),
        data_file_count=len(current["data"]),
        baseline_database_count=len(baseline["databases"]),
        snapshot_file_count=len(current["backup_files"]),
        patch_sha256=current["patch_sha256"],
    )
else:
    before = json.loads((product / "data/30d-foundation/d13-source-before.json").read_text())
    checks.update({f"unchanged_{k}": current[k] == v for k, v in before.items()})
    output = dict(
        stage="after",
        checks=checks,
        all_passed=all(checks.values()),
        source_file_count=len(current["files"]),
        data_file_count=len(current["data"]),
        baseline_database_count=len(baseline["databases"]),
        snapshot_file_count=len(current["backup_files"]),
        patch_sha256=current["patch_sha256"],
        source_head=current["head"],
        source_index_sha256=current["index_sha256"],
        source_status=current["status"],
        source_staged_diff_sha256=current["staged_diff_sha256"],
        protected_product_head=current["protected_product"]["head"],
        protected_product_origin=current["protected_product"]["origin"],
        protected_product_file_count=len(current["protected_product"]["files"]),
        protected_product_data_count=len(current["protected_product"]["data"]),
        analyst_default_runtime_file_count=len(current["analyst_default_runtime"]),
        local_manifest="data/30d-foundation/d13-source-before.json",
        manifest_sha256=digest(product / "data/30d-foundation/d13-source-before.json"),
    )
    (product / "product/validation/d13-protection-results.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    assert output["all_passed"], output
print(json.dumps(output, indent=2))
