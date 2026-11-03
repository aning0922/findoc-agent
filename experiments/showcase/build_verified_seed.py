"""Freeze a closed, disposable official-PDF HTTP test runtime as a PARTIAL seed.

Never accepts an existing developer runtime. No model call, fact approval or
invented research/report history. Final E03 still needs its remaining artifacts.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from app.demo.seed import identifier, sha256, verify_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    source, target = args.source.resolve(), args.destination.resolve()
    evidence = source.parents[2]
    if (not evidence.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not evidence.name.startswith('findoc-integrated-http-')
            or source.parent.name != 'active' or (source.parents[1] / 'child.json').exists()
            or not (source / '.demo-manifest.json').is_file()):
        raise ValueError('Only a stopped, controller-owned disposable HTTP test runtime is allowed')
    db_path = source / 'documents.db'
    with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as db:
        docs = db.execute('SELECT document_id,content_sha256,status FROM documents').fetchall()
        if len(docs) != 1 or docs[0][1] != '7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c' or docs[0][2] != 'ready':
            raise ValueError('Expected the one verified official Gree2025 PDF, READY')
        counts = {row[0]: db.execute(f'SELECT count(*) FROM {identifier(row[0])}').fetchone()[0]
                  for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        # This intermediate seed must not import any real/simulated fact grants,
        # private notes, conversations or fabricated completed research history.
        if any(count for name, count in counts.items() if any(term in name for term in (
                'receipt', 'acceptance', 'fact_sets', 'conversation', 'memory_items', 'research_runs', 'template_tasks', 'reports'))):
            raise ValueError('Unexpected research/private/confirmation state in mechanism runtime')
        target.mkdir(parents=True, exist_ok=False, mode=0o700)
        with closing(sqlite3.connect(target / 'documents.db')) as copied:
            db.backup(copied)
    with closing(sqlite3.connect(target / 'documents.db')) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute("DELETE FROM companies WHERE security_code='SYNTHETIC' AND exchange='DEMO'")
        if db.execute('SELECT count(*) FROM companies').fetchone()[0] != 1:
            raise ValueError('Unexpected company scope')
    (target / 'objects/documents').mkdir(parents=True)
    pdf = Path('objects/documents') / f'{docs[0][0]}.pdf'
    shutil.copyfile(source / pdf, target / pdf)
    if sha256(target / pdf) != docs[0][1]:
        raise ValueError('Copied PDF checksum changed')
    shutil.copytree(source / 'milvus.db', target / 'milvus.db')
    from pymilvus import MilvusClient
    client = MilvusClient(str(target / 'milvus.db'))
    try:
        vectors = [{'collection': name, 'rows': int(client.get_collection_stats(collection_name=name)['row_count'])}
                   for name in sorted(client.list_collections())]
    finally:
        client.close()
    with closing(sqlite3.connect(target / 'documents.db')) as db:
        tables = {row[0]: db.execute(f'SELECT count(*) FROM {identifier(row[0])}').fetchone()[0]
                  for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        indexes = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")]
    files = [{'path': f.relative_to(target).as_posix(), 'sha256': sha256(f)}
             for f in sorted(target.rglob('*')) if f.is_file()]
    manifest = {'schema_version': 'demo-seed-v1', 'seed_version': 'public-gree-2025-partial-v1',
                'data_origin': 'verified_public_pdf_partial', 'complete_product_seed': False,
                'files': files, 'sqlite': [{'path': 'documents.db', 'tables': tables, 'indexes': indexes}],
                'preset_task_ids': [], 'vector_indexes': vectors}
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    for p in sorted(target.rglob('*'), reverse=True):
        p.chmod(0o500 if p.is_dir() else 0o400)
    target.chmod(0o500)
    _, digest = verify_seed(target)
    print(json.dumps({'seed_root': str(target), 'manifest_sha256': digest, 'complete_product_seed': False,
                      'documents': 1, 'companies': 1, 'vector_indexes': vectors}, ensure_ascii=False))


if __name__ == '__main__':
    main()
