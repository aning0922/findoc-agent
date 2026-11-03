from contextlib import contextmanager
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from uuid import UUID, uuid4

from .models import Candidate, EvidenceRef, RetrievalError, SourceRef


def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(v):
    return hashlib.sha256(canonical(v).encode()).hexdigest()


async def resolve(v):
    return await v if inspect.isawaitable(v) else v


class HybridRetrievalService:
    def __init__(
        self,
        runtime_root,
        sources,
        parse_service,
        dense_search,
        embedder=None,
        embedding_model_version="unknown",
        memory=None,
        provider_once=None,
        identity_validator=None,
        publication_guard=None,
        parent_validator=None,
        before_commit=None,
    ):
        self.root = Path(runtime_root).resolve()
        if sources.documents._repository._database_path.resolve() != self.root / "documents.db":
            raise ValueError("retrieval_runtime_mismatch")
        if parse_service is not None and (
            parse_service.root != self.root or parse_service.sources is not sources
        ):
            raise ValueError("parse_runtime_mismatch")
        self.sources, self.parse = sources, parse_service
        self.dense_search, self.embedder, self.model_version = (
            dense_search,
            embedder,
            embedding_model_version,
        )
        self.memory, self.provider = memory, provider_once
        self.identity_validator, self.guard, self.parent_validator = (
            identity_validator,
            publication_guard,
            parent_validator,
        )
        self.before_commit = before_commit
        self.path = self.root / "cplus-research.db"
        with self.tx() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,kind TEXT,owner TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,owner TEXT,digest TEXT,state TEXT,result TEXT);
            CREATE TABLE IF NOT EXISTS manifests(source_key TEXT PRIMARY KEY,payload TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(source_key UNINDEXED,evidence UNINDEXED,text,tokenize='trigram');
            CREATE TRIGGER IF NOT EXISTS no_object_update BEFORE UPDATE ON objects BEGIN SELECT RAISE(ABORT,'immutable'); END;
            CREATE TRIGGER IF NOT EXISTS no_object_delete BEFORE DELETE ON objects BEGIN SELECT RAISE(ABORT,'immutable'); END;""")
        self.path.chmod(0o600)

    @contextmanager
    def tx(self, *, before_commit=None):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db
                if before_commit is not None:
                    before_commit()
        finally:
            db.close()

    def commit_check(self, identity):
        """Synchronous controller identity check inside our write transaction, before COMMIT."""
        if self.before_commit is None:
            raise RetrievalError("before_commit_required", 503)
        if identity.expires_at <= time.time():
            raise RetrievalError("lease_expired", 401)
        value = self.before_commit(identity)
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise RetrievalError("synchronous_commit_check_required", 503)
        if value is False or identity.expires_at <= time.time():
            raise RetrievalError("identity_rejected_at_commit", 403)

    async def authorize(self, identity):
        if self.identity_validator is None or identity.expires_at <= time.time():
            raise RetrievalError("trusted_identity_required", 403)
        if await resolve(self.identity_validator(identity)) is False:
            raise RetrievalError("identity_rejected", 403)
        if identity.workspace_id != self.sources.documents.workspace_id:
            raise RetrievalError("workspace_mismatch", 403)
        return sha(identity.model_dump())

    async def records(self, ref):
        if ref.workspace_id != self.sources.documents.workspace_id:
            raise RetrievalError("workspace_mismatch", 403)
        if ref.kind == "fast":
            if (
                ref.identity_status != "fast_source_verified"
                or ref.artifact_id
                or ref.selected_pages
            ):
                raise RetrievalError("invalid_fast_ref", 422)
            source, records = await self.sources.parsed_evidence(
                ref.document_id, company_id=ref.company_id, source_revision=ref.source_revision
            )
            if any(
                source[k] != getattr(ref, k)
                for k in ("content_sha256", "parser_version", "company_id", "report_year")
            ):
                raise RetrievalError("source_changed")
            for field in ("attempt", "report_type", "basis", "period_start", "period_end"):
                if getattr(ref, field) is None or source.get(field) != getattr(ref, field):
                    raise RetrievalError("full_fast_identity_required", 422)
            return [
                EvidenceRef(
                    source_ref=ref,
                    evidence_id=r["evidence_id"],
                    physical_page=r["physical_page"],
                    text=r["text"],
                )
                for r in records
            ]
        if (
            self.parse is None
            or not ref.artifact_id
            or not ref.selected_pages
            or len(set(ref.selected_pages)) != len(ref.selected_pages)
            or ref.identity_status != "file_transcription_only"
        ):
            raise RetrievalError("explicit_artifact_required", 422)
        value = await self.parse.quality(ref.document_id, ref.artifact_id)
        if (
            value["source_status"] != "current"
            or value["state"] != "completed"
            or any(
                value[k] != getattr(ref, k)
                for k in (
                    "source_revision",
                    "content_sha256",
                    "parser_version",
                    "company_id",
                    "report_year",
                    "config_hash",
                    "metadata_sha256",
                )
            )
            or value["output_sha256"] != ref.artifact_sha256
        ):
            raise RetrievalError("artifact_changed")
        result = []
        for n in ref.selected_pages:
            pages = [
                p for p in value["pages"] if p["physical_page"] == n and p["status"] == "completed"
            ]
            if len(pages) != 1:
                raise RetrievalError("page_unavailable")
            for i, line in enumerate(pages[0].get("lines", [])):
                result.append(
                    EvidenceRef(
                        source_ref=ref,
                        evidence_id=f"{ref.artifact_id}:{n}:{i}",
                        physical_page=n,
                        line_index=i,
                        text=line["text"],
                        bbox=[float(x) for x in line["bbox"]] if line.get("bbox") else None,
                    )
                )
        return result

    async def verify(self, evidence):
        records = await self.records(evidence.source_ref)
        if not any(
            e.source_ref == evidence.source_ref
            and e.evidence_id == evidence.evidence_id
            and e.physical_page == evidence.physical_page
            and e.line_index == evidence.line_index
            and e.bbox == evidence.bbox
            and evidence.text
            and evidence.text in e.text
            for e in records
        ):
            raise RetrievalError("exact_evidence_unverified")
        if evidence.source_ref.kind == "fast":
            await self.sources.page_context(
                evidence.source_ref.document_id,
                evidence.source_ref.source_revision,
                evidence.physical_page,
            )
        return evidence

    async def prepare_build(self, refs):
        if not 1 <= len(refs) <= 4:
            raise RetrievalError("source_limit", 422)
        batches = [(r, await self.records(r)) for r in refs]
        if sum(len(v) for _, v in batches) > 6000:
            raise RetrievalError("index_budget_exceeded", 422)
        return batches

    def write_build(self, db, batches):
        for ref, records in batches:
            key = sha(ref.model_dump())
            db.execute("DELETE FROM passages WHERE source_key=?", (key,))
            db.executemany(
                "INSERT INTO passages VALUES (?,?,?)",
                [(key, e.model_dump_json(), e.text) for e in records],
            )
            db.execute(
                "INSERT OR REPLACE INTO manifests VALUES (?,?)", (key, ref.model_dump_json())
            )

    def build_result(self, batches):
        return dict(
            state="completed",
            indexed_passages=sum(len(v) for _, v in batches),
            embedding_model_version=self.model_version,
        )

    async def build(self, refs, *, identity):
        await self.authorize(identity)
        self.commit_check(identity)
        if self.guard is None:
            raise RetrievalError("publication_guard_required", 503)
        batches = await self.prepare_build(refs)
        with self.guard(identity, dict(selected_sources=[r.model_dump() for r in refs])):
            with self.tx(before_commit=lambda: self.commit_check(identity)) as db:
                self.write_build(db, batches)
        return self.build_result(batches)

    async def search(self, refs, query, top_k=5, *, _legacy=False):
        if not 1 <= len(refs) <= 4 or not query.strip() or len(query) > 2000 or not 1 <= top_k <= 5:
            raise RetrievalError("invalid_search", 422)
        records = {sha(r.model_dump()): await self.records(r) for r in refs}
        terms = re.findall(r"[\w\u4e00-\u9fff]+", query)
        terms += [
            x
            for x in ("经营风险", "原材料", "市场竞争", "委托理财", "现金流", "主营业务", "研发",
                      "主要会计数据", "财务指标", "营业收入", "净利润")
            if x in query
        ]
        if "风险" in query:
            terms += (
                ["委托理财", "理财产品", "风险特征"]
                if any(t in query for t in ("理财", "委托贷款"))
                else ["主要风险", "风险因素", "市场竞争", "原材料价格", "海外市场"]
            )
        # A natural Chinese sentence is not one exact phrase in the source. Keep
        # explicit domain terms first, then bounded overlapping trigrams. This
        # changes lexical recall only; every hit still verifies its exact source.
        phrases = re.findall(r"[\u4e00-\u9fff]{4,48}", query)
        terms += [phrase[i:i+3] for phrase in phrases for i in range(0,len(phrase)-2,2)]
        terms = list(dict.fromkeys(x for x in terms if len(x) >= 3))[:12]
        lex = []
        missing = []
        with self.tx() as db:
            for key in records:
                if not db.execute("SELECT 1 FROM manifests WHERE source_key=?", (key,)).fetchone():
                    missing.append(key)
            if terms:
                expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
                keys = list(records)
                sql = (
                    "SELECT evidence FROM passages WHERE passages MATCH ? AND source_key IN ("
                    + ",".join("?" for _ in keys)
                    + ") ORDER BY bm25(passages) LIMIT 20"
                )
                lex = [
                    EvidenceRef.model_validate_json(r[0])
                    for r in db.execute(sql, [expression, *keys])
                ]
        candidates = {}
        raw = {}
        for rank, e in enumerate(lex, 1):
            candidates[e.evidence_id] = dict(
                e=e,
                lexical_rank=rank,
                dense_rank=None,
                dense_cosine=None,
                document_type="ocr_line" if e.source_ref.kind == "ocr" else "paragraph",
                section=None,
            )
        fast = [r for r in refs if r.kind == "fast"]
        dense = (
            await resolve(self.dense_search(query, fast, 20)) if fast and self.dense_search else []
        )
        for rank, h in enumerate(dense, 1):
            if not math.isfinite(h.score):
                raise RetrievalError("dense_score_invalid")
            matches = [
                e
                for values in records.values()
                for e in values
                if e.source_ref.kind == "fast"
                and h.workspace_id == e.source_ref.workspace_id
                and h.document_id == e.source_ref.document_id
                and h.source_revision == e.source_ref.source_revision
                and h.page == e.physical_page
                and bool(h.text.strip())
                and h.text[:1200] in e.text
            ]
            if len(matches) != 1:
                continue
            e = matches[0]
            raw[e.evidence_id] = h
            c = candidates.setdefault(
                e.evidence_id,
                dict(
                    e=e,
                    lexical_rank=None,
                    dense_rank=None,
                    dense_cosine=None,
                    document_type=h.type,
                    section=h.section or None,
                ),
            )
            c.update(dense_rank=rank, dense_cosine=h.score)
        output = []
        for c in candidates.values():
            e = c.pop("e")
            text = e.text
            fusion = sum(1 / (60 + c[k]) for k in ("lexical_rank", "dense_rank") if c[k])
            topic = sum(t in text for t in terms[1:])
            numeric = sum(ch.isdigit() for ch in text) / max(1, len(text))
            entrusted = any(t in query for t in ("理财", "投资产品", "委托贷款"))
            relevance = topic * 0.008 + (
                0.025 if "风险" in query and ("主要风险" in text or "市场竞争" in text) else 0
            )
            if "风险" in query and not entrusted and ("委托理财" in text or numeric > 0.3):
                relevance -= 0.04
            try:
                await self.verify(e)
            except Exception:
                continue
            output.append(
                Candidate(
                    evidence_ref=e,
                    text=text,
                    **c,
                    fusion_score=fusion,
                    rerank_score=fusion + relevance,
                )
            )
        output.sort(key=lambda c: (-c.rerank_score, c.evidence_ref.evidence_id))
        return dict(
            schema_version="retrieval-diagnostics-v1",
            items=[c.model_dump() for c in output[:top_k]],
            index_status="degraded_not_built" if missing else "ready",
            relevance_policy="topic-table-v1",
            **({"_raw": raw} if _legacy else {}),
        )

    async def legacy_fast_adapter(self, refs, query, top_k=5):
        result = await self.search(refs, query, top_k, _legacy=True)
        return tuple(
            result["_raw"][c["evidence_ref"]["evidence_id"]]
            for c in result["items"]
            if c["evidence_ref"]["source_ref"]["kind"] == "fast"
            and c["dense_cosine"] is not None
            and c["dense_cosine"] >= 0.55
        )

    def read(self, kind, resource_id, owner):
        with self.tx() as db:
            row = db.execute(
                "SELECT payload FROM objects WHERE id=? AND kind=? AND owner=?",
                (resource_id, kind, owner),
            ).fetchone()
        if not row:
            raise RetrievalError("resource_not_found", 404)
        return json.loads(row[0])

    def operation(self, op, owner):
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=? AND owner=?", (op, owner)
            ).fetchone()
        if not row:
            raise RetrievalError("operation_not_found", 404)
        return dict(
            operation_id=op,
            state=row["state"],
            result=json.loads(row["result"]) if row["result"] else None,
        )

    def reserve(self, op, owner, body, *, before_commit):
        try:
            if str(UUID(op)) != op:
                raise ValueError()
        except (TypeError, ValueError, AttributeError):
            raise RetrievalError("invalid_operation", 422) from None
        with self.tx(before_commit=before_commit) as db:
            old = db.execute("SELECT * FROM operations WHERE id=?", (op,)).fetchone()
            if old:
                if old["owner"] != owner or old["digest"] != sha(body):
                    raise RetrievalError("operation_conflict")
                return False
            db.execute(
                "INSERT INTO operations VALUES (?,?,?,'unknown',NULL)", (op, owner, sha(body))
            )
        return True

    async def validate_context(self, context, owner):
        if context.get("parent_conversation_id"):
            if self.parent_validator is None:
                raise RetrievalError("parent_validator_required", 503)
            await resolve(self.parent_validator(context["parent_conversation_id"]))
        refs = [SourceRef.model_validate(r) for r in context["selected_sources"]]
        for r in refs:
            if r.kind == "ocr":
                enrollment = self.read("enrollment", r.enrollment_id, owner)
                if enrollment["source_ref"] != r.model_dump():
                    raise RetrievalError("enrollment_changed")
            await self.records(r)
        if self.memory is not None:
            self.memory.check_generation(context["memory_generation"])
        return refs

    async def mutate(self, kind, body, identity):
        owner = await self.authorize(identity)
        self.commit_check(identity)
        if not self.reserve(
            body["operation_id"],
            owner,
            dict(kind=kind, **body),
            before_commit=lambda: self.commit_check(identity),
        ):
            return self.operation(body["operation_id"], owner)
        if self.guard is None:
            raise RetrievalError("publication_guard_required", 503)
        identifier = str(uuid4())
        context = None
        build_batches = None
        if kind == "enrollment":
            if body["confirmed"] is not True:
                raise RetrievalError("explicit_confirmation_required", 422)
            value = await self.parse.quality(body["document_id"], body["artifact_id"])
            ref = SourceRef(
                kind="ocr",
                workspace_id=identity.workspace_id,
                enrollment_id=identifier,
                **{
                    k: value[k]
                    for k in (
                        "company_id",
                        "document_id",
                        "source_revision",
                        "content_sha256",
                        "parser_version",
                        "report_year",
                        "config_hash",
                        "metadata_sha256",
                    )
                },
                artifact_id=body["artifact_id"],
                artifact_sha256=body["expected_artifact_sha256"],
                selected_pages=body["selected_pages"],
                identity_status="file_transcription_only",
            )
            if ref.source_revision != body["expected_source_revision"]:
                raise RetrievalError("source_changed")
            await self.records(ref)
            payload = dict(
                enrollment_id=identifier,
                source_ref=ref.model_dump(),
                research_only=True,
                financial_authority=False,
            )
        elif kind == "context":
            context = dict(
                context_id=identifier,
                revision=1,
                title=body["title"],
                selected_sources=body["selected_sources"],
                parent_conversation_id=body.get("parent_conversation_id"),
                memory_generation=None,
                financial_focus=body.get('financial_focus'),
            )
            if self.memory is not None:
                with self.memory.tx() as db:
                    context["memory_generation"] = self.memory._generation(db)
            await self.validate_context(context, owner)
            context["context_sha256"] = sha(context)
            payload = context
        elif kind == "answer":
            context = self.read("context", body["context_id"], owner)
            if (
                context["revision"] != body["context_revision"]
                or context["context_sha256"] != body["context_sha256"]
            ):
                raise RetrievalError("context_changed")
            refs = await self.validate_context(context, owner)
            result = await self.search(refs, body["question"])
            # Versioned conservative relevance policy; no forced call for empty/weak results.
            evidence = [
                c
                for c in result["items"]
                if c["rerank_score"] >= 0.015
                and (c["lexical_rank"] is not None or (c["dense_cosine"] or 0) >= 0.55)
            ]
            for candidate in evidence:
                if candidate["evidence_ref"]["source_ref"]["kind"] == "fast":
                    candidate["text"] = candidate["text"][:1200]
                    candidate["evidence_ref"]["text"] = candidate["text"]
            outcome = "insufficient_evidence"
            interpretation = None
            if evidence and self.provider is None:
                outcome = "provider_unconfigured"
            if evidence and self.provider is not None:
                await self.authorize(identity)
                await self.validate_context(context, owner)
                with self.guard(identity, context):
                    pass
                question=body['question']
                if context.get('financial_focus'):
                    question=canonical({'user_question':question,'server_verified_point_focus':context['financial_focus'],
                                        'authority':'unreviewed_focus_not_financial_confirmation'})
                draft = await resolve(self.provider(question, evidence))
                if (
                    not isinstance(draft, dict)
                    or not isinstance(draft.get("text"), str)
                    or len(draft["text"]) > 6000
                ):
                    raise RetrievalError("invalid_provider_output")
                interpretation = draft["text"]
                outcome = "completed"
            for c in evidence:
                await self.verify(EvidenceRef.model_validate(c["evidence_ref"]))
            await self.validate_context(context, owner)
            payload = dict(
                schema_version="cplus-research-answer-v1",
                answer_id=identifier,
                context_id=context["context_id"],
                context_revision=context["revision"],
                context_sha256=context["context_sha256"],
                question=body["question"],
                state=outcome,
                findings=[
                    dict(
                        kind="sourced_excerpt",
                        text=c["text"],
                        evidence_ref=c["evidence_ref"],
                        source_status="current",
                        transcription_review_status="ocr_transcription_unreviewed"
                        if c["evidence_ref"]["source_ref"]["kind"] == "ocr"
                        else "fast_extraction_unreviewed",
                        interpretation_review_status="not_applicable",
                    )
                    for c in evidence
                ],
                interpretation=interpretation,
                interpretation_review_status="ai_unreviewed" if interpretation else "not_generated",
                numeric_claim_status="unverified",
                financial_authority=False,
                financial_focus=context.get('financial_focus'),
                coverage=dict(
                    selected_sources=len(refs),
                    cited_sources=len({sha(c["evidence_ref"]["source_ref"]) for c in evidence}),
                ),
                limitations=["OCR身份未核验时仅解读文件转录；不代表该企业核准经营结论。"],
            )
        elif kind in ("build", "search"):
            refs = [SourceRef.model_validate(r) for r in body["sources"]]
            if kind == "build":
                build_batches = await self.prepare_build(refs)
                payload = self.build_result(build_batches)
            else:
                payload = await self.search(refs, body["query"], body["top_k"])
            payload.pop("_raw", None)
        else:
            raise RetrievalError("unknown_action", 422)
        await self.authorize(identity)
        fence = context or dict(
            selected_sources=payload.get("source_ref")
            and [payload["source_ref"]]
            or body.get("sources", [])
        )
        with self.guard(identity, fence):
            with self.tx(before_commit=lambda: self.commit_check(identity)) as db:
                if build_batches is not None:
                    self.write_build(db, build_batches)
                db.execute(
                    "INSERT INTO objects VALUES (?,?,?,?)",
                    (identifier, kind, owner, canonical(payload)),
                )
                db.execute(
                    "UPDATE operations SET state='completed',result=? WHERE id=?",
                    (canonical(payload), body["operation_id"]),
                )
        return self.operation(body["operation_id"], owner)
