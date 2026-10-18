"""Losslessly bundle repeated JSON; preserve original names and byte hashes."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zstandard as zstd

root = Path(__file__).resolve().parents[1] / 'product/d29-b'
manifest_path = root / 'evidence-packaging.json'
entries = json.loads(manifest_path.read_text())
selected = []
for entry in entries:
    name = entry['archive']
    if name.startswith('evidence/after-r5/') and (name.endswith('-audit.json.gz') or
            name.endswith('source-503-before-recovery.json.gz') or
            name.endswith('source-503-recovered.json.gz')):
        continue
    selected.append(entry)
archive_path = root / 'evidence/repeated-json.tar.zst'
assert not archive_path.exists()
params = zstd.ZstdCompressionParameters.from_level(10, window_log=28)
with archive_path.open('wb') as output:
    with zstd.ZstdCompressor(compression_params=params).stream_writer(output) as packed:
        with tarfile.open(fileobj=packed, mode='w|') as tar:
            for entry in selected:
                raw = gzip.decompress((root / entry['archive']).read_bytes())
                assert hashlib.sha256(raw).hexdigest() == entry['original_sha256']
                info = tarfile.TarInfo(entry['original'])
                info.size, info.mtime = len(raw), 0
                tar.addfile(info, io.BytesIO(raw))
expected = {e['original']: e['original_sha256'] for e in selected}
verified = []
with archive_path.open('rb') as file:
    with zstd.ZstdDecompressor(max_window_size=2**28).stream_reader(file) as reader:
        with tarfile.open(fileobj=reader, mode='r|') as tar:
            for member in tar:
                raw = tar.extractfile(member).read()
                assert hashlib.sha256(raw).hexdigest() == expected[member.name]
                verified.append(member.name)
assert len(verified) == len(selected)
sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
for entry in selected:
    (root / entry['archive']).unlink()
    entry['gzip_sha256'] = entry['archive_sha256']
    entry.update(archive='evidence/repeated-json.tar.zst', archive_sha256=sha,
                 member=entry['original'], archive_format='tar.zstd')
manifest_path.write_text(json.dumps(entries, indent=2) + '\n')
print(dict(members=len(selected), verified_all=True,
           archive_bytes=archive_path.stat().st_size, sha256=sha))
