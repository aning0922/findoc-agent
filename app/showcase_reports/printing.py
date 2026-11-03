"""Controlled, same-origin HTML with no model execution or remote assets."""

from html import escape
from urllib.parse import quote


def render_print(report):
    def e(value):
        return escape(str(value), quote=True)

    def status(value):
        return {
            "current": "当前有效",
            "stale": "来源已变化",
            "unavailable": "无法复验",
            "unreviewed": "待人工审核",
            "ocr_transcription_unreviewed": "OCR 转录待对照原图",
        }.get(value, "详见审阅记录")

    snapshot = report["snapshot"]
    origin = {"live": "真实运行快照", "seed": "预置演示资料", "fake": "模拟数据 / 非真实 LLM 结果"}
    labels = {
        "confirmed_financial": "财务已核准引用",
        "sourced_excerpt": "原文引用",
        "model_interpretation": "AI 待审核解释",
        "unresolved_question": "待解决问题",
    }
    findings = snapshot["findings"]

    def card(f):
        refs = []
        for ref in f["evidence_refs"]:
            doc, page = ref.get("document_id"), ref.get("physical_page")
            revision = ref.get("source_revision")
            if (
                isinstance(doc, str)
                and type(page) is int
                and page > 0
                and isinstance(revision, str)
            ):
                href = (
                    "/api/documents/"
                    + quote(doc, safe="")
                    + "/file?source_revision="
                    + quote(revision, safe="")
                    + "#page="
                    + str(page)
                )
                refs.append('<a href="' + e(href) + '">原 PDF · 物理第 ' + str(page) + " 页</a>")
        return (
            "<article><strong>"
            + e(labels[f["kind"]])
            + ('</strong><p class="excerpt">' if f["kind"] == "sourced_excerpt" else "</strong><p>")
            + e(f["text"])
            + "</p><small>"
            + e(origin[f["data_origin"]])
            + " · 保存时来源 "
            + e(status(f["source_status"]))
            + " · 转录审阅 "
            + e(status(f["transcription_review_status"]))
            + " · 解释审阅 "
            + e(status(f["interpretation_review_status"]))
            + (" · 含待核实数字，未构成已核准金额" if f.get("numeric_claim_status") == "numeric_claim_unverified" else "")
            + "</small><p>"
            + " · ".join(refs)
            + "</p></article>"
        )

    sections = ""
    for title, kind in [
        ("财务已核准数据", "confirmed_financial"),
        ("经营解释与风险", "model_interpretation"),
        ("原文引用", "sourced_excerpt"),
        ("待解决问题", "unresolved_question"),
    ]:
        rows = [card(f) for f in findings if f["kind"] == kind]
        sections += (
            "<section><h2>"
            + title
            + "</h2>"
            + ("".join(rows) if rows else '<p class="gap">当前未覆盖；没有可展示的已验证结果。</p>')
            + "</section>"
        )
    return (
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>研究报告</title>
<style>
@page{size:A4;margin:18mm 17mm 20mm}*{box-sizing:border-box}body{font-family:"PingFang SC","Noto Sans CJK SC",sans-serif;color:#172a3b;font-size:11pt;line-height:1.7;margin:0}main{max-width:180mm;margin:auto}header{border-top:6px solid #167a73;padding:18px 0 25px}h1{font-size:27pt;line-height:1.3}h2{font-size:16pt;border-bottom:1px solid #ccd8df;padding-bottom:6px;break-after:avoid}article{border-left:3px solid #b6d5cf;padding:9px 16px;margin:12px 0;overflow-wrap:anywhere}p{white-space:pre-wrap;overflow-wrap:anywhere}p.excerpt{white-space:normal;font-size:10pt}small,.muted{color:#526575}a{color:#126860;overflow-wrap:anywhere}.banner{padding:12px;background:#fff0cb;border:1px solid #b88a1e;font-weight:bold}.gap{color:#657080}section{margin-top:24px}button{padding:10px;margin:12px}footer{border-top:1px solid #bbcbd5;margin-top:30px;font-size:9pt}@media print{button{display:none}main{max-width:none}.banner{print-color-adjust:exact}section{break-inside:auto}article{break-inside:auto}h1,h2,strong{break-after:avoid}p{orphans:3;widows:3}}
</style><button onclick="window.print()">打印/保存PDF</button><main>"""
        + '<div class="banner">'
        + e(origin[snapshot["data_origin"]])
        + "</div><header><p>企业研究报告 · 版本 "
        + str(report["revision"])
        + "</p><h1>"
        + e(report["title"])
        + "</h1><p>"
        + e(snapshot["company_name"])
        + " ｜ "
        + e(snapshot["period_label"])
        + "</p><small>"
        + e(report["created_at"])
        + '</small></header><p class="banner">历史快照 · 当前来源状态：'
        + e(status(report.get("current_source_status", "unavailable")))
        + "</p><section><h2>重要发现摘要</h2>"
        + "".join(
            "<p>"
            + e(labels[f["kind"]])
            + "："
            + e(f["text"][:160] + ("……（详见下文）" if len(f["text"]) > 160 else ""))
            + "</p>"
            for f in ([f for f in findings if f["kind"] in ("model_interpretation", "confirmed_financial", "unresolved_question")] or findings)[:5]
        )
        + "</section>"
        + sections
        + "<section><h2>用户备注</h2><p>"
        + e(report["notes"] or "无")
        + '</p><p class="muted">备注属于用户解释，不构成财务确认。</p></section><section><h2>方法与限制</h2><p>保存已验证研究快照；AI 解释保持待审核。没有财务回执时不生成已核准金额或图表。原文页链接需要同源服务运行及有效访问权限，离线 PDF 无法保证可访问。</p>'
        + "".join("<p>" + e(x) + "</p>" for x in snapshot["limitations"])
        + "</section><footer>研究材料仅供资料核查。版本只读；打印对话框打开不代表文件已下载。</footer></main></html>"
    )
