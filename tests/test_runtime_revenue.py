"""生产 factory 的收入接线/关闭证据：真实服务与临时库，模型/向量存储是替身。

HTTP 接受是自动化模拟；固定 local_operator 字段不能作为本人确认的证据。
"""

from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.api import runtime_factory
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
from app.rag.retriever import Retriever, SearchStore
from app.rag.service import RAGService
from tests.test_revenue_confirmation import Harness


@pytest.fixture
def assembled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    """替换重依赖后用生产 factory 装配；所有持久层使用同一显式临时根目录。"""
    h = Harness(tmp_path)
    calls: list[str] = []
    model = Mock(spec=OpenAICompatibleLLMClient, model="controlled-test-model")
    monkeypatch.setattr(
        runtime_factory.OpenAICompatibleLLMClient,
        "from_env",
        Mock(side_effect=lambda: (calls.append("config"), model)[1]),
    )
    monkeypatch.setattr(
        runtime_factory,
        "_warm_runtime_bge_before_milvus",
        Mock(side_effect=lambda: calls.append("bge")),
    )
    monkeypatch.setattr(runtime_factory, "_build_runtime_indexer", Mock(return_value=Mock()))
    store = Mock(spec=SearchStore)
    store.search.return_value = [asdict(hit) for hit in h.retriever.retrieve.return_value]
    embedder = Mock(return_value=[[0.1, 0.2]])
    retriever = Retriever(embedder, store)
    milvus = Mock()
    resources = runtime_factory.RuntimeRAGResources(
        rag_service=Mock(spec=RAGService),
        retriever=retriever,
        milvus_client=milvus,
    )
    monkeypatch.setattr(
        runtime_factory,
        "_build_runtime_rag_resources",
        Mock(side_effect=lambda *args: (calls.append("rag_resources"), resources)[1]),
    )
    agent_factory = Mock(wraps=runtime_factory.AgentRuntimeService)
    monkeypatch.setattr(runtime_factory, "AgentRuntimeService", agent_factory)
    return h, calls, model, store, embedder, milvus, resources, agent_factory


def test_factory_shares_resources_and_rejects_legacy_ready_without_source_snapshot(
    tmp_path: Path,
    assembled: tuple,
) -> None:
    """实际 HTTP 经生产装配到真实 SQLite，检索/模型替身只提供受控输入。"""
    h, calls, model, store, embedder, milvus, resources, agent_factory = assembled
    app = runtime_factory.create_runtime_app(tmp_path)
    agent = app.state.agent_service
    revenue = app.state.revenue_service
    reader = revenue._source_reader
    assert reader._documents is agent._document_preparer._document_service
    assert reader._objects is reader._documents._object_store
    assert reader._candidates._preparer is agent._document_preparer
    assert reader._candidates._retriever is resources.retriever
    assert agent_factory.call_args.kwargs["retriever"] is resources.retriever
    assert revenue._repository._database_path == tmp_path / "documents.db"
    assert calls == ["config", "bge", "rag_resources"]
    with TestClient(app) as client:
        reviewed = client.post("/revenue-research/reviews", json={"document_id": h.document_id})
        assert reviewed.status_code == 409, reviewed.text
        assert reader._candidates is app.state.candidate_service
        assert reader._candidates._sources is app.state.source_service
        confirmed = client.post(
            "/revenue-research/confirmations",
            json={"document_id": h.document_id, "snapshot_id": "0" * 64, "accepted": True},
        )
        assert confirmed.status_code == 409, confirmed.text
    assert h.counts() == (0, 0)
    store.search.assert_not_called()
    embedder.assert_not_called()
    model.complete.assert_not_called()
    model.generate.assert_not_called()
    milvus.close.assert_called_once_with()


@pytest.mark.parametrize("failure_at", ["SQLiteRevenueConfirmationRepository", "create_app"])
def test_income_assembly_failure_closes_existing_shared_resource(
    tmp_path: Path,
    assembled: tuple,
    monkeypatch: pytest.MonkeyPatch,
    failure_at: str,
) -> None:
    """新增收入装配及 app 挂载失败仍由原 factory 释放已创建的共享检索连接。"""
    milvus = assembled[5]
    monkeypatch.setattr(runtime_factory, failure_at, Mock(side_effect=OSError("simulated failure")))
    with pytest.raises(OSError, match="simulated failure"):
        runtime_factory.create_runtime_app(tmp_path)
    milvus.close.assert_called_once_with()
