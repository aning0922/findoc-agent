"""Fresh interpreter, DB-only v1/v2/result reads with execution/network bombs."""

import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from unittest.mock import Mock, AsyncMock

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))


def read_phase(runtime):
    os.environ["FINDOC_RUNTIME_ROOT"] = str(runtime)
    for key in list(os.environ):
        if key.startswith("LLM_") or key == "OPENAI_API_KEY":
            del os.environ[key]
    from app.api.research_history_app import create_history_app_from_env
    from app.agent.financial_analysis import FinancialAnalysisService
    from app.research.templates import TemplateService
    from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
    from app.rag.retriever import Retriever
    from app.agent.revenue_confirmation import RevenueConfirmationService
    import app.documents.fast_pdf_parser as parser

    bombs = {}
    for cls, method in [
        (FinancialAnalysisService, "analyze"),
        (FinancialAnalysisService, "compare"),
        (TemplateService, "prepare"),
        (OpenAICompatibleLLMClient, "complete"),
        (OpenAICompatibleLLMClient, "generate_once"),
        (Retriever, "retrieve"),
        (RevenueConfirmationService, "confirm_financial"),
        (RevenueConfirmationService, "persist_financial"),
    ]:
        bomb = (AsyncMock if asyncio.iscoroutinefunction(getattr(cls, method)) else Mock)(
            side_effect=AssertionError("GET execution")
        )
        setattr(cls, method, bomb)
        bombs[cls.__name__ + "." + method] = bomb
    parser.parse_fast_pdf_bytes = Mock(side_effect=AssertionError("GET parser"))
    socket.create_connection = Mock(side_effect=AssertionError("GET network"))
    import httpx

    httpx.Client.send = Mock(side_effect=AssertionError("GET provider"))
    # TestClient's own ASGI request needs its send method; use ASGITransport after app assembly.
    app = create_history_app_from_env()
    import sqlite3

    with sqlite3.connect(runtime / "documents.db") as conn:
        identities = conn.execute("SELECT task_id,operation_id FROM template_tasks").fetchall()
    async def checks():
        results = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for task_id, op in identities:
                a = await client.get("/research/tasks/" + task_id)
                b = await client.get("/research/tasks/by-operation/" + op)
                assert a.status_code in (200,409,503) and a.status_code == b.status_code and a.json() == b.json(), a.text[:200]
                results.append(a.json())
            page = await client.get("/research/tasks?limit=50")
            assert len(page.json()["items"]) == len(results)
            assert (await client.post("/research/tasks", json={})).status_code == 405
        return results

    try:
        results = asyncio.run(checks())
    finally:
        for handler in app.router.on_shutdown:
            handler()
    assert (
        not any(b.call_count for b in bombs.values()) and not parser.parse_fast_pdf_bytes.call_count
    )
    proof = dict(
        pid=os.getpid(),
        database_only=True,
        restored_tasks=len(results),
        graph_versions=sorted({r["graph_version"] for r in results}),
        statuses=[r["status"] for r in results],
        full_results_sha256=[],
        execution_calls={k: b.call_count for k, b in bombs.items()},
        parser_calls=0,
        network_calls=socket.create_connection.call_count,
        provider_calls=httpx.Client.send.call_count,
    )
    import hashlib

    for r in results:
        proof["full_results_sha256"].append(
            dict(
                task_id=r["task_id"],
                sha256=hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest(),
            )
        )
    (runtime / "read-proof.json").write_text(json.dumps(proof, indent=2))
    return proof


if sys.argv[1:] == ["read"]:
    read_phase(Path(os.environ["FINDOC_RUNTIME_ROOT"]))
else:
    import sqlite3

    source = Path(
        json.loads((root / "product/validation/d21-real-research.json").read_text())["runtime_root"]
    )
    runtime = Path(tempfile.mkdtemp(prefix="findoc-d21-db-only-"))
    shutil.copy2(source / "documents.db", runtime / "documents.db")
    # Import actual v1 waits/operations/checkpoints from the proven D19 isolated runtime,
    # preserving JSON bytes. These are independent historic tasks, not upgraded children.
    old = Path(
        json.loads((root / "product/validation/d19-persistent-recovery-proof.json").read_text())[
            "runtime_root"
        ]
    )
    with sqlite3.connect(runtime / "documents.db") as conn:
        conn.execute("ATTACH DATABASE ? AS legacy", (str(old / "documents.db"),))
        for table in (
            "template_tasks",
            "template_operations",
            "template_checkpoints",
            "template_checkpoint_writes",
        ):
            columns = [
                r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[1] != "sequence"
            ]
            text = ",".join(columns)
            conn.execute(f"INSERT INTO {table} ({text}) SELECT {text} FROM legacy.{table}")
    command = [sys.executable, str(Path(__file__).resolve()), "read"]
    env = dict(os.environ, FINDOC_RUNTIME_ROOT=str(runtime), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    output = dict(
        command=command,
        exit_code=result.returncode,
        runtime_root=str(runtime),
        stdout_summary=result.stdout[-1000:],
        stderr_summary=result.stderr[-1500:],
    )
    if result.returncode == 0:
        output["proof"] = json.loads((runtime / "read-proof.json").read_text())
    (root / "product/validation/d21-restart-proof.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps(output, indent=2))
    sys.exit(result.returncode)
