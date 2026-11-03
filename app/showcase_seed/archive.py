"""Read-only historical snapshots with independent, current source checks."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


class ArchiveError(Exception):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


def digest(value):
    return digest_text(canonical(value))


def read_db(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


class ShowcaseArchiveService:
    def __init__(self, runtime_root: Path, *, sources, workspace_id="demo", parse_service=None):
        self.root = runtime_root.resolve()
        if (
            sources.repository.registry._database_path.resolve() != self.root / "documents.db"
            or not workspace_id
        ):
            raise ValueError("Archive source runtime mismatch")
        self.path, self.sources, self.workspace, self.parse = (
            self.root / "showcase-archive.db",
            sources,
            workspace_id,
            parse_service,
        )

    def _rows(self, kind=None, archive_id=None, revision=None, limit=20):
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise ArchiveError("archive_symlink_forbidden", 503)
        with closing(read_db(self.path)) as db:
            rows = db.execute(
                "SELECT * FROM archive_items WHERE workspace=? AND (? IS NULL OR kind=?) "
                "AND (? IS NULL OR archive_id=?) AND (? IS NULL OR revision=?) ORDER BY saved_at DESC,archive_id LIMIT ?",
                (self.workspace, kind, kind, archive_id, archive_id, revision, revision, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = json.loads(row["payload"])
            if digest(item) != row["sha256"] or item["archive_id"] != row["archive_id"]:
                raise ArchiveError("archive_integrity_error", 503)
            provenance = item["provenance"]
            if (
                digest_text(provenance["original_scope_json"])
                != provenance["original_scope_sha256"]
                or digest_text(provenance["original_result_json"])
                != provenance["original_result_sha256"]
            ):
                raise ArchiveError("archive_provenance_corrupt", 503)
            if (
                item["kind"] == "report"
                and digest_text(provenance["original_report_payload_json"])
                != provenance["original_report_payload_sha256"]
            ):
                raise ArchiveError("archive_report_provenance_corrupt", 503)
            result.append(item)
        return result

    async def _current(self, item, cache):
        scope = json.loads(item["provenance"]["original_scope_json"])
        sources = scope.get("sources")
        if not isinstance(sources, list) or not sources:
            return "unavailable", [{"status": "unavailable", "reason": "original_sources_unknown"}]
        states = []
        for expected in sources:
            key = digest(expected)
            if key not in cache:
                status, reason = "current", None
                try:
                    if expected.get("workspace_id") != self.workspace:
                        raise ArchiveError("source_workspace_mismatch")
                    current = await self.sources.source(
                        expected["document_id"],
                        company_id=expected["company_id"],
                        source_revision=expected["source_revision"],
                    )
                    if any(
                        current.get(k) != expected.get(k)
                        for k in (
                            "document_id",
                            "company_id",
                            "source_revision",
                            "content_sha256",
                            "parser_version",
                            "attempt",
                            "report_year",
                            "report_type",
                            "period_start",
                            "period_end",
                            "basis",
                        )
                    ):
                        raise ArchiveError("source_identity_changed")
                except Exception as exc:
                    reason = getattr(exc, "code", "source_check_failed")
                    code_status = getattr(exc, "status", None)
                    status = (
                        "stale"
                        if code_status == 409
                        or reason
                        in ("source_changed", "selection_changed", "source_identity_changed")
                        else "unavailable"
                    )
                cache[key] = {
                    "document_id": expected.get("document_id"),
                    "source_revision": expected.get("source_revision"),
                    "content_sha256": expected.get("content_sha256"),
                    "status": status,
                    "reason": reason,
                }
            states.append(cache[key])
        if all(state["status"] == "current" for state in states):
            findings = (
                item["snapshot"].get("findings", [])
                if item["kind"] == "job"
                else item["snapshot"].get("snapshot", {}).get("findings", [])
            )
            for finding in findings:
                if finding.get("kind") == "confirmed_financial" or finding.get("financial_refs"):
                    states.append(
                        {"status": "unavailable", "reason": "archive_financial_authority_forbidden"}
                    )
                    continue
                for ref in finding.get("evidence_refs", []):
                    try:
                        expected = next(
                            d for d in sources if d["document_id"] == ref["document_id"]
                        )
                        if any(
                            ref.get(k) != expected.get(k)
                            for k in (
                                "company_id",
                                "source_revision",
                                "content_sha256",
                                "parser_version",
                            )
                        ):
                            raise ArchiveError("quote_identity_changed")
                        if ref.get("artifact_id"):
                            if self.parse is None:
                                raise ArchiveError("archive_artifact_verifier_unavailable", 503)
                            artifact = await self.parse.quality(
                                ref["document_id"], ref["artifact_id"]
                            )
                            if (
                                artifact["source_status"] != "current"
                                or artifact["source_revision"] != ref["source_revision"]
                            ):
                                raise ArchiveError("artifact_changed")
                            page = next(
                                p
                                for p in artifact["pages"]
                                if p["physical_page"] == ref["physical_page"]
                            )
                            if ref["text"] not in page["text"]:
                                raise ArchiveError("quote_text_changed")
                        else:
                            record = await self.sources.evidence(
                                ref["document_id"],
                                ref["evidence_id"],
                                source_revision=ref["source_revision"],
                                company_id=ref["company_id"],
                            )
                            if (
                                record["physical_page"] != ref["physical_page"]
                                or ref["text"] not in record["text"]
                            ):
                                raise ArchiveError("quote_text_changed")
                    except Exception as exc:
                        reason = getattr(exc, "code", "archive_quote_unverified")
                        status = (
                            "stale"
                            if reason
                            in (
                                "quote_identity_changed",
                                "quote_text_changed",
                                "artifact_changed",
                                "source_changed",
                            )
                            else "unavailable"
                        )
                        states.append(
                            {
                                "document_id": ref.get("document_id"),
                                "status": status,
                                "reason": reason,
                            }
                        )
        aggregate = (
            "unavailable"
            if any(s["status"] == "unavailable" for s in states)
            else "stale"
            if any(s["status"] == "stale" for s in states)
            else "current"
        )
        return aggregate, states

    async def _project(self, item, cache, *, summary=False):
        status, states = await self._current(item, cache)
        snapshot = item["snapshot"]
        result = {
            "schema_version": "showcase-archive-item-v1",
            "archive_id": item["archive_id"],
            "kind": item["kind"],
            "original_id": item["original_id"],
            "revision": item["revision"],
            "data_origin": "preset_demo",
            "original_data_origin": item["original_data_origin"],
            "historical_snapshot": True,
            "label": "预置演示案例",
            "notice": "历史已保存结果；当前请求未调用模型，不提供计划、接管或恢复权限。",
            "title": snapshot.get("title", snapshot.get("goal", "预置演示案例")),
            "saved_at": item["saved_at"],
            "current_source_status": status,
            "source_checked_at": datetime.now(timezone.utc).isoformat(),
            "current_sources": states,
            "capabilities": {"plan": False, "handoff": False, "resume": False, "regenerate": False},
        }
        if summary:
            result["provenance_sha256"] = digest(item["provenance"])
        else:
            result.update(snapshot=snapshot, provenance=item["provenance"])
        return result

    async def list(self, *, kind=None, limit=20):
        if kind not in (None, "job", "report") or not 1 <= limit <= 20:
            raise ArchiveError("invalid_archive_query", 422)
        cache = {}
        return {
            "schema_version": "showcase-archive-list-v1",
            "data_origin": "preset_demo",
            "items": [
                await self._project(item, cache, summary=True)
                for item in self._rows(kind=kind, limit=limit)
            ],
            "limitations": [] if self.path.exists() else ["archive_not_installed"],
        }

    async def job(self, archive_id):
        rows = self._rows(kind="job", archive_id=archive_id)
        if not rows:
            raise ArchiveError("archive_not_found", 404)
        return await self._project(rows[0], {})

    async def report(self, archive_id, revision):
        rows = self._rows(kind="report", archive_id=archive_id, revision=revision)
        if not rows:
            raise ArchiveError("archive_not_found", 404)
        return await self._project(rows[0], {})
