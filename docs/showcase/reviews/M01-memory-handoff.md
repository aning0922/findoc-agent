# M01/M02 研究记忆最小合同（实现进行中）

基线 `b81962f`。独立研究记忆与旧 MemoryService 的枚举偏好分开；不修改旧迁移、Graph 或 runtime。拟注入 `ResearchMemoryService(runtime_root, workspace_id, sources, conversations, embedder, embedding_model_version, parse_service=None)`，提供独立 router；主控负责 runtime/gateway 接线。

- 三类 `research_question|note|saved_evidence` 都需明确 confirmed=true。前两类可无 document/conversation/turn，纯用户文本只作为研究线索；可选 company_id 须服务端核验。turn 必须与 conversation 成对并通过旧 repository 验归属；document_id/source_revision/company_id 成组，服务端调用 sources 复验。saved_evidence 必须携带 document/source/company/evidence_id；服务端读取原文并保存，不接受客户端伪造引文。artifact_id 仅在明确提供 parse_service 且身份/文本可验证时可支持；不可验证时安全拒绝，不将 OCR 当正式原文事实。
- generation 属于独立研究记忆上下文，不复用 lease generation 或 source revision。所有实际 create/patch/delete 在 SQLite 事务内原子变更 revision 与 memory_generation；删除留墓碑。操作 UUID 与请求 hash 持久化；unknown 不重放。embedding 使用本地 BGE，生成过程在事务外，回填时 CAS memory_id+revision+未删除；不允许过期向量复活。
- GET 列表可显示 stale；语义召回至多5项（q≤2000），只对服务端校验为当前来源、当前有效 revision 的记录做余弦排序，末尾二次读取有效行并核对 generation。返回 memory_generation 供后续 Agent 调用前/最终提交前重验；对旧 assistant 全文不回灌已删除笔记。注意独立 SQLite 与旧 conversation DB 不是同事务，主控必须为新 Agent 的最终写入提供可原子化 fencing；不能仅在写入前普通 GET generation 后宣称竞态已关闭。
- 写入、更新、删除使用 operation_id；PATCH/DELETE expected_revision，confirmed 明示。GET `/research-memories/operations/{operation_id}` 只查已登记状态；GET不调用 LLM。embedding_model_version 由服务端注入，不可从请求设置。列表/语义接口最多20条已保存笔记，超限拒绝；语义召回不产财务 facts。

source 失效的引用收藏不可召回；普通 note 无来源时仍可用，带来源后来源失效标 stale 并排除当前召回。对话被删时 source turn 不再通过校验；已发布历史回答不自动删除。以上是实现中合同，真实BGE/删除和竞态验证未完成。

## 实现与验证（2026-11-03）

分支 `codex/showcase-m01` 基于 `b81962f`。新增 `app/research_memory/`，没有接入 runtime、gateway、Graph 或 UI。注入同一 runtime root/workspace 的 source service 和 conversation repository；可选 parse service 必须指向同一 root 和相同 source service。来源字段为 `source_conversation_id` 与 `source_turn_ids`（最多 8 个）、`company_id`、`document_id`、`source_revision`、`evidence_id` 或 `artifact_id`（后者还需 `physical_page` 与 `source_line_index`）。artifact 引文读取 parse quality 中的指定行并标记 `ocr_candidate_unreviewed`；该分支没有实测该路径，接线前仍需独立验证。引用与来源分别存在独立数据库，来源变化在校验后、返回前的跨库竞态未原子关闭。

`completed` 表示记忆与操作记录已持久提交，不保证向量已生成；列表的 `embedding_revision=null` 表示暂不可用于语义召回。嵌入失败不会凭空生成结果，也尚无自动重试任务。需要后续集成的控制器处理向量重建、删除记忆与 conversation 最终落库之间的跨库原子 fencing、来源变更竞态和查询/投喂预算。删除请求通过 DELETE 行为表达确认，不另要求 confirmed 字段；create/PATCH 必须明确为布尔 true。

- `.venv/bin/pytest -q tests/test_research_memory.py`：5 passed；合成来源 PDF，涵盖确认、重放、版本/代际、来源失效、查询和删除竞态、迟到向量及 router 基本请求。
- `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m tests.real_research_memory_bge`：通过；两条合成笔记、一次中文语义排序与删除后不召回。使用本地 `BAAI/bge-m3`，模型具体 revision 未知；没有 LLM 调用。不构成真实财务数据或召回质量验收。
- `ruff check`：新增代码和上述测试通过。未运行全量测试，也未进行集成、push、部署或真实数据验收。

## Agent 快照与发布栅栏合同（2026-11-03）

- `await service.recall_snapshot(q: str, company_id: str | None = None) -> dict`：返回 `schema_version`、`memory_generation`、`items`、`limitations`；最多五个 items，每项有 `memory_id`、`revision`、`text`、来源引用和 `source_status`。这是已有语义召回的包装，q 不可为空；只有当前来源和当前版本的有效向量参与。模型调用前可用 `service.check_generation(snapshot["memory_generation"])` 再检查，失败则丢弃快照并重新获取或中断；模型调用期间不持锁。
- `with service.publication_guard(expected_generation: int, memory_revisions: dict[str, int] | None = None): ...`：同步上下文管理器，成功进入不返回值。可把本次 items 的 `{memory_id: revision}` 作为第二参数。在内部以只读连接开始 SQLite 事务，读取 generation 取得 SHARED lock，并要求 journal mode 为 `delete`、`truncate` 或 `persist`；WAL 等其他模式抛出 `MemoryError(code="memory_fence_unsupported_journal", status=503)`。generation 或所传记录版本不匹配、删除时抛 `memory_context_changed`（409）。非法参数抛 422。数据库锁/IO 异常必须让调用方中断发布，不能降级为无锁发布。
- 最终 job 写入必须在 `with` 内完成并 **COMMIT 后才退出**；写入失败应回滚，退出栅栏后处理。这样先拿栅栏的发布先于删除/修改提交，先提交的删除/修改则使旧快照进栅栏失败。不要在栅栏内调用会写研究记忆数据库的代码，也不要把模型调用置于栅栏内。generation 包含整个 workspace 的记忆修改，非本次召回条目的修改也会使旧快照失效。
- 栅栏只约束本 SQLite 数据库：外部来源、conversation 与 job DB 的其他写入不受其保护，job owner 仍须根据自身提交协议复验来源并处理相关竞态。此前文档中“需要后续集成控制器处理删除与最终落库 fencing”指使用此合同完成接线，并非声明现有 runtime 已接线。不要回灌旧 assistant 全文；最终复验失败时丢弃新回答或保存 interrupted。
- 本地测试覆盖栅栏内另一 SQLite 数据库提交先于阻塞的记忆删除、删除后旧代际失败、错误 revision 拒绝和 WAL fail-closed；不能据此宣称生产部署或跨来源原子性。
