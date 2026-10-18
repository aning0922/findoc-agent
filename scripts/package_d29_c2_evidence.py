"""Lossless packaging of bulky evidence; no failure records or original bytes discarded."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

import zstandard

ROOT = Path(__file__).resolve().parents[1] / "product/d29-c2"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


if (ROOT / "evidence-packaging.json").exists():
    raise FileExistsError("Existing packaging manifest; restore evidence before packaging again")
index = []
# Temporary Playwright artifacts repeat source PDFs and screenshot resources. Keep
# one content-addressed member for each exact byte string, with every original path.
files = sorted(p for p in ROOT.rglob("*") if p.is_file() and ".playwright-artifacts-" in str(p))
blobs = {}
paths = []
for p in files:
    raw = p.read_bytes()
    digest = sha(raw)
    blobs.setdefault(digest, p)
    paths.append(
        dict(path=str(p.relative_to(ROOT)), sha256=digest, bytes=len(raw), member="blobs/" + digest)
    )
if paths:
    archive = ROOT / "evidence/playwright-resources.tar.zst"
    with archive.open("wb") as dest:
        params = zstandard.ZstdCompressionParameters.from_level(10, window_log=27, enable_ldm=True)
        with zstandard.ZstdCompressor(compression_params=params).stream_writer(dest) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as tar:
                for digest, p in sorted(blobs.items()):
                    raw = p.read_bytes()
                    info = tarfile.TarInfo("blobs/" + digest)
                    info.size = len(raw)
                    tar.addfile(info, io.BytesIO(raw))
    with archive.open("rb") as f:
        with zstandard.ZstdDecompressor().stream_reader(f) as stream:
            with tarfile.open(fileobj=stream, mode="r|") as tar:
                verified = set()
                for member in tar:
                    raw = tar.extractfile(member).read()
                    assert sha(raw) == member.name.split("/")[1]
                    verified.add(sha(raw))
    assert verified == set(blobs)
    for p in files:
        p.unlink()
    for p in sorted(ROOT.rglob(".playwright-artifacts-*"), reverse=True):
        for d in sorted(
            (d for d in p.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True
        ):
            d.rmdir()
        p.rmdir()
    index.append(
        dict(
            kind="content_addressed_tar_zstd",
            archive=str(archive.relative_to(ROOT)),
            archive_sha256=sha(archive.read_bytes()),
            paths=paths,
            unique_blobs=len(blobs),
            all_members_verified=True,
        )
    )
# Preserve readable smaller summaries; compress large repeated DOM/source JSON.
for p in sorted(ROOT.rglob("*.json")):
    if p.stat().st_size < 250000:
        continue
    raw = p.read_bytes()
    target = p.with_suffix(p.suffix + ".gz")
    target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    assert gzip.decompress(target.read_bytes()) == raw
    index.append(
        dict(
            kind="gzip",
            path=str(p.relative_to(ROOT)),
            archive=str(target.relative_to(ROOT)),
            sha256=sha(raw),
            bytes=len(raw),
            archive_sha256=sha(target.read_bytes()),
            verified=True,
        )
    )
    p.unlink()
(ROOT / "evidence-packaging.json").write_text(
    json.dumps(index, ensure_ascii=False, indent=2) + "\n"
)
print("Preserved all original paths and SHA256; verified every gzip and archive member.")
print("Unique Playwright resource blobs:", len(blobs), "from", len(paths), "original paths.")
