"""默认 runtime ASGI 入口；显式隔离运行应导入无副作用的 factory。"""

from app.api.runtime_factory import create_runtime_app


# 保留既有 ``uvicorn app.api.main:app`` 的默认启动语义。
app = create_runtime_app()
