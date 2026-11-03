from decimal import Decimal, localcontext
from uuid import uuid4
from app.finance_v2.contracts import FinanceError


class CheckupService:
    def __init__(self, statements, explanation_callback=None):
        self.statements = statements
        self.explanation_callback = explanation_callback

    async def create(
        self, operation_id, collection_refs, candidate_view=False, generate_explanation=False
    ):
        if generate_explanation:
            raise FinanceError("guarded_explanation_not_connected", 503)
        old = self.statements.reserve(operation_id, ["checkup", collection_refs, candidate_view])
        if old:
            return old
        collections, contexts = await self.statements.selected(collection_refs)
        with self.statements.tx(source=True) as db:
            self.statements.guard(db, contexts)
            values = {}
            refs = []
            for collection in collections:
                for cell in collection["cells"]:
                    if cell["extraction_status"] != "candidate":
                        continue
                    receipt = self.statements.admitted(db, cell)
                    if not receipt and not candidate_view:
                        continue
                    key = (cell["company_id"], cell["metric_key"], str(cell["time"]))
                    if key in values:
                        raise FinanceError("explicit_disclosure_selection_required")
                    values[key] = cell
                    refs.append(cell)
            rules = []
            for rule, keys in [
                ("income_profit_divergence", ["revenue", "net_profit_parent"]),
                ("cash_profit_divergence", ["operating_cash_flow", "net_profit_parent"]),
                ("debt_asset_change", ["total_assets", "total_liabilities"]),
            ]:
                series = [[c for c in refs if c["metric_key"] == key] for key in keys]
                eligible = (
                    all(len(s) == 2 for s in series)
                    and len({c["company_id"] for s in series for c in s}) == 1
                )
                observation = None
                if eligible:
                    series = [sorted(s, key=lambda c: str(c["time"])) for s in series]
                    eligible = [c["time"] for c in series[0]] == [
                        c["time"] for c in series[1]
                    ] and len({c["basis"] for s in series for c in s}) == 1
                if eligible:
                    with localcontext() as ctx:
                        ctx.prec = 60
                        pairs = [[Decimal(c["normalized_decimal"]) for c in s] for s in series]
                        if rule == "debt_asset_change":
                            if min(pairs[0]) > 0 and min(pairs[1]) >= 0:
                                observation = format(
                                    (pairs[1][1] / pairs[0][1] - pairs[1][0] / pairs[0][0]) * 100,
                                    ".6f",
                                )
                        elif all(p[0] > 0 for p in pairs):
                            observation = (
                                "direction_diverges"
                                if (pairs[0][1] - pairs[0][0]) * (pairs[1][1] - pairs[1][0]) < 0
                                else "no_direction_divergence"
                            )
                rules.append(
                    {
                        "rule_id": rule,
                        "rule_version": "v1",
                        "status": (
                            "candidate_observation" if candidate_view else "confirmed_observation"
                        )
                        if observation is not None
                        else "insufficient",
                        "observation": observation,
                        "unit": "PERCENTAGE_POINTS" if rule == "debt_asset_change" else "DIRECTION",
                        "input_refs": [c["cell_id"] for s in series for c in s],
                        "reason": None
                        if observation is not None
                        else "missing_incomparable_or_nonpositive_baseline",
                        "interpretation_review": "not_generated",
                    }
                )
            value = {
                "id": str(uuid4()),
                "schema_version": "checkup-v1",
                "rules": rules,
                "candidate_view": candidate_view,
                "collection_refs": collection_refs,
                "limitations": [
                    "Arithmetic observations only; no cause, investment score or AI interpretation."
                ],
            }
            self.statements._record(db, "checkup", value)
            return self.statements.finish(db, operation_id, value)


def create_checkup_router(service):
    from fastapi import APIRouter
    from app.finance_v2.api import FinanceRoute
    from app.financial_statements_v3.api import Operation, CollectionSelection
    from app.finance_v2.contracts import UUIDText
    from pydantic import Field

    class Checkup(Operation):
        collection_refs: list[UUIDText | CollectionSelection] = Field(min_length=1, max_length=5)
        candidate_view: bool = False
        generate_explanation: bool = False

    router = APIRouter(prefix="/cplus", route_class=FinanceRoute)

    @router.post("/checkups")
    async def create(p: Checkup):
        return await service.create(
            p.operation_id,
            p.model_dump()["collection_refs"],
            p.candidate_view,
            p.generate_explanation,
        )

    @router.get("/checkups/{result_id}")
    async def read(result_id: str):
        value = service.statements.read(result_id, "checkup")
        try:
            await service.statements.selected(value["collection_refs"])
            status = "current"
        except Exception:
            status = "unavailable"
        return {**value, "historical_snapshot": True, "current_source_status": status}

    return router
