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
        rows = data[key]
        priorities = {
            "财务数据": [
                "company_code",
                "company_name",
                "metric_key",
                "period_kind",
                "as_of_date",
                "period_start",
                "period_end",
                "raw_decimal",
                "raw_unit",
                "physical_page",
                "financial_review",
            ],
            "来源证据": [
                "company_name",
                "report_year",
                "physical_page",
                "text",
                "interpretation_review_status",
            ],
        }
        visible = priorities.get(name, rows[0])
        if name in priorities:
            order = [rows[0].index(k) for k in visible if k in rows[0]]
            order += [i for i in range(len(rows[0])) if i not in order]
            rows = [[r[i] for i in order] for r in rows]
        if name == "来源证据" and "text" in rows[0]:
            index = rows[0].index("text")
            expanded = [rows[0] + ["excerpt_part"]]
            for row in rows[1:]:
                text = str(row[index] or "")
                chunks = [text[i : i + 600] for i in range(0, len(text), 600)] or [""]
                for i, chunk in enumerate(chunks):
                    expanded.append(
                        row[:index] + [chunk] + row[index + 1 :] + [f"{i + 1}/{len(chunks)}"]
                    )
            rows = expanded
        for row in rows:
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
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.data_type = "s"
                cell.number_format = "@"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.font = Font(name="STHeiti", size=11)
        for column in ws.columns:
            field = column[0].value
            dim = ws.column_dimensions[column[0].column_letter]
            dim.width = (
                (28 if column[0].column == 1 else 95)
                if name == "概览"
                else {
                    "company_code": 12,
                    "company_name": 27,
                    "metric_key": 22,
                    "period_kind": 13,
                    "as_of_date": 15,
                    "period_start": 15,
                    "period_end": 15,
                    "raw_decimal": 25,
                    "raw_unit": 10,
                    "physical_page": 14,
                    "financial_review": 18,
                    "text": 85,
                    "report_year": 14,
                    "interpretation_review_status": 24,
                }.get(field, 28)
            )
            if name != "概览" and field not in visible:
                dim.hidden = True
                dim.outlineLevel = 1
        for r in range(2, ws.max_row + 1):
            import math

            lines = []
            for cell in ws[r]:
                dim = ws.column_dimensions[cell.column_letter]
                if dim.hidden:
                    continue
                width = max(10, dim.width - 2)
                # CJK occupies roughly two Latin character widths; explicit newlines survive.
                lines.append(
                    sum(
                        max(1, math.ceil(sum(2 if ord(c) > 255 else 1 for c in line) / width))
                        for line in str(cell.value or "").split("\n")
                    )
                )
            ws.row_dimensions[r].height = min(409, max(26, max(lines, default=1) * 15 + 8))
        ws.row_dimensions[1].height = 32
        ws.print_title_rows = "1:1"
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
    from decimal import Decimal
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    font = "STHeiti"
    payload = data["snapshot"]
    labels = {
        "revenue": "营业收入",
        "net_profit_parent": "归母净利润",
        "operating_cash_flow": "经营现金流",
        "total_assets": "总资产",
        "total_liabilities": "总负债",
    }
    topic_labels = {
        "continued": "共同延续",
        "comparison_required": "待比较",
        "insufficient": "证据不足",
        "wording_changed": "披露表述变化",
        "new_disclosure_candidate": "新增披露候选",
    }
    rules_labels = {
        "income_profit_divergence": "收入与利润方向",
        "cash_profit_divergence": "现金流与利润方向",
        "debt_asset_change": "资产负债率变化",
    }
    companies = data.get("display_companies") or {}
    refs = [e for e in data["evidence"] if e.get("document_id") and e.get("physical_page")]
    unique = {}
    for e in refs:
        unique.setdefault((e["document_id"], e.get("source_revision"), e["physical_page"]), e)
    refs = list(unique.values())

    def cut(value, count):
        text = str(value or "")
        return text if len(text) <= count else text[:count] + "…〔节选〕"

    def company(row):
        return (
            row.get("company_name")
            or companies.get(row.get("company_id"), {}).get("name")
            or "企业名称未载明"
        )

    def period(row):
        t = row.get("time") or {}
        return t.get("as_of_date") or (
            str(t.get("period_start", "")) + " 至 " + str(t.get("period_end", ""))
        )

    def authority(row):
        return (
            "已核准" if row.get("financial_review") == "local_operator_confirmed" else "候选待核对"
        )

    def source_text(items):
        lines = []
        for e in items:
            source = e.get("source_ref") or e
            saved = unique.get(
                (source.get("document_id"), source.get("source_revision"), e.get("physical_page")),
                {},
            )
            e = {**saved, **e}
            src = e.get("source_ref") or e
            cid = src.get("company_id") or e.get("company_id")
            name = (
                e.get("company_name")
                or companies.get(cid, {}).get("name")
                or "资料" + str(src.get("document_id", ""))[:6]
            )
            line = f"{name} {src.get('report_year') or e.get('report_year') or '年度未载明'}年报 p{e.get('physical_page', '—')}"
            if line not in lines:
                lines.append(line)
        return "；".join(lines[:3]) or "此快照未附具体 PDF 页码；来源限制请见末页"

    def box(slide, text, x, y, w, h, size=22, color="17324D"):
        sh = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = sh.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.04)
        tf.text = str(text)
        for p in tf.paragraphs:
            p.font.name = font
            p.font.size = Pt(size)
            p.font.color.rgb = RGBColor.from_string(color)
            p.space_after = Pt(7)
        return sh

    def slide(title, evidence=None):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = RGBColor.from_string("F7F9FC")
        box(s, title, 0.65, 0.42, 12, 0.75, 30)
        selected = refs if evidence is None else evidence
        box(s, cut(source_text(selected), 150), 0.65, 6.65, 12, 0.42, 11, "4E6174")
        box(
            s,
            f"{len(prs.slides):02d}  版本 {data['ref']['revision']} · 来源 {data['display_status']} · 金额/转录与AI解释分别保留审阅状态",
            0.65,
            7.08,
            12,
            0.25,
            10,
            "4E6174",
        )
        s.notes_slide.notes_text_frame.text = json.dumps(
            dict(
                report_ref=data["ref"],
                sources=selected,
                generated_at=data.get("generated_at"),
                display_companies=companies,
            ),
            ensure_ascii=False,
        )
        return s

    domain_titles = {
        "peer_comparison_v1": "企业财务对比",
        "annual_diff_v1": "双年经营变化",
        "checkup_v1": "财报体检",
        "research_answer_v1": "年报研究",
        "showcase_report_v2": "综合研究报告",
    }
    s = slide(domain_titles.get(data["ref"]["domain"], "已保存研究"))
    names = " / ".join(v.get("name") or "企业名称未载明" for v in companies.values())
    box(
        s,
        cut(payload.get("title") or names or payload.get("question") or "已保存研究与证据", 90),
        0.8,
        1.65,
        11.7,
        1.7,
        30,
    )
    box(s, "财务与原文来自所选版本；AI解释为已保存待审草稿。", 0.8, 3.7, 11.7, 0.9, 22)
    box(
        s,
        f"生成时间：{data.get('generated_at') or '未载明'}\n来源状态：{data['display_status']} · 本次导出不生成新模型结论",
        0.8,
        5.0,
        11.7,
        1.0,
        18,
    )

    chart_spec = data.get("chart")
    topics = payload.get("topics") or []
    rules = payload.get("rules") or (payload.get("checkup") or {}).get("rules") or []
    if chart_spec:
        points = chart_spec["points"]
        s = slide(
            labels.get(chart_spec["metric_key"], chart_spec["metric_key"])
            + ("同期对比" if chart_spec["kind"] == "bar" else "年度趋势"),
            [e for p in points for e in p.get("evidence_refs") or []],
        )
        cdata = CategoryChartData()
        cdata.categories = [
            company(p) if chart_spec["kind"] == "bar" else period(p) for p in points
        ]
        scale = Decimal("100000000") if chart_spec["unit"] == "CNY_YUAN" else Decimal(1)
        unit = "亿元人民币" if scale != 1 else chart_spec["unit"]
        cdata.add_series(
            labels.get(chart_spec["metric_key"], chart_spec["metric_key"]),
            [float(Decimal(p["normalized_decimal"]) / scale) for p in points],
        )
        chart = s.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED
            if chart_spec["kind"] == "bar"
            else XL_CHART_TYPE.LINE_MARKERS,
            Inches(0.8),
            Inches(1.65),
            Inches(11.6),
            Inches(3.7),
            cdata,
        ).chart
        chart.has_legend = False
        chart.has_title = False
        for axis in (chart.category_axis, chart.value_axis):
            axis.tick_labels.font.name = font
            axis.tick_labels.font.size = Pt(14)
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = unit
        chart.value_axis.axis_title.text_frame.paragraphs[0].font.name = font
        chart.value_axis.axis_title.text_frame.paragraphs[0].font.size = Pt(14)
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.number_format = "0.00"
        chart.plots[0].data_labels.font.size = Pt(14)
        chart.plots[0].data_labels.position = XL_LABEL_POSITION.ABOVE
        box(
            s,
            f"{period(points[0])} · {points[0]['basis']} · {points[0]['scope']} · "
            + " / ".join(dict.fromkeys(authority(p) for p in points)),
            0.8,
            1.15,
            11.6,
            0.45,
            16,
        )
        exact = [
            f"{company(p)} {period(p)}：{p['normalized_decimal']} {'元人民币' if chart_spec['unit'] == 'CNY_YUAN' else chart_spec['unit']}（{authority(p)}）"
            for p in points
        ]
        box(s, "\n".join(exact), 0.8, 5.45, 11.7, 1.0, 13 if len(points) > 3 else 16)

        s = slide("财务指标与原始期间")
        rows = data["financial"][:10]
        headers = ["企业", "指标", "期间末", "原始金额 / 单位", "状态"]
        table = s.shapes.add_table(
            len(rows) + 1, 5, Inches(0.7), Inches(1.4), Inches(12), Inches(4.8)
        ).table
        for col, width in zip(table.columns, (2.7, 1.65, 1.35, 4.3, 2.0)):
            col.width = Inches(width)
        for ri, values in enumerate(
            [headers]
            + [
                [
                    company(r),
                    labels.get(r["metric_key"], r["metric_key"]),
                    r.get("as_of_date") or r.get("period_end") or "未知",
                    str(r.get("raw_decimal") or r.get("normalized_decimal"))
                    + " "
                    + str(r.get("raw_unit") or r.get("normalized_unit")),
                    authority(r),
                ]
                for r in rows
            ]
        ):
            for ci, text in enumerate(values):
                cell = table.cell(ri, ci)
                cell.text = str(text)
                cell.margin_top = cell.margin_bottom = Inches(0.025)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string(
                    "17324D" if ri == 0 else ("FFFFFF" if ri % 2 else "EAF0F5")
                )
                for p in cell.text_frame.paragraphs:
                    p.font.name = font
                    p.font.size = Pt(13)
                    p.font.color.rgb = RGBColor.from_string("FFFFFF" if ri == 0 else "17324D")
        box(
            s,
            f"展示 {len(rows)} / {len(data['financial'])} 项；完整期间、币种、口径与逐项页码见表格导出。",
            0.8,
            6.23,
            11.6,
            0.35,
            13,
        )
        s = slide("可比范围与待核查事项")
        lines = [
            f"{labels.get(c['metric_key'], c['metric_key'])}："
            + (
                {
                    "candidate_observation": "同口径候选观察，尚未核准",
                    "confirmed_comparison": "已核准输入的比较",
                    "incomparable": "不可直接比较",
                }.get(c["state"], c["state"])
            )
            + (f"（{c['reason']}）" if c.get("reason") else "")
            for c in payload.get("comparisons", [])
        ]
        box(
            s,
            "\n".join(lines[:6])
            or "图中仅展示同公司、同口径、不同期间的已保存数值。\n缺失数据未补零。",
            0.85,
            1.6,
            11.6,
            4.6,
            23,
        )
    elif topics:
        s = slide("双年研究范围")
        left, right = payload.get("left_source") or {}, payload.get("right_source") or {}
        box(s, names or "所选企业资料", 0.8, 1.6, 11.6, 1.0, 28)
        box(
            s,
            f"{left.get('report_year') or '年份未载明'} / {right.get('report_year') or '年份未载明'} 年报\n"
            + "主题："
            + "、".join(str(t["topic"]) for t in topics[:3])
            + "\n双侧引用按保存版本展示；变化判断仍待人工审阅。",
            0.8,
            3.1,
            11.6,
            2.8,
            23,
        )
        for topic in topics[:3]:
            cited_ids = set(topic.get("ai_evidence_ids") or [])
            shown = {}
            for side in ("left", "right"):
                available = topic.get(side, {}).get("evidence_refs", [])
                cited = [r for r in available if r.get("evidence_id") in cited_ids]
                shown[side] = cited or available
            bilateral = [r for side in ("left", "right") for r in shown[side]]
            s = slide(str(topic["topic"]) + "：双年原文对照", bilateral)
            box(
                s,
                "程序标记："
                + topic_labels.get(
                    topic.get("program_label"), str(topic.get("program_label") or "未载明")
                )
                + (
                    " · AI判读："
                    + topic_labels.get(topic["ai_label"], topic["ai_label"])
                    + "（待审）"
                    if topic.get("ai_label")
                    else ""
                ),
                0.8,
                1.25,
                11.6,
                0.5,
                17,
            )
            for side, x in (("left", 0.8), ("right", 6.8)):
                items = shown[side]
                source = payload.get(side + "_source") or {}
                year = source.get("report_year") or next(
                    (r.get("source_ref", {}).get("report_year") for r in items), None
                )
                box(s, f"{year or '年份未载明'} 年报", x, 1.95, 5.6, 0.5, 24)
                text = "\n".join(r.get("text", "") for r in items)
                box(
                    s,
                    cut(" ".join(text.split()), 190)
                    if text
                    else "未取得该侧证据，不能推断业务取消。",
                    x,
                    2.65,
                    5.6,
                    3.55,
                    19,
                )
    else:
        s = slide("研究范围与数据条件")
        box(
            s,
            cut(payload.get("question") or payload.get("title") or "所选资料与保存结果", 150),
            0.8,
            1.6,
            11.6,
            1.6,
            25,
        )
        box(
            s,
            "没有满足同期间、同口径及来源条件的财务序列。\n不补造财务图；以下展示已保存观察与原文。",
            0.8,
            3.7,
            11.6,
            1.6,
            23,
        )
        s = slide("财报体检规则" if rules else "已保存研究发现")
        if rules:
            lines = []
            for r in rules[:3]:
                observation = r.get("observation")
                shown = {
                    "direction_diverges": "变化方向不同",
                    "no_direction_divergence": "未发现方向分化",
                }.get(observation, str(observation) if observation is not None else "数据不足")
                lines.append(
                    f"{rules_labels.get(r['rule_id'], r['rule_id'])}：{shown}"
                    + (
                        " 个百分点"
                        if r.get("unit") == "PERCENTAGE_POINTS" and observation is not None
                        else ""
                    )
                    + f"\n状态：{r.get('status')} · 原因：{r.get('reason') or '见所选输入'}"
                )
            box(s, "\n\n".join(lines), 0.8, 1.5, 11.6, 4.7, 22)
        else:
            findings = (
                payload.get("findings") or (payload.get("snapshot") or {}).get("findings") or []
            )
            box(
                s,
                "\n\n".join(cut(f.get("text"), 150) for f in findings[:3]) or "快照未附研究发现。",
                0.8,
                1.5,
                11.6,
                4.7,
                21,
            )
        s = slide("原文证据与转录状态")
        box(
            s,
            cut("\n".join(e.get("text") or "" for e in refs[:2]), 440)
            or "此快照未附原文；保留来源限制。",
            0.8,
            1.6,
            11.6,
            4.7,
            22,
        )

    s = slide("已保存的 AI 解释 · 待审阅")
    explanations = []
    if payload.get("interpretation"):
        explanations.append(payload["interpretation"])
    explanations.extend(
        str(t["topic"]) + "：" + str(t["explanation"]) for t in topics if t.get("explanation")
    )
    explanations.extend(
        str(e.get("text") or "") for e in payload.get("explanations", []) if e.get("text")
    )
    findings = payload.get("findings") or (payload.get("snapshot") or {}).get("findings") or []
    explanations.extend(
        f["text"] for f in findings if f.get("kind") == "model_interpretation" and f.get("text")
    )
    box(
        s,
        "\n\n".join(cut(t, 150 if len(explanations) > 1 else 450) for t in explanations[:3])
        or "该快照没有已保存的 AI 解释。\n本次导出没有调用模型或补充推断。",
        0.8,
        1.55,
        11.6,
        4.8,
        21,
    )
    s = slide("来源与后续核查")
    source_lines = [source_text([e]) for e in refs[:5]]
    limitations = [cut(x, 90) for x in payload.get("limitations", [])[:2]]
    box(
        s,
        "\n".join(source_lines + limitations) or "此快照未附具体来源；请回到研究结果核查。",
        0.8,
        1.5,
        11.6,
        4.8,
        20,
    )
    raw = io.BytesIO()
    prs.save(raw)
    raw.seek(0)
    check = Presentation(raw)
    assert 5 <= len(check.slides) <= 8
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
