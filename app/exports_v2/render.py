"""Local renderer CLI. User-authorized openpyxl/python-pptx; no network or models."""

import csv
import io
import json
from pathlib import Path
import re
import sys


def xlsx(data):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, key in [
        ("概览", "overview_matrix"),
        ("财务数据", "financial_matrix"),
        ("来源证据", "evidence_matrix"),
    ]:
        ws = wb.create_sheet(name)
        for row in data[key]:
            if any(len(str(v)) > 32000 for v in row):
                raise ValueError("workbook_cell_text_limit")
            ws.append(
                [
                    re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", lambda m: "\\x%02x" % ord(m[0]), str(v))
                    for v in row
                ]
            )
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(name="STHeiti", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17324D")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.data_type = "s"
                cell.number_format = "@"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.font = Font(name="STHeiti", size=11)
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = (
                32 if name != "概览" else (28 if column[0].column == 1 else 95)
            )
        for r in range(2, ws.max_row + 1):
            ws.row_dimensions[r].height = 54
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def csv_bytes(data):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    rows = (
        data["financial_matrix"] if len(data["financial_matrix"]) > 1 else data["evidence_matrix"]
    )
    decimal_columns = {
        i
        for i, k in enumerate(rows[0])
        if k in ("raw_decimal", "normalized_decimal", "value_decimal")
    }
    writer.writerow(rows[0])
    for row in rows[1:]:
        writer.writerow(
            [
                "'" + str(v)
                if i in decimal_columns and v
                else ("'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v)
                for i, v in enumerate(row)
            ]
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def pptx(data):
    from collections import Counter
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    font = "STHeiti"

    def box(slide, text, x, y, w, h, size=22, color="17324D"):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = shape.text_frame
        tf.word_wrap = True
        # Bound visible excerpt length; complete text remains in CSV/XLSX.
        tf.text = str(text)
        for para in tf.paragraphs:
            para.font.name = font
            para.font.size = Pt(size)
            para.font.color.rgb = RGBColor.from_string(color)
            para.space_after = Pt(10)
        return shape

    def slide(title):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = RGBColor.from_string("F7F9FC")
        box(s, title, 0.65, 0.45, 12, 0.8, 30)
        box(
            s,
            f"{len(prs.slides):02d}  |  {data['ref']['domain']}  ·  revision {data['ref']['revision']}  |  来源 {data['display_status']}",
            0.65,
            6.95,
            12,
            0.3,
            11,
        )
        s.notes_slide.notes_text_frame.text = (
            "固定快照："
            + json.dumps(data["ref"], ensure_ascii=False)
            + "\n展示状态："
            + data["display_status"]
        )
        return s

    title = data["snapshot"].get("title", "已保存研究与证据")
    s = slide("研究快照与证据")
    box(s, str(title)[:80], 0.8, 1.8, 11.6, 1.4, 32)
    box(s, "已保存版本导出 · AI解释与财务候选均保留审阅状态", 0.8, 4, 11.6, 0.8, 22)
    box(
        s,
        "历史来源" if data["display_status"] != "current" else "来源在导出时可核验",
        0.8,
        5.3,
        11.6,
        0.7,
        20,
    )
    s = slide("研究范围与版本")
    lines = [
        "Domain: " + data["ref"]["domain"],
        "ID: " + data["ref"]["id"],
        "Revision: " + str(data["ref"]["revision"]),
        "Payload SHA256:",
        data["ref"]["payload_sha256"][:32],
        data["ref"]["payload_sha256"][32:],
        "当前来源状态：" + data["display_status"],
    ]
    box(s, "\n".join(lines), 0.8, 1.5, 11.6, 4.9, 21)
    s = slide("已保存引用的页码分布")
    refs = [e for e in data["evidence"] if e.get("physical_page") is not None]
    counts = Counter(
        (
            str(e.get("document_id") or (e.get("source_ref") or {}).get("document_id") or "source"),
            str(e["physical_page"]),
        )
        for e in refs
    )
    if counts:
        chartdata = CategoryChartData()
        pairs = counts.most_common(8)
        chartdata.categories = [f"来源{i + 1} · p{p[0][1]}" for i, p in enumerate(pairs)]
        s.notes_slide.notes_text_frame.text += "\n图表来源映射：" + json.dumps(
            pairs, ensure_ascii=False
        )
        chartdata.add_series("引用条目数", [p[1] for p in pairs])
        chart = s.shapes.add_chart(
            XL_CHART_TYPE.BAR_CLUSTERED,
            Inches(0.9),
            Inches(1.5),
            Inches(11.4),
            Inches(4.5),
            chartdata,
        ).chart
        chart.has_legend = False
        for axis in (chart.category_axis, chart.value_axis):
            axis.tick_labels.font.name = font
            axis.tick_labels.font.size = Pt(14)
        box(
            s,
            "统计固定快照引用数量，不表示财务表现或证据相关性评分。最多显示8组。",
            0.9,
            6.15,
            11.4,
            0.5,
            15,
        )
    else:
        box(s, "快照未提供可统计页码；没有补造财务趋势或引用。", 0.9, 2.2, 11.4, 2, 24)
    s = slide("原文摘录与转录状态")
    text = refs[0]["text"] if refs else "快照无带来源页码的原文摘录。"
    excerpt = text[:240] + ("…〔节选，完整原文见表格导出〕" if len(text) > 240 else "")
    box(s, excerpt, 0.9, 1.6, 11.4, 3.9, 23)
    box(s, "来源引用保持原快照；OCR转录未经人工核对，不能代替财务确认。", 0.9, 5.9, 11.4, 0.7, 17)
    s = slide("AI解释与审阅状态")
    interpretation = data["snapshot"].get("interpretation")
    if not interpretation:
        findings = (data["snapshot"].get("snapshot") or {}).get("findings", [])
        interpretation = "\n".join(
            f["text"] for f in findings if f.get("kind") == "model_interpretation"
        )
    text = interpretation or "原快照未生成AI解释。本次导出没有调用模型或补充推断。"
    box(s, text[:260] + ("…〔节选〕" if len(text) > 260 else ""), 0.9, 1.6, 11.4, 4.1, 23)
    box(
        s,
        "AI解释：待审阅；不构成核准财务结论。" if interpretation else "原快照未生成额外AI解释。",
        0.9,
        6,
        11.4,
        0.6,
        18,
    )
    s = slide("来源、限制与后续核查")
    limitations = data["snapshot"].get("limitations", [])
    source_lines = [
        f"{e.get('document_id') or (e.get('source_ref') or {}).get('document_id') or 'document'} · 物理页 {e.get('physical_page', '未知')}"
        for e in refs[:4]
    ]
    lines = (
        source_lines
        + [str(x)[:100] for x in limitations[:3]]
        + [
            "金额以表格中原始Decimal文本为准；不将缺失值补零。",
            "source stale/unavailable时，本文件为历史快照。",
        ]
    )
    box(s, "\n".join(lines), 0.9, 1.5, 11.4, 5.1, 20)
    raw = io.BytesIO()
    prs.save(raw)
    # Reopen the actual archive and bound every text shape to the slide canvas.
    raw.seek(0)
    check = Presentation(raw)
    assert len(check.slides) == 6
    for sl in check.slides:
        for sh in sl.shapes:
            assert (
                sh.left >= 0
                and sh.top >= 0
                and sh.left + sh.width <= check.slide_width + 100
                and sh.top + sh.height <= check.slide_height + 100
            )
    return raw.getvalue()


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[2]).read_text())
    output = Path(sys.argv[3])
    output.write_bytes({"xlsx": xlsx, "csv": csv_bytes, "pptx": pptx}[sys.argv[1]](data))
    output.chmod(0o600)
