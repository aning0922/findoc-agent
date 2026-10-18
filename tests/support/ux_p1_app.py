"""UX-P1 fresh HTTP assembly: real contracts/PDF/SQLite, simulated consent.

No outgoing network connections are permitted from this test server. SQLite
connections are restricted to this run's temporary root; D25 files are blocked.
"""

import os
from pathlib import Path
import sys
from urllib.parse import urlparse, unquote
from tests.support.ux_v21_app import create_ux_v21_app


def create_ux_p1_app():
    runtime = Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve()
    protected = Path(__file__).resolve().parents[3] / "findoc-analyst-d25"

    def audit(event, args):
        if event == "socket.connect":
            raise RuntimeError("UX-P1 test server forbids outgoing service connections")
        if event == "sqlite3.connect" and args[0] != ":memory:":
            value = args[0]
            if isinstance(value, str) and value.startswith("file:"):
                value = unquote(urlparse(value).path)
            if not Path(value).resolve().is_relative_to(runtime):
                raise RuntimeError("UX-P1 SQLite connection outside isolated runtime")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if Path(os.fsdecode(args[0])).resolve().is_relative_to(protected):
                raise RuntimeError("UX-P1 forbids any D25 file access")

    sys.addaudithook(audit)
    app = create_ux_v21_app()
    # Extend only this disposable assembly with the existing isolated D11 service.
    # The production /analyses route continues to reject simulated receipts.
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
    from app.agent.financial_analysis import FinancialAnalysisService, FinancialFactReference
    from app.agent.financial_analysis import IsolatedAnalysisTestConfig
    from app.api.financial_analyses import FinancialAnalysisRequest, CompanyComparisonRequest, AnalysisRoute
    from tests.support.d19_runtime import reopen

    h = reopen(runtime)
    analysis = FinancialAnalysisService(
        facts=h.confirmations,
        workspace_id="demo",
        isolated_test=IsolatedAnalysisTestConfig(runtime),
    )
    router = APIRouter(prefix="/__test__", route_class=AnalysisRoute)

    @router.post("/analyses")
    async def isolated_analysis(payload: FinancialAnalysisRequest):
        result = await analysis.analyze(
            company_id=payload.company_id,
            metric_key=payload.metric_key,
            current=FinancialFactReference(**payload.current.model_dump())
            if payload.current
            else None,
            previous=FinancialFactReference(**payload.previous.model_dump())
            if payload.previous
            else None,
        )
        return JSONResponse(
            result,
            status_code=409 if result["status"] == "blocked" else 200,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/company-comparison")
    async def isolated_comparison(payload: CompanyComparisonRequest):
        # The same D13 service and admission gates; this route exists only in
        # the disposable test assembly, as in real_product_app.py.
        result = await analysis.compare(
            company_a_id=payload.company_a_id,
            company_b_id=payload.company_b_id,
            period=payload.period,
            selections={
                s.metric_key: (
                    FinancialFactReference(**s.a.model_dump()) if s.a else None,
                    FinancialFactReference(**s.b.model_dump()) if s.b else None,
                )
                for s in payload.selections
            },
        )
        return JSONResponse(
            result,
            status_code=409 if result["status"] == "blocked" else 200,
            headers={"Cache-Control": "no-store"},
        )

    app.include_router(router)
    return app
