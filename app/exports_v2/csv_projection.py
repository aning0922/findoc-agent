"""Pure CSV projection for a server-verified immutable showcase report snapshot.

Callers must authorize, verify domain/id/revision/hash and source status before calling.
This function does not resolve identities or grant any authority.
"""

import csv
import io
import json


def safe_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    value = str(value)
    # Include whitespace/control prefixes: spreadsheets may trim these before interpreting formulas.
    if value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


def render_showcase_csv(snapshot, *, current_source_status):
    """Export unchanged saved findings/evidence with explicit current-source status.

    Financial values are not inferred from model text. Existing typed financial refs
    are preserved verbatim; unknown period, unit and value fields remain empty.
    """
    if snapshot.get("schema_version") != "showcase-report-v2":
        raise ValueError("unsupported_report_schema")
    if current_source_status not in ("current", "stale", "unavailable"):
        raise ValueError("invalid_source_status")
    inner = snapshot.get("snapshot")
    if not isinstance(inner, dict) or not isinstance(inner.get("findings"), list):
        raise ValueError("invalid_report_snapshot")
    output = io.StringIO(newline="")
    fields = [
        "report_id",
        "revision",
        "finding_id",
        "kind",
        "text",
        "saved_data_origin",
        "saved_source_status",
        "current_source_status",
        "historical_snapshot",
        "transcription_review_status",
        "interpretation_review_status",
        "numeric_claim_status",
        "financial_refs",
        "document_id",
        "source_revision",
        "content_sha256",
        "physical_page",
        "evidence_id",
        "evidence_text",
        "period_kind",
        "period_start",
        "period_end",
        "unit",
        "value_decimal",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for finding in inner["findings"]:
        if not isinstance(finding, dict):
            raise ValueError("invalid_finding")
        refs = finding.get("evidence_refs", [])
        if not isinstance(refs, list):
            raise ValueError("invalid_evidence")
        for ref in refs or [None]:
            if ref is not None and not isinstance(ref, dict):
                raise ValueError("invalid_evidence")
            ref = ref or {}
            row = dict(
                report_id=snapshot.get("report_id"),
                revision=snapshot.get("revision"),
                finding_id=finding.get("finding_id"),
                kind=finding.get("kind"),
                text=finding.get("text"),
                saved_data_origin=finding.get("data_origin"),
                saved_source_status=finding.get("source_status"),
                current_source_status=current_source_status,
                historical_snapshot=current_source_status != "current",
                transcription_review_status=finding.get("transcription_review_status"),
                interpretation_review_status=finding.get("interpretation_review_status"),
                numeric_claim_status=finding.get("numeric_claim_status"),
                financial_refs=finding.get("financial_refs", []),
                document_id=ref.get("document_id"),
                source_revision=ref.get("source_revision"),
                content_sha256=ref.get("content_sha256"),
                physical_page=ref.get("physical_page"),
                evidence_id=ref.get("evidence_id"),
                evidence_text=ref.get("text"),
            )
            writer.writerow({key: safe_text(row.get(key)) for key in fields})
    return ("\ufeff" + output.getvalue()).encode("utf-8")
