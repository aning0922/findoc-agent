import asyncio
import threading

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _run_health_during_blocking_work(
    *,
    use_to_thread: bool,
) -> bool:
    """运行一次受控阻塞实验，返回health是否在释放worker前执行。"""

    async def scenario() -> bool:
        """并发发送worker和health请求，并等待观察线程释放barrier。"""
        started = threading.Event()
        release = threading.Event()
        health_handled = threading.Event()
        observation: list[tuple[bool, bool]] = []

        def blocking_work() -> None:
            """通知任务已开始，并阻塞到测试控制器明确释放。"""
            started.set()
            if not release.wait(timeout=3):
                raise TimeoutError("测试未及时释放blocking worker")

        app = FastAPI()

        @app.post("/work")
        async def work() -> dict[str, str]:
            """按实验参数直接运行或通过to_thread运行同步任务。"""
            if use_to_thread:
                await asyncio.to_thread(blocking_work)
            else:
                blocking_work()
            return {"status": "finished"}

        @app.get("/health")
        async def health() -> dict[str, str]:
            """记录health路由已获得event loop执行机会。"""
            health_handled.set()
            return {"status": "ok"}

        def observe_then_release() -> None:
            """在独立线程观察health，然后无条件释放阻塞worker。"""
            worker_started = started.wait(timeout=2)
            health_before_release = health_handled.wait(timeout=0.5)
            observation.append((worker_started, health_before_release))
            release.set()

        controller = threading.Thread(
            target=observe_then_release,
            daemon=True,
        )
        controller.start()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                # 两个请求先创建为Task，再把执行权交给event loop。
                # 创建顺序确保/work首先进入受控阻塞点。
                work_task = asyncio.create_task(client.post("/work"))
                health_task = asyncio.create_task(client.get("/health"))
                work_response, health_response = await asyncio.gather(
                    work_task,
                    health_task,
                )
        finally:
            # 即使请求或断言异常，也不能把测试线程永久卡住。
            release.set()
            controller.join(timeout=2)

        assert work_response.status_code == 200
        assert health_response.status_code == 200
        assert observation
        assert observation[0][0] is True
        return observation[0][1]

    return asyncio.run(scenario())


def test_to_thread_keeps_health_responsive_during_sync_work() -> None:
    """同一同步worker直接调用时health被拖住，to_thread时health可先响应。

    如果失败，说明同步阻塞边界没有被移出event loop，或者测试的受控
    barrier没有正确建立。
    """
    direct_health_before_release = _run_health_during_blocking_work(
        use_to_thread=False,
    )
    threaded_health_before_release = _run_health_during_blocking_work(
        use_to_thread=True,
    )

    assert direct_health_before_release is False
    assert threaded_health_before_release is True
