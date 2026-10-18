"""UTF-8 Markdown from the immutable revision, with inert untrusted text and full audit."""

import json
import re
import unicodedata
from typing import Any
from urllib.parse import quote, urlencode
from app.reports.builder import LABELS
from app.research.models import canonical, sha

RENDERER_VERSION = "trusted-markdown-v1"


def text(value: Any) -> str:
    # Escape HTML, autolinks, images, Markdown syntax and table delimiters. Preserve Chinese.
    raw = str(value).replace("\r\n", "\n").replace("\r", "\n")
    raw = "".join(c for c in raw if c in "\n\t" or unicodedata.category(c) != "Cc")
    raw = raw.replace("&", "&amp;")
    return re.sub(r"([\\`*_{}\[\]()<>#!|~+\-.=])", r"\\\1", raw).replace("\n", "<br>")


def json_block(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    # Upstream/user text may contain fences; choose one longer than any embedded run.
    fence = "`" * max(3, max((len(m) + 1 for m in re.findall(r"`+", raw)), default=3))
    return f"{fence}json\n{raw}\n{fence}\n"


def filename(value: dict[str, Any]) -> str:
    title = value["editor_revision"]["title"] or value["trusted_snapshot"]["title"]
    stem = "".join(c for c in unicodedata.normalize("NFKC", title) if c.isalnum() or c in "-_ ")
    stem = stem.strip()[:50] or "研究报告"
    return f"FinDoc-{stem}-{value['report_id']}-v{value['revision']}.md"


def pdf_link(item: dict[str, Any]) -> str:
    # Only application-generated version-pinned relative URLs become active links.
    query = urlencode(
        {"company_id": item["company_id"], "source_revision": item["source_revision"]}
    )
    return f"/api/documents/{quote(item['document_id'], safe='')}/file?{query}#page={item['physical_page']}"


def render(value: dict[str, Any]) -> bytes:
    s, e = value["trusted_snapshot"], value["editor_revision"]
    out = [
        f"# {text(e['title'] or s['title'])}",
        f"已保存报告 · {value['report_id']} · 明确版本 v{value['revision']} · 父版本 {value['parent_revision'] or '无'}",
        f"保存时间：{text(value['created_at'])}；原快照生成时间：{text(s['generated_at'])}",
        f"导出合同：{RENDERER_VERSION}；payload SHA-256：{sha(canonical(value))}",
        "导出时已重新核验 D6 原 PDF 字节与身份、D10 完整接受事实组和 D21 冻结研究。资格仅代表本次检查；后续变化需再次核验。",
        "人工语义审阅：pending；经营因果归因未验证。引用存在不能证明经营因果。",
    ]
    if s["watermark"]:
        out += [f"> **{text(s['watermark'])}**", "仅供隔离测试；模拟接受不具备正式可信报告资格。"]
    else:
        out += ["财务接受类型：local_operator；当前发布资格通过，人工语义审阅仍待完成。"]
    if e["title"]:
        out += [
            "标题来源：user_edit / pending_semantic_review / user_assertions_unverified。",
            f"原系统标题：{text(s['title'])}",
        ]
    out += [
        "## 研究问题与范围",
        text(s["research_question"]),
        f"{text(s['side_labels']['first'])}；{text(s['side_labels']['second'])}。全年 / CNY 元 / 合并口径 / PRC_GAAP。",
        f"父研究：{s['task_id']} / revision {s['task_revision']}；模板：{text(s['report_type'])}；方向：{text(s['research_scope']['direction'])}",
        json_block(s["research_scope"]),
        "## 执行摘要",
    ]
    out += [f"- {text(item)}" for item in s["executive_summary"]]
    out += [
        "## 六项财务事实",
        "原值、原单位和规范金额分别保留；规范金额单位为 CNY 元。",
    ]
    table = [
        "| 企业 / 期间 / 侧 | 指标 | 原值 | 原单位 | 规范 CNY 元 | 披露版本 | PDF 物理页 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in s["financial_facts"]:
        table += [
            "| "
            + " | ".join(
                text(x)
                for x in (
                    f"{f['company_name']} / {f['company_id']} / {f['period']} / {s['side_labels'][f['side']]}",
                    LABELS[f["metric_key"]],
                    f["raw_value"],
                    f["raw_unit"],
                    f["value_cny_yuan"],
                    f["disclosure_version"],
                    f["physical_page"],
                )
            )
            + " |"
        ]
    out += ["\n".join(table)]
    for f in s["financial_facts"]:
        out += [
            f"### 财务证据：{text(LABELS[f['metric_key']])} / {text(s['side_labels'][f['side']])}",
            f"[原 PDF · 物理 {f['physical_page']} 页]({pdf_link(f)})",
            json_block(f),
        ]
    out += ["## 三项确定性分析", "仅引用已保存计算结果；本次导出没有重新计算。"]
    for a in s["financial_analysis"]:
        comparison = a["direction"] == "B_minus_A"
        pct = (
            f"{a['percentage_change']}%"
            if a["percentage_change"] is not None
            else f"未定义（{a['percentage_reason']}）"
        )
        out += [
            f"### {text(LABELS[a['metric_key']])}",
            f"{'B−A 差额' if comparison else '本期−上期差额'}：{text(a['absolute_change'])} CNY 元；{'以 A 为基准的相对差异' if comparison else '同比'}：{text(pct)}。",
            f"差额公式：{text(a['absolute_formula_id'])} / {text(a['absolute_expression'])}",
            f"百分比公式：{text(a['percentage_formula_id'])} / {text(a['percentage_expression'])}",
            "操作数事实、公式与限制：",
            json_block(a),
        ]
    out += [
        "## 经营年报原文与完整引用",
        "原文匹配已核验；人工语义审阅：pending。以下链接相对于 FinDoc 服务根地址；离线阅读时需在原服务打开，原 PDF 未嵌入文件。",
    ]
    for d in s["operating_information"]:
        c = d["citation"]
        out += [
            f"### 引用 [{c['number']}] · {text(c['company_id'])} · {c['report_year']} 年报 · 物理 {c['physical_page']} 页",
            text(d["text"]),
            f"[查看版本固定的原 PDF]({pdf_link(c)})",
            "完整来源（含文件、期间、披露来源版本、SHA、parser、chunk 和物理页）：",
            json_block(c),
        ]
    out += [
        "## 模型解释（人工语义待审）",
        "pending_semantic_review；verified_operating_attribution=false；以下解释不构成已验证经营因果。",
    ]
    for m in s["model_interpretations"]:
        out += [
            text(m["text"]),
            f"引用编号：{', '.join(str(n) for n in m['citations'])}",
            json_block(m),
        ]
    out += ["## 未解决问题"]
    out += [f"- {text(q)}" for q in s["unresolved_questions"]] or ["无新增问题；人工审阅仍待完成。"]
    out += ["## 风险与限制"]
    out += [
        f"- {text(limit)}" for limit in s["limitations"] if not limit.startswith("草稿尚未保存")
    ]
    out += [
        "外层 persisted=true 表示本版本已保存。附录 trusted_snapshot.persisted=false 和“草稿尚未保存”是 D22 生成时的生命周期审计记录。",
        "## 用户自行编辑的结论（未验证）",
        "origin=user_edit；pending_semantic_review；user_assertions_unverified；verified_operating_attribution=false。",
    ]
    out += [f"- {text(c)}" for c in e["conclusions"]] or ["未提供用户结论。"]
    out += [
        "## 证据与审计附录",
        "完整不可变保存版本如下，包含所有原始证据、字段级核验、来源与接受身份、公式、检索与模型审计、用户编辑及生成时生命周期状态。",
        json_block(value),
    ]
    return ("\n\n".join(out) + "\n").encode("utf-8")
