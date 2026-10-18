"""Observe open D25 defects in fresh integration data without changing sources."""

import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock, Mock
from app.documents.preparation import PreparedDocumentSelection, SelectedDocumentIdentity
from app.rag.retriever import SearchHit, TrustedContext
from app.rag.service import RAGService

root = Path(__file__).resolve().parent.parent
out = root / "product/d25-ux-integration/evidence"
record = json.loads((out / "seed/record.json").read_text())
runtime = Path(record["runtime_root"]).resolve()
assert record["servers_stopped"] and record["simulated_test"]
manifest = json.loads((root / "product/validation/sources.json").read_text())
checks = []
with sqlite3.connect((runtime / "documents.db").as_uri() + "?mode=ro", uri=True) as conn:
    for name, year, amount, page in [
        ("gree-2024", 2024, "189,163,654,064.64", 7),
        ("midea-2025", 2025, "456,451,731", 9),
    ]:
        source = next(s for s in manifest if s["id"] == name)
        row = conn.execute(
            "SELECT s.source_revision,e.evidence_id,e.text FROM document_evidence e JOIN document_sources s ON s.source_revision=e.source_revision WHERE s.content_sha256=? AND e.kind='table' AND e.physical_page=? AND e.text LIKE ?",
            (source["sha256"], page, f"%{amount}%"),
        ).fetchone()
        assert row
        lines = row[2].splitlines()

        def cells(line):
            return [v.strip() for v in line.strip().strip("|").split("|")]

        header = cells(lines[0])
        income = cells(next(line for line in lines if "营业收入" in line))
        y = header.index(f"{year}年")
        a = income.index(amount)
        checks.append(
            {
                "source": name,
                "pdf_sha256": source["sha256"],
                "source_revision": row[0],
                "evidence_id": row[1],
                "physical_page": page,
                "table_sha256": hashlib.sha256(row[2].encode()).hexdigest(),
                "header_year_column_zero_based": y,
                "income_amount_column_zero_based": a,
                "aligned": y == a,
                "header_cells": header,
                "income_cells": income,
                "original_table": row[2],
            }
        )
identity = SelectedDocumentIdentity(
    "demo",
    "doc-0",
    "company-0",
    2024,
    "annual",
    "2024-01-01",
    "2024-12-31",
    "consolidated",
    "0" * 64,
    "a" * 64,
    1,
    "controlled-observation",
)
selection = PreparedDocumentSelection(
    "请列营业收入原值，不计算同比", TrustedContext("demo"), (identity,)
)
scope = Mock(
    search=AsyncMock(
        return_value=(
            SearchHit(
                score=1,
                chunk_id="controlled",
                text="营业收入原值100元",
                page=1,
                source_file="controlled.pdf",
                type="paragraph",
                workspace_id="demo",
                document_id="doc-0",
                source_revision="0" * 64,
            ),
        )
    ),
    revalidate=AsyncMock(),
)
model = Mock()
rag = RAGService(
    retriever=Mock(),
    llm_client=model,
    evidence_gate=Mock(allows=Mock(return_value=True)),
    max_evidence_chars=4000,
)
result = asyncio.run(rag.answer_selected(selection, scope))
(out / "quality-observations.json").write_text(
    json.dumps(
        {
            "table_columns": checks,
            "negative_calculation_intent": {
                "query": selection.query,
                "response": result,
                "model_calls": model.generate.call_count,
                "desired_behavior": "raw-value extraction without calculating; current guard refusal is a defect",
            },
            "source_snapshot_writes": 0,
            "accepted_fact_writes": 0,
            "table_evidence": "fresh actual parser snapshots",
            "guard_evidence": "production RAGService with controlled evidence and no provider",
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n"
)
