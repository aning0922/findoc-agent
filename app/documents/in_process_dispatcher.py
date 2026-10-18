from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial

from app.documents.models import DocumentRecord
from app.documents.ports import TaskDispatcher


DocumentProcessorCallable = Callable[[str], DocumentRecord]


class InProcessTaskDispatcher(TaskDispatcher):
    """在当前进程内调度文档任务，并把同步处理工作移出 event loop。

    每个 document_id 同时最多存在一个活动任务；所有文档任务共享一个
    并发槽。任务只保存在内存中，进程退出后不会恢复。
    """

    def __init__(self, processor: DocumentProcessorCallable) -> None:
        """保存同步处理函数，并建立并发数固定为 1 的任务容器。"""
        self._processor = processor
        self._semaphore = asyncio.Semaphore(1)
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

    def dispatch(self, document_id: str) -> bool:
        """调度文档任务；已有同 ID 活动任务时返回 False。

        必须从正在运行的 event loop 中调用。返回 True 只表示内存任务
        已建立，不表示处理成功或任务具有重启恢复能力。
        """
        existing = self._active_tasks.get(document_id)

        if existing is not None:
            if not existing.done():
                return False

            # 极短时间窗口内，任务可能完成但 done callback 尚未执行。
            self._on_task_done(document_id, existing)

        task = asyncio.create_task(
            self._run(document_id),
            name=f"process-document:{document_id}",
        )
        self._active_tasks[document_id] = task
        task.add_done_callback(partial(self._on_task_done, document_id))
        return True

    async def _run(self, document_id: str) -> None:
        """取得唯一并发槽，并在线程中运行同步文档处理函数。"""
        async with self._semaphore:
            await asyncio.to_thread(self._processor, document_id)

    def _on_task_done(
        self,
        document_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """释放任务强引用，并消费异常以避免未处理任务异常警告。"""
        current = self._active_tasks.get(document_id)
        if current is task:
            self._active_tasks.pop(document_id, None)

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            # 具体解析和索引错误应由 DocumentProcessor 写入 repository。
            # 这里仅消费逃逸异常，不能把原始异常暴露给 API。
            pass

    @property
    def active_count(self) -> int:
        """返回当前仍被 dispatcher 跟踪的活动任务数。"""
        return sum(not task.done() for task in self._active_tasks.values())

    async def wait_for_idle(self) -> None:
        """等待当前进程内已经派发的任务结束，主要供测试和关闭流程使用。"""
        while self._active_tasks:
            tasks = tuple(self._active_tasks.values())
            await asyncio.gather(*tasks, return_exceptions=True)
