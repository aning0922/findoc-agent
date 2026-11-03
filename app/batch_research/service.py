"""Serial bounded tool batches; injected existing tools, no provider or private budget."""

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
            p = await resolve(self.prepare(cell, i))
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

    async def start(self, body, i):
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
                    not in ("retrieval_v2", "annual_diff", "financial_statements_v3")
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
        await self.owner(i)
        snapshot = self.matrix(batch, owner)
        with self.guard(i, fence):
            with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                self.store.finish(db, batch, owner, body["operation_id"], snapshot)
        return self.store.operation(body["operation_id"], owner)

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
            cells=[
                dict(
                    cell_key=r["key"],
                    state=r["state"],
                    operation_id=r["operation_id"],
                    error_code=r["error"],
                    result=self.store.read(r["result_id"], owner) if r["result_id"] else None,
                )
                for r in rows
            ],
        )

    async def read(self, batch, i):
        return self.matrix(batch, await self.owner(i))

    async def cancel(self, batch, body, i):
        owner = await self.owner(i)
        if not self.store.reserve(body["operation_id"], owner, dict(batch_id=batch, **body)):
            return self.store.operation(body["operation_id"], owner)
        current = self.matrix(batch, owner)
        plan = self.store.read(current["batch_plan_id"], owner)
        fence = self.fence([c["prepared"] for c in plan["cells"]])
        with self.guard(i, fence):
            with self.store.tx(before_commit=lambda: self.before_commit(i, fence)) as db:
                if (
                    db.execute("SELECT revision FROM batches WHERE id=?", (batch,)).fetchone()[0]
                    != body["expected_revision"]
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
