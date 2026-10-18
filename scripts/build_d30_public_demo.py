"""Export a finite, escaped, script-free historical reading package.

Inputs are committed D28 public-business evidence and a NEW D30 reader manifest.
No runtime DB, receipt payload, model config or PDF file is read. No server runs.
"""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
from urllib.parse import urlparse

from app.reports.markdown import render
from scripts.build_d29_c2_reviews import build, canonical, operating_target

ROOT = Path(__file__).resolve().parents[1]
BASE = "ec4d624ed4c933e0d7ccebe246fda2acb5b2855e"
METRICS = dict(revenue="营业收入", net_profit_parent="归母净利润",
               operating_cash_flow="经营活动现金流量净额")
STYLE = """body{margin:0;background:#f4f6f5;color:#172923;font:16px/1.7 system-ui,sans-serif}
header,main,footer{max-width:1120px;margin:auto;padding:24px}header{border-bottom:1px solid #cad6ce}
nav{display:flex;gap:20px;flex-wrap:wrap}a{color:#096347;text-underline-offset:4px}a:focus,summary:focus{outline:3px solid #bb7900;outline-offset:3px}
.notice{background:#e1eee8;padding:16px;border-left:4px solid #19734e}.card,section{background:white;padding:24px;margin:20px 0;border:1px solid #d7e1db;border-radius:12px}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:640px}th,td{border-bottom:1px solid #d7e1db;text-align:left;padding:12px;vertical-align:top}
details{margin:12px 0}summary{cursor:pointer;color:#096347}pre,code{overflow-wrap:anywhere;white-space:pre-wrap;font-size:14px}pre{background:#f4f6f5;padding:14px}
h1{line-height:1.3;font-size:32px}h2{font-size:23px}.value{font-size:32px;font-weight:700}.muted{color:#516259}.columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
@media(max-width:600px){header,main,footer{padding:16px}section,.card{padding:16px}h1{font-size:26px}}
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def e(value):
    return escape(str(value), quote=True)


def pre(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return "<pre>" + e(text) + "</pre>"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reader-manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    reader = json.loads(args.reader_manifest.read_text())
    reviews = build()  # Recomputes pinned source bytes and exact frozen identities.
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_inputs = {}

    def load(path):
        raw = (ROOT / path).read_bytes()
        source_inputs[path] = sha(raw)
        return json.loads(raw)

    tasks = {name: load(f"product/d28/evidence/human-followup/{name}-user-resume-completed.json")["task"]
             for name in ("midea", "gree", "comparison")}
    reports = {v: load(f"product/d28/evidence/human-followup/midea-report-v{v}-user-saved.json")["detail"]
               for v in (1, 2)}
    sources = load("product/validation/sources.json")
    source_by_sha = {s["sha256"]: s for s in sources}

    def put(name, raw):
        (out / name).write_bytes(raw if isinstance(raw, bytes) else raw.encode())

    def page(name, title, content):
        put(name, '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)} · FinDoc 历史演示</title><link rel="stylesheet" href="style.css"></head>'
            '<body><header><nav aria-label="历史演示导航"><a href="index.html">历史成果首页</a>'
            '<a href="qa-A10.html">可信问答 A10</a><a href="report-v2.html">报告 v2</a>'
            '<a href="compare.html">版本对照</a><a href="recovery.html">未知恢复说明</a></nav>'
            '<p class="notice">真实历史快照 · D28 保存结果 / D30 只读展示。'
            '本页不会调用模型，不授予当前财务资格。D30 新运行的真人验收另列 pending。</p></header>'
            f'<main><h1>{e(title)}</h1>{content}</main><footer>'
            '单人求职作品 · 原生语义 pending / 经营因果 false。公开 PDF 由发行人或交易所提供；'
            '链接在新标签打开，物理页定位由 PDF 阅读器决定。<br>'
            '<a href="release-public-manifest.json">文件白名单与来源 SHA</a> · '
            '<a href="sources.html">四报来源及使用范围</a></footer></body></html>')

    def source_link(c):
        s = source_by_sha[c["content_sha256"]]
        assert urlparse(s["url"]).hostname in {"www.midea.com.cn", "static.cninfo.com.cn", "disc.static.szse.cn"}
        page_no = c["physical_page"]
        return (f'<a href="{e(s["url"])}#page={page_no}" target="_blank" rel="noreferrer">'
                f'原 PDF · {e(s["id"])} · 物理 {page_no} 页 ↗</a>'
                f'<details><summary>冻结来源身份</summary>{pre({k:c[k] for k in ("document_id","source_revision","content_sha256","parser_version")})}</details>')

    def review_html(record):
        # Public derivative, not a falsely byte-identical replacement for private originals.
        name = "review-" + record["record_id"] + ".json"
        public = dict(copy_kind="reviewed_projection", historical_only=True,
                      original_access="private repository; original links may require access",
                      record=record)
        put(name, json.dumps(public, ensure_ascii=False, indent=2) + "\n")
        label = {"pass":"本题通过", "approved_with_rewrite":"同意改写", "approved_as_written":"接受原句"}.get(record["decision"], record["decision"])
        return ('<aside class="notice"><strong>外部人工审阅 · ' + e(label) + '</strong><p>'
                + e(record.get("rewrite") or record["opinion"]) + '</p><details><summary>审阅原话与适用范围</summary><p>'
                + e(record["original_words"]) + '</p><p>' + e(record["scope"]) + '</p><p>'
                + e(record["recorded_at"]) + '</p><p>原始仓库为私有，原证据需访问权限；此处提供经筛选的公开证据摘录，包含原文件 SHA 和精确对象身份。</p>'
                + f'<a href="{name}">本地公开证据摘录</a></details></aside>')

    def operating(task):
        content = task["final_research_content"]
        result = '<section><h2>业务原文与待审线索</h2><p>未执行逐指标经营变化原因检索。模型原句与外部人工意见分别保留；原生语义 pending，经营因果 false。</p>'
        target_hash = sha(canonical(operating_target(task)).encode())
        records = [r for r in reviews["records"] if r["kind"] == "operating" and r["target_sha256"] == target_hash]
        for i, item in enumerate(content["model_interpretations"]):
            result += f'<article id="interpretation-{i+1}"><h3>模型原句 {i+1}</h3><p>{e(item["text"])}</p>'
            record = next((r for r in records if r["statement_index"] == i), None)
            result += review_html(record) if record else '<p>外部人工审阅：无本项适用记录 · 待审</p>'
            result += '<p>参考原文 ' + '、'.join(f'<a href="#cite-{n}">[{n}]</a>' for n in item["citations"]) + '</p></article>'
        result += '<details><summary>经营原文与完整引用</summary>'
        for d in content["operating_descriptions"]:
            c = d["citation"]
            result += f'<article id="cite-{c["number"]}"><h3>原文 [{c["number"]}] · {e(c["report_year"])} 年报</h3>{source_link(c)}{pre(d["text"])}</article>'
        return result + '</details><details><summary>未解决问题和限制</summary>' + pre(content["unresolved_questions"] + content["limitations"]) + '</details></section>'

    names = dict(midea="美的 2024→2025", gree="格力 2024→2025", comparison="美的 A / 格力 B · 2025 同期")
    for name, task in tasks.items():
        assert task["final_research_content"]["test_mode"] is None
        assert task["final_research_content"]["verified_operating_attribution"] is False
        analyses = task["snapshot"]["analysis_results"]
        rows = analyses[0]["rows"] if name == "comparison" else analyses
        cards = '<div class="columns">'
        for a in rows:
            change = a.get("absolute_change", a.get("difference"))
            percent = a.get("percentage_change", a.get("relative_difference_percent"))
            cards += f'<div class="card"><h2>{e(METRICS[a["metric_key"]])}</h2><p class="value">{e(percent)}%</p><p>差额 {e(change)} 元</p></div>'
        cards += '</div>'
        page(f'task-{name}.html', names[name], '<p>历史 Task ' + e(task["task_id"]) + ' / revision ' + e(task["revision"])
             + ' · D28 本人财务核对后完成；本次仅阅读。</p>' + cards
             + '<details><summary>完整财务事实、原值和确定性分析</summary>' + pre(analyses) + '</details>' + operating(task))

    qa_links = ''
    for item in reader["runs"]:
        case, run, projection = item["case"], item["run"], item["projection"]
        original = load(f"product/d28/evidence/qa-real/{case}.json")["response"]
        assert run == original and projection["run_id"] == run["run_id"]
        record = next(r for r in reviews["records"] if r.get("run_id") == run["run_id"])
        assert record["target_sha256"] == run["integrity_sha256"]
        body = '<p>' + e(run["query"]) + '</p><p>历史 Run ' + e(run["run_id"]) + ' · ' + e(run["status"]) + '</p>'
        f = projection["focus"]
        if f:
            body += '<section aria-label="本题可信焦点"><h2>本题可信焦点 · ' + e(f["row_label"]) + '</h2><p class="value">' + e(f["raw_value"]) + ' ' + e(f["raw_unit"]) + '</p><p>' + e(f["financial_year"]) + ' 财务年度 · D30 正式 C1 算法重新校验冻结原表，仅供历史阅读。</p>' + source_link(f) + '<details><summary>核对原始表格行、年度列和投影身份</summary>' + pre(projection) + '</details></section>'
        else:
            body += '<p>本题无可信数值焦点：' + e(projection["reason"]) + '</p>'
        body += '<section><h2>完整已保存回答</h2>' + pre(run["result"]["content"]) + '<p>原生语义：' + e(run["result"]["human_review"]) + '</p></section>' + review_html(record)
        for c in run["result"]["citations"]:
            body += '<details><summary>完整原文与引用 [' + e(c["number"]) + ']</summary>' + source_link(c) + pre(c["text"]) + '</details>'
        if run["status"] == "refused":
            body += pre({k:v for k,v in run["result"].items() if k != "content"})
        page(f'qa-{case}.html', '历史问答 ' + case, body)
        qa_links += f'<li><a href="qa-{case}.html">{e(case)} · {e(run["query"])}</a></li>'

    for v, detail in reports.items():
        report, draft = detail["report"], detail["report"]["trusted_snapshot"]
        raw = render(report)
        expected = {1:"28ddda7dc495e3396a387ff966d9c56a99679084de8841d9eb57d940fd61b9d0",2:"007405bac67158f9eeea1e3ee1405c72b00262d15bc6b153a0a94847f8fbc80a"}[v]
        assert sha(raw) == expected
        put(f'report-v{v}.md', raw)
        body = f'<nav><a href="report-v1.html">读取 v1</a><a href="report-v2.html">读取 v2</a><a href="compare.html">版本对照</a><a href="report-v{v}.md" download>精确下载历史 v{v} Markdown</a></nav><p>报告 {e(report["report_id"])} / v{v} · 原 renderer trusted-markdown-v1</p><p>下载 SHA256 <code>{expected}</code></p>'
        body += '<section><h2>执行摘要</h2>' + ''.join('<p>'+e(s)+'</p>' for s in draft["executive_summary"]) + '</section><section><h2>用户编辑内容 · 待人工语义审阅</h2>' + pre(report["editor_revision"]) + '</section>'
        for title,key in [('财务变化','financial_analysis'),('已确认财务事实','financial_facts'),('完整证据附录','evidence_appendix')]:
            body += '<details><summary>' + title + '</summary>' + pre(draft[key]) + '</details>'
        body += operating(tasks["midea"])
        page(f'report-v{v}.html', report["editor_revision"]["title"] or draft["title"], body)

    # Each saved draft has its own generation timestamp. The frozen business
    # fields (including content hashes, sources and amounts) must be identical.
    snapshots = [reports[v]['report']['trusted_snapshot'] for v in (1, 2)]
    assert {k:v for k,v in snapshots[0].items() if k != 'generated_at'} == {
        k:v for k,v in snapshots[1].items() if k != 'generated_at'}
    a, b = [reports[v]["report"]["editor_revision"] for v in (1,2)]
    page('compare.html', '报告 v1 / v2 版本对照', '<p>保存版本追加；原财务与冻结研究内容保持不变。用户结论单独待审。</p><div class="columns"><section><h2>v1 用户编辑</h2>'+pre(a)+'</section><section><h2>v2 用户编辑</h2>'+pre(b)+'</section></div><nav><a href="report-v1.html">读取 v1 和指定下载</a><a href="report-v2.html">读取 v2 和指定下载</a></nav>')
    page('recovery.html', '未知恢复说明 · 历史协议', '<section><h2>停止等待后先查询原 operation</h2><p>停止本页等待不等于取消后台。记录原 operation，GET 查证同 Run/Task/报告；不得自动重发 POST 或模型请求。本只读包没有恢复执行接口。</p><p>D28 真实未知恢复与 D29 A/B/S6 工程恢复证据保留在私有仓库；此页只解释协议，不伪装本次执行了真实未知模型场景。</p></section>')
    page('sources.html', '公开 PDF 来源与展示范围', '<p>四报仅链接到发行人/交易所公开原件，不在此包重分发完整 PDF。SHA 是 D30 下载核对的固定版本；外部网站未来变动、可用性及阅读器页定位不能由本包保证。</p>' + ''.join('<section><h2>'+e(s['id'])+'</h2><a target="_blank" rel="noreferrer" href="'+e(s['url'])+'">打开官方原件</a><p>SHA256 '+e(s['sha256'])+'</p></section>' for s in sources))
    page('index.html', 'FinDoc Analyst · 从年报到可追溯研究', '<p>三项财务变化、可信原文、独立人工意见与不可变版本报告。</p><div class="columns">'+''.join('<section><h2>'+e(title)+'</h2><a href="task-'+name+'.html">读取真实历史成果</a></section>' for name,title in names.items())+'</div><details><summary>十八道真实历史问答与拒答</summary><ul>'+qa_links+'</ul></details><p>本包不接受上传、财务接受、保存、撤销、resume 或新提问。真人验收、通用准确率、陌生用户易用性与生产部署均有独立边界。</p>')
    put('style.css', STYLE)
    manifest = dict(schema="d30-public-files-v1", baseline=BASE, snapshot_origin="D28 real historical evidence",
                    native_eligibility_imported=False, model_credentials=False, executable_scripts=False,
                    full_pdfs_redistributed=False, source_inputs=source_inputs,
                    reader_manifest_sha256=sha(args.reader_manifest.read_bytes()),
                    files={f.name:dict(sha256=sha(f.read_bytes()), bytes=f.stat().st_size)
                           for f in sorted(out.iterdir())})
    put('release-public-manifest.json', json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(files=len(manifest['files'])+1, output=str(out))))


if __name__ == '__main__':
    main()
