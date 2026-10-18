from app.rag.retriever import Retriever, SearchHit, TrustedContext, SearchFilters
from app.rag.service import (
    RAGService,
    RAGResult,
    RefusalReason,
    RefusalResult,
    SystemErrorResult,
    SystemErrorType,
)


class FakeRetriever(Retriever):
    """模拟现有 Retriever 边界，返回预设结果或异常，并记录调用参数。"""

    def __init__(self, hits: list[SearchHit], error: Exception | None = None) -> None:
        """初始化 FakeRetriever，用于模拟 Retriever 客户端

        Args:
            hits: 模拟的搜索结果
            error: 模拟的错误
        """
        self.hits = hits
        self.error = error
        self.calls: list[tuple[str, TrustedContext, int, SearchFilters | None]] = []

    def retrieve(
        self,
        query: str,
        *,
        context: TrustedContext,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> list[SearchHit]:
        """使用可信的上下文和业务过滤条件执行一次向量检索

        Args:
            query: 查询词
            context: 可信的上下文
            top_k: 返回的搜索结果数量
            filters: 业务过滤条件
        Returns:
            预设的稳定 SearchHit 列表
        Raises:
            配置了检索异常时，抛出该预设异常
        """
        self.calls.append((query, context, top_k, filters))
        if self.error is not None:
            raise self.error
        return self.hits


class FakeLLMClient:
    """提供与 LLMClient.generate(...) 相同的方法，但不访问网络；
    按测试安排返回固定文本或抛出固定异常，同时记录控制层传入的 prompt
    """

    def __init__(self, response: str, error: Exception | None = None) -> None:
        """初始化 FakeLLMClient，用于模拟 LLM 客户端

        Args:
            response: 模拟的响应内容
            error: 模拟的错误
        """
        self.prompts: list[str] = []
        self.response = response
        self.error = error

    def generate(self, prompt: str) -> str:
        """模拟 LLM 客户端的 generate 方法
        Args:
            prompt: 控制层构造好的 prompt
        Returns:
            未经过引用验证的生成内容
        Raises:
            超时或调用失败时由具体实现抛出异常
        """
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response


class FakeEvidenceGate:
    """返回预设判断并记录调用参数，不修改证据或访问模型。"""

    def __init__(self, *, allowed: bool = True, error: Exception | None = None) -> None:
        """设置固定许可结果，并为当前实例初始化独立调用记录。

        Args:
            allowed: True 表示允许生成，False 表示证据不足。
            error: 可选预设异常；非 None 时 allows 在记录调用后抛出。
        """
        self.allowed = allowed
        self.calls: list[tuple[str, list[SearchHit]]] = []
        self.error = error

    def allows(self, query: str, hits: list[SearchHit]) -> bool:
        """记录当前 query 和 hits，并返回预设许可结果。

        Args:
            query: 当前用户问题。
            hits: Retriever 返回的非空有序证据。

        Returns:
            构造时设置的固定许可结果。
        Raises:
            Exception: 构造时配置了 error 时，记录本次调用后抛出该异常。
        """
        self.calls.append((query, hits))
        if self.error is not None:
            raise self.error
        return self.allowed


def test_happy_path_passes_retrieved_evidence_to_llm() -> None:
    """Happy Path：顺利检索到证据，并传递给 LLM 客户端"""
    search_hits = [
        SearchHit(
            score=0.9,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        ),
    ]
    query: str = "营业收入是多少？"
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    fake_retriever: FakeRetriever = FakeRetriever(search_hits)
    fake_llm: FakeLLMClient = FakeLLMClient(
        response='{"decision":"answer","content":"营业收入为100亿元。[1]"}'
    )
    fake_evidence_gate: FakeEvidenceGate = FakeEvidenceGate(allowed=True)
    service: RAGService = RAGService(
        retriever=fake_retriever,
        llm_client=fake_llm,
        evidence_gate=fake_evidence_gate,
        max_evidence_chars=500,
    )
    rag_result = service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    assert isinstance(rag_result, RAGResult)
    assert rag_result.content == "营业收入为100亿元。[1]"
    assert len(fake_retriever.calls) == 1
    assert fake_retriever.calls[0] == (query, trusted_context, top_k, search_filters)
    assert len(fake_llm.prompts) == 1
    assert query in fake_llm.prompts[0]
    assert search_hits[0].text in fake_llm.prompts[0]
    assert len(rag_result.citations) == 1
    assert rag_result.citations[0].number == 1
    assert rag_result.citations[0].source_file == "demo.pdf"
    assert rag_result.citations[0].page == 7
    assert rag_result.citations[0].chunk_id == "C-REV"


def test_switching_trusted_context_is_forwarded_to_retriever() -> None:
    """验证同一控制层的两次请求会分别传递服务端可信上下文；
    无输入和返回值，若 Retriever 收到的 workspace 顺序不正确则断言失败。
    """
    search_hits = [
        SearchHit(
            score=0.9,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        ),
    ]
    query = "营业收入是多少？"
    context_a = TrustedContext(workspace_id="W-SA")
    context_b = TrustedContext(workspace_id="W-SB")
    search_filters = SearchFilters(source_file="demo.pdf")
    fake_retriever = FakeRetriever(hits=search_hits)
    fake_llm = FakeLLMClient(response='{"decision":"answer","content":"营业收入为100亿元。[1]"}')
    fake_evidence_gate = FakeEvidenceGate(allowed=True)
    service = RAGService(
        retriever=fake_retriever,
        llm_client=fake_llm,
        evidence_gate=fake_evidence_gate,
        max_evidence_chars=500,
    )

    service.answer(query, context=context_a, filters=search_filters)
    service.answer(query, context=context_b, filters=search_filters)

    assert [call[1] for call in fake_retriever.calls] == [context_a, context_b]
    assert len(fake_llm.prompts) == 2
    assert "W-SA" not in fake_llm.prompts[0]
    assert "W-SB" not in fake_llm.prompts[1]


def test_retrieval_failure_is_system_error_and_skips_llm() -> None:
    """输入为 Retriever 抛出带内部诊断文本的连接异常；
    预期返回 retrieval_error 系统失败，保留内部 raw_error，
    但安全 message 不暴露底层异常，且 gate 和 LLM 均不调用；
    若异常直接逃逸、诊断信息丢失、泄露到安全说明、
    返回 empty_retrieval 或计入正常拒答，
    说明检索故障与空检索的终态及错误信息分层合同被破坏。
    """
    query: str = "营业收入是多少？"
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    fake_retriever: FakeRetriever = FakeRetriever(hits=[], error=ConnectionError("offLine"))
    fake_llm: FakeLLMClient = FakeLLMClient(response="营业收入为100亿元")
    fake_evidence_gate = FakeEvidenceGate(allowed=True)
    service: RAGService = RAGService(
        retriever=fake_retriever,
        llm_client=fake_llm,
        evidence_gate=fake_evidence_gate,
        max_evidence_chars=500,
    )

    result = service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    assert isinstance(result, SystemErrorResult)
    assert result.error_type == SystemErrorType.RETRIEVAL_ERROR
    assert result.message == "检索服务失败，本次未生成答案"
    assert result.raw_error == "ConnectionError: offLine"
    assert "offLine" not in result.message
    assert len(fake_retriever.calls) == 1
    assert len(fake_evidence_gate.calls) == 0
    assert len(fake_llm.prompts) == 0


def test_empty_evidence_skips_llm() -> None:
    """输入为空检索结果时返回 empty_retrieval 拒答且不调用 LLM；
    若抛出异常、调用 LLM 或发布成功答案，说明空检索终态合同被破坏。
    """
    query: str = "营业收入是多少？"
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    fake_retriever: FakeRetriever = FakeRetriever(hits=[])
    fake_llm: FakeLLMClient = FakeLLMClient(response="营业收入为100亿元")
    fake_evidence_gate = FakeEvidenceGate(allowed=True)
    service: RAGService = RAGService(
        retriever=fake_retriever,
        llm_client=fake_llm,
        evidence_gate=fake_evidence_gate,
        max_evidence_chars=500,
    )

    result = service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    assert isinstance(result, RefusalResult)
    assert result.reason == RefusalReason.EMPTY_RETRIEVAL
    assert len(fake_retriever.calls) == 1
    assert len(fake_llm.prompts) == 0
    assert len(fake_evidence_gate.calls) == 0


def test_generation_timeout_is_system_error() -> None:
    """输入为通过检索和 evidence gate 的证据，但 LLM 调用抛出 TimeoutError；
    预期返回 llm_timeout 系统失败，LLM 恰好调用1次且不发布答案；
    若异常直接逃逸、返回 model_refusal 或进入引用校验，
    说明模型超时与正常拒答的终态边界被破坏。
    """
    search_hits = [
        SearchHit(
            score=0.9,
            chunk_id="C-REV",
            text="2025年营业收入为100亿元",
            page=7,
            source_file="demo.pdf",
            type="paragraph",
            section="主要财务数据",
            table_md=None,
        ),
    ]
    query: str = "营业收入是多少？"
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    fake_retriever: FakeRetriever = FakeRetriever(hits=search_hits)
    fake_llm: FakeLLMClient = FakeLLMClient(
        response="营业收入为100亿元", error=TimeoutError("timeout")
    )
    fake_evidence_gate = FakeEvidenceGate(allowed=True)
    service: RAGService = RAGService(
        retriever=fake_retriever,
        llm_client=fake_llm,
        evidence_gate=fake_evidence_gate,
        max_evidence_chars=500,
    )

    result = service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    assert isinstance(result, SystemErrorResult)
    assert result.error_type == SystemErrorType.LLM_TIMEOUT
    assert result.raw_error == "TimeoutError: timeout"
    assert "timeout" not in result.message
    assert len(fake_retriever.calls) == 1
    assert len(fake_evidence_gate.calls) == 1
    assert len(fake_llm.prompts) == 1
    assert fake_evidence_gate.calls == [(query, search_hits)]


def test_changing_evidence_changes_llm_prompt() -> None:
    """改变证据后，LLM 客户端的 prompt 也改变"""
    search_hit_1: SearchHit = SearchHit(
        score=0.9,
        chunk_id="C-REV",
        text="2025年营业收入为100亿元",
        page=7,
        source_file="demo.pdf",
        type="paragraph",
        section="主要财务数据",
        table_md=None,
    )
    search_hit_2: SearchHit = SearchHit(
        score=0.8,
        chunk_id="C-PROFIT",
        text="2025年净利润为20亿元",
        page=7,
        source_file="demo.pdf",
        type="paragraph",
        section="主要财务数据",
        table_md=None,
    )
    query: str = "营业收入是多少？"
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    fake_retriever: FakeRetriever = FakeRetriever(hits=[search_hit_1])
    fake_llm: FakeLLMClient = FakeLLMClient(
        response='{"decision":"answer","content":"营业收入为100亿元。[1]"}'
    )
    fake_evidence_gate = FakeEvidenceGate(allowed=True)
    service: RAGService = RAGService(
        retriever=fake_retriever,
        llm_client=fake_llm,
        evidence_gate=fake_evidence_gate,
        max_evidence_chars=500,
    )
    service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    prompt1 = fake_llm.prompts[0]

    fake_retriever.hits = [search_hit_2]
    service.answer(query, context=trusted_context, top_k=top_k, filters=search_filters)
    prompt2 = fake_llm.prompts[1]

    assert prompt1 != prompt2
    assert search_hit_1.text in prompt1
    assert search_hit_2.text in prompt2
    assert len(fake_llm.prompts) == 2
    assert len(fake_retriever.calls) == 2
    assert search_hit_1.text not in prompt2
    assert search_hit_2.text not in prompt1
