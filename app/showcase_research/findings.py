"""Program-owned findings and exact source verifier; provider text cannot mint facts."""
import re
from uuid import uuid4

from app.agent.financial_analysis import FinancialAnalysisService, FinancialFactReference
from app.documents.source_models import SourceError
from app.showcase_research.models import ConfirmedFinancial, ModelInterpretation, ResearchError, SourcedExcerpt, UnresolvedQuestion

LABELS = {"revenue": "营业收入", "net_profit_parent": "归母净利润", "operating_cash_flow": "经营活动产生的现金流量净额"}


def selected_financial_scope(intent):
    scope = intent["scope"]
    companies, periods, metrics = set(intent["company_ids"]), set(intent["periods"]), set(intent["metric_keys"])
    choices = [choice for choice in scope["selected_fact_refs"] if choice["company_id"] in companies
               and (not periods or choice["period"] in periods)
               and (choice["metric_key"] in metrics if metrics else choice["metric_key"] in LABELS)]
    return {**scope, "selected_fact_refs": choices}


def unresolved(question, code="evidence_or_confirmation_missing"):
    return UnresolvedQuestion(finding_id=str(uuid4()), kind="unresolved_question", text=question,
        unresolved_question=question, origin="system", data_origin="unresolved", source_status="unresolved",
        transcription_review_status="not_applicable", interpretation_review_status="not_applicable",
        actions=[{"kind": "review_sources", "label": "核对来源及明确选择已确认事实", "href": "/research?mode=operating"},
                 {"kind": "reason", "label": code, "href": "/sources"}]).model_dump()


def interpretation(text, evidence_refs=()):
    return ModelInterpretation(finding_id=str(uuid4()), kind="model_interpretation", text=text,
        origin="model_draft", data_origin="ai_draft", source_status="current_valid" if evidence_refs else "not_applicable",
        transcription_review_status="not_applicable", interpretation_review_status="ai_unreviewed",
        evidence_refs=list(evidence_refs), numeric_claim_status="numeric_claim_unverified" if re.search(r"\d|[零〇一二三四五六七八九十百千万亿两半]|百分之|翻番|翻倍", text) else "no_numeric_claim").model_dump()


class Findings:
    def __init__(self, sources, facts):
        self.sources, self.facts = sources, facts

    async def quote(self, scope, hit):
        doc = next((d for d in scope["sources"] if d["document_id"] == hit.document_id), None)
        if (doc is None or hit.workspace_id != scope["workspace_id"] or hit.source_revision != doc["source_revision"]
                or type(hit.page) is not int or hit.page < 1 or not hit.chunk_id):
            raise ResearchError("retrieval_outside_scope")
        _, records = await self.sources.parsed_evidence(hit.document_id, company_id=doc["company_id"], source_revision=hit.source_revision)
        # page_context enforces the existing unsupported-table page rejection.
        try:
            await self.sources.page_context(hit.document_id, hit.source_revision, hit.page)
        except SourceError as exc:
            if exc.code == "table_structure_unsupported":
                # Reject this whole page; other retrieved pages may still qualify.
                raise ResearchError("table_structure_unsupported") from exc
            raise
        text = hit.text[:1200]
        matches = [r for r in records if r["physical_page"] == hit.page and text and text in r["text"]]
        if len(matches) != 1:
            raise ResearchError("exact_excerpt_unverified")
        ref = {**{key: doc[key] for key in ("company_id", "document_id", "source_revision", "content_sha256", "parser_version")},
               "physical_page": hit.page, "chunk_id": hit.chunk_id, "evidence_id": matches[0]["evidence_id"], "text": text}
        return SourcedExcerpt(finding_id=str(uuid4()), kind="sourced_excerpt", text=text, origin="verified_source",
            data_origin="local_runtime", source_status="current_valid", transcription_review_status="fast_extraction_unreviewed",
            interpretation_review_status="not_applicable", evidence_refs=[ref]).model_dump()

    async def confirmed(self, scope):
        if self.facts is None or not scope["selected_fact_refs"]:
            return [unresolved("没有为本次研究明确选择可用的已确认财务事实。", "explicit_fact_selection_required")], []
        analysis = FinancialAnalysisService(facts=self.facts, workspace_id=scope["workspace_id"])
        output, groups = [], []
        for choice in scope["selected_fact_refs"]:
            if choice["metric_key"] not in LABELS:
                continue
            group = await self.facts.read_financial_facts(workspace_id=scope["workspace_id"], receipt_id=choice["fact_set_id"], confirmation_kind="local_operator")
            source = group.receipt.review.to_payload()["source"]
            match = next((d for d in scope["sources"] if d["document_id"] == source["document_id"]), None)
            if match is None or any(source.get(k) != v for k, v in match.items() if k != "workspace_id"):
                raise ResearchError("financial_fact_outside_scope")
            ref = FinancialFactReference(choice["fact_set_id"], choice["fact_id"], choice["period"], source["source_revision"], choice["disclosure_version"])
            admitted, fact, reason = await analysis.admit_reference(ref, choice["company_id"], choice["metric_key"])
            if reason or admitted != group or fact is None:
                raise ResearchError(reason or "financial_admission_failed")
            public = {**choice, "document_id": source["document_id"], "source_revision": source["source_revision"],
                      "content_sha256": source["content_sha256"], "receipt_id": group.receipt.receipt_id,
                      "value_decimal": fact["value_cny_yuan"], "unit": "CNY_YUAN", "confirmation_kind": "local_operator"}
            finding = ConfirmedFinancial(finding_id=str(uuid4()), kind="confirmed_financial",
                text=f"{choice['period']}年度{LABELS[choice['metric_key']]}为{fact['value_cny_yuan']}元。",
                origin="deterministic_tool", data_origin="local_runtime", source_status="current_valid",
                transcription_review_status="human_reviewed", interpretation_review_status="deterministic", financial_refs=[public])
            output.append(finding.model_dump())
            groups.append(group)
        return output or [unresolved("当前明确选择中没有可用于本次研究的旧三指标事实。")], groups

    async def revalidate_quotes(self, scope, findings):
        for finding in findings:
            for ref in finding.get("evidence_refs", []):
                doc = next((d for d in scope["sources"] if d["document_id"] == ref["document_id"]), None)
                if doc is None or any(ref[key] != doc[key] for key in ("source_revision", "content_sha256", "company_id", "parser_version")):
                    raise ResearchError("quote_scope_changed")
                record = await self.sources.evidence(ref["document_id"], ref["evidence_id"], company_id=ref["company_id"], source_revision=ref["source_revision"])
                if record["physical_page"] != ref["physical_page"] or ref["text"] not in record["text"]:
                    raise ResearchError("quote_source_changed")
                await self.sources.page_context(ref["document_id"], ref["source_revision"], ref["physical_page"])
