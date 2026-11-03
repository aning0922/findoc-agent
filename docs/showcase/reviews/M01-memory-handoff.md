# M01/M02 研究记忆最小合同（实现进行中）

基线 `b81962f`。独立研究记忆与旧 MemoryService 的枚举偏好分开；不修改旧迁移、Graph 或 runtime。拟注入 `ResearchMemoryService(runtime_root, workspace_id, sources, conversations, embedder, embedding_model_version, parse_service=None)`，提供独立 router；主控负责 runtime/gateway 接线。

- 三类 `research_question|note|saved_evidence` 都需明确 confirmed=true。前两类可无 document/conversation/turn，纯用户文本只作为研究线索；可选 company_id 须服务端核验。turn 必须与 conversation 成对并通过旧 repository 验归属；document_id/source_revision/company_id 成组，服务端调用 sources 复验。saved_evidence 必须携带 document/source/company/evidence_id；服务端读取原文并保存，不接受客户端伪造引文。artifact_id 仅在明确提供 parse_service 且身份/文本可验证时可支持；不可验证时安全拒绝，不将 OCR 当正式原文事实。
- generation 属于独立研究记忆上下文，不复用 lease generation 或 source revision。所有实际 create/patch/delete 在 SQLite 事务内原子变更 revision 与 memory_generation；删除留墓碑。操作 UUID 与请求 hash 持久化；unknown 不重放。embedding 使用本地 BGE，生成过程在事务外，回填时 CAS memory_id+revision+未删除；不允许过期向量复活。
- GET 列表可显示 stale；语义召回至多5项（q≤2000），只对服务端校验为当前来源、当前有效 revision 的记录做余弦排序，末尾二次读取有效行并核对 generation。返回 memory_generation 供后续 Agent 调用前/最终提交前重验；对旧 assistant 全文不回灌已删除笔记。注意独立 SQLite 与旧 conversation DB 不是同事务，主控必须为新 Agent 的最终写入提供可原子化 fencing；不能仅在写入前普通 GET generation 后宣称竞态已关闭。
- 写入、更新、删除使用 operation_id；PATCH/DELETE expected_revision，confirmed 明示。GET `/research-memories/operations/{operation_id}` 只查已登记状态；GET不调用 LLM。embedding_model_version 由服务端注入，不可从请求设置。列表/语义接口最多20条已保存笔记，超限拒绝；语义召回不产财务 facts。

source 失效的引用收藏不可召回；普通 note 无来源时仍可用，带来源后来源失效标 stale 并排除当前召回。对话被删时 source turn 不再通过校验；已发布历史回答不自动删除。以上是实现中合同，真实BGE/删除和竞态验证未完成。
