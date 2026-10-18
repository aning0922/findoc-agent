"""Per-answer immutable multi-source evidence, used by the existing RAGService.

The limited answer contract is extractive: no model-authored financial assertions or
calculations are published. Table evidence is quoted whole, preserving column/year/unit
context. A valid quote is provenance support, not a claim of human-reviewed accuracy.
"""

from dataclasses import asdict, dataclass
import json
from types import MappingProxyType
from typing import Any

from app.documents.preparation import PreparedDocumentSelection, SelectedDocumentIdentity
from app.rag.retriever import SearchHit
from app.rag.service import (
    CitationValidationError,
    ContextBudgetError,
    NumberedContext,
    validate_and_build_citations,
)


@dataclass(frozen=True)
class SelectedEvidence:
    context: NumberedContext
    documents: tuple[SelectedDocumentIdentity, ...]
    originals: MappingProxyType[int, str]


def build_selected_evidence(
    hits: tuple[SearchHit, ...],
    selection: PreparedDocumentSelection,
    budget: int = 16000,
    table_context: dict[tuple[str, str, int], str] | None = None,
) -> SelectedEvidence:
    identities = {d.document_id: d for d in selection.documents}
    seen: dict[tuple[str | None, str | None, str | None, str], SearchHit] = {}
    mapping: dict[int, SearchHit] = {}
    originals: dict[int, str] = {}
    included_pages: set[tuple[str | None, str | None, int]] = set()
    rendered = []
    used = 0
    for hit in hits:
        identity = identities.get(hit.document_id or "")
        if (
            identity is None
            or hit.workspace_id != identity.workspace_id
            or hit.source_revision != identity.source_revision
        ):
            raise CitationValidationError("evidence_outside_selection")
        key = (hit.workspace_id, hit.document_id, hit.source_revision, hit.chunk_id)
        if key in seen:
            if asdict(seen[key]) | {"score": hit.score} != asdict(hit):
                raise CitationValidationError("conflicting_evidence_identity")
            continue
        seen[key] = hit
        body = hit.table_md if hit.type == "table" else hit.text
        if not body:
            raise CitationValidationError("missing_table_context")
        if hit.type == "table" or (hit.document_id, hit.source_revision, hit.page) in (
            table_context or {}
        ):
            context = (table_context or {}).get(
                (hit.document_id or "", hit.source_revision or "", hit.page)
            )
            if not context:
                raise CitationValidationError("missing_table_page_context")
            page_key = (hit.document_id, hit.source_revision, hit.page)
            if page_key in included_pages:
                continue
            if hit.type == "table" and (not hit.table_md or hit.table_md not in context):
                raise CitationValidationError("table_missing_from_page_snapshot")
            body = context
            included_pages.add(page_key)
        number = len(mapping) + 1
        text = json.dumps(
            dict(
                number=number,
                report_year=identity.report_year,
                company_id=identity.company_id,
                source_file=hit.source_file,
                physical_page=hit.page,
                kind=hit.type,
                original=body,
            ),
            ensure_ascii=False,
        )
        if used + len(text) > budget:
            continue  # Never truncate a table or a row to fit the budget.
        rendered.append(text)
        used += len(text)
        mapping[number] = hit
        originals[number] = body
    if not mapping:
        raise ContextBudgetError("no_complete_evidence_fits")
    return SelectedEvidence(
        NumberedContext("\n".join(rendered), MappingProxyType(mapping)),
        selection.documents,
        MappingProxyType(originals),
    )


def validate_selected_output(raw: str, evidence: SelectedEvidence) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CitationValidationError("duplicate_model_key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique_pairs)
    if value == {"decision": "refuse"}:
        return dict(outcome="refused", reason="insufficient_evidence", content="", citations=[])
    if (
        not isinstance(value, dict)
        or set(value) != {"decision", "quotes"}
        or value["decision"] != "answer"
        or not isinstance(value["quotes"], list)
        or not 1 <= len(value["quotes"]) <= 8
    ):
        raise CitationValidationError("invalid_selected_answer_protocol")
    citations = []
    paragraphs = []
    identities = {d.document_id: d for d in evidence.documents}
    for item in value["quotes"]:
        if not isinstance(item, dict) or set(item) != {"number"} or type(item["number"]) is not int:
            raise CitationValidationError("invalid_quote")
        n = item["number"]
        hit = evidence.context.hits_by_number.get(n)
        if hit is None:
            raise CitationValidationError("unknown_evidence_number")
        original = evidence.originals[n]
        # No model-authored financial claim is accepted. The service restores the whole
        # original snapshot, so years, numbers, signs and units cannot be rewritten.
        quote = original
        doc = asdict(identities[hit.document_id or ""])
        if any(
            doc[k] != getattr(hit, k) for k in ("workspace_id", "document_id", "source_revision")
        ):
            raise CitationValidationError("citation_identity_changed")
        paragraphs.append(f"{doc['report_year']}年报《{hit.source_file}》原文：\n{quote}\n[{n}]")
        citations.append(
            dict(
                number=n,
                **doc,
                chunk_id=hit.chunk_id,
                physical_page=hit.page,
                source_file=hit.source_file,
                text=original,
                kind=hit.type,
                verification="exact_original_with_context",
            )
        )
    # Reuse the existing numbering validator; quote contents may contain literal [n], so
    # validate the server's citation tokens independently from quoted document text.
    validate_and_build_citations(
        "原文证据 " + " ".join(f"[{c['number']}]" for c in citations), evidence.context
    )
    return dict(
        outcome="answered",
        content="\n\n".join(paragraphs),
        citations=citations,
        reason=None,
        answer_mode="verified_excerpts",
        human_review="pending",
    )
