"""The legacy finite QA HTTP path must also use the one-attempt provider callable."""

from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.research_qa import create_research_qa_router
from tests.test_d16_qa import scope, service  # noqa: F401


def test_finite_qa_router_uses_explicit_single_attempt_callable(scope):  # noqa: F811
    rag, adapter, model = service(scope)
    once = Mock(side_effect=ConnectionError("D26 injected unknown provider outcome"))
    app = FastAPI()
    app.include_router(create_research_qa_router(scope[0], adapter, rag, generate_once=once))
    result = TestClient(app).post(
        "/research/questions", json={"document_ids": ["doc-0", "doc-1"], "query": "营业收入原文"}
    )
    assert result.status_code == 503 and result.json()["error_code"] == "llm_error"
    assert not result.json()["content"] and not result.json()["citations"]
    assert once.call_count == 1 and model.generate.call_count == 0
