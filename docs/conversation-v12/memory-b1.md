# B1：明确确认的研究偏好

日期：2026-11-02，Asia/Taipei。实现范围限 `app/memory/**`、`tests/test_memory_b1.py` 与本文；没有改共享 migration registry、runtime、会话代码或前端，没有 git 提交，没有访问正式数据或调用真实模型。

## 接入方式

```python
from app.memory.api import create_memory_router
from app.memory.repository import MemoryRepository
from app.memory.schema import MEMORY_MIGRATION
from app.memory.service import MemoryService

# backend 统一将 MEMORY_MIGRATION 追加到 MIGRATIONS（v11），再初始化已有公司仓储。
# 此模块不自行迁移或创建数据库，复用 companies._connect。
repository = MemoryRepository(companies)
service = MemoryService(repository)
app.include_router(create_memory_router(service))
# DB-only history app 如需只读偏好入口：
# app.include_router(create_memory_router(service, read_only=True))
```

构造器没有 IO；服务端作用域固定 `demo/local_operator`，没有 caller 可选 workspace/principal 参数。路由实际路径不含 `/api`（代理负责该前缀）：

- `GET /memories` → 严格 MemoryList（items + generation），`GET /memories/{id}` → MemoryItem。
- `POST /memories` → 201 MemoryItem，原操作相同载荷重放 200。
- `PATCH /memories/{id}` → 200 MemoryItem；需要独立 `confirmed:true`、operation_id 与 expected_revision。
- `DELETE /memories/{id}` → 200 无正文 MemoryOperation；需要 operation_id 与 expected_revision。
- `GET /memory-operations/{op}` → 200 无正文 MemoryOperation，查证创建/修改/删除。

DTO 字段与 backend-a0 第3.4节一致；所有 nullable 响应字段显式为 null；创建请求的 source_turn_id 可以省略，显式值必须为 UUID（不接受 null）。UUID 校验 lowercase canonical，extra forbid、strict 类型校验；数字/字符串 `1`/`"true"` 不能代替明确布尔确认。写请求不能指定 workspace/principal/owner/revision 等服务端身份。

`MemoryService.create(request)` 返回 `(MemoryItem, replayed)`；`update(id, request)` 返回 MemoryItem；`delete(id, request)` 返回 MemoryOperation。`get/get_operation/list` 只读。MemoryError 有 `status_code/detail`；HTTP 仅映射固定错误码或脱敏 503，SQL/路径/原始异常不返回客户端。所有已注册路由的成功、HTTP 错误和请求校验错误响应均设置 `Cache-Control: no-store`；query 中的 workspace_id/owner_id/principal_id/source_revision/selection_id 返回 422 workspace_is_server_owned，不静默忽略伪授权参数。

## Graph / B2 的协作边界

- `service.recall_context()` / `repository.recall_context()` 每次开启新的读取事务，返回同一 SQLite snapshot 的当前条目与 generation；没有持久 prompt、缓存或模型调用。当前仅三个 key，最多三条；Graph 的最多五条预算仍须由 Graph 保证。
- `service.excluded_source_turn_ids()` / repository 同名方法返回 `frozenset[str]`，包含已保存/曾保存偏好的用户出处 UUID。CRUD 不删除这些无正文标记；删除正文后旧出处也不能重新进入新 prompt。
- B2 必须合并这些 exclusions 与自己的管理 turn 标记、过滤上下文/摘要，并在调用前/发布前 recheck generation；本实现不宣称已完成在途模型 fencing，也不替 B2 修改摘要表或既有会话 Turn。
- backend 在删除会话事务内、实际删除 turn 前调用 `MemoryRepository.detach_source_turns_in(connection, turn_ids)`。只将本地偏好 `source_turn_id` 置 null，不改变 revision/generation 或旧 turn payload，且不删除偏好正文。出处 UUID 排除标记保留，无旧聊天正文；同 workspace 来源校验在新建偏好事务中完成。**该协作调用尚需 backend 集成。**
- `extract_user_memory_candidates(user_text, source_turn_id)` 为纯函数，返回 MemoryCandidate 列表。仅九种完整明确中文用户表达映射有限 enum，例如“记住：我更关注现金流。”；引用、否定、嵌入报告文字和任意财务/敏感文本不匹配。Graph 必须只传当前已登记用户原话，不能传模型/PDF/tool 输出；函数不保存候选、不执行确认/接受/继续，也不证明任意 caller 的文字来源。

## 存储和幂等

仅导出 `MEMORY_MIGRATION=(11, "research_preferences_v1", statements)`；没有注册迁移。v11 建立五张 Memory 所有的表：`memory_items`、`memory_operations`、`memory_events`、`memory_context_generation`、`memory_context_exclusions`。B2 的 conversation summary/exclusions 表由 backend 统一设计与注册，本模块不争抢。所有 SQL 用现有迁移器逐条 execute 的事务；无 executescript 或旧迁移修改。

条目 `UNIQUE(workspace_id,principal_id,type,key)`，SQL CHECK 与严格模型同时限制九种 enum 值。相同 operation 的 kind、目标及 canonical 请求 hash 必须一致，检查在新动作/source 校验之前。每次实际创建/修改/删除事务 generation +1；重放/失败/GET 不递增。修改确认时间随新明确确认更新；创建时 revision=1，修改和删除分别 current+1（删除回执也记录新 revision）。

创建/修改旧 operation 在条目已更新时重放 409 `memory_operation_superseded`，已删除时 410 `memory_deleted`；应以 `GET /memory-operations/{原operation_id}` 查证。删除后重新建立同 key 生成全新 memory_id，旧 op 继续 410。删除 op 本身重放原无正文回执，不受该 key 后续重新建立影响。revision 冲突、重复 key、operation 请求冲突分别为固定 409 错误。

事务物理删除 active value，并将该 memory_id 的既有回执标记 resource_deleted。审计、回执、排除表没有 value/raw request/旧正文，仅保留 ID、hash、动作、revision、时间。读回在 commit 后重新连接完成；提交/读回失败不返回内存候选。SQLite 空闲页、备份与供应商端不属于取证级擦除承诺；历史已提交回答保持原状。

## 隔离验证

使用现有 Python：`/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python`，cwd 为本 worktree。

```bash
python -m pytest tests/test_memory_b1.py -q -p no:cacheprovider
python -m ruff check app/memory tests/test_memory_b1.py
```

结果：**31 passed，0 failed，0 skipped（0.70秒）；ruff All checks passed。** 实际使用临时 SQLite + FastAPI TestClient；fixture 临时 monkeypatch MIGRATIONS 追加 v11。覆盖：

- DTO/enum/确认/服务端身份拒绝（含 query 伪授权）、no-store 响应、精确响应字段；CRUD、重放、generation、无正文回执/审计、删后新 identity。
- 不同载荷/目标/动作复用 op，过期 revision，superseded 与 deleted 防复活。
- 两连接同 op、同 key、同 revision 并发各只有一次写入。
- 同 workspace 用户 turn 来源、跨 workspace 拒绝、出处排除、会话删除协作 detach 不修改 terminal turn。
- GET SQL trace 无 INSERT/UPDATE/DELETE/CREATE，read_only router 无写路由；重新实例化可恢复。
- 旧迁移日志/校验和不变、失败 DDL 回滚、foreign_key_check、SQL enum/audit immutable constraints。
- commit 失败无条目/回执；commit 后 readback 失败 503，随后 GET 可查到真实回执；事务异常回滚且不泄漏原始错误。
- 纯候选映射不接受报告嵌入、否定、财务/敏感资料。

未运行完整后端、前端、真实模型、真实 PDF 或 browser；迁移注册、runtime 装配、会话删除协作、B2 上下文过滤/fencing、前端中文 label 由主控安排集成与高推理边界复验。
