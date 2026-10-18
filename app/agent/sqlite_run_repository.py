from contextlib import closing
from datetime import UTC, datetime
import json
from uuid import uuid4
from pathlib import Path
import sqlite3

from app.agent.result_storage import (
    USER_RESULT_VERSION,
    AgentResultIntegrityError,
    AgentResultNotReadyError,
    AgentResultNotStoredError,
    StoredAgentUserResult,
    decode_user_result,
    encode_user_result,
)
from app.agent.user_result import AgentAnswer, AgentRefusal, AgentSystemError, AgentUserResult
from app.agent.run_models import (
    AgentRun,
    AgentRunNotFoundError,
    AgentRunStateConflictError,
    AgentTerminalStatus,
    RunEvent,
    RunEventSequenceError,
    RunEventType,
    RunStatus,
)


class SQLiteAgentRunRepository:
    """使用独立 SQLite 表持久化 Agent Run 和安全事件。"""

    def __init__(self, database_path: Path) -> None:
        """绑定数据库路径并幂等初始化 Run/Event 表。"""
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = database_path
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """创建启用外键约束的新 SQLite 连接。"""
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row

        # SQLite 的外键开关属于单个连接，不能只在初始化时设置一次
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        """幂等创建 Agent Run 和 Event 表。

        表级约束保护状态组合、事件外键和复合唯一性；
        连续 sequence、workspace 隔离和原子终结由 repository 写方法负责。
        """
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_runs (
                        run_id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK (
                                status IN (
                                    'running',
                                    'succeeded',
                                    'failed'
                                )
                            ),
                        terminal_status TEXT
                            CHECK (
                                terminal_status IS NULL
                                OR terminal_status IN (
                                    'success',
                                    'protocol_error',
                                    'tool_error',
                                    'provider_error',
                                    'max_steps_reached'
                                )
                            ),
                        started_at TEXT NOT NULL,
                        ended_at TEXT,
                        safe_result_json TEXT,
                        execution_config_version TEXT NOT NULL,
                        CHECK (
                            (
                                status = 'running'
                                AND terminal_status IS NULL
                                AND ended_at IS NULL
                                AND safe_result_json IS NULL
                            )
                            OR
                            (
                                status = 'succeeded'
                                AND terminal_status = 'success'
                                AND ended_at IS NOT NULL
                            )
                            OR
                            (
                                status = 'failed'
                                AND terminal_status IN (
                                    'protocol_error',
                                    'tool_error',
                                    'provider_error',
                                    'max_steps_reached'
                                )
                                AND ended_at IS NOT NULL
                            )
                        )
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS run_events (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL
                            CHECK (sequence > 0),
                        event_type TEXT NOT NULL
                            CHECK (
                                event_type IN (
                                    'tool_requested',
                                    'tool_succeeded',
                                    'tool_failed',
                                    'run_succeeded',
                                    'run_failed'
                                )
                            ),
                        payload_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        PRIMARY KEY (run_id, sequence),
                        FOREIGN KEY (run_id)
                            REFERENCES agent_runs(run_id)
                    )
                    """
                )

                # 只做非破坏性扩展；旧行保持 NULL，不回填不存在的产品结果。
                columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(agent_runs)")
                }
                for column in ("document_id", "user_result_version"):
                    if column not in columns:
                        connection.execute(f"ALTER TABLE agent_runs ADD COLUMN {column} TEXT")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_user_results (
                        run_id TEXT PRIMARY KEY REFERENCES agent_runs(run_id),
                        payload_json TEXT NOT NULL
                    )
                    """
                )

    def start_run(
        self, *, workspace_id: str, execution_config_version: str,
        document_id: str | None = None, user_result_version: str | None = None,
    ) -> AgentRun:
        """创建运行中 Run；产品路径须传核准文档及已知版本，非法输入不落盘。"""
        run_id = str(uuid4())
        status = RunStatus.RUNNING
        terminal_status = None
        started_at = datetime.now(UTC)
        ended_at = None
        safe_result = None
        if user_result_version is not None and user_result_version != USER_RESULT_VERSION:
            raise ValueError("不支持的用户结果版本")
        run = AgentRun(
            run_id=run_id, workspace_id=workspace_id, status=status,
            terminal_status=terminal_status, started_at=started_at, ended_at=ended_at,
            safe_result=safe_result, execution_config_version=execution_config_version,
            document_id=document_id, user_result_version=user_result_version,
        )

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO agent_runs (run_id, workspace_id, status, terminal_status, started_at, ended_at, safe_result_json, execution_config_version, document_id, user_result_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        workspace_id,
                        status.value,
                        terminal_status,
                        started_at.isoformat(),
                        ended_at,
                        safe_result,
                        execution_config_version,
                        document_id,
                        user_result_version,
                    ),
                )
                return run

    def _row_to_run(self, row: sqlite3.Row) -> AgentRun:
        """把 SQLite 行恢复为 AgentRun 领域对象。"""
        return AgentRun(
            run_id=row["run_id"],
            workspace_id=row["workspace_id"],
            status=RunStatus(row["status"]),
            terminal_status=AgentTerminalStatus(row["terminal_status"])
            if row["terminal_status"]
            else None,
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            safe_result=(
                None
                if row["safe_result_json"] is None
                else json.loads(str(row["safe_result_json"]))
            ),
            execution_config_version=row["execution_config_version"],
            document_id=row["document_id"],
            user_result_version=row["user_result_version"],
        )

    def get_run(self, *, workspace_id: str, run_id: str) -> AgentRun | None:
        """按可信 workspace 和 run_id 查询一次 Agent Run。"""
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT * FROM agent_runs WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, run_id),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_run(row)

    def append_event(self, *, workspace_id: str, event: RunEvent) -> RunEvent:
        """向运行中的 Run 追加一条连续的非终态安全事件。"""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                run_row = connection.execute(
                    """
                    SELECT status
                    FROM agent_runs
                    WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, event.run_id),
                ).fetchone()

                if run_row is None:
                    raise AgentRunNotFoundError(f"Run {event.run_id} 不存在")

                if RunStatus(str(run_row["status"])) is not RunStatus.RUNNING:
                    raise AgentRunStateConflictError(f"Run {event.run_id} 不是运行中状态")

                if event.event_type in {
                    RunEventType.RUN_SUCCEEDED,
                    RunEventType.RUN_FAILED,
                }:
                    raise AgentRunStateConflictError("终态事件只能由 finalize_run 写入")

                sequence_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0)
                    FROM run_events
                    WHERE run_id = ?
                    """,
                    (event.run_id,),
                ).fetchone()

                if sequence_row is None:
                    raise RuntimeError("读取 Event sequence 失败")

                expected_sequence = int(sequence_row[0]) + 1
                if event.sequence != expected_sequence:
                    raise RunEventSequenceError(f"下一条 Event sequence 必须是 {expected_sequence}")

                connection.execute(
                    """
                    INSERT INTO run_events (
                        run_id,
                        sequence,
                        event_type,
                        payload_json,
                        occurred_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.run_id,
                        event.sequence,
                        event.event_type.value,
                        json.dumps(event.payload, ensure_ascii=False),
                        event.occurred_at.isoformat(),
                    ),
                )

        return event

    def _row_to_event(self, row: sqlite3.Row) -> RunEvent:
        """把 SQLite 行恢复为 RunEvent 领域对象。"""
        return RunEvent(
            run_id=row["run_id"],
            sequence=row["sequence"],
            event_type=RunEventType(row["event_type"]),
            payload=json.loads(str(row["payload_json"])),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
        )

    def list_events(self, *, workspace_id: str, run_id: str) -> list[RunEvent]:
        """按可信 workspace 查询一次 Run 的全部有序事件。"""
        with closing(self._connect()) as connection:
            with connection:
                run_row = connection.execute(
                    """
                    SELECT 1
                    FROM agent_runs
                    WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, run_id),
                ).fetchone()
                if run_row is None:
                    raise AgentRunNotFoundError("Agent Run 不存在")
                rows = connection.execute(
                    """
                    SELECT * FROM run_events
                    WHERE run_id=?
                    ORDER BY sequence ASC
                    """,
                    (run_id,),
                ).fetchall()
                return [self._row_to_event(row) for row in rows]

    def finalize_run(
        self,
        *,
        workspace_id: str,
        terminal_status: AgentTerminalStatus,
        safe_result: dict[str, object] | None,
        terminal_event: RunEvent,
        user_result: AgentUserResult | None = None,
    ) -> AgentRun:
        """原子保存产品结果（若约定）、唯一结束事件和执行终态。

        输入的产品结果必须已在本次证据会话验证；此处检查结构及层级一致性。
        已终结时一律状态冲突；任一步失败向上传播，事务回滚，不重跑模型。
        """
        if not isinstance(terminal_status, AgentTerminalStatus):
            raise TypeError("terminal_status 必须是 AgentTerminalStatus")

        if safe_result is not None and not isinstance(safe_result, dict):
            raise TypeError("safe_result 必须是字典或 None")

        safe_result_json = (
            None if safe_result is None else json.dumps(safe_result, ensure_ascii=False)
        )

        if terminal_status is AgentTerminalStatus.SUCCESS:
            run_status = RunStatus.SUCCEEDED
            expected_event_type = RunEventType.RUN_SUCCEEDED
        else:
            run_status = RunStatus.FAILED
            expected_event_type = RunEventType.RUN_FAILED

        if terminal_event.event_type is not expected_event_type:
            raise AgentRunStateConflictError(f"终态 Event 必须是 {expected_event_type.value}")

        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                run_row = connection.execute(
                    """
                    SELECT *
                    FROM agent_runs
                    WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, terminal_event.run_id),
                ).fetchone()

                if run_row is None:
                    raise AgentRunNotFoundError("Agent Run 不存在")

                if RunStatus(str(run_row["status"])) is not RunStatus.RUNNING:
                    raise AgentRunStateConflictError("Agent Run 已经终结")

                version = run_row["user_result_version"]
                if version is None:
                    if user_result is not None:
                        raise AgentRunStateConflictError("此 Run 未约定产品结果持久化")
                elif version != USER_RESULT_VERSION or user_result is None:
                    raise AgentResultIntegrityError("新版本 Run 必须原子保存受支持的产品结果")
                if user_result is not None:
                    self._check_product_terminal(
                        result=user_result, terminal_status=terminal_status,
                        payload=terminal_event.payload, safe_result=safe_result,
                    )

                sequence_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0)
                    FROM run_events
                    WHERE run_id = ?
                    """,
                    (terminal_event.run_id,),
                ).fetchone()

                if sequence_row is None:
                    raise RuntimeError("读取 Event sequence 失败")

                expected_sequence = int(sequence_row[0]) + 1
                if terminal_event.sequence != expected_sequence:
                    raise RunEventSequenceError(f"终态 Event sequence 必须是 {expected_sequence}")

                final_run = AgentRun(
                    run_id=str(run_row["run_id"]),
                    workspace_id=str(run_row["workspace_id"]),
                    status=run_status,
                    terminal_status=terminal_status,
                    started_at=datetime.fromisoformat(str(run_row["started_at"])),
                    ended_at=terminal_event.occurred_at,
                    safe_result=safe_result,
                    execution_config_version=str(run_row["execution_config_version"]),
                    document_id=run_row["document_id"],
                    user_result_version=version,
                )

                # 三项共享当前连接/事务；不允许 INSERT OR REPLACE 覆盖历史结果。
                if user_result is not None:
                    connection.execute(
                        "INSERT INTO agent_user_results (run_id, payload_json) VALUES (?, ?)",
                        (final_run.run_id, encode_user_result(user_result)),
                    )
                connection.execute(
                    """
                    INSERT INTO run_events (
                        run_id,
                        sequence,
                        event_type,
                        payload_json,
                        occurred_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        terminal_event.run_id,
                        terminal_event.sequence,
                        terminal_event.event_type.value,
                        json.dumps(terminal_event.payload, ensure_ascii=False),
                        terminal_event.occurred_at.isoformat(),
                    ),
                )

                update_cursor = connection.execute(
                    """
                    UPDATE agent_runs
                    SET
                        status = ?,
                        terminal_status = ?,
                        ended_at = ?,
                        safe_result_json = ?
                    WHERE workspace_id = ?
                        AND run_id = ?
                        AND status = 'running'
                    """,
                    (
                        final_run.status.value,
                        terminal_status.value,
                        final_run.ended_at.isoformat() if final_run.ended_at else None,
                        safe_result_json,
                        workspace_id,
                        final_run.run_id,
                    ),
                )

                if update_cursor.rowcount != 1:
                    raise AgentRunStateConflictError("Agent Run 无法原子终结")

        return final_run

    @staticmethod
    def _check_product_terminal(
        *, result: AgentUserResult, terminal_status: AgentTerminalStatus,
        payload: dict[str, object], safe_result: dict[str, object] | None,
    ) -> None:
        """核对执行失败映射和两处产品摘要；拒绝用执行 success 冒充 answered。"""
        if type(result) not in (AgentAnswer, AgentRefusal, AgentSystemError):
            raise AgentResultIntegrityError("不支持的用户结果类型")
        if (
            payload.get("terminal_status") != terminal_status.value
            or payload.get("user_result_status") != result.status
            or safe_result is None
            or safe_result.get("user_result_status") != result.status
        ):
            raise AgentResultIntegrityError("用户结果与终态摘要不一致")
        loop_errors = {"protocol_error", "tool_error", "provider_error", "max_steps_reached"}
        if terminal_status is not AgentTerminalStatus.SUCCESS:
            if (
                not isinstance(result, AgentSystemError)
                or result.error_code.value != terminal_status.value
            ):
                raise AgentResultIntegrityError("执行失败必须对应同类产品系统错误")
        elif isinstance(result, AgentSystemError) and result.error_code.value in loop_errors:
            raise AgentResultIntegrityError("正常执行不能映射为执行层错误")

    def get_user_result(self, *, workspace_id: str, run_id: str) -> StoredAgentUserResult:
        """先按可信范围查 Run，再在同一读快照恢复受限结果；不调用模型或检索。

        不存在与错误 workspace 同为 not-found；运行中、旧版未存、新版不一致
        分别抛 NotReady、NotStored、Integrity 异常，不返回候选或损坏载荷。
        """
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN")
                row = connection.execute(
                    "SELECT * FROM agent_runs WHERE workspace_id = ? AND run_id = ?",
                    (workspace_id, run_id),
                ).fetchone()
                if row is None:
                    raise AgentRunNotFoundError("Agent Run 不存在")
                result_row = connection.execute(
                    "SELECT payload_json FROM agent_user_results WHERE run_id = ?", (run_id,)
                ).fetchone()
                try:
                    run = self._row_to_run(row)
                    if run.status is RunStatus.RUNNING:
                        if result_row is not None:
                            raise AgentResultIntegrityError("运行中的 Run 含有终态结果")
                        raise AgentResultNotReadyError("用户结果尚未提交")
                    if run.user_result_version is None:
                        if result_row is not None:
                            raise AgentResultIntegrityError("旧版 Run 含有未约定的产品结果")
                        raise AgentResultNotStoredError("此旧版或离线记录未保存产品结果")
                    if result_row is None or run.document_id is None:
                        raise AgentResultIntegrityError("已终结的新版本 Run 缺少产品结果")
                    result = decode_user_result(
                        result_row["payload_json"], version=run.user_result_version,
                    )
                    events = connection.execute(
                        """SELECT * FROM run_events WHERE run_id = ?
                        AND event_type IN ('run_succeeded', 'run_failed')""", (run_id,),
                    ).fetchall()
                    if len(events) != 1 or run.terminal_status is None:
                        raise AgentResultIntegrityError("产品结果缺少唯一结束事件")
                    event = self._row_to_event(events[0])
                    last_sequence = connection.execute(
                        "SELECT MAX(sequence) FROM run_events WHERE run_id = ?", (run_id,),
                    ).fetchone()[0]
                    expected_type = (
                        RunEventType.RUN_SUCCEEDED if run.status is RunStatus.SUCCEEDED
                        else RunEventType.RUN_FAILED
                    )
                    if (event.event_type is not expected_type or event.occurred_at != run.ended_at
                            or event.sequence != last_sequence):
                        raise AgentResultIntegrityError("Run 与结束事件不一致")
                    self._check_product_terminal(
                        result=result, terminal_status=run.terminal_status,
                        payload=event.payload, safe_result=run.safe_result,
                    )
                    return StoredAgentUserResult(
                        run_id=run.run_id, workspace_id=run.workspace_id,
                        document_id=run.document_id,
                        execution_config_version=run.execution_config_version,
                        result_version=run.user_result_version, user_result=result,
                    )
                except (ValueError, TypeError, KeyError, AttributeError):
                    raise AgentResultIntegrityError("已保存的用户结果或终态记录不合法") from None
