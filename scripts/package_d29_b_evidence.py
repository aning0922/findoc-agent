"""Lossless compression of repeated large JSON evidence; originals remain recoverable."""

import gzip
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'product/d29-b'
packed = []
for path in sorted((root / 'evidence').rglob('*.json')):
    if path.name in ('record.json', 'results.json', 'manifest.json') or path.stat().st_size < 250000:
        continue
    raw = path.read_bytes()
    target = path.with_suffix('.json.gz')
    assert not target.exists()
    target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    assert gzip.decompress(target.read_bytes()) == raw
    packed.append(dict(original=str(path.relative_to(root)), archive=str(target.relative_to(root)),
                       original_bytes=len(raw), original_sha256=hashlib.sha256(raw).hexdigest(),
                       archive_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    path.unlink()
(root / 'evidence-packaging.json').write_text(json.dumps(packed, indent=2) + '\n')
print(f'Losslessly packed {len(packed)} repeated JSON files')
