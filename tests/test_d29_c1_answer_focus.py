"""Independent adversarial targets over explicitly synthetic verified geometry."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

import pytest

from app.rag.parse.models import PDFCell, PDFLayout
from app.rag.parse.table_structure import project_table, render_structure
from app.research.answer_focus import project_focus
from app.research.models import Envelope, canonical, sha
from app.rag.calculation_intent import requires_financial_analysis


def fixture(query="请摘录2024年度营业收入原值及原单位，不计算同比。", unit="元"):
    data = [
        ["项目", "2025年", "2024年", "2023年"],
        [f"营业收入（{unit}）", "1,500.00", "1,200.00", "1,000.00"],
        [f"营业总收入（{unit}）", "1,600.00", "1,300.00", "1,100.00"],
        [f"归属于上市公司股东的净利润（{unit}）", "300.00", "200.00", "100.00"],
        [f"归属于上市公司股东的扣除非经常性损益的净利润（{unit}）", "260.00", "160.00", "60.00"],
        [f"经营活动产生的现金流量净额（{unit}）", "400.00", "350.00", "250.00"],
    ]
    # A comparative percentage is not a metric-label column.
    data[0].append("本年比上年增减")
    for row in data[1:]:
        row.append("10.00%")
    layout = PDFLayout(
        strategy="ruled",
        rows=[
            [
                PDFCell(text=t, bbox=(c * 100.0, r * 20.0, (c + 1) * 100.0, (r + 1) * 20.0))
                for c, t in enumerate(row)
            ]
            for r, row in enumerate(data)
        ],
    )
    layout.table_structure = project_table(layout)
    table = render_structure(layout.table_structure)
    records = [
        dict(
            evidence_id="a" * 64,
            source_revision="b" * 64,
            physical_page=7,
            kind="paragraph",
            text="主要会计数据和财务指标",
            layout=None,
        ),
        dict(
            evidence_id="c" * 64,
            source_revision="b" * 64,
            physical_page=7,
            kind="table",
            text=table,
            layout=layout.model_dump(mode="json"),
        ),
    ]
    identity = dict(
        workspace_id="test",
        document_id="d",
        company_id="company",
        report_year=2025,
        report_type="annual",
        period_start="2025-01-01",
        period_end="2025-12-31",
        basis="PRC_GAAP",
        source_revision="b" * 64,
        content_sha256="d" * 64,
        attempt=1,
        parser_version="fast-pdf-v4;table-geometry-v2;synthetic=1",
    )
    selection = hashlib.sha256(
        json.dumps([identity], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    text = "\n".join(r["text"] for r in records)
    citation = dict(
        **identity,
        number=1,
        chunk_id="synthetic",
        physical_page=7,
        source_file="synthetic.pdf",
        text=text,
        kind="table",
        verification="exact_original_with_context",
    )
    result = dict(
        schema_version="research-answer-v1",
        selection_id=selection,
        documents=[identity],
        outcome="answered",
        content=f"2025年报《synthetic.pdf》原文：\n{text}\n[1]",
        citations=[citation],
        answer_mode="verified_excerpts",
        human_review="pending",
    )
    run = Envelope.model_validate(
        dict(
            execution_config={"test": "synthetic"},
            run_id=str(uuid.uuid4()),
            operation_id=str(uuid.uuid4()),
            workspace_id="test",
            query=query,
            document_ids=["d"],
            selection_id=selection,
            documents=[identity],
            created_at="2026-10-15T00:00:00+00:00",
            ended_at="2026-10-15T00:00:01+00:00",
            status="answered",
            result=result,
        )
    )
    return run, records


CASES = [
    ("营业收入", 2024, "元", "1,200.00", 1, 2),
    ("营业总收入", 2024, "元", "1,300.00", 2, 2),
    ("归母净利润", 2024, "元", "200.00", 3, 2),
    ("扣非净利润", 2024, "元", "160.00", 4, 2),
    ("营业收入", 2023, "元", "1,000.00", 1, 3),
    ("营业收入", 2025, "元", "1,500.00", 1, 1),
    ("归母净利润", 2023, "元", "100.00", 3, 3),
    ("扣非净利润", 2025, "元", "260.00", 4, 1),
    ("营业收入", 2024, "千元", "1,200.00", 1, 2),
    ("营业总收入", 2025, "千元", "1,600.00", 2, 1),
    ("归母净利润", 2024, "千元", "200.00", 3, 2),
    ("经营现金流量净额", 2023, "千元", "250.00", 5, 3),
]


@pytest.mark.parametrize("metric,year,unit,value,row,col", CASES)
def test_adjacent_rows_years_and_units(metric, year, unit, value, row, col):
    run, records = fixture(f"请摘录{year}年度{metric}原值及原单位，不做同比。", unit)
    before = canonical(run.model_dump())
    focus = project_focus(run, {"company": "Example"}, lambda c: records)
    f = focus["focus"]
    assert focus["status"] == "located" and (
        f["raw_value"],
        f["raw_unit"],
        f["financial_year"],
    ) == (value, unit, year)
    assert (f["row_index"], f["column_index"]) == (row, col)
    assert canonical(run.model_dump()) == before


@pytest.mark.parametrize(
    "query",
    [
        "请摘录2024年度营业收入和归母净利润原值",
        "请摘录2024年度毛利润原值",
        "请摘录营业收入原值",
        "请摘录2024年及2023年营业收入原值",
        "请摘录2022年度营业收入原值",
        "请计算2024年度营业收入同比",
        "请摘录2024年度营业收入原值，不计算同比，但计算差额",
        "请摘录2024年度营业收入原值，不计算同比吗",
        "请摘录2024年度营业收入原值，别不计算同比",
        "请摘录Other2024年度营业收入原值",
        "请将2024年度营业收入原值换算美元",
        "请摘录2024年度营业收入原值并解释增长原因",
    ],
)
def test_complex_missing_and_positive_calculation_never_claim_a_cell(query):
    run, records = fixture(query)
    value = project_focus(run, {"company": "Example"}, lambda c: records)
    assert value["status"] == "unlocated" and value["focus"] is None


@pytest.mark.parametrize(
    "fault",
    [
        "unit_missing",
        "unsupported",
        "tamper_geometry",
        "duplicate_row",
        "duplicate_table",
        "wrong_page",
        "wrong_revision",
        "wrong_snapshot",
        "old_parser",
        "non_amount",
    ],
)
def test_source_and_table_ambiguities_fail_closed(fault):
    run, records = fixture()
    if fault == "old_parser":
        data = run.model_dump()
        for d in data["documents"] + data["result"]["documents"] + data["result"]["citations"]:
            d["parser_version"] = "fast-pdf-v3"
        data["selection_id"] = data["result"]["selection_id"] = hashlib.sha256(
            json.dumps(data["documents"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        run = Envelope.model_validate(data)
    elif fault in ("wrong_page", "wrong_revision", "wrong_snapshot"):
        records[1][
            {
                "wrong_page": "physical_page",
                "wrong_revision": "source_revision",
                "wrong_snapshot": "text",
            }[fault]
        ] = {"wrong_page": 8, "wrong_revision": "f" * 64, "wrong_snapshot": "wrong"}[fault]
    else:
        layout = PDFLayout.model_validate(records[1]["layout"])
        if fault == "unit_missing":
            layout.rows[1][0].text = "营业收入"
        elif fault == "unsupported":
            layout.rows[1][1].bbox = None
        elif fault == "non_amount":
            layout.rows[1][2].text = "1,200.00%"
        elif fault == "duplicate_row":
            layout.rows[2][0].text = "营业收入（元）"
        layout.table_structure = project_table(layout, financial_page=True)
        if fault == "tamper_geometry":
            next(
                c for c in layout.table_structure.cells if c.row == 1 and c.column == 2
            ).actual_year = 2025
        records[1]["layout"] = layout.model_dump(mode="json")
        records[1]["text"] = render_structure(layout.table_structure)
        if fault == "duplicate_table":
            records.append(deepcopy(records[1]))
            records[-1]["evidence_id"] = "e" * 64
        c = run.result.citations[0]
        c.text = "\n".join(r["text"] for r in records)
        run.result.content = f"2025年报《synthetic.pdf》原文：\n{c.text}\n[1]"
        run = Envelope.model_validate(run.model_dump())
    result = project_focus(run, {"company": "Example"}, lambda c: records)
    assert result["status"] == "unlocated" and result["focus"] is None


def test_same_answer_and_citation_require_independent_run_and_query_projection():
    one, records = fixture()
    two = one.model_copy(
        update={"query": "请摘录2024年度归母净利润原值", "run_id": str(uuid.uuid4())}
    )
    a = project_focus(one, {"company": "Example"}, lambda c: records)
    b = project_focus(two, {"company": "Example"}, lambda c: records)
    assert a["answer_sha256"] == b["answer_sha256"]
    assert (
        a["query_sha256"] != b["query_sha256"] and a["projection_sha256"] != b["projection_sha256"]
    )
    assert (a["focus"]["row_index"], b["focus"]["row_index"]) == (1, 3)


@pytest.mark.parametrize(
    "q,requires",
    [
        ("不做同比", False),
        ("不要做同比", False),
        ("不做同比但计算差额", True),
        ("不要不做同比", True),
        ("不做同比吗", True),
    ],
)
def test_negative_calculation_boundary(q, requires):
    assert requires_financial_analysis(q) == requires


def test_all_d28_original_run_envelopes_still_validate_and_nonanswers_cannot_focus():
    root = Path(__file__).resolve().parents[1] / "product/d28/evidence/qa-real"
    for p in sorted(root.glob("[AR][0-9][0-9].json")):
        v = json.loads(p.read_bytes())
        raw = v["response"]
        run = Envelope.model_validate({k: raw[k] for k in Envelope.model_fields})
        assert sha(run.result.content) == v["answer_utf8_sha256"]
        if p.stem.startswith("R"):

            def no_reads(c):
                raise AssertionError("Refusals cannot inspect cells")

            assert project_focus(run, {}, no_reads)["focus"] is None
