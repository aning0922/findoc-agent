"""Immutable two-year source comparison. No financial authority or provider construction."""

from contextlib import closing, contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4

from app.retrieval_v2.models import EvidenceRef, SourceRef
from app.retrieval_v2.service import canonical, resolve, sha
from .models import AnnualDiffError, AnnualDiffRequest

QUERIES = {
    "经营风险": "主要经营风险 原材料价格 市场竞争 海外市场",
    "主要业务": "公司主要业务 主要产品 主营业务",
    "研发": "研发投入 研发项目 技术创新",
}
MARKERS = {
    "经营风险": ("主要风险", "经营风险", "市场竞争", "原材料", "海外市场", "风险因素"),
    "主要业务": ("主要业务", "主营业务", "主要产品", "核心业务"),
    "研发": ("研发", "技术创新", "研发项目"),
}


class AnnualDiffService:
    def __init__(
        self,
        runtime_root,
        *,
        hybrid,
        sources,
        identity_validator,
        publication_guard,
        provider_json=None,
        memory=None,
    ):
        self.root = Path(runtime_root).resolve()
        if (
            hybrid.root != self.root
            or hybrid.sources is not sources
            or sources.documents._repository._database_path.resolve() != self.root / "documents.db"
        ):
            raise ValueError("annual_diff_runtime_mismatch")
        self.hybrid, self.sources = hybrid, sources
        self.identity_validator, self.guard, self.provider = (
            identity_validator,
            publication_guard,
            provider_json,
        )
        self.memory = memory if memory is not None else hybrid.memory
        self.path = self.root / "annual-diff.db"
        with self.tx() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,owner TEXT,digest TEXT,state TEXT,result_id TEXT,error_code TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,owner TEXT,payload TEXT)"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON results BEGIN SELECT RAISE(ABORT,'immutable'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON results BEGIN SELECT RAISE(ABORT,'immutable'); END"
            )
        self.path.chmod(0o600)

    @contextmanager
    def tx(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    async def owner(self, identity):
        if (
            self.identity_validator is None
            or identity.expires_at <= time.time()
            or identity.workspace_id != self.sources.documents.workspace_id
        ):
            raise AnnualDiffError("trusted_identity_required", 403)
        if await resolve(self.identity_validator(identity)) is False:
            raise AnnualDiffError("identity_rejected", 403)
        return sha(identity.model_dump())

    def generation(self):
        if self.memory is None:
            return None
        with self.memory.tx() as db:
            return self.memory._generation(db)

    async def validate_scope(self, left, right, identity, generation):
        if left.kind != "fast" or right.kind != "fast":
            raise AnnualDiffError("fast_sources_required", 422)
        if (
            left.company_id != right.company_id
            or left.workspace_id != right.workspace_id
            or left.workspace_id != identity.workspace_id
        ):
            raise AnnualDiffError("same_company_scope_required", 422)
        if (
            left.report_year == right.report_year
            or left.document_id == right.document_id
            or left.source_revision == right.source_revision
        ):
            raise AnnualDiffError("distinct_year_versions_required", 422)
        await self.hybrid.records(left)
        await self.hybrid.records(right)
        if self.memory is not None:
            self.memory.check_generation(generation)
        await self.owner(identity)

    def operation_record(self, op, owner):
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=? AND owner=?", (op, owner)
            ).fetchone()
            if not row:
                raise AnnualDiffError("operation_not_found", 404)
            result = (
                db.execute(
                    "SELECT payload FROM results WHERE id=? AND owner=?", (row["result_id"], owner)
                ).fetchone()
                if row["result_id"]
                else None
            )
        return dict(
            operation_id=op,
            state=row["state"],
            result_id=row["result_id"],
            error_code=row["error_code"],
            result=json.loads(result[0]) if result else None,
        )

    async def operation(self, op, identity):
        return self.operation_record(op, await self.owner(identity))

    async def read(self, result_id, identity):
        owner = await self.owner(identity)
        with self.tx() as db:
            row = db.execute(
                "SELECT payload FROM results WHERE id=? AND owner=?", (result_id, owner)
            ).fetchone()
        if not row:
            raise AnnualDiffError("result_not_found", 404)
        value = json.loads(row[0])
        status = "current"
        try:
            await self.hybrid.records(SourceRef.model_validate(value["left_source"]))
            await self.hybrid.records(SourceRef.model_validate(value["right_source"]))
        except Exception:
            status = "stale_or_unavailable"
        return {**value, "current_source_status": status, "historical_snapshot": True}

    async def side(self, ref, topic):
        diagnostics = await self.hybrid.search([ref], QUERIES[topic], top_k=5)
        refs = []
        for item in diagnostics["items"]:
            evidence = EvidenceRef.model_validate(item["evidence_ref"])
            if evidence.source_ref != ref:
                raise AnnualDiffError("retrieval_outside_selected_source")
            if not any(word in evidence.text for word in MARKERS[topic]):
                continue
            if item.get("lexical_rank") is None and (item.get("dense_cosine") or 0) < 0.55:
                continue
            if item.get("rerank_score", 0) < 0.015:
                continue
            # Exact bounded excerpts, never normalize or fabricate words.
            if len(evidence.text) > 1600:
                positions = [evidence.text.find(w) for w in MARKERS[topic] if w in evidence.text]
                start = max(0, min(positions) - 100)
                evidence = evidence.model_copy(update={"text": evidence.text[start : start + 1600]})
            await self.hybrid.verify(evidence)
            refs.append(evidence.model_dump())
            if len(refs) == 2:
                break
        return dict(
            state="available" if refs else "missing_in_retrieval",
            evidence_refs=refs,
            index_status=diagnostics["index_status"],
            semantic_review_status="human_pending",
        )

    async def create(self, request: AnnualDiffRequest, identity):
        owner = await self.owner(identity)
        try:
            if str(UUID(request.operation_id)) != request.operation_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise AnnualDiffError("invalid_operation", 422) from None
        body = request.model_dump()
        digest = sha(body)
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=?", (request.operation_id,)
            ).fetchone()
            if row:
                if row["owner"] != owner or row["digest"] != digest:
                    raise AnnualDiffError("operation_conflict")
            else:
                db.execute(
                    "INSERT INTO operations VALUES (?,?,?,'unknown',NULL,NULL)",
                    (request.operation_id, owner, digest),
                )
        if row:
            return self.operation_record(request.operation_id, owner)
        try:
            if self.guard is None:
                raise AnnualDiffError("publication_guard_required", 503)
            if len(set(request.topics)) != len(request.topics):
                raise AnnualDiffError("duplicate_topics", 422)
            generation = self.generation()
            left, right = request.left_source, request.right_source
            await self.validate_scope(left, right, identity, generation)
            fence = dict(
                selected_sources=[left.model_dump(), right.model_dump()],
                memory_generation=generation,
                operation_id=request.operation_id,
                request_sha256=digest,
            )
            pairs = []
            for topic in request.topics:
                lhs, rhs = await self.side(left, topic), await self.side(right, topic)
                complete = lhs["state"] == rhs["state"] == "available"
                identical = complete and [e["text"] for e in lhs["evidence_refs"]] == [
                    e["text"] for e in rhs["evidence_refs"]
                ]
                pairs.append(
                    dict(
                        topic=topic,
                        left=lhs,
                        right=rhs,
                        program_label="continued"
                        if identical
                        else "comparison_required"
                        if complete
                        else "insufficient",
                        label_basis="exact_excerpt_equality"
                        if identical
                        else "two_sided_evidence"
                        if complete
                        else "missing_in_retrieval",
                        explanation=None,
                        ai_label=None,
                        interpretation_review_status="not_generated",
                    )
                )
            provider_outcome = "not_requested"
            eligible = [p for p in pairs if p["program_label"] == "comparison_required"]
            if request.generate_explanation and eligible:
                provider_outcome = "unconfigured"
                if self.provider is not None:
                    await self.validate_scope(left, right, identity, generation)
                    with self.guard(identity, fence):
                        pass
                    draft = await resolve(self.provider(eligible, identity))
                    provider_outcome = "returned"
                    if (
                        not isinstance(draft, dict)
                        or set(draft) != {"topics"}
                        or not isinstance(draft["topics"], list)
                    ):
                        raise AnnualDiffError("invalid_provider_json")
                    seen = set()
                    for entry in draft["topics"]:
                        if not isinstance(entry, dict) or set(entry) != {
                            "topic",
                            "label",
                            "explanation",
                            "evidence_ids",
                        }:
                            raise AnnualDiffError("invalid_provider_topic")
                        pair = next((p for p in eligible if p["topic"] == entry["topic"]), None)
                        if (
                            pair is None
                            or entry["topic"] in seen
                            or entry["label"]
                            not in (
                                "wording_changed",
                                "new_disclosure_candidate",
                                "continued",
                                "insufficient",
                            )
                            or not isinstance(entry["explanation"], str)
                            or len(entry["explanation"]) > 2000
                            or not isinstance(entry["evidence_ids"], list)
                        ):
                            raise AnnualDiffError("invalid_provider_topic")
                        seen.add(entry["topic"])
                        ids = entry["evidence_ids"]
                        left_ids = {e["evidence_id"] for e in pair["left"]["evidence_refs"]}
                        right_ids = {e["evidence_id"] for e in pair["right"]["evidence_refs"]}
                        if (
                            any(
                                not isinstance(v, str) or v not in left_ids | right_ids for v in ids
                            )
                            or not left_ids.intersection(ids)
                            or not right_ids.intersection(ids)
                        ):
                            raise AnnualDiffError("two_sided_citations_required")
                        pair.update(
                            ai_label=entry["label"],
                            explanation=entry["explanation"],
                            interpretation_review_status="ai_unreviewed",
                            ai_evidence_ids=ids,
                        )
            elif request.generate_explanation:
                provider_outcome = "not_called_insufficient_or_identical"
            await self.validate_scope(left, right, identity, generation)
            for pair in pairs:
                for side in ("left", "right"):
                    for ref in pair[side]["evidence_refs"]:
                        await self.hybrid.verify(EvidenceRef.model_validate(ref))
            result = dict(
                schema_version="annual-diff-v1",
                result_id=str(uuid4()),
                left_source=left.model_dump(),
                right_source=right.model_dump(),
                topics=pairs,
                request_sha256=digest,
                memory_generation=generation,
                provider_outcome=provider_outcome,
                data_origin="source_backed",
                source_status="current",
                source_status_scope="validated_at_creation",
                historical_snapshot=True,
                transcription_review_status="fast_extraction_unreviewed",
                financial_authority=False,
                created_at=datetime.now(UTC).isoformat(),
                limitations=[
                    "缺少检索证据不表示业务取消或未披露。",
                    "双侧摘录有主题词不等于完整语义对齐，仍需人工审阅。",
                    "AI标签、原因和数值解释均待审核，不构成财务确认。",
                ],
            )
            result["payload_sha256"] = sha(result)
            with self.guard(identity, fence):
                with self.tx() as db:
                    db.execute(
                        "INSERT INTO results VALUES (?,?,?)",
                        (result["result_id"], owner, canonical(result)),
                    )
                    db.execute(
                        "UPDATE operations SET state='completed',result_id=? WHERE id=?",
                        (result["result_id"], request.operation_id),
                    )
            return self.operation_record(request.operation_id, owner)
        except Exception as exc:
            with self.tx() as db:
                db.execute(
                    "UPDATE operations SET error_code=? WHERE id=?",
                    (getattr(exc, "code", "execution_unknown"), request.operation_id),
                )
            raise
