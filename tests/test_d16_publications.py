"""Actual Milvus Lite publication tests. Synthetic 2-D vectors test integrity, not RAG quality."""

import json
from contextlib import closing
from unittest.mock import Mock

import pytest

from app.documents.models import DocumentStatus
from app.documents.source_repository import revision_id
from app.rag.publications import IndexPublications
from app.rag.retriever import IndexVersionUnverifiedError, Retriever, SearchFilters, TrustedContext
from app.rag.store import MilvusSearchStore, get_client
from tests.test_document_sources import Harness, pdf_bytes


@pytest.fixture
def indexed(tmp_path):
    h = Harness(tmp_path)
    client = get_client(str(tmp_path / 'milvus.db'))
    pub = IndexPublications(h.registry, client)
    h.processor._index_document = pub.publish
    h.processor._embedder = lambda texts: [[0.6, 0.8] for _ in texts]
    h.processor._source_identity = lambda r: dict(
        source_revision=revision_id(r, h.service.parser_version),
        content_sha256=r.content_sha256, attempt=r.attempt, parser_version=h.service.parser_version)
    h.ready()
    h.pub, h.milvus = pub, client
    yield h
    client.close()


def retrieve(h, *, document=None, revision=None, legacy=False):
    embed = Mock(return_value=[[0.6, 0.8]])
    r = Retriever(embed, MilvusSearchStore(h.milvus, 'legacy', publications=h.pub))
    filters = (SearchFilters(document_id=h.id) if legacy else SearchFilters(
        document_ids=(document or h.id,), source_revisions=((document or h.id, revision or h.rev),)))
    return r.retrieve('report', context=TrustedContext('demo'), filters=filters)


def test_real_lite_publish_query_restart_and_legacy(indexed, tmp_path):
    h = indexed
    generation, manifest = h.pub.verified('demo', h.id, h.rev)
    hits = retrieve(h)
    assert hits and hits[0].source_revision == h.rev
    assert retrieve(h, legacy=True) == hits
    h.pub.recover()
    assert h.pub.verified('demo', h.id, h.rev) == (generation, manifest)
    h.milvus.close()
    h.milvus = get_client(str(tmp_path / 'milvus.db'))
    h.pub = IndexPublications(h.registry, h.milvus)
    assert retrieve(h) == hits
    (tmp_path / 'd16-publication-proof.json').write_text(json.dumps(dict(
        generation=generation, manifest=manifest, actual_rows=h.pub._read_rows(generation),
        restart_verified=True, vectors='synthetic 2-D integrity fixture'), indent=2))
    h.milvus.close()


@pytest.mark.parametrize('mutation', ['delete', 'text', 'vector', 'page', 'revision', 'document',
                                      'manifest', 'state', 'source', 'attempt'])
def test_partial_corrupt_or_stale_index_rejected(indexed, mutation):
    h = indexed
    gen, _ = h.pub.verified('demo', h.id, h.rev)
    rows = h.pub._read_rows(gen)
    if mutation == 'delete':
        h.milvus.delete(collection_name=gen, ids=[rows[0]['chunk_id']])
    elif mutation in ('text', 'vector', 'page', 'revision', 'document'):
        key = {'revision': 'source_revision', 'document': 'document_id'}.get(mutation, mutation)
        rows[0][key] = {'text': 'tampered', 'vector': [0.8, 0.6], 'page': 999}.get(mutation, 'wrong')
        h.milvus.upsert(collection_name=gen, data=[rows[0]])
    else:
        with closing(h.registry._connect()) as c, c:
            sql = {
                'manifest': "UPDATE index_publications SET manifest_json='{}'",
                'state': "UPDATE index_publications SET state='complete'",
                'source': "UPDATE document_sources SET invalidated_at='now'",
                'attempt': 'UPDATE documents SET attempt=attempt+1',
            }[mutation]
            c.execute(sql)
    with pytest.raises((IndexVersionUnverifiedError, KeyError)):
        retrieve(h)


def test_unversioned_scope_rejected_before_embedding(indexed):
    h = indexed
    embed = Mock()
    r = Retriever(embed, MilvusSearchStore(h.milvus, 'legacy', publications=h.pub))
    with pytest.raises(IndexVersionUnverifiedError):
        r.retrieve('q', context=TrustedContext('demo'), filters=SearchFilters(document_ids=(h.id,)))
    embed.assert_not_called()
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h, document='foreign')


def test_correction_retry_and_cleanup(indexed):
    h = indexed
    old_gen, _ = h.pub.verified('demo', h.id, h.rev)
    assert h.correct().status_code == 200
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h)
    assert h.client.post(f'/documents/{h.id}/retry').status_code == 202
    assert h.processor.process(h.id).status == DocumentStatus.READY
    new_rev = h.client.get(f'/documents/{h.id}/source').json()['source_revision']
    assert new_rev != h.rev and retrieve(h, revision=new_rev)
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h)
    h.pub.cleanup()
    assert not h.milvus.has_collection(old_gen)


def test_partial_write_failure_never_ready_and_recovery(indexed, monkeypatch):
    h = indexed
    uploaded = h.upload(content=pdf_bytes('A different annual report with detailed financial information and supporting evidence.'))
    doc = uploaded.json()['document_id']
    original = h.milvus.insert
    def fail(**kwargs):
        original(**{**kwargs, 'data': kwargs['data'][:1]})
        raise RuntimeError('injected partial write')
    monkeypatch.setattr(h.milvus, 'insert', fail)
    assert h.processor.process(doc).status == DocumentStatus.FAILED
    with closing(h.registry._connect()) as c:
        row = c.execute('SELECT * FROM index_publications WHERE document_id=?', (doc,)).fetchone()
    assert row['state'] == 'failed'
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h, document=doc, revision=row['source_revision'])
    h.pub.recover()
    assert not h.milvus.has_collection(row['generation'])
    assert retrieve(h)


def test_same_chunk_id_different_document_isolated(indexed):
    h = indexed
    first = retrieve(h)
    doc = h.upload(content=pdf_bytes('Another annual report with detailed financial information and supporting evidence.')) .json()['document_id']
    assert h.processor.process(doc).status == DocumentStatus.READY
    rev = h.client.get(f'/documents/{doc}/source').json()['source_revision']
    second = retrieve(h, document=doc, revision=rev)
    assert first[0].chunk_id == second[0].chunk_id
    assert first[0].document_id != second[0].document_id
    assert retrieve(h) == first


@pytest.mark.parametrize('state', ['building', 'complete', 'active'])
def test_crash_before_ready_requires_retry(indexed, state):
    h = indexed
    gen, _ = h.pub.verified('demo', h.id, h.rev)
    with closing(h.registry._connect()) as c, c:
        c.execute('UPDATE index_publications SET state=?', (state,))
        c.execute("UPDATE documents SET status='indexing'")
    h.pub.recover()
    assert h.docs.get(h.id).status == DocumentStatus.FAILED
    assert not h.milvus.has_collection(gen)
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h)


def test_source_changes_during_milvus_search_cannot_publish(indexed, monkeypatch):
    h = indexed
    search = h.milvus.search
    def racing_search(**kwargs):
        hits = search(**kwargs)
        assert h.correct().status_code == 200
        return hits
    monkeypatch.setattr(h.milvus, 'search', racing_search)
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h)


def test_hit_payload_must_match_manifest_even_after_full_scan(indexed, monkeypatch):
    h = indexed
    search = h.milvus.search
    def wrong_hit(**kwargs):
        hits = search(**kwargs)
        hits[0][0]['entity']['document_id'] = 'other'
        return hits
    monkeypatch.setattr(h.milvus, 'search', wrong_hit)
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h)


def test_explicit_ready_reindex_revokes_old_source(indexed):
    h = indexed
    body = {'expected_attempt': h.docs.get(h.id).attempt}
    response = h.client.post(f'/documents/{h.id}/reindex', json=body)
    assert response.status_code == 202
    assert h.client.post(f'/documents/{h.id}/reindex', json=body).status_code == 409
    with pytest.raises(IndexVersionUnverifiedError):
        retrieve(h)
    assert h.processor.process(h.id).status == DocumentStatus.READY
    rev = h.client.get(f'/documents/{h.id}/source').json()['source_revision']
    assert rev != h.rev and retrieve(h, revision=rev)
    assert h.client.post('/documents/foreign/reindex', json=body).status_code == 404
    assert h.client.post(f'/documents/{h.id}/reindex', json={**body, 'workspace_id': 'x'}).status_code == 422


def test_full_manifest_exceeds_iterator_page_size(indexed):
    h = indexed
    old_gen, manifest = h.pub.verified('demo', h.id, h.rev)
    original = h.pub._read_rows(old_gen)[0]
    # More than two pages, shuffled hash-like primary keys; no query-iterator assumptions.
    rows = [{**original, 'chunk_id': f'{i:064x}'} for i in range(600)]
    with closing(h.registry._connect()) as c, c:
        c.execute("UPDATE documents SET status='indexing'")
    result = h.pub.publish(h.id, rows)
    assert len(result.final_ids) == 600
    with closing(h.registry._connect()) as c, c:
        c.execute("UPDATE documents SET status='ready'")
    assert len(h.pub.verified('demo', h.id, h.rev)[1]['rows']) == 600
    assert retrieve(h)


def test_migration6_failure_rolls_back_and_retries(tmp_path, monkeypatch):
    import sqlite3
    from app.companies import migrations
    from app.companies.sqlite_repository import SQLiteCompanyRepository
    all_migrations = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, 'MIGRATIONS', all_migrations[:5])
    registry = SQLiteCompanyRepository(tmp_path / 'documents.db')
    with closing(registry._connect()) as c, c:
        before = c.execute('SELECT * FROM analyst_schema_migrations').fetchall()
        c.execute("CREATE TRIGGER fail_v6 BEFORE INSERT ON analyst_schema_migrations "
                  "WHEN NEW.version=6 BEGIN SELECT RAISE(ABORT,'fault'); END")
    monkeypatch.setattr(migrations, 'MIGRATIONS', all_migrations)
    with pytest.raises(sqlite3.IntegrityError):
        SQLiteCompanyRepository(tmp_path / 'documents.db')
    with closing(registry._connect()) as c, c:
        assert c.execute('SELECT * FROM analyst_schema_migrations').fetchall() == before
        assert not c.execute("SELECT name FROM sqlite_master WHERE name='index_publications'").fetchall()
        c.execute('DROP TRIGGER fail_v6')
    SQLiteCompanyRepository(tmp_path / 'documents.db')
    SQLiteCompanyRepository(tmp_path / 'documents.db')
    with closing(registry._connect()) as c:
        assert c.execute('SELECT COUNT(*) FROM analyst_schema_migrations').fetchone()[0] == len(all_migrations)


def test_section_anchor_is_a_restrictive_native_filter(indexed):
    h = indexed
    r = Retriever(lambda _: [[0.6, 0.8]], MilvusSearchStore(h.milvus, 'legacy', publications=h.pub))
    scoped = SearchFilters(document_ids=(h.id,), source_revisions=((h.id, h.rev),))
    # Fixture has no Chinese accounting section; it must not fall back to arbitrary hits.
    assert r.retrieve('主要会计数据和财务指标', context=TrustedContext('demo'), filters=scoped) == []
    assert r.retrieve('report', context=TrustedContext('demo'), filters=scoped)
