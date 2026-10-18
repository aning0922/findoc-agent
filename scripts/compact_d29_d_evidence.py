"""Consolidate repeated B JSON without losing an original byte or path."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zstandard

ROOT = Path(__file__).resolve().parents[1] / 'product/d29-d'
manifest = ROOT / 'evidence-packaging.json'
entries = json.loads(manifest.read_bytes())
selected = [e for e in entries if e['kind'] == 'gzip'
            and e['path'].startswith(('evidence/b-regression/', 'evidence/b-final/', 'evidence/b-final-r2/'))
            and Path(e['path']).name not in ('record.json', 'results.json', 'manifest.json')]
assert selected
archive = ROOT / 'evidence/repeated-b-json.tar.zst'
assert not archive.exists()
def sha(raw):
    return hashlib.sha256(raw).hexdigest()

paths, seen = [], set()
params = zstandard.ZstdCompressionParameters.from_level(10, window_log=27, enable_ldm=True)
with archive.open('wb') as dest:
    with zstandard.ZstdCompressor(compression_params=params).stream_writer(dest) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as tar:
            for e in selected:
                raw = gzip.decompress((ROOT / e['archive']).read_bytes())
                assert len(raw) == e['bytes'] and sha(raw) == e['sha256']
                member = 'blobs/' + e['sha256']
                paths.append(dict(path=e['path'], sha256=e['sha256'], bytes=len(raw), member=member))
                if member not in seen:
                    info = tarfile.TarInfo(member)
                    info.size = len(raw)
                    tar.addfile(info, io.BytesIO(raw))
                    seen.add(member)
verified = set()
with archive.open('rb') as source:
    with zstandard.ZstdDecompressor().stream_reader(source) as stream:
        with tarfile.open(fileobj=stream, mode='r|') as tar:
            for member in tar:
                assert sha(tar.extractfile(member).read()) == member.name.split('/')[1]
                verified.add(member.name)
assert verified == seen
for e in selected:
    (ROOT / e['archive']).unlink()
entries = [e for e in entries if e not in selected]
entries.append(dict(kind='content_addressed_tar_zstd', archive=str(archive.relative_to(ROOT)),
                    archive_sha256=sha(archive.read_bytes()), paths=paths,
                    unique_blobs=len(seen), all_members_verified=True))
manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(dict(paths=len(paths), unique_blobs=len(seen), all_members_verified=True,
                      archive_bytes=archive.stat().st_size, sha256=sha(archive.read_bytes()))))
