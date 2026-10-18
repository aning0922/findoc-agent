"""SQLite BaseCheckpointSaver for the existing LangGraph scheduler.

Full checkpoints and pending writes, typed JSON/msgpack serializer, no pickle.
Every write is fenced by the durable execution claim. No graph retries or forks.
"""

import asyncio
import base64
from collections.abc import Sequence
from contextlib import closing
import hashlib
import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    WRITES_IDX_MAP,
)
from app.research.models import canonical
from app.research.repository import HistoryError
from app.research.task_repository import TaskRepository


class TaskCheckpointer(BaseCheckpointSaver[int]):
    def __init__(self, repository: TaskRepository, task_id: str, claim: str):
        super().__init__()
        self.repository, self.task_id, self.claim = repository, task_id, claim

    def scope(self, config: RunnableConfig) -> str:
        c = config["configurable"]
        if c["thread_id"] != self.task_id or c.get("checkpoint_ns", ""):
            raise HistoryError("checkpoint_scope_invalid")
        return self.task_id

    def pack(self, value: Any) -> bytes:
        kind, raw = self.serde.dumps_typed(value)
        return canonical(dict(kind=kind, data=base64.b64encode(raw).decode())).encode()

    def unpack(self, row: Any) -> Any:
        raw = row["payload"]
        if hashlib.sha256(raw).hexdigest() != row["payload_sha"]:
            raise HistoryError("checkpoint_integrity_error")
        try:
            data = json.loads(raw)
            return self.serde.loads_typed(
                (data["kind"], base64.b64decode(data["data"], validate=True))
            )
        except Exception:
            raise HistoryError("checkpoint_integrity_error") from None

    def config(self, checkpoint_id: str) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": self.task_id,
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint_id,
            }
        }

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        self.scope(config)
        with closing(self.repository.registry._connect()) as conn:
            args: list[Any] = [self.repository.workspace, self.task_id]
            sql = "SELECT * FROM template_checkpoints WHERE workspace_id=? AND task_id=? AND namespace=''"
            if identity := config["configurable"].get("checkpoint_id"):
                sql += " AND checkpoint_id=?"
                args.append(identity)
            row = conn.execute(sql + " ORDER BY checkpoint_id DESC LIMIT 1", args).fetchone()
            if row is None:
                return None
            checkpoint, metadata = self.unpack(row)
            writes = conn.execute(
                """SELECT * FROM template_checkpoint_writes WHERE workspace_id=?
                AND task_id=? AND namespace='' AND checkpoint_id=? ORDER BY node_task_id,write_index""",
                (self.repository.workspace, self.task_id, row["checkpoint_id"]),
            ).fetchall()
            return CheckpointTuple(
                config=self.config(row["checkpoint_id"]),
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=self.config(row["parent_id"]) if row["parent_id"] else None,
                pending_writes=[self.unpack(w) for w in writes],
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        self.scope(config)
        raw = self.pack((checkpoint, metadata))
        with closing(self.repository.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            self.repository.fence(conn, self.task_id, self.claim)
            conn.execute(
                "INSERT INTO template_checkpoints VALUES(?,?,?,?,?,?,?)",
                (
                    self.repository.workspace,
                    self.task_id,
                    "",
                    checkpoint["id"],
                    config["configurable"].get("checkpoint_id"),
                    raw,
                    hashlib.sha256(raw).hexdigest(),
                ),
            )
        return self.config(checkpoint["id"])

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.scope(config)
        with closing(self.repository.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            self.repository.fence(conn, self.task_id, self.claim)
            for index, (channel, value) in enumerate(writes):
                idx = WRITES_IDX_MAP.get(channel, index)
                raw = self.pack((task_id, channel, value))
                mode = "REPLACE" if idx < 0 else "IGNORE"
                conn.execute(
                    f"INSERT OR {mode} INTO template_checkpoint_writes VALUES(?,?,?,?,?,?,?,?)",
                    (
                        self.repository.workspace,
                        self.task_id,
                        "",
                        config["configurable"]["checkpoint_id"],
                        task_id,
                        idx,
                        raw,
                        hashlib.sha256(raw).hexdigest(),
                    ),
                )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)
