"""Domain-qualified immutable snapshot projections; no value or authority inference."""

import hashlib
import json
from .csv_projection import safe_text

SCHEMAS = {
    "showcase_report_v2": ("showcase-report-v2", "report_id"),
    "annual_diff_v1": ("annual-diff-v1", "result_id"),
    "checkup_v1": ("checkup-v1", "id"),
    "peer_comparison_v1": ("peer-comparison-v1", "result_id"),
    "research_answer_v1": ("cplus-research-answer-v1", "answer_id"),
}


def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(v):
    return hashlib.sha256(canonical(v).encode()).hexdigest()


def project(ref, resolved):
    payload = resolved["snapshot"]
    schema, id_key = SCHEMAS[ref["domain"]]
    if payload.get("schema_version") != schema or payload.get(id_key) != ref["id"]:
        raise ValueError("resolved_domain_or_id_mismatch")
    if (payload.get("revision") if ref["domain"] == "showcase_report_v2" else 1) != ref["revision"]:
        raise ValueError("resolved_revision_mismatch")
    if digest(payload) != ref["payload_sha256"]:
        raise ValueError("resolved_payload_hash_mismatch")
    status = resolved["display_status"]
    if status not in ("current", "stale", "unavailable"):
        raise ValueError("invalid_display_status")
    financial = []
    evidence = []
    texts = []

    def visit(v, path="snapshot"):
        if isinstance(v, dict):
            if "metric_key" in v and any(
                k in v for k in ("normalized_decimal", "raw_decimal", "value_decimal")
            ):
                financial.append(
                    dict(
                        path=path,
                        **{
                            k: v.get(k)
                            for k in [
                                "company_id",
                                "company_code",
                                "company_name",
                                "statement_kind",
                                "metric_key",
                                "report_year",
                                "time",
                                "basis",
                                "scope",
                                "currency",
                                "raw_unit",
                                "raw_decimal",
                                "normalized_decimal",
                                "value_decimal",
                                "financial_review",
                                "receipt_ref",
                                "source_revision",
                                "document_id",
                                "evidence_refs",
                            ]
                        },
                    )
                )
            if "text" in v:
                evidence.append(
                    dict(
                        path=path,
                        **{
                            k: v.get(k)
                            for k in [
                                "kind",
                                "text",
                                "source_ref",
                                "document_id",
                                "source_revision",
                                "content_sha256",
                                "physical_page",
                                "evidence_id",
                                "bbox",
                                "source_status",
                                "data_origin",
                                "transcription_review_status",
                                "interpretation_review_status",
                                "numeric_claim_status",
                                "financial_refs",
                            ]
                        },
                    )
                )
                if isinstance(v["text"], str):
                    texts.append(v["text"])
            for k, x in v.items():
                visit(x, path + "." + k)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                visit(x, f"{path}[{i}]")

    visit(payload)
    if (
        len(financial) > 5000
        or len(evidence) > 5000
        or len(canonical(payload).encode()) > 8_000_000
    ):
        raise ValueError("export_size_limit")
    overview = [
        {"field": k, "value": v}
        for k, v in dict(
            domain=ref["domain"],
            id=ref["id"],
            revision=ref["revision"],
            payload_sha256=ref["payload_sha256"],
            title=payload.get("title", "已保存研究"),
            current_source_status=status,
            historical_snapshot=status != "current",
            saved_source_status=payload.get("source_status"),
            interpretation=payload.get("interpretation") or "未生成额外AI解释",
            limitations=payload.get("limitations", []),
            precision_policy="原始Decimal保持文本；缺值留空；不推断确认状态",
        ).items()
    ]
    return dict(
        overview=overview,
        financial=financial,
        evidence=evidence,
        texts=texts,
        ref=ref,
        display_status=status,
        snapshot=payload,
    )


def matrix(rows, defaults):
    fields = list(dict.fromkeys(defaults + [k for r in rows for k in r]))
    return [fields] + [[safe_text(row.get(k)) for k in fields] for row in rows]
