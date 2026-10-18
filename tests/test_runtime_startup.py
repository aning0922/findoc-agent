"""验证runtime应用在配置不完整时不会留下半初始化资源。"""

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.api.runtime_factory import (
    DEFAULT_RUNTIME_ROOT,
    ISOLATED_RUNTIME_ROOT_ENV,
    create_isolated_runtime_app_from_env,
)


class _RecordingMilvusClient:
    """仅记录启动测试中的Milvus动作，不连接真实数据库。"""

    def load_collection(self, *, collection_name: str) -> None:
        """模拟加载collection；测试中的缺配置路径不应到达这里。"""

    def close(self) -> None:
        """模拟关闭client，避免测试触碰真实Milvus。"""


@pytest.mark.parametrize("raw_root", [None, "", "relative/runtime"])
def test_isolated_runtime_factory_requires_explicit_absolute_root(
    monkeypatch: pytest.MonkeyPatch,
    raw_root: str | None,
) -> None:
    """隔离 Uvicorn 入口没有安全绝对目录时在真实装配前失败。"""
    if raw_root is None:
        monkeypatch.delenv(ISOLATED_RUNTIME_ROOT_ENV, raising=False)
    else:
        monkeypatch.setenv(ISOLATED_RUNTIME_ROOT_ENV, raw_root)
    with pytest.raises((RuntimeError, ValueError)):
        create_isolated_runtime_app_from_env()


def test_isolated_runtime_factory_rejects_default_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式隔离入口也不能把项目默认 runtime 当作测试目录。"""
    monkeypatch.setenv(ISOLATED_RUNTIME_ROOT_ENV, str(DEFAULT_RUNTIME_ROOT))
    with pytest.raises(ValueError, match="拒绝使用项目默认 runtime"):
        create_isolated_runtime_app_from_env()


def test_missing_llm_api_key_stops_before_runtime_resource_initialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """缺少API key时只检查配置，不预热BGE或创建runtime持久化资源。"""
    calls: list[str] = []
    fail_config = True

    from app.agent import sqlite_run_repository
    from app.documents import local_object_store, sqlite_repository
    from app.rag import openai_compatible_llm, store

    class RecordingRepository:
        """记录SQLite构造动作，不创建数据库文件。"""

        def __init__(self, database_path: Path) -> None:
            calls.append("sqlite")

    class RecordingObjectStore:
        """记录对象目录构造动作，不创建目录。"""

        def __init__(self, root: Path) -> None:
            calls.append("object_store")

    class RecordingAgentRepository:
        """记录 Run 库初始化，避免模块级装配写入真实 runtime 数据。"""

        def __init__(self, database_path: Path) -> None:
            """只记录构造动作，不创建 SQLite 文件。"""
            calls.append("agent_sqlite")

    def fake_from_env(cls: object) -> object:
        """先允许模块级应用装配，再让目标调用模拟缺少API key。"""
        calls.append("config")
        if fail_config:
            raise KeyError("LLM_API_KEY")
        return object()

    def fake_embed(texts: list[str]) -> list[list[float]]:
        """记录BGE预热调用，不加载真实模型。"""
        calls.append("bge")
        return [[0.0] * 1024 for _ in texts]

    def fake_get_client(database_path: str) -> _RecordingMilvusClient:
        """记录Milvus构造动作，不创建数据库。"""
        calls.append("milvus")
        return _RecordingMilvusClient()

    def fake_ensure_collection(client: _RecordingMilvusClient, name: str) -> None:
        """模拟collection存在检查，不执行真实Milvus操作。"""
        calls.append("ensure_collection")

    fake_embed_module = ModuleType("app.rag.embed")
    fake_embed_module.embed = fake_embed  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.rag.embed", fake_embed_module)
    monkeypatch.setattr(sqlite_repository, "SQLiteDocumentRepository", RecordingRepository)
    monkeypatch.setattr(local_object_store, "LocalObjectStore", RecordingObjectStore)
    monkeypatch.setattr(sqlite_run_repository, "SQLiteAgentRunRepository", RecordingAgentRepository)
    monkeypatch.setattr(
        openai_compatible_llm.OpenAICompatibleLLMClient,
        "from_env",
        classmethod(fake_from_env),
    )
    monkeypatch.setattr(store, "get_client", fake_get_client)
    monkeypatch.setattr(store, "ensure_document_collection", fake_ensure_collection)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")

    import app.api as api_package

    previous_factory = sys.modules.pop("app.api.runtime_factory", None)
    had_factory_attribute = hasattr(api_package, "runtime_factory")
    previous_factory_attribute = getattr(api_package, "runtime_factory", None)
    try:
        runtime_factory = importlib.import_module("app.api.runtime_factory")
        # 安全 factory 的导入本身不能读取配置、预热或构造任何持久化资源。
        assert calls == []
        runtime_root = tmp_path / "runtime"

        with pytest.raises(KeyError, match="LLM_API_KEY"):
            runtime_factory.create_runtime_app(runtime_root)

        assert calls == ["config"]
        unexpected_runtime_paths = (
            runtime_root / "documents.db",
            runtime_root / "objects",
            runtime_root / "milvus.db",
            runtime_root / "agent-runs.db",
        )
        created_runtime_paths = [path for path in unexpected_runtime_paths if path.exists()]

        assert created_runtime_paths == []
    finally:
        sys.modules.pop("app.api.runtime_factory", None)
        if previous_factory is not None:
            sys.modules["app.api.runtime_factory"] = previous_factory
        if had_factory_attribute:
            setattr(api_package, "runtime_factory", previous_factory_attribute)
        elif hasattr(api_package, "runtime_factory"):
            delattr(api_package, "runtime_factory")
