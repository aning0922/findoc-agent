from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from app.disclosures.download import DisclosureError


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str = Field(max_length=36)
    candidate_id: str = Field(min_length=1, max_length=200)
    company_id: str = Field(min_length=1, max_length=100)


class DisclosureRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def validated(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    {"detail": {"code": "invalid_request", "message": "资料请求字段无效。"}},
                    422,
                    headers={"Cache-Control": "no-store"},
                )

        return validated


def create_disclosure_router(service):
    router = APIRouter(prefix="/disclosures", tags=["disclosures"], route_class=DisclosureRoute)

    def response(value, status=200):
        return JSONResponse(value, status, headers={"Cache-Control": "no-store"})

    def fail(exc):
        return response(
            {
                "detail": {
                    "code": exc.code
                    if isinstance(exc, DisclosureError)
                    else "disclosure_unavailable",
                    "message": "资料查询或导入未完成，请查看操作状态或使用手动上传。",
                }
            },
            exc.status if isinstance(exc, DisclosureError) else 503,
        )

    @router.get("/search")
    async def search(request: Request, code: str = "", report_year: str = ""):
        try:
            if set(request.query_params) - {"code", "report_year"} or any(
                len(request.query_params.getlist(k)) > 1 for k in request.query_params
            ):
                raise DisclosureError("invalid_query", 422)
            if len(code) > 200 or (
                report_year
                and (
                    len(report_year) > 4
                    or not report_year.isdigit()
                    or not 1 <= int(report_year) <= 9999
                )
            ):
                raise DisclosureError("invalid_query", 422)
            return response(service.search(code, int(report_year) if report_year else None))
        except Exception as exc:
            return fail(exc)

    @router.post("/import")
    async def import_pdf(payload: ImportRequest):
        try:
            value = await service.import_candidate(**payload.model_dump())
            return response(
                value, {"completed": 200, "unknown": 409, "failed": 502}[value["state"]]
            )
        except Exception as exc:
            return fail(exc)

    @router.get("/imports/{operation_id}")
    async def operation(operation_id: str):
        try:
            return response(service.operation(operation_id))
        except Exception as exc:
            return fail(exc)

    return router
