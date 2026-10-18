"""Copy trusted D16 runtime without rebuilding indices; actual RAG save, three-state seed."""

import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from dotenv import dotenv_values
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
output = root / "product/validation"
for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    assert os.environ.get(key) == "1"
source = json.loads((output / "d16-real-index.json").read_text())
runtime = Path(tempfile.mkdtemp(prefix="findoc-d17-real-")) / "runtime"
# D16 runtime is offline. Preserve its trusted manifests and immutable PDF objects verbatim.
shutil.copytree(source["runtime_root"], runtime)
for k, v in dotenv_values(root.parent / "findoc-rag/.env").items():
    if k.startswith("LLM_") and v is not None:
        os.environ[k] = v
os.environ["LLM_TIMEOUT_SECONDS"] = "120"
os.environ["FINDOC_RUNTIME_ROOT"] = str(runtime)
from app.api.runtime_factory import create_runtime_app  # noqa: E402

app = create_runtime_app(runtime)
proof = dict(
    runtime_root=str(runtime),
    source_runtime=source["runtime_root"],
    index_rebuilt=False,
    actual_bge=True,
    actual_milvus=True,
    actual_llm=True,
    human_review="pending",
    reports=[],
    runs=[],
    pdf_checks=[],
    controlled_faults=[],
)
(output / "d17-real-runtime.json").write_text(json.dumps({"runtime_root": str(runtime)}, indent=2))
with TestClient(app) as client:
    repo = app.state.research_repository
    with closing(repo.registry._connect()) as c:
        proof["publications_before"] = [
            dict(r)
            for r in c.execute(
                "SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation"
            )
        ]
    for report in source["reports"]:
        result = client.get("/documents/" + report["document_id"] + "/source")
        assert result.status_code == 200
        s = result.json()
        assert s["content_sha256"] == report["source"]["content_sha256"]
        proof["reports"].append(
            dict(report_id=report["report_id"], document_id=report["document_id"], source=s)
        )
    ids = [r["document_id"] for r in source["reports"]]
    query = "请分别摘录四份年报公司简介中公司中文名称、股票简称或股票代码的原文。"
    body = dict(operation_id=str(uuid.uuid4()), document_ids=ids, query=query)
    response = client.post("/research/runs", json=body)
    proof["runs"].append(
        dict(
            kind="actual_four_report_answer",
            http_status=response.status_code,
            result=response.json(),
        )
    )
    (output / "d17-real-save.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    assert response.status_code == 200 and response.json()["status"] == "answered", (
        "actual_answer_failed"
    )
    answered = response.json()
    assert set(c["document_id"] for c in answered["result"]["citations"]) == set(ids)
    for citation in answered["result"]["citations"]:
        pdf = client.get(
            "/documents/" + citation["document_id"] + "/file",
            params={
                "company_id": citation["company_id"],
                "source_revision": citation["source_revision"],
            },
        )
        assert pdf.status_code == 200
        digest = hashlib.sha256(pdf.content).hexdigest()
        assert digest == citation["content_sha256"]
        proof["pdf_checks"].append(
            {
                k: citation[k]
                for k in ("document_id", "source_revision", "chunk_id", "physical_page", "text")
            }
            | {"sha256": digest}
        )
    assert client.post("/research/runs", json=body).json() == answered
    refusal = client.post(
        "/research/runs",
        json={**body, "operation_id": str(uuid.uuid4()), "query": "请计算美的营业收入同比增长率。"},
    )
    assert refusal.status_code == 200 and refusal.json()["status"] == "refused"
    proof["runs"].append(
        dict(kind="actual_calculation_refusal", http_status=200, result=refusal.json())
    )
    scope = app.state.selected_scope_search
    search = scope.search

    async def fail(*args, **kwargs):
        raise RuntimeError("controlled retrieval failure")

    scope.search = fail
    error = client.post("/research/runs", json={**body, "operation_id": str(uuid.uuid4())})
    scope.search = search
    assert error.status_code == 200 and error.json()["status"] == "system_error"
    assert error.json()["result"]["error_code"] == "retrieval_error"
    proof["runs"].append(
        dict(kind="controlled_retrieval_failure", http_status=200, result=error.json())
    )
    proof["controlled_faults"].append("selected_scope.search raises before BGE/Milvus/LLM")
    selection = asyncio.run(
        app.state.selection_preparer.prepare_many(document_ids=ids, query="中断恢复验证")
    )
    interrupted, _ = repo.register(
        str(uuid.uuid4()), selection, {"mode": "controlled_interruption"}
    )
    proof["interrupted_run_id"] = interrupted.run_id
    with closing(repo.registry._connect()) as c:
        proof["publications_after"] = [
            dict(r)
            for r in c.execute(
                "SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation"
            )
        ]
    assert proof["publications_before"] == proof["publications_after"]
    # All historical GETs must work with execution dependencies that now fail on any use.
    counters = dict(model=0, embedder=0, retriever=0, parser=0)

    def bomb(name):
        def blocked(*args, **kwargs):
            counters[name] += 1
            raise AssertionError("history invoked execution dependency")

        return blocked

    app.state.runtime_rag_resources.retriever.retrieve = bomb("retriever")
    app.state.runtime_rag_resources.rag_service._llm_client.generate = bomb("model")
    import app.rag.embed
    import app.documents.fast_pdf_parser

    app.rag.embed.embed = bomb("embedder")
    app.documents.fast_pdf_parser.parse_fast_pdf_bytes = bomb("parser")
    for entry in proof["runs"]:
        value = entry["result"]
        assert client.get("/research/runs/" + value["run_id"]).json() == value
        assert client.get("/research/runs/by-operation/" + value["operation_id"]).json() == value
    assert client.get("/research/runs?limit=2").status_code == 200
    proof["history_get_execution_calls"] = counters
    assert not any(counters.values())
(output / "d17-real-save.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
print(
    json.dumps(
        dict(
            runtime_root=str(runtime),
            states=[r["result"]["status"] for r in proof["runs"]],
            pdf_checks=len(proof["pdf_checks"]),
            get_calls=proof["history_get_execution_calls"],
        )
    )
)
