"""Four independently downloaded PDFs -> parser -> snapshots -> bounded QA.

Controlled retrieval/model only. No acceptance or production facts are created.
Existing manually transcribed gold is read AFTER extraction, only for assertions.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from app.agent.metric_extraction import metric_for
from app.documents.preparation import DocumentTaskPreparer
from app.documents.models import DocumentStatus
from app.rag.retriever import SearchHit
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.service import RAGService
from tests.test_document_sources import Harness, metadata
from tests.test_financial_reviews import assemble
from app.companies.models import CompanyCreate


@pytest.mark.parametrize("report", ["gree-2024", "gree-2025", "midea-2024", "midea-2025"])
def test_four_pdf_structure_persistence_and_qa(tmp_path, report):
    manifest = next(
        s
        for s in json.loads(Path("product/validation/sources.json").read_text())
        if s["id"] == report
    )
    raw = Path(manifest["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    h = assemble(Harness(tmp_path))
    name, code = (
        ("珠海格力电器股份有限公司", "000651")
        if report.startswith("gree")
        else ("美的集团股份有限公司", "000333")
    )
    company = h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
    year = int(report[-4:])
    h.id = h.upload(raw, metadata(company.company_id, year), filename=report + ".pdf").json()[
        "document_id"
    ]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    source, records = asyncio.run(
        h.service.parsed_evidence(
            h.id,
            company_id=company.company_id,
            source_revision=asyncio.run(h.service.source(h.id))["source_revision"],
        )
    )
    extracted = asyncio.run(
        h.candidates.collect_metrics(
            document_id=h.id,
            company_id=company.company_id,
            source_revision=source["source_revision"],
            metric_keys=("revenue", "net_profit_parent", "operating_cash_flow"),
            periods=(year - 1, year),
        )
    )
    gold = [
        g
        for g in json.loads(Path("product/validation/manual-benchmark.json").read_text())["facts"]
        if g["document_id"] == report
    ]
    checks = []
    for g in gold:
        candidate = next(
            c
            for c in extracted["candidates"]
            if c["period"] == g["period"] and c["metric_key"] == g["metric"]
        )
        for f in (
            "raw_value",
            "raw_unit",
            "value_cny_yuan",
            "physical_page",
            "scope",
            "accounting_basis",
            "period_start",
            "period_end",
        ):
            assert candidate[f] == g[f], (report, f, candidate)
        assert candidate["status"] == "candidate"
        assert any(
            e["role"] == "statement" and e["physical_page"] == g["statement_page"]
            for e in candidate["evidence"]
        )
        table = next(
            e
            for e in records
            if e["kind"] == "table"
            and e["physical_page"] == g["physical_page"]
            and g["raw_value"] in e["text"]
        )
        structure = table["layout"]["table_structure"]
        assert structure["status"] == "verified"
        labels = [c for c in structure["cells"] if metric_for(c["text"]) == g["metric"]]
        assert len(labels) == 1
        amount = next(
            c
            for c in structure["cells"]
            if c["row"] == labels[0]["row"] and c["actual_year"] == g["period"]
        )
        assert amount["text"] == g["raw_value"]
        assert all(table["layout"]["rows"][r][c]["bbox"] for r, c in amount["raw_cells"])
        checks.append(
            dict(
                gold=g,
                candidate=candidate,
                table_evidence_id=table["evidence_id"],
                logical_amount_cell=amount,
                logical_label_cell=labels[0],
                pdf_correct=True,
                structure_correct=True,
            )
        )
    summary = next(
        e
        for e in records
        if e["kind"] == "table"
        and e["physical_page"] == gold[0]["physical_page"]
        and gold[0]["raw_value"] in e["text"]
    )
    hit = SearchHit(
        score=0.99,
        chunk_id="controlled-summary",
        text="主要会计数据和财务指标",
        table_md=summary["text"],
        type="table",
        page=summary["physical_page"],
        source_file=report + ".pdf",
        workspace_id="demo",
        document_id=h.id,
        source_revision=source["source_revision"],
    )
    retrieval = Mock(retrieve=Mock(return_value=[hit]))
    model = Mock(generate=Mock(return_value='{"decision":"answer","quotes":[{"number":1}]}'))
    preparer = DocumentTaskPreparer(
        document_service=h.documents, sources=h.service, workspace_id="demo"
    )
    scope = SelectedScopeSearch(preparer, retrieval)
    selection = asyncio.run(
        preparer.prepare_many(document_ids=[h.id], query="列出主要会计数据和财务指标原文")
    )
    rag = RAGService(
        retriever=retrieval,
        llm_client=model,
        evidence_gate=Mock(allows=Mock(return_value=True)),
        max_evidence_chars=16000,
    )
    result = asyncio.run(rag.answer_selected(selection, scope))
    assert result["outcome"] == "answered", result
    assert len(result["citations"]) == 1 and summary["text"] in result["content"]
    assert result["citations"][0]["source_revision"] == source["source_revision"]
    # Snapshot readback preserves raw boxes, null slots, spans, years and rendered text.
    read = asyncio.run(
        h.service.evidence(h.id, summary["evidence_id"], source_revision=source["source_revision"])
    )
    assert read["layout"] == summary["layout"] and read["text"] == summary["text"]
    proof = dict(
        report=report,
        source=source,
        checks=checks,
        layout=summary["layout"],
        table=summary["text"],
        answer=result,
        actual_pdf=True,
        actual_parser=True,
        actual_sqlite=True,
        actual_object_store=True,
        actual_model=False,
        actual_embedding=False,
        actual_vector_search=False,
        human_acceptances=0,
        raw_pdf_sha256=hashlib.sha256(raw).hexdigest(),
        model_calls=model.generate.call_count,
        retrieval_calls=retrieval.retrieve.call_count,
        runtime_root=str(tmp_path),
        gold_is_validation_only=True,
        human_semantic_review="pending",
    )
    if os.environ.get("FINDOC_D26_EVIDENCE_DIR"):
        (Path(os.environ["FINDOC_D26_EVIDENCE_DIR"]) / f"a-{report}.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
        )
