"""Domain-qualified immutable snapshot projections; no value or authority inference."""

import hashlib
from decimal import Decimal, InvalidOperation
import json
import re
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
    companies = json.loads(canonical(resolved.get("display_companies") or {}))
    if not isinstance(companies, dict) or any(
        not isinstance(v, dict)
        or any(
            v.get(k) is not None and not isinstance(v[k], str)
            for k in ("name", "security_code", "exchange")
        )
        for v in companies.values()
    ):
        raise ValueError("invalid_display_companies")
    generated_at = resolved.get("generated_at")
    source_meta = {}

    def index_sources(v):
        if isinstance(v, dict):
            if v.get("document_id") and v.get("source_revision"):
                key = (v["document_id"], v["source_revision"])
                source_meta.setdefault(key, {}).update(
                    {k: v[k] for k in ("company_id", "report_year") if v.get(k) is not None}
                )
            for x in v.values():
                index_sources(x)
        elif isinstance(v, list):
            for x in v:
                index_sources(x)

    index_sources(payload)
    index_sources(resolved.get("selected_sources", []))

    def visit(v, path="snapshot"):
        if isinstance(v, dict):
            if "text" not in v and all(
                k in v
                for k in (
                    "document_id",
                    "source_revision",
                    "physical_page",
                    "raw_label",
                    "raw_value",
                )
            ):
                evidence.append(
                    dict(
                        path=path,
                        kind="statement_cell_transcription",
                        text=f"候选表格单元转录（待核对）：{v['raw_label']} · {v['raw_value']}",
                        document_id=v["document_id"],
                        source_revision=v["source_revision"],
                        physical_page=v["physical_page"],
                        content_sha256=v.get("content_sha256"),
                        transcription_review_status="unreviewed",
                        financial_review="unconfirmed",
                    )
                )
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
                                "unit",
                                "raw_decimal",
                                "normalized_decimal",
                                "normalized_unit",
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
                row = financial[-1]
                company = companies.get(row["company_id"], {})
                row.update(
                    company_name=company.get("name", row["company_name"]),
                    company_code=company.get("security_code", row["company_code"]),
                    exchange=company.get("exchange"),
                    display_label_origin="registry_at_export" if company else "saved_snapshot",
                    authority=row["financial_review"],
                    generated_at=generated_at,
                )
                period = row.get("time") or {}
                row.update(
                    period_kind=period.get("kind"),
                    as_of_date=period.get("as_of_date"),
                    period_start=period.get("period_start"),
                    period_end=period.get("period_end"),
                )
                pages = sorted(
                    {
                        r["physical_page"]
                        for r in row.get("evidence_refs") or []
                        if r.get("physical_page")
                    }
                )
                row.update(
                    physical_page=pages[0] if len(pages) == 1 else None, physical_pages=pages
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
            if "rule" in v or ("rule_id" in v and "observation" in v):
                evidence.append(dict(path=path, kind="saved_checkup_rule", text=canonical(v)))
            elif "topic" in v and "explanation" in v:
                evidence.append(
                    dict(
                        path=path,
                        kind="saved_topic_explanation",
                        text=v["explanation"],
                        interpretation_review_status=v.get("interpretation_review_status"),
                        evidence_refs=[
                            r
                            for side in ("left", "right")
                            for r in (v.get(side) or {}).get("evidence_refs", [])
                        ],
                    )
                )
            for k, x in v.items():
                visit(x, path + "." + k)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                visit(x, f"{path}[{i}]")

    visit(payload)
    for row in evidence:
        source = row.get("source_ref") or {}
        for key in (
            "company_id",
            "document_id",
            "source_revision",
            "report_year",
            "content_sha256",
        ):
            if row.get(key) is None:
                row[key] = source.get(key)
        meta = source_meta.get((row.get("document_id"), row.get("source_revision")), {})
        for key in ("company_id", "report_year"):
            if row.get(key) is None:
                row[key] = meta.get(key)
        company = companies.get(row.get("company_id"), {})
        row.update(
            company_name=company.get("name"),
            company_code=company.get("security_code"),
            generated_at=generated_at,
        )
    for row in [*financial, *evidence]:
        if row.get("document_id") and row.get("source_revision") and row.get("physical_page"):
            from urllib.parse import quote

            row["source_link"] = (
                f"/api/documents/{quote(row['document_id'], safe='')}/file?"
                f"source_revision={quote(row['source_revision'], safe='')}#page={row['physical_page']}"
            )
    if (
        len(financial) > 5000
        or len(evidence) > 5000
        or len(canonical(payload).encode()) > 8_000_000
    ):
        raise ValueError("export_size_limit")
    interpretations = []
    if payload.get("interpretation"):
        interpretations.append(payload["interpretation"])
    interpretations.extend(
        f"{t['topic']}：{t['explanation']}"
        for t in payload.get("topics", [])
        if t.get("explanation")
    )
    interpretations.extend(e["text"] for e in payload.get("explanations", []) if e.get("text"))
    interpretations.extend(
        f["text"]
        for f in (payload.get("findings") or (payload.get("snapshot") or {}).get("findings") or [])
        if f.get("kind") == "model_interpretation" and f.get("text")
    )
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
            interpretation="\n".join(interpretations) or "未生成额外AI解释",
            limitations=payload.get("limitations", []),
            precision_policy="原始Decimal保持文本；缺值留空；不推断确认状态",
            workbook_view="右侧分组可展开技术列；长原文按excerpt_part拆行，CSV保留完整条目。",
            generated_at=generated_at,
            display_companies=companies,
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
        display_companies=companies,
        generated_at=generated_at,
        chart=financial_chart(payload, financial),
    )


def financial_chart(payload, rows):
    """Select a saved comparable series; never infer comparability from names."""
    groups = []
    if payload.get("schema_version") == "peer-comparison-v1":
        for comparison in payload.get("comparisons", []):
            if comparison.get("state") in ("candidate_observation", "confirmed_comparison"):
                groups.append(
                    (
                        "bar",
                        [
                            r
                            for r in rows
                            if r.get("metric_key") == comparison["metric_key"]
                            and any(
                                p.get("company_id") == r.get("company_id")
                                and p.get("time") == r.get("time")
                                for p in comparison.get("points", [])
                            )
                        ],
                    )
                )
    else:
        grouped = {}
        for row in rows:
            key = (row.get("company_id"), row["metric_key"])
            grouped.setdefault(key, []).append(row)
        groups = [("line", values) for values in grouped.values()]
    for kind, points in groups:
        if not 2 <= len(points) <= 5:
            continue
        dimensions = ("basis", "scope", "currency", "normalized_unit")
        if any(
            not points[0].get(k)
            or points[0][k] == "unknown"
            or any(p.get(k) != points[0][k] for p in points)
            for k in dimensions
        ):
            continue
        times = [canonical(p.get("time")) for p in points]
        if kind == "bar" and (
            len(set(times)) != 1 or len({p.get("company_id") for p in points}) != len(points)
        ):
            continue
        if kind == "line" and (
            len(set(times)) != len(points) or len({p.get("period_kind") for p in points}) != 1
        ):
            continue
        if kind == "line":
            shapes = set()
            for p in points:
                t = p.get("time") or {}
                if t.get("kind") == "instant":
                    shapes.add(("instant", str(t.get("as_of_date", ""))[4:]))
                else:
                    shapes.add(
                        (
                            "duration",
                            t.get("period_type"),
                            str(t.get("period_start", ""))[4:],
                            str(t.get("period_end", ""))[4:],
                        )
                    )
            if len(shapes) != 1:
                continue
        try:
            values = [Decimal(p["normalized_decimal"]) for p in points]
            if any(not v.is_finite() or abs(v) > Decimal("1e18") for v in values):
                continue
        except (InvalidOperation, TypeError, KeyError):
            continue
        if not all(
            p.get("document_id") and p.get("source_revision") and p.get("physical_page")
            for p in points
        ):
            continue
        return dict(
            kind=kind,
            metric_key=points[0]["metric_key"],
            unit=points[0]["normalized_unit"],
            points=sorted(points, key=lambda p: canonical(p.get("time"))),
        )
    return None


def matrix(rows, defaults):
    fields = list(dict.fromkeys(defaults + [k for r in rows for k in r]))

    def value(row, key):
        raw = row.get(key)
        if (
            key in ("raw_decimal", "normalized_decimal", "value_decimal")
            and isinstance(raw, str)
            and re.fullmatch(r"-?\d+(?:\.\d+)?", raw)
        ):
            return raw  # XLSX stores this exact original string, including negative sign.
        return safe_text(raw)

    return [fields] + [[value(row, k) for k in fields] for row in rows]
