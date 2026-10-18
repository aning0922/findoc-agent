import pytest
from app.rag.retriever import SearchFilters, SearchHit, TrustedContext
from app.rag.service import (
    RAGService,
    RefusalReason,
    RefusalResult,
    SystemErrorResult,
    SystemErrorType,
)
from tests.test_day44_rag_service import FakeEvidenceGate, FakeRetriever, FakeLLMClient


def test_non_empty_evidence_rejected_by_gate_skips_llm() -> None:
    """输入为 Retriever 返回的非空证据，但生成前 evidence gate 判定不通过；
    预期返回 insufficient_evidence 正常拒答，gate 调用1次且 LLM 调用0次；
    若返回 empty_retrieval、调用 LLM、发布 RAGResult 或抛出异常，
    说明生成前第一层拒答合同被破坏。
    """
    query = "营业收入是多少？"
    hits = [
        SearchHit(
            score=0.99,
            text="公司未来将关注相关技术发展",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source.txt",
            type="paragraph",
            section="section_1",
            table_md=None,
        )
    ]
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    gate = FakeEvidenceGate(allowed=False)
    llm = FakeLLMClient(response="公司未来将关注相关技术发展。[1]")
    retriever = FakeRetriever(hits=hits)
    rag_service = RAGService(
        retriever=retriever, llm_client=llm, evidence_gate=gate, max_evidence_chars=1000
    )
    result = rag_service.answer(
        query=query, context=trusted_context, top_k=top_k, filters=search_filters
    )
    assert isinstance(result, RefusalResult)
    assert result.reason == RefusalReason.INSUFFICIENT_EVIDENCE
    assert len(gate.calls) == 1
    assert gate.calls == [(query, hits)]
    assert len(llm.prompts) == 0
    assert len(retriever.calls) == 1


def test_valid_model_refusal_skips_citation_validation() -> None:
    """输入为通过第一层 gate 的非空证据，以及模型返回的合法拒答 JSON；
    预期返回 model_refusal，LLM 调用1次且不进入成功答案的引用校验；
    若抛出 CitationValidationError、构造 Citation、发布 RAGResult 或归类为系统错误，
    说明模型拒答分流与成功答案引用合同的边界被破坏。
    """
    query = "营业收入是多少？"
    hits = [
        SearchHit(
            score=0.99,
            text="公司未来将关注相关技术发展",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source.txt",
            type="paragraph",
            section="section_1",
            table_md=None,
        )
    ]
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    gate = FakeEvidenceGate(allowed=True)
    llm = FakeLLMClient(response='{"decision":"refuse"}')
    retriever = FakeRetriever(hits=hits)
    rag_service = RAGService(
        retriever=retriever, llm_client=llm, evidence_gate=gate, max_evidence_chars=1000
    )
    result = rag_service.answer(
        query=query, context=trusted_context, top_k=top_k, filters=search_filters
    )
    assert isinstance(result, RefusalResult)
    assert result.reason == RefusalReason.MODEL_REFUSAL
    assert len(gate.calls) == 1
    assert len(llm.prompts) == 1
    assert len(retriever.calls) == 1
    assert gate.calls == [(query, hits)]
    assert '{"decision":"refuse"}' in llm.prompts[0]


@pytest.mark.parametrize(
    ("response", "error", "expected_error_type", "expected_raw_error_fragment"),
    [
        (
            '{"decision":"answer","content":"不会被返回。[1]"}',
            ConnectionError("provider unavailable"),
            SystemErrorType.LLM_PROVIDER_ERROR,
            "ConnectionError: provider unavailable",
        ),
        ("", None, SystemErrorType.EMPTY_MODEL_OUTPUT, None),
        (
            '```json\n{"decision":"refuse"}\n```',
            None,
            SystemErrorType.PROTOCOL_PARSE_ERROR,
            "_ModelProtocolError: 模型返回了非法 JSON",
        ),
    ],
)
def test_model_failures_return_system_error(
    response: str,
    error: Exception | None,
    expected_error_type: SystemErrorType,
    expected_raw_error_fragment: str | None,
) -> None:
    """输入为已通过检索和 gate 的证据，以及供应商异常、空输出或非法协议输出；
    预期分别返回稳定的 llm_provider_error、empty_model_output 或 protocol_parse_error，
    且 LLM 恰好调用1次，不发布答案也不计入拒答；
    若异常逃逸、返回 RefusalResult 或构造 RAGResult，
    说明模型失败与正常拒答的终态边界被破坏。
    """
    query = "营业收入是多少？"
    hits = [
        SearchHit(
            score=0.99,
            text="公司未来将关注相关技术发展",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source.txt",
            type="paragraph",
            section="section_1",
            table_md=None,
        )
    ]
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    gate = FakeEvidenceGate(allowed=True)

    llm = FakeLLMClient(response=response, error=error)
    retriever = FakeRetriever(hits=hits)
    rag_service = RAGService(
        retriever=retriever, llm_client=llm, evidence_gate=gate, max_evidence_chars=1000
    )
    result = rag_service.answer(
        query=query, context=trusted_context, top_k=top_k, filters=search_filters
    )
    assert isinstance(result, SystemErrorResult)
    assert result.error_type == expected_error_type
    if expected_raw_error_fragment is None:
        assert result.raw_error is None
    else:
        assert result.raw_error is not None
        assert expected_raw_error_fragment in result.raw_error
    assert len(gate.calls) == 1
    assert len(llm.prompts) == 1
    assert len(retriever.calls) == 1
    assert gate.calls == [(query, hits)]


def test_evidence_gate_failure_is_system_error_and_skips_llm() -> None:
    """输入为 Retriever 返回非空证据，但 EvidenceGate 自身抛出配置异常；
    预期返回 evidence_gate_error 系统失败，保留内部 raw_error，
    使用安全 message，且 LLM 调用0次；
    若异常直接逃逸、返回 insufficient_evidence 或调用模型，
    说明 gate 故障与正常证据不足拒答的终态边界被破坏。
    """
    query = "营业收入是多少？"
    hits = [
        SearchHit(
            score=0.99,
            text="公司未来将关注相关技术发展",
            chunk_id="chunk_id_1",
            page=1,
            source_file="source.txt",
            type="paragraph",
            section="section_1",
            table_md=None,
        )
    ]
    trusted_context: TrustedContext = TrustedContext(workspace_id="W-SA")
    search_filters: SearchFilters = SearchFilters(source_file="demo.pdf")
    top_k: int = 5
    gate = FakeEvidenceGate(allowed=True, error=RuntimeError("gate configuration invalid"))
    llm = FakeLLMClient(response="公司未来将关注相关技术发展。[1]")
    retriever = FakeRetriever(hits=hits)
    rag_service = RAGService(
        retriever=retriever, llm_client=llm, evidence_gate=gate, max_evidence_chars=1000
    )
    result = rag_service.answer(
        query=query, context=trusted_context, top_k=top_k, filters=search_filters
    )
    assert isinstance(result, SystemErrorResult)
    assert result.error_type == SystemErrorType.EVIDENCE_GATE_ERROR
    assert result.message == "证据资格判断失败，本次未生成答案"
    assert result.raw_error == "RuntimeError: gate configuration invalid"
    assert "gate configuration invalid" not in result.message
    assert gate.calls == [(query, hits)]
    assert len(retriever.calls) == 1
    assert len(llm.prompts) == 0