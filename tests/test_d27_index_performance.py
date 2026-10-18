"""Optimization must keep real Milvus pre/post integrity and race rejection."""

from unittest.mock import Mock
import pytest

from app.rag.retriever import Retriever, SearchFilters, TrustedContext, IndexVersionUnverifiedError
from app.rag.store import MilvusSearchStore
from tests.test_d16_publications import indexed  # noqa: F401


def test_query_has_two_full_scans_and_no_integrity_cache(indexed, monkeypatch):  # noqa: F811
    h = indexed
    verify = Mock(wraps=h.pub._verify_rows)
    monkeypatch.setattr(h.pub, "_verify_rows", verify)
    r = Retriever(lambda _: [[0.6, 0.8]], MilvusSearchStore(h.milvus, "legacy", publications=h.pub))
    scope = SearchFilters(document_ids=(h.id,), source_revisions=((h.id, h.rev),))
    assert r.retrieve("report", context=TrustedContext("demo"), filters=scope)
    assert verify.call_count == 2
    assert r.retrieve("report", context=TrustedContext("demo"), filters=scope)
    assert verify.call_count == 4


def test_index_mutation_during_embedding_rejected_before_native_search(indexed, monkeypatch):  # noqa: F811
    h = indexed
    gen, _ = h.pub.verified("demo", h.id, h.rev)
    row = h.pub._read_rows(gen)[0]
    search = Mock(wraps=h.milvus.search)
    monkeypatch.setattr(h.milvus, "search", search)

    def embed(_):
        h.milvus.upsert(collection_name=gen, data=[dict(row, vector=[0.8, 0.6])])
        return [[0.6, 0.8]]

    r = Retriever(embed, MilvusSearchStore(h.milvus, "legacy", publications=h.pub))
    with pytest.raises(IndexVersionUnverifiedError):
        r.retrieve(
            "report",
            context=TrustedContext("demo"),
            filters=SearchFilters(document_ids=(h.id,), source_revisions=((h.id, h.rev),)),
        )
    search.assert_not_called()


def test_vector_mutation_during_search_rejected_by_post_scan(indexed, monkeypatch):  # noqa: F811
    h = indexed
    gen, _ = h.pub.verified("demo", h.id, h.rev)
    row = h.pub._read_rows(gen)[0]
    original = h.milvus.search

    def search(**kw):
        result = original(**kw)
        h.milvus.upsert(collection_name=gen, data=[dict(row, vector=[0.8, 0.6])])
        return result

    monkeypatch.setattr(h.milvus, "search", search)
    r = Retriever(lambda _: [[0.6, 0.8]], MilvusSearchStore(h.milvus, "legacy", publications=h.pub))
    with pytest.raises(IndexVersionUnverifiedError):
        r.retrieve(
            "report",
            context=TrustedContext("demo"),
            filters=SearchFilters(document_ids=(h.id,), source_revisions=((h.id, h.rev),)),
        )
