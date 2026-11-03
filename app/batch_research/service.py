"""Serial bounded tool batches; injected existing tools, no provider or private budget."""

import asyncio
import time
from uuid import uuid4
from app.peer_compare.store import Store
from app.retrieval_v2.models import RetrievalError
from app.retrieval_v2.service import canonical, resolve, sha
from app.peer_compare.service import PeerComparisonService

TEMPLATES = {
    "risk_excerpt": "摘录主要经营风险并给出处",
    "annual_changes": "比较两年经营风险、主要业务与研发原文",
}


class BatchResearchService:
    before_commit = PeerComparisonService.before_commit

    def __init__(
        self,
        runtime_root,
        *,
        identity_validator,
        publication_guard,
        commit_check,
        prepare_cell,
        validate_prepared,
        execute_cell,
    ):
        self.validator, self.guard, self.commit_check = (
            identity_validator,
            publication_guard,
            commit_check,
        )
        self.prepare, self.validate, self.execute = prepare_cell, validate_prepared, execute_cell
        self._tasks = set()
        self.store = Store(runtime_root, "batch-research")
        with self.store.tx() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,plan_id TEXT UNIQUE,owner TEXT,revision INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS cells(batch_id TEXT,key TEXT,state TEXT,operation_id TEXT,result_id TEXT,error TEXT,PRIMARY KEY(batch_id,key))"
            )

    async def owner(self, i):
        if (
            i.expires_at <= time.time()
            or self.validator is None
            or await resolve(self.validator(i)) is False
        ):
            raise RetrievalError("trusted_identity_required", 403)
        return sha(i.model_dump())

    async def checked(self, p, i):
        await self.owner(i)
        if await resolve(self.validate(p, i)) is False:
            raise RetrievalError("prepared_scope_changed")

    def fence(self, prepared):
        return dict(
            prepared_cells=prepared,
            selected_sources=list(
                {sha(s): s for p in prepared for s in p["selected_sources"]}.values()
            ),
        )

    async def plan(self, body, i):
        owner = await self.owner(i)
        if not body.get("generate_explanations"):
            body={k:v for k,v in body.items() if k!="generate_explanations"}
        if not self.store.reserve(body["operation_id"], owner, body):
            return self.store.operation(body["operation_id"], owner)
        if body.get("preparation_confirmed") is not True:
            raise RetrievalError("explicit_preparation_required", 422)
        cells = body["cells"]
        if (
            not 1 <= len(cells) <= 12
            or len({c["cell_key"] for c in cells}) != len(cells)
            or len({c["company_id"] for c in cells}) > 3
        ):
            raise RetrievalError("batch_bounds", 422)
        prepared = []
        for cell in cells:
            if cell["template"] not in TEMPLATES:
                raise RetrievalError("unknown_template", 422)
            # This callback is contractually read-only: no model/plan/job or writes.
            p = await resolve(self.prepare({**cell,"generate_explanation":body.get("generate_explanations",False)}, i))
            if (
                not isinstance(p, dict)
                or not p.get("selected_sources")
                or any(
                    s["company_id"] != cell["company_id"] or s["workspace_id"] != i.workspace_id
                    for s in p["selected_sources"]
                )
            ):
                raise RetrievalError("prepared_scope_mismatch")
            await self.checked(p, i)
            prepared.append(
                dict(
                    cell_key=cell["cell_key"],
                    company_id=cell["company_id"],
                    template=cell["template"],
                    question=TEMPLATES[cell["template"]],
                    prepared=p,
                    child_operation_id=str(uuid4()),
                    child_context_operation_id=str(uuid4()),
                )
            )
        value = dict(
            schema_version="prepared-batch-v1",
            batch_plan_id=str(uuid4()),
            revision=1,
            cells=prepared,
            limits={
                "max_cells": 12,
                "parallel_cells": 1,
                "templates": list(TEMPLATES),
                "provider_calls_by_service": 0,
                "execution_mode":"ai_review" if body.get("generate_explanations") else "pure_tools",
                "max_provider_attempts":len(cells) if body.get("generate_explanations") else 0,
            },
            approval_required=True,
        )
        value["batch_plan_sha256"] = sha(value)
        fence = self.fence([c["prepared"] for c in prepared])
        for p in fence["prepared_cells"]:
            await self.checked(p, i)
        with self.guard(i, fence):
            with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                self.store.finish(db, value["batch_plan_id"], owner, body["operation_id"], value)
        return self.store.operation(body["operation_id"], owner)

    async def start(self, body, i, *, background=False):
        owner = await self.owner(i)
        if not self.store.reserve(body["operation_id"], owner, body):
            return self.store.operation(body["operation_id"], owner)
        plan = self.store.read(body["batch_plan_id"], owner)
        if (
            body.get("confirmed") is not True
            or plan["revision"] != body["batch_plan_revision"]
            or plan["batch_plan_sha256"] != body["batch_plan_sha256"]
        ):
            raise RetrievalError("plan_approval_mismatch")
        fence = self.fence([c["prepared"] for c in plan["cells"]])
        for p in fence["prepared_cells"]:
            await self.checked(p, i)
        batch = str(uuid4())
        with self.guard(i, fence):
            with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                if db.execute(
                    "SELECT 1 FROM batches WHERE plan_id=?", (plan["batch_plan_id"],)
                ).fetchone():
                    raise RetrievalError("plan_already_dispatched")
                db.execute(
                    "INSERT INTO batches VALUES (?,?,?,1)", (batch, plan["batch_plan_id"], owner)
                )
                db.execute(
                    "UPDATE operations SET result=? WHERE id=?",
                    (canonical(dict(batch_id=batch, state="running")), body["operation_id"]),
                )
                db.executemany(
                    "INSERT INTO cells VALUES (?,?,?,?,NULL,NULL)",
                    [
                        (batch, c["cell_key"], "queued", c["child_operation_id"])
                        for c in plan["cells"]
                    ],
                )
        if background:
            # The durable receipt acknowledges dispatch, not research completion.
            # The caller can immediately observe/cancel queued cells via matrix GET.
            acknowledged = self.matrix(batch, owner)
            acknowledged.update(dispatch_acknowledged=True, completion_via_get=True)
            with self.guard(i, fence):
                with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                    db.execute("UPDATE operations SET state='completed',result=? WHERE id=? AND owner=?",
                               (canonical(acknowledged), body["operation_id"], owner))
            task = asyncio.create_task(self._background_dispatch(plan, batch, owner, i, fence))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return self.store.operation(body["operation_id"], owner)
        await self._dispatch_cells(plan, batch, owner, i, fence)
        await self.owner(i)
        snapshot = self.matrix(batch, owner)
        with self.guard(i, fence):
            with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                self.store.finish(db, batch, owner, body["operation_id"], snapshot)
        return self.store.operation(body["operation_id"], owner)

    async def _background_dispatch(self, plan, batch, owner, i, fence):
        try:
            await self._dispatch_cells(plan, batch, owner, i, fence)
        except BaseException as exc:
            # Only mark this old, private namespace. No task is resumed or replayed.
            with self.store.tx() as db:
                db.execute("UPDATE cells SET state='unknown',error='dispatch_interrupted' "
                           "WHERE batch_id=? AND state IN ('queued','dispatching')", (batch,))
                db.execute("UPDATE batches SET revision=revision+1 WHERE id=?", (batch,))
            if isinstance(exc, asyncio.CancelledError):
                raise

    async def _dispatch_cells(self, plan, batch, owner, i, fence):
        for cell in plan["cells"]:
            try:
                await self.checked(cell["prepared"], i)
                with self.guard(i, self.fence([cell["prepared"]])):
                    with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                        changed = db.execute(
                            "UPDATE cells SET state='dispatching' WHERE batch_id=? AND key=? AND state='queued'",
                            (batch, cell["cell_key"]),
                        ).rowcount
                        if changed:
                            db.execute(
                                "UPDATE batches SET revision=revision+1 WHERE id=?", (batch,)
                            )
                if not changed:
                    continue
                # No automatic retry. Root adapter invokes only the frozen tool with the saved UUID.
                await self.checked(cell["prepared"], i)
                result = await resolve(self.execute(cell, cell["child_operation_id"], i))
                await self.checked(cell["prepared"], i)
                if (
                    not isinstance(result, dict)
                    or result.get("domain")
                    not in ("retrieval_v2", "annual_diff", "financial_statements_v3", "research_answer_v1")
                    or result.get("state") not in ("completed", "partial", "failed")
                    or not isinstance(result.get("payload"), dict)
                ):
                    raise RetrievalError("invalid_tool_result")
                result_id = str(uuid4())
                payload = dict(
                    cell_key=cell["cell_key"],
                    child_operation_id=cell["child_operation_id"],
                    result=result,
                )
                with self.guard(i, self.fence([cell["prepared"]])):
                    with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                        db.execute(
                            "INSERT INTO snapshots VALUES (?,?,?)",
                            (result_id, owner, canonical(payload)),
                        )
                        db.execute(
                            "UPDATE cells SET state=?,result_id=? WHERE batch_id=? AND key=? AND state='dispatching'",
                            (result["state"], result_id, batch, cell["cell_key"]),
                        )
                        db.execute("UPDATE batches SET revision=revision+1 WHERE id=?", (batch,))
            except Exception as exc:
                # Preserve UNKNOWN. No restart handler or GET can dispatch it again.
                with self.store.tx() as db:
                    db.execute(
                        "UPDATE cells SET state='unknown',error=? WHERE batch_id=? AND key=? AND state IN ('queued','dispatching')",
                        (getattr(exc, "code", "execution_unknown"), batch, cell["cell_key"]),
                    )
                    db.execute("UPDATE batches SET revision=revision+1 WHERE id=?", (batch,))
    def matrix(self, batch, owner):
        with self.store.tx() as db:
            b = db.execute(
                "SELECT * FROM batches WHERE id=? AND owner=?", (batch, owner)
            ).fetchone()
            if not b:
                raise RetrievalError("batch_not_found", 404)
            rows = db.execute(
                "SELECT * FROM cells WHERE batch_id=? ORDER BY rowid", (batch,)
            ).fetchall()
        plan=self.store.read(b['plan_id'],owner)
        planned={c['cell_key']:c for c in plan['cells']}
        cells=[]
        for row in rows:
            frozen=planned[row['key']]
            saved=self.store.read(row['result_id'],owner) if row['result_id'] else None
            result=(saved or {}).get('result',{})
            payload=result.get('payload',{})
            evidence=[]
            if result.get('domain')=='retrieval_v2':
                evidence=[item['evidence_ref'] for item in payload.get('items',[]) if item.get('evidence_ref')]
            elif result.get('domain')=='research_answer_v1':
                evidence=[item['evidence_ref'] for item in payload.get('findings',[]) if item.get('evidence_ref')]
            elif result.get('domain')=='annual_diff':
                evidence=[ref for topic in payload.get('topics',[]) for side in ('left','right')
                          for ref in topic.get(side,{}).get('evidence_refs',[])]
            result_ref=None
            if result.get('domain')=='annual_diff' and payload.get('result_id'):
                result_ref={'domain':'annual_diff_v1','id':payload['result_id'],'revision':1,
                            'payload_sha256':sha(payload)}
            if result.get('domain')=='research_answer_v1' and payload.get('answer_id'):
                result_ref={'domain':'research_answer_v1','id':payload['answer_id'],'revision':1,'payload_sha256':sha(payload)}
            sources=frozen['prepared']['selected_sources']
            ai_review=bool(frozen['prepared'].get('generate_explanation'))
            cells.append(dict(cell_key=row['key'],state=row['state'],status=row['state'],
                operation_id=row['operation_id'],child_operation_id=row['operation_id'],
                error_code=row['error'],result=saved,
                row_company={'company_id':frozen['company_id']},
                column_question=frozen['question'],template=frozen['template'],
                period=[{'report_year':ref.get('report_year'),'period_start':ref.get('period_start'),
                         'period_end':ref.get('period_end')} for ref in sources],
                selected_sources=sources,excerpt_count=len(evidence),
                finding_count=len(payload.get('findings',[])),
                answer_summary=(payload.get('interpretation') or
                    f"已保存 {len(evidence)} 段原文；"+('解释状态见原文详情，结果待审。' if ai_review else '纯工具模式未生成 AI 综合结论。')) if saved else
                    '任务结果尚未取得。' if row['state'] in ('queued','dispatching') else '本格未生成可用研究结果。',
                evidence_refs=evidence,result_ref=result_ref,job_id=None,
                cost_observed_or_reserved={'mode':'ai_review' if ai_review else 'pure_tools',
                                           'provider_calls':None if ai_review else 0,
                                           'max_provider_attempts':1 if ai_review else 0,
                                           'reserved_cny':None if ai_review else '0',
                                           'actual_billed_cny':'not_observed'},
                source_status_scope='validated_at_execution'))
        return dict(
            schema_version="batch-matrix-v1",
            batch_id=batch,
            batch_plan_id=b["plan_id"],
            revision=b["revision"],
            state="running"
            if any(r["state"] in ("queued", "dispatching") for r in rows)
            else "completed"
            if all(r["state"] == "completed" for r in rows)
            else "partial",
            cells=cells,
        )

    async def list(self, i):
        owner=await self.owner(i)
        with self.store.tx() as db:
            ids=[row[0] for row in db.execute("SELECT id FROM batches WHERE owner=? ORDER BY rowid DESC LIMIT 20",(owner,))]
        items=[]
        for identifier in ids:
            value=self.matrix(identifier,owner)
            items.append({'batch_id':identifier,'state':value['state'],'cell_count':len(value['cells']),
                          'company_ids':sorted({c['row_company']['company_id'] for c in value['cells']})})
        return {'schema_version':'saved-batches-v1','items':items}

    async def read(self, batch, i):
        return self.matrix(batch, await self.owner(i))

    async def cancel(self, batch, body, i):
        owner = await self.owner(i)
        if not self.store.reserve(body["operation_id"], owner, dict(batch_id=batch, **body)):
            return self.store.operation(body["operation_id"], owner)
        current = self.matrix(batch, owner)
        plan = self.store.read(current["batch_plan_id"], owner)
        # Cancelling only queued cells cannot publish source/financial data. A
        # broken source must not block stopping other work from this same plan.
        fence = {'selected_sources':[], 'cancellation_of':batch,
                 'immutable_plan_id':plan['batch_plan_id']}
        with self.guard(i, fence):
            with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                if (
                    db.execute("SELECT revision FROM batches WHERE id=?", (batch,)).fetchone()[0]
                    < body["expected_revision"]
                ):
                    raise RetrievalError("batch_revision_conflict")
                count = db.execute(
                    "UPDATE cells SET state='cancelled' WHERE batch_id=? AND state='queued'",
                    (batch,),
                ).rowcount
                db.execute("UPDATE batches SET revision=revision+1 WHERE id=?", (batch,))
                receipt = dict(batch_id=batch, cancelled_queued=count, running_not_cancelled=True)
                self.store.finish(db, str(uuid4()), owner, body["operation_id"], receipt)
        return self.store.operation(body["operation_id"], owner)
