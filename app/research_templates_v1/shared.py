"""Finite template/chart snapshot checks over the original statement/source contracts."""

from datetime import UTC, datetime
import inspect
import time

from app.retrieval_v2.models import RetrievalError, SourceRef
from app.retrieval_v2.service import resolve, sha

CORE = ("revenue", "net_profit_parent", "operating_cash_flow", "total_assets", "total_liabilities")
SOURCE_KEYS = (
    "company_id",
    "document_id",
    "source_revision",
    "content_sha256",
    "parser_version",
    "report_year",
    "attempt",
    "report_type",
    "basis",
    "period_start",
    "period_end",
)


def source_ref(statements, source):
    return SourceRef(
        kind="fast",
        workspace_id=statements.sources.documents.workspace_id,
        identity_status="fast_source_verified",
        **{k: source[k] for k in SOURCE_KEYS},
    ).model_dump()


async def owner(identity, validator, workspace):
    if (
        validator is None
        or identity.expires_at <= time.time()
        or identity.workspace_id != workspace
        or await resolve(validator(identity)) is False
    ):
        raise RetrievalError("trusted_identity_required", 403)
    return sha(identity.model_dump())


def commit_check(callback, identity, fence):
    if callback is None or identity.expires_at <= time.time():
        raise RetrievalError("publication_hooks_required", 503)
    value = callback(identity, fence)
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise RetrievalError("synchronous_commit_check_required", 503)
    if value is False or identity.expires_at <= time.time():
        raise RetrievalError("identity_rejected_before_commit", 403)


def now():
    return datetime.now(UTC).isoformat()


def current_core(collection):
    year = collection["source"]["report_year"]
    chosen = []
    missing = []
    for metric in CORE:
        cells = [
            c
            for c in collection["cells"]
            if c["metric_key"] == metric
            and c["extraction_status"] == "candidate"
            and (
                c["time"].get("as_of_date") == f"{year}-12-31"
                if c["time"]["kind"] == "instant"
                else c["time"].get("period_start") == f"{year}-01-01"
                and c["time"].get("period_end") == f"{year}-12-31"
            )
        ]
        if len(cells) == 1:
            chosen.append(cells[0]["cell_id"])
        else:
            missing.append(
                {
                    "company_id": collection["source"]["company_id"],
                    "report_year": year,
                    "metric_key": metric,
                    "reason": "missing_current_period" if not cells else "ambiguous_current_period",
                }
            )
    return {"collection_id": collection["id"], "cell_ids": chosen}, missing


async def selected_points(statements, refs):
    if not refs:
        return [], [], []
    collections, contexts = await statements.selected(refs)
    points = []
    with statements.tx(source=True) as db:
        statements.guard(db, contexts)
        for collection in collections:
            for cell in collection["cells"]:
                receipt = statements.admitted(db, cell)
                points.append(
                    {
                        **cell,
                        "source_status": "current",
                        "receipt_ref": receipt,
                        "financial_review": "local_operator_confirmed"
                        if receipt
                        else "unconfirmed",
                    }
                )
    return collections, contexts, points


def validate_point_snapshot(expected, actual):
    if len(expected) != len(actual) or {p["cell_id"] for p in expected} != {
        p["cell_id"] for p in actual
    }:
        raise RetrievalError("selected_cells_changed")
    by_id = {p["cell_id"]: p for p in actual}
    for point in expected:
        current = by_id[point["cell_id"]]
        if any(point.get(k) != current.get(k) for k in current):
            raise RetrievalError("selected_cells_or_receipt_changed")


def check_receipts(statements, db, points):
    if db.execute("PRAGMA main.journal_mode").fetchone()[0].lower() not in (
        "delete",
        "truncate",
        "persist",
    ):
        raise RetrievalError("receipt_fence_journal_unsupported", 503)
    for p in points:
        if statements.admitted(db, p) != p["receipt_ref"]:
            raise RetrievalError("receipt_changed")


def comparable_changes(changes, points):
    known = {p["cell_id"]: p for p in points}
    result = []
    for raw in changes:
        value = dict(raw)
        inputs = [known[k] for k in raw["input_refs"] if k in known]
        if len(inputs) != 2 or any(p.get("basis") in (None, "", "unknown") for p in inputs):
            value.update(
                delta_decimal=None, change_percent_decimal=None, reason="unknown_or_missing_basis"
            )
        elif any(
            inputs[0].get(k) != inputs[1].get(k)
            for k in ("basis", "scope", "currency", "normalized_unit")
        ):
            value.update(
                delta_decimal=None, change_percent_decimal=None, reason="incomparable_inputs"
            )
        years = [p["time"].get("as_of_date", p["time"].get("period_end", ""))[:4] for p in inputs]
        value["comparison_kind"] = (
            "year_over_year"
            if len(years) == 2
            and all(y.isdigit() for y in years)
            and abs(int(years[0]) - int(years[1])) == 1
            else "period_change"
        )
        result.append(value)
    return result
