"""D25 real regressions: gold is test-only, never available to parser."""

import pytest
from app.rag.parse.models import PDFCell, PDFLayout
from app.rag.parse.table_structure import project_table, render_structure

from app.rag.parse.tables import extract_table_chunks


@pytest.mark.parametrize(
    "report,page,year,amount",
    [
        ("gree-2024", 7, 2024, "189,163,654,064.64"),
        ("midea-2025", 9, 2025, "456,451,731"),
        ("gree-2025", 7, 2025, "170,447,058,533.57"),
        ("midea-2024", 9, 2024, "407,149,600"),
    ],
)
def test_d25_year_amount_column_regression(report, page, year, amount):
    chunks = extract_table_chunks(f"data/30d-foundation/{report}.pdf", page)
    table = next(c for c in chunks if amount in (c.table_md or ""))
    rows = [
        [s.strip() for s in row.strip().strip("|").split("|")]
        for row in table.table_md.splitlines()
    ]
    header = next(r for r in rows if f"{year}年" in r)
    income = next(r for r in rows if any("营业收入" in s for s in r))
    assert header.index(f"{year}年") == income.index(amount)


def grid(labels=("营业收入（元）",), values=(("-10", "0"),), headers=("2025年", "2024年")):
    rows = [
        [
            PDFCell(text=t, bbox=(i * 100, 0, (i + 1) * 100, 20))
            for i, t in enumerate(("项目", *headers))
        ]
    ]
    for r, (label, value) in enumerate(zip(labels, values), 1):
        rows.append(
            [
                PDFCell(text=t, bbox=(i * 100, r * 20, (i + 1) * 100, (r + 1) * 20))
                for i, t in enumerate((label, *value))
            ]
        )
    return PDFLayout(strategy="ruled", rows=rows)


@pytest.mark.parametrize(
    "values", [(("-10", "0"),), (("100", "100"),), (("(123)", "-0.5"),), (("1[2]", "1,000"),)]
)
def test_amounts_are_literal_and_never_control_geometry(values):
    layout = grid(values=values)
    structure = project_table(layout)
    assert structure.status == "verified"
    assert [c.text for c in structure.cells if c.row == 1 and c.actual_year] == list(values[0])
    assert [c.actual_year for c in structure.cells if c.row == 1 and c.actual_year] == [2025, 2024]
    assert all(c.raw_cells for c in structure.cells)
    assert all(value in render_structure(structure) for value in values[0])


@pytest.mark.parametrize(
    "headers", [("2025年", "2025年"), ("本期", "上期"), ("2025年", "2024/2023年")]
)
def test_ambiguous_years_are_unsupported(headers):
    structure = project_table(grid(headers=headers))
    assert structure.status == "unsupported"
    assert "unsupported" in render_structure(structure)
    assert "-10" not in render_structure(structure)


def test_geometry_cannot_merge_two_values_or_hide_unit_change():
    layout = grid(
        labels=("营业收入（元）", "营业收入（千元）"), values=(("10", "20"), ("30", "40"))
    )
    structure = project_table(layout)
    assert structure.status == "verified"
    assert "营业收入（元）" in render_structure(
        structure
    ) and "营业收入（千元）" in render_structure(structure)
    # A label spanning two amount rows would collapse distinct amounts: fail closed.
    layout.rows[1][0].bbox = (0, 20, 100, 60)
    layout.rows[2][0] = PDFCell(text=None, bbox=None)
    assert project_table(layout).status == "unsupported"


def test_geometry_overlap_and_multilevel_header_fail_closed():
    layout = grid()
    layout.rows[1][1].bbox = (90, 20, 200, 40)
    assert project_table(layout).status == "unsupported"
    layout = grid()
    layout.rows[0][1].bbox = (100, 0, 300, 20)
    layout.rows[0][2] = PDFCell(text=None, bbox=None)
    assert project_table(layout).status == "unsupported"


def test_36_visually_transcribed_summary_amount_year_unit_cells():
    import json
    from pathlib import Path
    from app.agent.metric_extraction import metric_for

    gold = json.loads(Path("product/d26/gold-summary-cells.json").read_text())
    for report in {g["report"] for g in gold["facts"]}:
        expected = [g for g in gold["facts"] if g["report"] == report]
        chunks = extract_table_chunks(
            f"data/30d-foundation/{report}.pdf", expected[0]["physical_page"]
        )
        table = next(c for c in chunks if expected[0]["raw_value"] in (c.table_md or ""))
        s = table.layout.table_structure
        assert s.status == "verified"
        for g in expected:
            label = next(c for c in s.cells if metric_for(c.text) == g["metric"])
            amount = next(
                c for c in s.cells if c.row == label.row and c.actual_year == g["actual_year"]
            )
            assert amount.text == g["raw_value"]
            assert f"（{g['raw_unit']}）" in label.text.replace(" ", "")
            assert table.page == g["physical_page"]
            assert all(table.layout.rows[r][c].bbox for r, c in amount.raw_cells)


def test_financial_text_with_no_geometry_cannot_fall_back_to_sparse_markdown():
    layout = PDFLayout(
        strategy="ruled",
        rows=[
            [PDFCell(text=t, bbox=None) for t in row]
            for row in [["项目", "2025年", "2024年"], ["营业收入（元）", "100", "100"]]
        ],
    )
    result = project_table(layout)
    assert result is not None and result.status == "unsupported"
    assert "100" not in render_structure(result)
