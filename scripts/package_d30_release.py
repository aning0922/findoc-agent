"""Deterministically package the public allowlist; losslessly compact D30 audits."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public-root', type=Path, required=True)
    p.add_argument('--delivery', type=Path, required=True)
    args = p.parse_args()
    root, delivery = args.public_root.resolve(), args.delivery.resolve()
    manifest = json.loads((root/'release-public-manifest.json').read_text())
    buffer = io.BytesIO()
    names = sorted([*manifest['files'], 'release-public-manifest.json'])
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name in names:
            path = root/name
            if path.is_symlink() or not path.is_file():
                raise ValueError('public file is missing or symlinked')
            raw = path.read_bytes()
            if name in manifest['files'] and sha(raw)!=manifest['files'][name]['sha256']:
                raise ValueError('public file changed')
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(raw), 0o644, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(raw))
    raw = gzip.compress(buffer.getvalue(), mtime=0)
    artifact = delivery/'public-demo-rc.tar.gz'
    artifact.write_bytes(raw)
    (delivery/'public-demo-manifest.json').write_bytes((root/'release-public-manifest.json').read_bytes())
    public = dict(artifact=artifact.name, sha256=sha(raw), bytes=len(raw), files=names,
                  public_manifest_sha256=sha((root/'release-public-manifest.json').read_bytes()))
    (delivery/'public-artifact.json').write_text(json.dumps(public,indent=2)+'\n')
    packaging = []
    for path in sorted((delivery/'evidence').rglob('*-audit.json')):
        original = path.read_bytes()
        if len(original)<128000:
            continue
        target = path.with_suffix(path.suffix+'.gz')
        packed = gzip.compress(original, mtime=0)
        if gzip.decompress(packed)!=original:
            raise ValueError('lossless packaging check failed')
        target.write_bytes(packed)
        packaging.append(dict(original_path=str(path.relative_to(delivery)),
            original_sha256=sha(original), original_bytes=len(original),
            archive_path=str(target.relative_to(delivery)),archive_sha256=sha(packed),
            archive_bytes=len(packed)))
        path.unlink()  # Only D30 newly generated audits, after exact roundtrip proof.
    (delivery/'evidence-packaging.json').write_text(json.dumps(dict(schema='d30-lossless-gzip-v1',files=packaging),indent=2)+'\n')
    print(json.dumps(public))


if __name__=='__main__':
    main()
