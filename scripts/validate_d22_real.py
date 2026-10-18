"""Actual D21 persisted model results -> D22, isolated copy, no research rerun."""

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from unittest.mock import Mock, AsyncMock

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from tests.support.d19_runtime import reopen  # noqa: E402
from app.research.task_repository import TaskRepository  # noqa: E402
from app.reports.service import ReportService  # noqa: E402
from app.reports.contracts import GenerateDraft, ReportDraft  # noqa: E402
from app.agent.financial_analysis import FinancialAnalysisService, IsolatedAnalysisTestConfig  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient  # noqa: E402

source = Path(
    json.loads((root / "product/validation/d21-real-research.json").read_text())["runtime_root"]
)
runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d22-real-"))
shutil.copy2(source / "documents.db", runtime / "documents.db")
shutil.copytree(source / "objects", runtime / "objects")
h = reopen(runtime)
repo = TaskRepository(h.registry, "demo")
service = ReportService(repo, h.service, isolated_test=IsolatedAnalysisTestConfig(runtime))
bombs = {}
for cls, method in [
    (FinancialAnalysisService, "analyze"),
    (FinancialAnalysisService, "compare"),
    (Retriever, "retrieve"),
    (OpenAICompatibleLLMClient, "complete"),
    (OpenAICompatibleLLMClient, "generate_once"),
]:
    bomb = (AsyncMock if asyncio.iscoroutinefunction(getattr(cls, method)) else Mock)(
        side_effect=AssertionError("D22 execution forbidden")
    )
    setattr(cls, method, bomb)
    bombs[cls.__name__ + "." + method] = bomb


async def main():
    cases = []
    with sqlite3.connect(runtime / "documents.db") as conn:
        tasks = [json.loads(r[0]) for r in conn.execute("select payload from template_tasks")]
    before = hashlib.sha256((runtime / "documents.db").read_bytes()).hexdigest()
    (runtime / "drafts").mkdir()
    for task in tasks:
        if task["task_id"] not in {
            c["result"]["task_id"]
            for c in json.loads((root / "product/validation/d21-real-research.json").read_text())[
                "cases"
            ]
        }:
            continue
        request = GenerateDraft(task_id=task["task_id"], expected_revision=task["revision"])
        draft = await service.generate(request)
        repeated = await service.generate(request)
        assert draft.business_content_sha256 == repeated.business_content_sha256
        ReportDraft.model_validate_json(draft.model_dump_json())
        assert draft.status == "simulated_draft" and draft.watermark
        c = task["final_research_content"]
        assert draft.evidence_appendix["financial_facts"] == c["financial_facts"]
        assert draft.evidence_appendix["deterministic_analysis"] == c["deterministic_analysis"]
        assert [v.model_dump() for v in draft.operating_information] == c["operating_descriptions"]
        assert [v.model_dump() for v in draft.model_interpretations] == c["model_interpretations"]
        (runtime / "drafts" / f"{task['task_id']}.json").write_text(draft.model_dump_json(indent=2))
        cases.append(
            dict(
                task_id=task["task_id"],
                revision=task["revision"],
                title=draft.title,
                template=draft.report_type,
                business_sha=draft.business_content_sha256,
                facts=[v.model_dump() for v in draft.financial_facts],
                analysis=[v.model_dump() for v in draft.financial_analysis],
                citations=[
                    dict(
                        number=v.citation.number,
                        document_id=v.citation.document_id,
                        source_revision=v.citation.source_revision,
                        sha=v.citation.content_sha256,
                        page=v.citation.physical_page,
                        chunk_id=v.citation.chunk_id,
                    )
                    for v in draft.operating_information
                ],
                field_checks=len(draft.field_verification),
                pending_interpretations=True,
                simulated_watermark=draft.watermark,
                stable=True,
            )
        )
    assert len(cases) == 4 and all(b.call_count == 0 for b in bombs.values())
    assert before == hashlib.sha256((runtime / "documents.db").read_bytes()).hexdigest()
    proof = dict(
        runtime_root=str(runtime),
        input_runtime=str(source),
        cases=cases,
        execution_calls={k: v.call_count for k, v in bombs.items()},
        database_unchanged=True,
        simulated_test=True,
        human_acceptances=0,
    )
    (root / "product/validation/d22-real-reports.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            dict(
                runtime_root=str(runtime),
                cases=len(cases),
                execution_calls=proof["execution_calls"],
            )
        )
    )


asyncio.run(main())
