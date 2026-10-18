"""Fresh DB-only process: zero inference/search/parse/network during historical GET."""

import json
import shutil
import tempfile
import os
from pathlib import Path
import sys
from types import ModuleType

from fastapi.testclient import TestClient

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
proof = json.loads((root / "product/validation/d17-real-save.json").read_text())
os.environ["FINDOC_RUNTIME_ROOT"] = proof["runtime_root"]
for key in list(os.environ):
    if key.startswith("LLM_") or key == "OPENAI_API_KEY":
        del os.environ[key]
calls = dict(model=0, embedder=0, retriever=0, milvus=0, parser=0, financial=0, network=0)


def bomb(name):
    def fail(*args, **kwargs):
        calls[name] += 1
        raise AssertionError("history_executed_dependency")

    return fail


embed = ModuleType("app.rag.embed")
embed.embed = bomb("embedder")
sys.modules["app.rag.embed"] = embed
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.store import MilvusSearchStore  # noqa: E402
from app.agent.financial_analysis import FinancialAnalysisService  # noqa: E402
import app.documents.fast_pdf_parser  # noqa: E402

OpenAICompatibleLLMClient.generate = bomb("model")
OpenAICompatibleLLMClient.generate_once = bomb("model")
Retriever.retrieve = bomb("retriever")
MilvusSearchStore.search = bomb("milvus")
FinancialAnalysisService.analyze = bomb("financial")
app.documents.fast_pdf_parser.parse_fast_pdf_bytes = bomb("parser")


def audit(event, args):
    if event == "socket.connect":
        calls["network"] += 1
        raise AssertionError("history_network_call")


sys.addaudithook(audit)
from app.api.research_history_app import create_history_app_from_env  # noqa: E402

with TestClient(create_history_app_from_env()) as client:
    restored = []
    for entry in proof["runs"]:
        value = entry["result"]
        response = client.get("/research/runs/" + value["run_id"])
        assert response.status_code == 200 and response.json() == value
        assert client.get("/research/runs/by-operation/" + value["operation_id"]).json() == value
        restored.append(
            dict(run_id=value["run_id"], status=value["status"], sha=value["integrity_sha256"])
        )
    interrupted = client.get("/research/runs/" + proof["interrupted_run_id"]).json()
    assert (
        interrupted["status"] == "system_error"
        and interrupted["result"]["error_code"] == "interrupted"
    )
    assert client.post("/research/runs", json={}).status_code == 405
    assert client.get("/research/runs/unknown").status_code == 404
    assert client.get("/research/runs?workspace_id=foreign").status_code == 422
    ids = []
    cursor = None
    while True:
        page = client.get(
            "/research/runs", params={"limit": 2, **({"cursor": cursor} if cursor else {})}
        ).json()
        ids.extend(i["run_id"] for i in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(set(ids)) == len(ids)
    assert set(v["run_id"] for v in restored) <= set(ids)
# Copy only documents.db: neither Milvus nor original PDFs exist in this new process root.
only_db_root = Path(tempfile.mkdtemp(prefix="findoc-d17-db-only-"))
shutil.copy2(Path(proof["runtime_root"]) / "documents.db", only_db_root / "documents.db")
assert sorted(p.name for p in only_db_root.iterdir()) == ["documents.db"]
os.environ["FINDOC_RUNTIME_ROOT"] = str(only_db_root)
with TestClient(create_history_app_from_env()) as db_client:
    for entry in proof["runs"]:
        value = entry["result"]
        assert db_client.get("/research/runs/" + value["run_id"]).json() == value
    assert db_client.get("/research/runs?limit=2").status_code == 200
assert not any(calls.values())
record = dict(
    fresh_process=True,
    database_only_root=str(only_db_root),
    database_only_without_milvus_or_pdfs=True,
    model_environment=False,
    sqlite_only=True,
    restored=restored,
    interrupted=interrupted,
    pagination_ids=ids,
    execution_calls=calls,
)
(root / "product/validation/d17-restart.json").write_text(
    json.dumps(record, indent=2, ensure_ascii=False) + "\n"
)
print(json.dumps(dict(restored=len(restored), pagination=len(ids), execution_calls=calls)))
