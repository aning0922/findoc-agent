"""Execute the fixed real-PDF 12-answer / 6-refusal set with the existing BGE/Milvus/LLM."""

import asyncio
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import sys
import time
from dotenv import dotenv_values
import pymupdf

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.api.runtime_factory import create_runtime_app  # noqa: E402

for key, value in dotenv_values(root.parent / "findoc-rag/.env").items():
    if value is not None:
        os.environ.setdefault(key, value)
index = json.loads((root / "product/validation/d16-real-index.json").read_text())
ids = {r["report_id"]: r["document_id"] for r in index["reports"]}
originals = {r["id"]: r for r in json.loads((root / "product/validation/sources.json").read_text())}
benchmarks = json.loads((root / "product/validation/manual-benchmark.json").read_text())["facts"]
questions = []
for name in ["midea-2024", "midea-2025", "gree-2024", "gree-2025"]:
    questions.append(
        dict(
            id=f"finance-{name}",
            selected=[name],
            expected="answered",
            question="请定位主要会计数据和财务指标表，摘录包含营业收入、归属于上市公司股东的净利润、经营活动产生的现金流量净额的原文及年份、单位。不计算、不改写数字；注意营业收入与营业总收入、归母净利润与扣非利润的区别。",
            expected_basis="原PDF主要会计数据表；必须保留各年份表头、原单位和指标全称，不混同相似指标。",
        )
    )
    questions.append(
        dict(
            id=f"business-{name}",
            selected=[name],
            expected="answered",
            question="这份年报怎样描述公司的主要业务和主要产品？请提供直接相关的原文。",
            expected_basis="管理层讨论与分析/主营业务；原文必须属于所选公司的该份报告。",
        )
    )
questions.extend(
    [
        dict(
            id="midea-cross-year",
            selected=["midea-2024", "midea-2025"],
            expected="answered",
            question="请分别摘录美的2024和2025两份年报描述主营业务或核心业务的原文，不推断变化原因。",
            expected_basis="两期美的报告各自主营业务原文，不用一份替代两期。",
        ),
        dict(
            id="gree-cross-year",
            selected=["gree-2024", "gree-2025"],
            expected="answered",
            question="请分别摘录格力2024和2025两份年报描述主营业务或主要产品的原文。",
            expected_basis="两期格力报告各自业务原文。",
        ),
        dict(
            id="cross-company",
            selected=["midea-2025", "gree-2025"],
            expected="answered",
            question="请分别摘录美的与格力2025年报的主营业务说明，不计算财务指标。",
            expected_basis="两家企业各自2025报告，不能交换公司归属。",
        ),
        dict(
            id="four-report-identity",
            selected=list(ids),
            expected="answered",
            question="请分别摘录四份年报公司简介中公司中文名称、股票简称或股票代码的原文。",
            expected_basis="四报告各自公司简介，股票代码与企业对应。",
        ),
        dict(
            id="unselected-company",
            selected=["midea-2025"],
            expected="refused",
            question="只依据所选资料，格力电器2025年的归母净利润是多少？",
            expected_basis="未选择格力报告，不得引用或从常识补充。",
        ),
        dict(
            id="unselected-year",
            selected=["gree-2024"],
            expected="refused",
            question="格力2025年全年营业收入是多少？",
            expected_basis="2024年报不披露2025全年实际值。",
        ),
        dict(
            id="forecast",
            selected=["midea-2025"],
            expected="refused",
            question="美的2028年的实际营业收入是多少？",
            expected_basis="未来未披露实际值。",
        ),
        dict(
            id="market-price",
            selected=list(ids),
            expected="refused",
            question="2026年10月10日美的和格力的实时股价各是多少？",
            expected_basis="年报不提供指定日实时行情。",
        ),
        dict(
            id="invented-cause",
            selected=["gree-2025"],
            expected="refused",
            question="请证明格力2025年利润变化完全由外星供应商停止供货造成。",
            expected_basis="原文没有所述虚构因果。",
        ),
        dict(
            id="needs-confirmed-calculation",
            selected=["midea-2024", "midea-2025"],
            expected="refused",
            question="请计算美的营业收入2025年相对2024年的同比增长率。",
            expected_basis="本runtime没有真人确认的D10事实；必须通过D11确定性分析，不能模型计算。",
        ),
    ]
)
output = root / "product/validation/d16-real-qa.json"
report = dict(
    runtime_root=index["runtime_root"],
    bge="BAAI/bge-m3",
    dimensions=1024,
    llm=os.environ.get("LLM_MODEL"),
    llm_timeout_seconds=os.environ.get("LLM_TIMEOUT_SECONDS"),
    protocol="d16-verified-excerpts-v2",
    questions=questions,
    results=[],
    human_review="pending",
)


def save():
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


async def main():
    app = create_runtime_app(Path(index["runtime_root"]))
    from app.rag.embed import _model
    report['bge_devices'] = list(_model.target_devices)
    report['bge_configured_use_fp16'] = _model.use_fp16
    report['dependencies'] = {name: version(name) for name in
                              ('pymilvus', 'milvus-lite', 'FlagEmbedding', 'torch')}
    report['llm_sdk_max_retries'] = app.state.runtime_rag_resources.rag_service._llm_client.client.max_retries
    try:
        for q in questions:
            t = time.monotonic()
            trace = {}
            selected = await app.state.selection_preparer.prepare_many(
                document_ids=[ids[name] for name in q["selected"]], query=q["question"]
            )
            result = await app.state.runtime_rag_resources.rag_service.answer_selected(
                selected, app.state.selected_scope_search, trace=trace
            )
            checks = []
            for cite in result.get("citations", []):
                name = next(name for name in q["selected"] if ids[name] == cite["document_id"])
                raw = (root / originals[name]["path"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == originals[name]["sha256"]
                with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                    page = pdf[cite["physical_page"] - 1].get_text()
                # Numbers are checked independently on the actual physical PDF page.
                values = re.findall(r"(?<![\w])\d[\d,]*\.\d+", cite["text"])
                normalized = re.sub(r"\s+", "", page)
                missing = [v for v in values if v not in normalized]
                checks.append(
                    dict(
                        document_id=cite["document_id"],
                        source_revision=cite["source_revision"],
                        physical_page=cite["physical_page"],
                        chunk_id=cite["chunk_id"],
                        pdf_sha256=originals[name]["sha256"],
                        numeric_tokens=values,
                        missing_numeric_tokens=missing,
                        numeric_page_check="passed" if not missing else "needs_review",
                        human_semantic_review="pending",
                    )
                )
            metric_checks = []
            if q["id"].startswith("finance-"):
                name = q["selected"][0]
                for fact in benchmarks:
                    if fact["document_id"] != name or fact["period"] != int(name.split("-")[1]):
                        continue
                    supported = any(
                        cite["physical_page"] == fact["physical_page"]
                        and fact["raw_value"] in re.sub(r"\s+", "", cite["text"])
                        and fact["raw_unit"] in cite["text"]
                        for cite in result.get("citations", [])
                    )
                    metric_checks.append(
                        dict(
                            benchmark_id=fact["id"],
                            raw_value=fact["raw_value"],
                            raw_unit=fact["raw_unit"],
                            period=fact["period"],
                            expected_physical_page=fact["physical_page"],
                            original_value_unit_page_supported=supported,
                            column_and_consolidation_human_review="pending",
                        )
                    )
            coverage = result["outcome"] != "answered" or {
                c["document_id"] for c in result.get("citations", [])
            } == set(selected.document_ids)
            outcome_matches = (
                result["outcome"] == q["expected"]
                and coverage
                and all(m["original_value_unit_page_supported"] for m in metric_checks)
                and all(c["numeric_page_check"] == "passed" for c in checks)
            )
            conclusion = (
                "pending_human_review"
                if outcome_matches and result["outcome"] == "answered"
                else "passed_refusal"
                if outcome_matches
                else "failed"
            )
            report["results"].append(
                dict(
                    id=q["id"],
                    selection=[asdict(d) for d in selected.documents],
                    trace=trace,
                    result=result,
                    pdf_checks=checks,
                    core_metric_checks=metric_checks,
                    required_document_coverage=coverage,
                    conclusion=conclusion,
                    seconds=time.monotonic() - t,
                )
            )
            save()
            print(q["id"], result["outcome"], conclusion, flush=True)
    finally:
        app.state.runtime_rag_resources.milvus_client.close()


save()
started = time.monotonic()
try:
    asyncio.run(main())
except Exception as exc:
    report["safe_error_type"] = type(exc).__name__
finally:
    report["seconds"] = time.monotonic() - started
    report["statistics"] = {
        name: sum(r["conclusion"] == name for r in report["results"])
        for name in ["pending_human_review", "passed_refusal", "failed"]
    }
    save()
sys.exit(int(len(report["results"]) != 18 or report["statistics"]["failed"] > 0))
