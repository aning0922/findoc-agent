"""唯一 SQLite 确认仓储：兼容旧两期收入并事务转换 D9 通用接受凭证。

与 documents 共用数据库；事实组原子提交，历史记录不可变。
读回验证完整组、已接受快照、可信证据和当前有效绑定，不重新抽取候选。
"""

from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import uuid
from typing import Any

from app.agent.financial_facts import FinancialFact, FinancialFactKey, FinancialFactRepository
from app.agent.research_workflow import RevenueCandidate, RevenueEvidence
from app.agent.financial_facts import FinancialUnit
from app.agent.revenue_confirmation import (
    ConfirmationKind,
    RevenueConfirmation,
    RevenueConfirmationError,
    RevenueReview,
    RevenueSourceRevision,
    FinancialReview,
    FinancialAcceptance,
    ConfirmedFinancialFact,
    FinancialFactSet,
    canonical_payload,
)
from app.agent.tool_loop import ToolExecutionContext
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.companies.models import RegistryNotFoundError
import hashlib


def disclosure_version_for_source(source: dict[str, Any]) -> str:
    """D10 disclosure identity, independent of acceptance and amounts."""
    s = source
    return (
        "disclosure-v1:"
        + hashlib.sha256(
            canonical_payload(
                {
                    k: s[k]
                    for k in (
                        "company_id",
                        "document_id",
                        "report_year",
                        "report_type",
                        "source_revision",
                    )
                }
            ).encode()
        ).hexdigest()
    )


class SQLiteRevenueConfirmationRepository:
    """同一确认仓储保存旧收入与通用财务事实；不保存计算结果。"""

    @property
    def financial_storage_path(self) -> Path:
        return self._database_path.resolve()

    def recheck_financial_fact_sets(
        self,
        *,
        workspace_id: str,
        receipt_ids: tuple[str, ...],
        confirmation_kind: ConfirmationKind,
    ) -> tuple[FinancialFactSet, ...]:
        """Final analysis admission reads both complete groups in one snapshot."""
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            return self.recheck_financial_fact_sets_in(c,workspace_id=workspace_id,
                receipt_ids=receipt_ids,confirmation_kind=confirmation_kind)

    def recheck_financial_fact_sets_in(self, c: sqlite3.Connection, *, workspace_id: str,
                                      receipt_ids: tuple[str, ...], confirmation_kind: ConfirmationKind
                                      ) -> tuple[FinancialFactSet, ...]:
        return tuple(self._load_financial_facts(c,workspace_id,rid,confirmation_kind,False)
                     for rid in receipt_ids)

    def __init__(self, database_path: Path, *, initialize: bool = True) -> None:
        """绑定已有文档库并增量建两表，不迁移或覆盖历史业务数据。"""
        self._database_path = database_path
        if not initialize:
            return  # DB-only qualification uses the same complete-group validator, no DDL.
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS revenue_confirmations (
                    confirmation_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL UNIQUE,
                    workspace_id TEXT NOT NULL,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    content_sha256 TEXT NOT NULL,
                    attempt INTEGER NOT NULL CHECK (attempt >= 1),
                    extraction_method TEXT NOT NULL,
                    extraction_version TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    confirmation_kind TEXT NOT NULL
                        CHECK (confirmation_kind IN ('local_operator', 'simulated_test'))
                );
                CREATE TABLE IF NOT EXISTS confirmed_revenue_facts (
                    confirmation_id TEXT NOT NULL
                        REFERENCES revenue_confirmations(confirmation_id),
                    fact_key TEXT NOT NULL CHECK (fact_key = 'revenue'),
                    period INTEGER NOT NULL CHECK (period IN (2024, 2025)),
                    source_ref TEXT NOT NULL,
                    value_text TEXT NOT NULL CHECK (typeof(value_text) = 'text'),
                    unit TEXT NOT NULL CHECK (unit = 'CNY_YUAN'),
                    chunk_id TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    page INTEGER NOT NULL CHECK (page >= 1),
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (confirmation_id, period),
                    UNIQUE (confirmation_id, source_ref)
                );
                CREATE TABLE IF NOT EXISTS financial_acceptance_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL CHECK (schema_version = 'financial-acceptance-v1'),
                    workspace_id TEXT NOT NULL,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    company_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    confirmation_kind TEXT NOT NULL
                        CHECK (confirmation_kind IN ('local_operator', 'simulated_test')),
                    accepted_at TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    UNIQUE (workspace_id, confirmation_kind, request_id)
                );
                CREATE TRIGGER IF NOT EXISTS d9_acceptance_immutable_update
                BEFORE UPDATE ON financial_acceptance_receipts
                BEGIN SELECT RAISE(ABORT, 'acceptance receipt is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS d9_acceptance_immutable_delete
                BEFORE DELETE ON financial_acceptance_receipts
                BEGIN SELECT RAISE(ABORT, 'acceptance receipt is immutable'); END;
                """
            )

    @staticmethod
    def _check_financial_document(connection: sqlite3.Connection, review: FinancialReview) -> None:
        p = review.to_payload()
        s = p["source"]
        row = connection.execute(
            "SELECT * FROM documents WHERE workspace_id=? AND document_id=?",
            (review.workspace_id, s["document_id"]),
        ).fetchone()
        source = connection.execute(
            "SELECT * FROM document_sources WHERE workspace_id=? AND document_id=? "
            "AND source_revision=?",
            (review.workspace_id, s["document_id"], s["source_revision"]),
        ).fetchone()
        try:
            # Read the same effective D6 binding inside this transaction, never the original join.
            metadata = SQLiteCompanyRepository._metadata(
                connection, review.workspace_id, s["document_id"]
            )
            correction = connection.execute(
                "SELECT new_attempt, old_attempt, sequence FROM report_binding_corrections WHERE workspace_id=? "
                "AND document_id=? ORDER BY sequence DESC LIMIT 1",
                (review.workspace_id, s["document_id"]),
            ).fetchone()
            if (
                row is None
                or source is None
                or row["status"] != "ready"
                or row["source_file"] != p["document"]["source_file"]
                or source["invalidated_at"] is not None
                or source["physical_pages"] != s["physical_pages"]
                or any(row[k] != s[k] or source[k] != s[k] for k in ("content_sha256", "attempt"))
                or source["parser_version"] != s["parser_version"]
                or hashlib.sha256(
                    json.dumps(
                        [
                            s["document_id"],
                            row["content_sha256"],
                            row["attempt"],
                            s["parser_version"],
                        ],
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                != s["source_revision"]
                or (
                    correction is not None
                    and (
                        correction["new_attempt"] > row["attempt"]
                        or correction["new_attempt"] != correction["old_attempt"] + 1
                    )
                )
                or any(
                    metadata.model_dump(mode="json")[k] != s[k]
                    for k in (
                        "company_id",
                        "report_year",
                        "report_type",
                        "basis",
                        "period_start",
                        "period_end",
                    )
                )
                or metadata.workspace_id != review.workspace_id
                or metadata.document_id != s["document_id"]
            ):
                raise RevenueConfirmationError("source_changed")
        except (RegistryNotFoundError, ValueError, KeyError, TypeError) as exc:
            raise RevenueConfirmationError("source_changed") from exc
        company = connection.execute(
            "SELECT name, security_code, exchange, country, updated_at FROM companies "
            "WHERE company_id=? AND workspace_id=?",
            (s["company_id"], review.workspace_id),
        ).fetchone()
        if company is None or any(
            company[k] != p["company"][k] for k in company.keys() if k != "updated_at"
        ):
            raise RevenueConfirmationError("source_changed")
        if datetime.fromisoformat(company["updated_at"]) != datetime.fromisoformat(
            p["company"]["updated_at"]
        ):
            raise RevenueConfirmationError("source_changed")

    def save_acceptance(
        self, *, review: FinancialReview, confirmation_kind: ConfirmationKind, request_id: str
    ) -> FinancialAcceptance:
        """D9 receipt-only transaction. Legacy facts and D10 dynamic facts are untouched."""
        if confirmation_kind not in ("local_operator", "simulated_test") or not review.acceptable:
            raise RevenueConfirmationError("candidate_not_acceptable")
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            self._check_financial_document(c, review)
            self._check_financial_evidence(c, review)
            existing = c.execute(
                "SELECT * FROM financial_acceptance_receipts WHERE workspace_id=? "
                "AND confirmation_kind=? AND request_id=?",
                (review.workspace_id, confirmation_kind, request_id),
            ).fetchone()
            if existing is not None:
                if existing["snapshot_id"] != review.snapshot_id:
                    raise RevenueConfirmationError("idempotency_conflict")
                self._check_receipt_active(c, review.workspace_id, existing["receipt_id"], confirmation_kind)
                return self._acceptance_from_row(existing, review)
            receipt_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO financial_acceptance_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt_id,
                    "financial-acceptance-v1",
                    review.workspace_id,
                    review.to_payload()["source"]["document_id"],
                    review.to_payload()["source"]["company_id"],
                    review.snapshot_id,
                    request_id,
                    confirmation_kind,
                    datetime.now(UTC).isoformat(),
                    review.payload_json,
                ),
            )
            row = c.execute(
                "SELECT * FROM financial_acceptance_receipts WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
            return self._acceptance_from_row(row, review)

    @staticmethod
    def _acceptance_from_row(row: sqlite3.Row, current: FinancialReview) -> FinancialAcceptance:
        try:
            stored = FinancialReview(row["workspace_id"], row["review_json"])
            p = stored.to_payload()
            accepted_at = datetime.fromisoformat(row["accepted_at"])
            if (
                row["schema_version"] != "financial-acceptance-v1"
                or p["schema"] != "financial-review-v1"
                or stored.payload_json != canonical_payload(p)
                or stored.snapshot_id != row["snapshot_id"]
                or not stored.acceptable
                or accepted_at.tzinfo is None
                or p["source"]["document_id"] != row["document_id"]
                or p["source"]["company_id"] != row["company_id"]
                or row["confirmation_kind"] not in ("local_operator", "simulated_test")
            ):
                raise ValueError("receipt integrity")
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise RevenueConfirmationError("confirmation_integrity_error") from exc
        if current.workspace_id != stored.workspace_id or current.snapshot_id != stored.snapshot_id:
            raise RevenueConfirmationError("review_changed")
        return FinancialAcceptance(
            row["receipt_id"], row["request_id"], accepted_at, row["confirmation_kind"], stored
        )

    def load_acceptance(
        self,
        *,
        current_review: FinancialReview,
        request_id: str,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialAcceptance:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            self._check_financial_document(c, current_review)
            row = c.execute(
                "SELECT * FROM financial_acceptance_receipts WHERE workspace_id=? AND document_id=? "
                "AND company_id=? AND confirmation_kind=? AND request_id=?",
                (
                    current_review.workspace_id,
                    current_review.to_payload()["source"]["document_id"],
                    current_review.to_payload()["source"]["company_id"],
                    confirmation_kind,
                    request_id,
                ),
            ).fetchone()
            if row is None:
                raise RevenueConfirmationError("acceptance_not_found")
            self._check_financial_evidence(c, current_review)
            self._check_receipt_active(c, current_review.workspace_id, row["receipt_id"], confirmation_kind)
            return self._acceptance_from_row(row, current_review)

    @staticmethod
    def _check_financial_evidence(c: sqlite3.Connection, review: FinancialReview) -> None:
        """Verify accepted PDF/basis proofs against captured D6/D7 records in this transaction."""
        from app.documents.source_repository import evidence_digest
        from app.rag.parse.models import PDFLayout

        for proof in review.to_payload()["source_evidence"]:
            row = c.execute(
                "SELECT * FROM document_evidence WHERE evidence_id=? AND source_revision=?",
                (proof["evidence_id"], proof["source_revision"]),
            ).fetchone()
            if row is None:
                raise RevenueConfirmationError("confirmation_integrity_error")
            actual = dict(row)
            digest = actual.pop("payload_sha256")
            if digest != evidence_digest(actual["physical_page"], actual["text"], actual["kind"]):
                raise RevenueConfirmationError("confirmation_integrity_error")
            layout = c.execute(
                "SELECT * FROM document_evidence_layout WHERE evidence_id=?",
                (proof["evidence_id"],),
            ).fetchone()
            actual["layout"] = None
            if layout is not None:
                try:
                    if (
                        hashlib.sha256(layout["payload_json"].encode()).hexdigest()
                        != layout["payload_sha256"]
                    ):
                        raise ValueError("layout digest")
                    actual["layout"] = PDFLayout.model_validate_json(
                        layout["payload_json"]
                    ).model_dump(mode="json")
                except ValueError as exc:
                    raise RevenueConfirmationError("confirmation_integrity_error") from exc
            if actual != proof:
                raise RevenueConfirmationError("confirmation_integrity_error")

    def acceptance_review_for_request(
        self,
        *,
        workspace_id: str,
        document_id: str,
        company_id: str,
        request_id: str,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialReview:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            row = c.execute(
                "SELECT * FROM financial_acceptance_receipts WHERE workspace_id=? AND document_id=? "
                "AND company_id=? AND request_id=? AND confirmation_kind=?",
                (workspace_id, document_id, company_id, request_id, confirmation_kind),
            ).fetchone()
            if row is None:
                raise RevenueConfirmationError("acceptance_not_found")
            review = self._acceptance_from_row(
                row, FinancialReview(workspace_id, row["review_json"])
            ).review
            self._check_financial_document(c, review)
            self._check_financial_evidence(c, review)
            return review

    def acceptance_by_id(
        self, *, workspace_id: str, receipt_id: str, confirmation_kind: ConfirmationKind
    ) -> FinancialAcceptance:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            receipt = self._receipt_by_id(c, workspace_id, receipt_id, confirmation_kind)
            self._check_financial_document(c, receipt.review)
            self._check_financial_evidence(c, receipt.review)
            return receipt

    def acceptance_ids_for_scope(
        self, *, workspace_id: str, document_id: str, company_id: str,
        source_revision: str, metric_keys: tuple[str, ...], periods: tuple[int, ...],
        confirmation_kind: ConfirmationKind,
    ) -> tuple[str, ...]:
        # No recency heuristic, amount matching, extraction or writes. Each result
        # keeps its original request/snapshot identity and is rechecked by the service.
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            rows = c.execute(
                "SELECT * FROM financial_acceptance_receipts WHERE workspace_id=? "
                "AND document_id=? AND company_id=? AND confirmation_kind=? ORDER BY receipt_id",
                (workspace_id, document_id, company_id, confirmation_kind),
            ).fetchall()
            ids = []
            for row in rows:
                receipt = self._acceptance_from_row(row, FinancialReview(workspace_id, row["review_json"]))
                p = receipt.review.to_payload()
                if (p["source"]["source_revision"] != source_revision
                    or sorted(p["selection"]["metric_keys"]) != sorted(metric_keys)
                    or sorted(p["selection"]["periods"]) != sorted(periods)):
                    continue
                try:
                    self._check_receipt_active(c, workspace_id, receipt.receipt_id, confirmation_kind)
                except RevenueConfirmationError as exc:
                    if exc.code == "acceptance_revoked":
                        continue
                    raise
                ids.append(receipt.receipt_id)
            return tuple(ids)

    @staticmethod
    def _check_receipt_active(c: sqlite3.Connection, workspace_id: str, receipt_id: str,
                              confirmation_kind: ConfirmationKind) -> None:
        # D9/D10 migration fixtures and archived pre-D19 databases have no revocation
        # table. Only their known older schema may use the old qualification contract.
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_acceptance_revocations'").fetchone():
            if c.execute("SELECT max(version) FROM analyst_schema_migrations").fetchone()[0] >= 8:
                raise RevenueConfirmationError("confirmation_integrity_error")
            return
        if c.execute("SELECT 1 FROM financial_acceptance_revocations WHERE workspace_id=? AND receipt_id=? AND confirmation_kind=?",
                     (workspace_id,receipt_id,confirmation_kind)).fetchone():
            raise RevenueConfirmationError("acceptance_revoked")

    def revoke_financial_receipt(self, *, workspace_id: str, receipt_id: str,
                                 confirmation_kind: ConfirmationKind, reason: str) -> dict[str, Any]:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            # Permit repeat revocation of the same existing receipt; never replace its audit row.
            self._receipt_by_id(c,workspace_id,receipt_id,confirmation_kind,allow_revoked=True)
            c.execute("INSERT OR IGNORE INTO financial_acceptance_revocations VALUES(?,?,?,?,?)",
                      (workspace_id,receipt_id,confirmation_kind,datetime.now(UTC).isoformat(),reason))
            row = c.execute("SELECT * FROM financial_acceptance_revocations WHERE workspace_id=? AND receipt_id=? AND confirmation_kind=?",
                            (workspace_id,receipt_id,confirmation_kind)).fetchone()
            return dict(row)

    def _receipt_by_id(
        self,
        c: sqlite3.Connection,
        workspace_id: str,
        receipt_id: str,
        confirmation_kind: ConfirmationKind,
        *, allow_revoked: bool = False,
    ) -> FinancialAcceptance:
        row = c.execute(
            "SELECT * FROM financial_acceptance_receipts WHERE workspace_id=? AND receipt_id=? "
            "AND confirmation_kind=?",
            (workspace_id, receipt_id, confirmation_kind),
        ).fetchone()
        if row is None:
            raise RevenueConfirmationError("acceptance_not_found")
        if not allow_revoked:
            self._check_receipt_active(c,workspace_id,receipt_id,confirmation_kind)
        return self._acceptance_from_row(row, FinancialReview(workspace_id, row["review_json"]))

    @staticmethod
    def _disclosure_version(review: FinancialReview) -> str:
        return disclosure_version_for_source(review.to_payload()["source"])

    @staticmethod
    def _fact_rows(receipt: FinancialAcceptance) -> list[tuple[Any, ...]]:
        rows = []
        for candidate in sorted(
            receipt.review.to_payload()["candidates"], key=lambda c: (c["metric_key"], c["period"])
        ):
            value = Decimal(candidate["value_cny_yuan"])
            if not value.is_finite() or format(value, "f") != candidate["value_cny_yuan"]:
                raise RevenueConfirmationError("confirmation_integrity_error")
            fact_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, receipt.receipt_id + "/" + candidate["candidate_id"])
            )
            rows.append(
                (
                    fact_id,
                    receipt.receipt_id,
                    candidate["metric_key"],
                    candidate["period"],
                    candidate["period_type"],
                    candidate["period_start"],
                    candidate["period_end"],
                    candidate["raw_value"],
                    candidate["raw_unit"],
                    format(value, "f"),
                    "CNY_YUAN",
                    candidate["currency"],
                    candidate["scope"],
                    candidate["accounting_basis"],
                    candidate["candidate_id"],
                    canonical_payload(candidate),
                )
            )
        return rows

    @staticmethod
    def _set_digest(header: tuple[Any, ...], rows: list[tuple[Any, ...]]) -> str:
        return hashlib.sha256(
            canonical_payload(dict(header=header, facts=rows)).encode()
        ).hexdigest()

    def save_financial_facts(
        self,
        *,
        receipt_id: str,
        current_review: FinancialReview,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialFactSet:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            receipt = self._receipt_by_id(
                c, current_review.workspace_id, receipt_id, confirmation_kind
            )
            if (
                receipt.review.snapshot_id != current_review.snapshot_id
                or not current_review.acceptable
            ):
                raise RevenueConfirmationError("review_changed")
            self._check_financial_document(c, current_review)
            self._check_financial_evidence(c, current_review)
            exists = c.execute(
                "SELECT 1 FROM financial_fact_sets WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
            if exists is not None:
                return self._load_financial_facts(
                    c, current_review.workspace_id, receipt_id, confirmation_kind, False
                )
            rows = self._fact_rows(receipt)
            s = current_review.to_payload()["source"]
            header = (
                receipt_id,
                receipt_id,
                current_review.workspace_id,
                s["company_id"],
                s["document_id"],
                s["source_revision"],
                self._disclosure_version(current_review),
                current_review.snapshot_id,
                confirmation_kind,
                datetime.now(UTC).isoformat(),
                len(rows),
            )
            c.execute(
                "INSERT INTO financial_fact_sets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*header, self._set_digest(header, rows)),
            )
            c.executemany(
                "INSERT INTO confirmed_financial_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            # Full readback is inside the transaction; integrity/trigger failures roll back the entire set.
            return self._load_financial_facts(
                c, current_review.workspace_id, receipt_id, confirmation_kind, False
            )

    def _load_financial_facts(
        self,
        c: sqlite3.Connection,
        workspace_id: str,
        receipt_id: str,
        confirmation_kind: ConfirmationKind,
        include_invalid: bool,
    ) -> FinancialFactSet:
        header = c.execute(
            "SELECT * FROM financial_fact_sets WHERE workspace_id=? AND receipt_id=? AND confirmation_kind=?",
            (workspace_id, receipt_id, confirmation_kind),
        ).fetchone()
        if header is None:
            raise RevenueConfirmationError("facts_not_found")
        try:
            receipt = self._receipt_by_id(c, workspace_id, receipt_id, confirmation_kind, allow_revoked=True)
            rows = c.execute(
                "SELECT * FROM confirmed_financial_facts WHERE fact_set_id=? ORDER BY metric_key, period",
                (header["fact_set_id"],),
            ).fetchall()
            expected_rows = self._fact_rows(receipt)
            saved_at = datetime.fromisoformat(header["saved_at"])
            s = receipt.review.to_payload()["source"]
            expected_header = (
                receipt_id,
                receipt_id,
                workspace_id,
                s["company_id"],
                s["document_id"],
                s["source_revision"],
                self._disclosure_version(receipt.review),
                receipt.review.snapshot_id,
                confirmation_kind,
                header["saved_at"],
                len(expected_rows),
            )
            if (
                saved_at.tzinfo is None
                or tuple(header)[:-1] != expected_header
                or [tuple(row) for row in rows] != expected_rows
                or header["payload_sha256"] != self._set_digest(expected_header, expected_rows)
            ):
                raise ValueError("fact set integrity")
            self._check_financial_evidence(c, receipt.review)
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise RevenueConfirmationError("confirmation_integrity_error") from exc
        current_valid, invalid_reason = True, None
        try:
            self._check_receipt_active(c,workspace_id,receipt_id,confirmation_kind)
            self._check_financial_document(c, receipt.review)
        except RevenueConfirmationError as exc:
            if not include_invalid:
                raise
            current_valid, invalid_reason = False, exc.code
        return FinancialFactSet(
            receipt_id,
            receipt,
            header["disclosure_version"],
            saved_at,
            tuple(ConfirmedFinancialFact(row[0], row[1], row[-1]) for row in expected_rows),
            current_valid,
            invalid_reason,
        )

    def load_financial_facts(
        self,
        *,
        workspace_id: str,
        receipt_id: str,
        confirmation_kind: ConfirmationKind,
        include_invalid: bool = False,
    ) -> FinancialFactSet:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            return self._load_financial_facts(
                c, workspace_id, receipt_id, confirmation_kind, include_invalid
            )

    def query_financial_fact_sets(
        self,
        *,
        workspace_id: str,
        confirmation_kind: ConfirmationKind,
        company_id: str,
        period: int | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        metric_key: str | None = None,
        scope: str = "consolidated",
        document_id: str | None = None,
        disclosure_version: str | None = None,
        source_revision: str | None = None,
        include_invalid: bool = False,
    ) -> tuple[FinancialFactSet, ...]:
        clauses = ["g.workspace_id=?", "g.confirmation_kind=?", "g.company_id=?"]
        params: list[Any] = [workspace_id, confirmation_kind, company_id]
        for column, value in (
            ("g.document_id", document_id),
            ("g.disclosure_version", disclosure_version),
            ("g.source_revision", source_revision),
        ):
            if value is not None:
                clauses.append(column + "=?")
                params.append(value)
        with closing(self._connect()) as c, c:
            c.execute("BEGIN")
            SQLiteCompanyRepository._company(c, workspace_id, company_id)
            keys = c.execute(
                "SELECT g.receipt_id FROM financial_fact_sets g WHERE "
                + " AND ".join(clauses)
                + " ORDER BY g.receipt_id",
                params,
            ).fetchall()
            # Always check each complete set, including rows outside the requested metric filter.
            groups = [
                self._load_financial_facts(c, workspace_id, row[0], confirmation_kind, True)
                for row in keys
            ]
            return tuple(
                g
                for g in groups
                if (include_invalid or g.current_valid)
                and any(
                    all(
                        value is None or fact.to_payload()[key] == value
                        for key, value in (
                            ("period", period),
                            ("period_start", period_start),
                            ("period_end", period_end),
                            ("metric_key", metric_key),
                            ("scope", scope),
                        )
                    )
                    for fact in g.facts
                )
            )

    def _connect(self) -> sqlite3.Connection:
        """每次创建短连接，启用外键；连接由调用方关闭。"""
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _check_document(connection: sqlite3.Connection, review: RevenueReview) -> None:
        """在当前事务中核对文档状态和版本，防止查证后官方状态已变化。"""
        revision = review.revision
        row = connection.execute(
            "SELECT workspace_id, content_sha256, attempt, status FROM documents "
            "WHERE document_id = ?",
            (revision.document_id,),
        ).fetchone()
        if row is None or (
            row["workspace_id"],
            row["content_sha256"],
            row["attempt"],
            row["status"],
        ) != (revision.workspace_id, revision.content_sha256, revision.attempt, "ready"):
            raise RevenueConfirmationError("source_changed")

    def save(
        self, *, review: RevenueReview, confirmation_kind: ConfirmationKind
    ) -> RevenueConfirmation:
        """事务保存整组确认；相同有效快照返回原记录，任一写入失败全部回滚。"""
        if confirmation_kind not in ("local_operator", "simulated_test"):
            raise RevenueConfirmationError("confirmation_required")
        revision = review.revision
        with closing(self._connect()) as connection:
            with connection:
                # 在同库锁定写事务，先核对文档，再写确认头和两条事实。
                connection.execute("BEGIN IMMEDIATE")
                self._check_document(connection, review)
                existing = connection.execute(
                    "SELECT confirmation_id FROM revenue_confirmations WHERE snapshot_id = ?",
                    (review.snapshot_id,),
                ).fetchone()
                if existing is not None:
                    confirmation = self._load(connection, str(existing["confirmation_id"]), review)
                    if confirmation.confirmation_kind != confirmation_kind:
                        raise RevenueConfirmationError("confirmation_kind_mismatch")
                    return confirmation
                confirmation_id = str(uuid.uuid4())
                confirmed_at = datetime.now(UTC)
                connection.execute(
                    "INSERT INTO revenue_confirmations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        confirmation_id,
                        review.snapshot_id,
                        revision.workspace_id,
                        revision.document_id,
                        revision.content_sha256,
                        revision.attempt,
                        revision.extraction_method,
                        revision.extraction_version,
                        confirmed_at.isoformat(),
                        confirmation_kind,
                    ),
                )
                for candidate in sorted(review.candidates, key=lambda item: item.period):
                    evidence = [
                        {
                            "chunk_id": item.chunk_id,
                            "source_file": item.source_file,
                            "page": item.page,
                            "text": item.text,
                            "start": item.start,
                            "end": item.end,
                            "raw_value": item.raw_value,
                            "raw_unit": item.raw_unit,
                        }
                        for item in candidate.evidence
                    ]
                    connection.execute(
                        "INSERT INTO confirmed_revenue_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            confirmation_id,
                            "revenue",
                            candidate.period,
                            candidate.source_ref,
                            format(candidate.value, "f"),
                            "CNY_YUAN",
                            candidate.chunk_id,
                            candidate.source_file,
                            candidate.page,
                            json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                return self._load(connection, confirmation_id, review)

    def _load(
        self, connection: sqlite3.Connection, confirmation_id: str, current_review: RevenueReview
    ) -> RevenueConfirmation:
        """同一读快照恢复确认与两条事实，重新计算摘要检测缺行/损坏/来源变化。"""
        revision = current_review.revision
        header = connection.execute(
            "SELECT * FROM revenue_confirmations WHERE confirmation_id = ? "
            "AND workspace_id = ? AND document_id = ?",
            (confirmation_id, revision.workspace_id, revision.document_id),
        ).fetchone()
        if header is None:
            raise RevenueConfirmationError("confirmation_required")
        rows = connection.execute(
            "SELECT * FROM confirmed_revenue_facts WHERE confirmation_id = ? ORDER BY period",
            (confirmation_id,),
        ).fetchall()
        try:
            if len(rows) != 2:
                raise ValueError("确认事实不完整")
            stored_revision = RevenueSourceRevision(
                workspace_id=header["workspace_id"],
                document_id=header["document_id"],
                content_sha256=header["content_sha256"],
                attempt=header["attempt"],
                extraction_method=header["extraction_method"],
                extraction_version=header["extraction_version"],
            )
            candidates: list[RevenueCandidate] = []
            for row in rows:
                evidence = json.loads(row["evidence_json"])
                if not isinstance(evidence, list) or row["fact_key"] != "revenue":
                    raise ValueError("确认记录结构非法")
                value = Decimal(row["value_text"])
                if format(value, "f") != row["value_text"]:
                    raise ValueError("金额不是规范十进制文本")
                candidates.append(
                    RevenueCandidate(
                        workspace_id=stored_revision.workspace_id,
                        document_id=stored_revision.document_id,
                        source_ref=row["source_ref"],
                        chunk_id=row["chunk_id"],
                        source_file=row["source_file"],
                        page=row["page"],
                        period=row["period"],
                        value=value,
                        unit=FinancialUnit(row["unit"]),
                        evidence=tuple(RevenueEvidence(**item) for item in evidence),
                        extraction_method=stored_revision.extraction_method,
                        extraction_version=stored_revision.extraction_version,
                    )
                )
            stored_review = RevenueReview(stored_revision, tuple(candidates))
            confirmed_at = datetime.fromisoformat(header["confirmed_at"])
            kind = header["confirmation_kind"]
            if confirmed_at.tzinfo is None or kind not in ("local_operator", "simulated_test"):
                raise ValueError("确认动作元数据非法")
            if stored_review.snapshot_id != header["snapshot_id"]:
                raise ValueError("确认内容摘要不匹配")
        except (ValueError, TypeError, KeyError, ArithmeticError, RevenueConfirmationError) as exc:
            raise RevenueConfirmationError("confirmation_integrity_error") from exc
        if stored_review.snapshot_id != current_review.snapshot_id:
            raise RevenueConfirmationError("source_changed")
        return RevenueConfirmation(confirmation_id, confirmed_at, kind, stored_review)

    def load(self, *, confirmation_id: str, current_review: RevenueReview) -> RevenueConfirmation:
        """只有完整且匹配当前来源的确认可以读回；历史记录仍保留，不回退旧值。"""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN")
                self._check_document(connection, current_review)
                return self._load(connection, confirmation_id, current_review)

    def fact_repository(
        self, *, confirmation_id: str, current_review: RevenueReview
    ) -> FinancialFactRepository:
        """为本次已查证计算创建范围受限的 SQLite 查询适配器，不注册进 runtime。"""
        return _CheckedSQLiteFinancialFacts(self, confirmation_id, current_review)


class _CheckedSQLiteFinancialFacts(FinancialFactRepository):
    """一次计算专用查询；每次查事实均整组读回，拒绝跨文档或跨指标引用。"""

    def __init__(
        self,
        repository: SQLiteRevenueConfirmationRepository,
        confirmation_id: str,
        current_review: RevenueReview,
    ) -> None:
        self._repository = repository
        self._confirmation_id = confirmation_id
        self._current_review = current_review

    def find_fact(
        self,
        *,
        execution_context: ToolExecutionContext,
        source_ref: str,
        fact_key: FinancialFactKey,
    ) -> FinancialFact | None:
        """从已保存确认读取金额；上下文必须匹配本次服务端核准的范围。"""
        revision = self._current_review.revision
        filters = execution_context.filters
        if (
            execution_context.trusted_context.workspace_id != revision.workspace_id
            or filters is None
            or filters.document_id != revision.document_id
            or fact_key is not FinancialFactKey.REVENUE
        ):
            return None
        confirmation = self._repository.load(
            confirmation_id=self._confirmation_id, current_review=self._current_review
        )
        for item in confirmation.confirmed_facts():
            if item.fact.source_ref == source_ref:
                return item.fact
        return None
