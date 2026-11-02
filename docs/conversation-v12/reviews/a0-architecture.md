# A0 独立架构与边界审查

审查日期：2026-11-02（Asia/Taipei）。审查者范围：只读代码、设计输入与公开依赖元数据；仅新增本文件。目标是 findoc-agent 的独立 worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`，分支 `codex/conversation-memory-v12-20261102`，实读 HEAD `1f0a3d4131480ac0ea742772127afac3c892fc7c`。未改 findoc-rag、业务代码、数据库、锁文件，未提交或操作远程。已完整阅读 handoff 的五份文档。文档仅是设计输入。

## 结论

**有条件支持推进 A1；本报告不是 A1–G 验收通过。** 最窄实现是：同一 documents.db 中追加独立 Conversation/Memory 表；每个新 Turn 从已提交历史重建有限 Graph 输入；只读白名单工具；服务层唯一登记、预算与终态提交；重启只封存中断轮次，不续跑旧模型调用。保留多轮线程语义，不承诺中途节点恢复、time travel 或模型调用 exactly-once。

优先采用 **Graph 不配置持久 saver、会话主表持久化线程状态** 的方案，属于 handoff 02 第 8 节允许的替代路线。不能使用 InMemorySaver 宣称跨重启持久化。若主控选择真正持久 saver，须实施下文完整的双存储恢复矩阵，而不能仅给图设置 `thread_id`。

三个必须在 A1/A2 设计时解决的阻断：

1. Graph 返回值/检查点不能直接对用户发布；只有主表终态成功提交并校验读回的结果能发布。
2. 财务服务的资格验证不等于会话范围验证；必须额外验证 document、完整 source identity、明确披露版本，并在 Turn 提交事务中重新验证事实撤销状态。
3. 不可安装未固定版本的 SQLite saver：最新 3.1.3 与当前 checkpoint 4.2.0 的依赖要求不匹配。3.1.1 的元数据范围兼容，但尚未实际安装或运行验证。

## 1. 已核实的旧合同与复用边界

下表源码路径均相对本报告顶部的目标仓库；行号对应审查时基线。

| 核实项 | 代码证据 | 对 V1.2 的要求 |
| --- | --- | --- |
| 原文合同 | `app/research/models.py:71–118`：answered 必须 1–8 引用、verified_excerpts、human_review=pending，引用 identity 必须等于 documents，content 精确等于带年度/文件名/编号的原文拼接 | Conversation 使用新结果 DTO；绝不能放宽 Result 校验，也不能把自然语言改写存入旧 content |
| 历史不可变 | `app/research/schema.py:22–29` 终态与身份触发器；`app/research/repository.py:50–66,143–189` canonical/hash 校验、条件更新、启动恢复 | 原 ResearchRun 行、checksum、公开 payload 不改；会话删除不级联删除 Run |
| 单次 POST/GET | `app/api/research_runs.py:66–99,130–182`：登记后执行一次，失败不发布候选，GET 只读 | 借鉴边界，不通过内部 HTTP 调旧 POST 再盲目保存 Turn；这会制造第二套不受控登记及提交窗口 |
| TaskCheckpointer | `app/research/task_checkpointer.py:27–46,96–166`：构造绑定 TaskRepository/task_id/claim，拒绝非空 namespace，写 template_* 表并 fence | 禁止共用实例、表或将 conversation_id 冒充 task_id；它不是 MemoryStore |
| 经营任务收口 | `app/research/task_repository.py:295–375`：release 在事务内 admission，启动把 claim 中断收口，撤下候选数值 | 可以借鉴提交 admission 与 stale claim 思路；不能自动调用旧任务 RESUME |
| 完整来源身份 | `app/documents/preparation.py:93–145,156–192`：1–4 文档、归属、ready、封面匹配、完整 identity、选择 hash、检索过滤与复验 | 冻结完整 identity，不仅 document_id/year/SHA；每轮都把 fresh selection 与冻结 identity 比较，禁止静默升级 |
| 检索前后复验 | `app/rag/selected_scope.py:60–72`；`app/rag/service.py:453–550` | 复用 answer_selected；复杂表格拒绝路径与引用身份仍保留 |
| 只读财务入口 | `app/agent/financial_analysis.py:91–175,177–275` | 使用 admit_reference/analyze；三指标；local_operator；Decimal；零基数/非相邻期保持 partial 与 limitation |
| 范围补充检查先例 | `app/research/templates.py:169–208` 取得完整 fact 后再次检查 source.document_id 与 period 起止 | 新会话也必须加这一层，不能只调用 FinancialAnalysisService 就认定来源属于会话 |
| 财务最终资格检查 | `app/agent/revenue_confirmation.py:607–628`；`app/agent/sqlite_financial_facts.py:66–83` 提供 caller-owned transaction 的 recheck_financial_fact_sets_in | 工具结束后若还要 draft/持久化，原服务的最终读快照已结束；Turn commit 必须同事务再读完整事实组并比较，防止期间撤销 |
| 旧 /chat | `app/chat/service.py:53–86` 仅单次 PreparedChat + 同步 RAG 转线程 | 旧 SSE 不是多轮持久化；不改旧 transport 来冒充本功能 |
| 模型次数 | `app/rag/openai_compatible_llm.py:146–173` generate_once/complete 关闭 SDK retry；`app/rag/service.py:531` 未注入时会退回 generate | 新入口必须显式传 generate_once，并禁用图节点 retry/客户端 POST retry；重试权限不能继承旧 Agent loop |

ResearchRun 复用建议：P0 在 Turn 新 DTO 内嵌经旧 `Result` 校验的证据结果，`research_run_id` 可空，避免为每轮制造额外历史行；这保持旧合同，但需在主控设计中明确“复用结果合同，而非每轮必建旧 Run”。若产品要求每轮出现在旧问答历史，则由服务层建立稳定的 turn→child_run 映射和派生 operation ID，持久登记后才执行；恢复时只读 child Run，不能重新调用旧 POST。Run 完成而 Turn 未完成也不能自动把 Run 当成聊天成功。删除说明必须披露保留的 Run 中可能仍有问题文本。

## 2. 数据库与迁移提案

`app/companies/migrations.py:14–73` 当前版本为 1–9（REPORT_MIGRATION=9）。**基线下下一个版本是 10**；主控实际实施前需再次确认，不和其他工作者分别抢版本。`migrate():76–114` 验证连续版本与旧 checksum，单 BEGIN IMMEDIATE 内逐条 execute，DDL/日志同事务。不能修改 1–9、补写旧 checksum 或用 executescript 破坏事务。

建议 v10 只放 Conversation，v11 Memory/摘要可随 B 阶段追加。表共享 documents.db 才能复用来源/事实的事务内 admission；“模块隔离”不等于必须独立物理 DB。每条连接开启并验证 foreign_keys，旧初始化顺序保持。

最低结构（可等价实现，不是已执行 SQL）：

- `conversations`：复合 PK `(workspace_id,conversation_id)`，title、完整 scope hash、created/updated、revision、status(active/deleted)；身份与 scope 不可 UPDATE。列表索引 `(workspace_id,updated_at,conversation_id)`。
- `conversation_sources`：复合 FK 回 conversation；唯一 `(workspace_id,conversation_id,document_id)`；完整 Identity：company、report_type、period_start/end、basis、attempt、parser_version、source_revision、content_sha256、report_year。保存 canonical identity 与 digest，读取时校验列与 payload 一致；禁止 UPDATE 来源身份。
- `conversation_operations`：服务端作用域下唯一 operation_id，action、target、request_sha、status、result identity。覆盖 create/delete，避免仅 Turn 有幂等。删除后保留最小墓碑，不留问题/偏好正文；同 op 不能重建已删除数据。
- `conversation_turns`：复合身份、seq、operation_id、request_sha、user_text、resolved_query、resolved_focus、answer_payload、research_run_id?、status、error_code、claim/owner_epoch、config_version、model/tool reservation counters、created/ended、payload_sha。
- UNIQUE `(workspace_id,conversation_id,seq)` 与 `(workspace_id,conversation_id,operation_id)`；partial UNIQUE `(workspace_id,conversation_id) WHERE status='running'`。seq 分配、检查既有 op、抢 active、登记全部在同一个短 BEGIN IMMEDIATE 中完成。重复同 op 优先返回旧记录，不能因另一个新轮次 running 而误报旧 op busy。
- CHECK 终态需 ended_at，running 不得有公开 answer；触发器禁止终态 UPDATE 和身份变化；允许明确删除操作走受控删除事务。内容 hash 是损坏检测，不是权限凭证或防恶意篡改签名。
- `conversation_tool_events`：复合 FK 到 Turn、事件序号、类型、状态、脱敏身份、时间；预留外部调用前先持久化 reservation，失败不发调用。事件/预算必须纳入主表校验或有自身 digest；不记录完整 Prompt/供应商异常。
- `conversation_summaries`：conversation、covered_through_seq、version、summary、source_turn_ids/source_digest、memory_epoch、payload_sha；覆盖范围只能来自已提交有效历史。
- `memory_items`：workspace + 服务端固定 local_principal + id/type/key/value/source_turn_id?/confirmed_at/revision；同作用域规范 key 唯一；source_turn 删除时置空或保留无正文 provenance，不能反向阻止用户删除会话。
- `memory_events`：动作/id/revision/时间/operation_id；不留被删除的 value、旧 Prompt 或可恢复正文。Memory CRUD 同样需要 operation request hash 与 revision。

终态推荐 `completed/refused/failed/interrupted`，clarify/needs_human_review 是 answer kind/reason；客户端网络 UNKNOWN 单独表示“未确认服务端结果”，不能自行改主表为 completed/failed。不要把 GET 503 当成不存在、不要把 404 当成可自动重发的授权。

## 3. 提交、Checkpoint 不一致及安全恢复（核心闸口）

### 首选方案：主表持久线程 + 每轮无 saver 的有界图

1. POST 先校验 DTO 与 operation；在登记事务内冻结当前有效来源、seq、基线焦点/上下文版本、预算和 claim。相同请求返回已有状态；异载荷 409；其他 active turn 409。
2. 提交登记后才启动图；图输入由主表已提交有效 Turn、经校验摘要和当前有效偏好构造。只把会话 ID 作为服务端追踪身份，不暗示其能让无 saver 图自动恢复。
3. 所有模型/工具调用先短事务预留次数；无自动重试。网络 timeout/cancellation 后不重发。异步取消不能终止已经发出的同步 provider 线程，因此废弃 claim；迟到返回只能被丢弃。
4. Graph 只返回候选 DTO。执行最终外部原文件复验后，服务层开启 BEGIN IMMEDIATE：校验 claim+running、完整冻结 scope、完整事实组/撤销状态、结果与引用 schema、预算、memory epoch（如适用）；写终态、焦点、事件与 digest；事务内严格读回，再成功 commit。响应只由 commit 后的数据库读取形成。
5. 提交异常时先只读查证同 op：若完整终态已存在，返回该终态；否则明确 pending/unknown/503，不返回内存候选。在进程仍活着但落盘失败的场景，不允许同 op 再次执行；数据库恢复后可仅把残留 running 收口为 interrupted。不能用时间超时抢占仍可能执行的旧 worker。
6. 启动先取得 ResearchOwner 独占权，再将遗留 running 在单事务中标 interrupted/unknown_execution，清 claim、不给候选答案；才开放新请求。GET/页面焦点恢复不能做这一写动作。
7. 下一次用户明确发送新的 operation 时，重新从已提交历史恢复指代。旧失败/中断草稿不进入事实上下文；澄清历史只用于待澄清焦点，不冒充已确认财务真值。

此方案真正可跨重启恢复的是会话与下一轮上下文；**中断的这一轮不会继续跑**。这也是最窄、最容易证明不重放的承诺。无法保证外部供应商实际执行/计费 exactly-once：崩溃可发生于发送后、落库前，只能保证本应用不自动发第二次。

### 若选择独立持久 saver，以下矩阵必须成立

所有 checkpoint 必须带 workspace/conversation/turn/operation/request_sha/source_scope_sha/config_version/claim。`thread_id=conversation_id` 不足以隔离不同轮次；至少使用独立 namespace 或显式绑定同一轮的 checkpoint ID。不能自动载入“这个 thread 最新的 checkpoint”继续下一轮。

| 主表状态 | Checkpoint 状态 | 唯一安全行为 |
| --- | --- | --- |
| 无 Turn | 有任意图状态 | 视为 orphan；不发布、不执行；受控维护时清理，GET 不修复 |
| running | 无/较旧/损坏 | 当前 owner 存活时只返回 running；重启独占恢复标 interrupted；不重跑 |
| running | 已有最终候选 | 仍未提交，不是成功；重启标 interrupted，不从 checkpoint 自动补交/再 invoke |
| completed/refused | 无/旧/保存失败 | 主表校验通过即可返回其终态；图持久化失败不能倒退终态，下一轮从主表重建 |
| failed/interrupted/deleted | 有最终候选或待执行任务 | 主表优先；丢弃候选，禁止 invoke(None)/Command(resume)/replay |
| 任意状态 | scope、operation、claim 或 payload hash 不符 | 隔离/拒绝，不能以图状态“修复”主表 |
| 主表损坏/读取不可用 | 图完整 | 返回 integrity_error/unavailable；绝不降级从图发布回答 |

不能把 SqliteSaver 使用同一个 SQLite 文件解释为共享同一事务。它的连接、锁、commit 与应用仓储分开。也不能长时间持有数据库写事务等待网络模型返回。若持久 saver 没有安全 fencing，只能作为可丢弃的诊断缓存，不能恢复执行。conversation delete 同时删除 saver 全线程与 pending writes，或墓碑先拦截所有访问，再做可追踪清理；不能让旧 checkpoint 重建已删除偏好。

## 4. 来源、财务与上下文约束

来源 hash 使用现有 PreparedDocumentSelection 的 canonical 规则（默认 ASCII JSON，排序 documents），不要直接用 `models.canonical(ensure_ascii=False)` 产生另一个同名 selection_id。冻结完整身份；prepare_many 拿到“当前同 document_id”以后必须比较冻结值，而不是覆盖旧 scope。一个来源失效时整轮拒绝，不静默丢掉该文件继续。

报告年度与财务期间分开：2025 年报可能披露 2024 财务数值，不能用 `period in report_years` 作为唯一资格判定；事实期间必须取服务端事实与来源关系。多个有效披露版本，即使金额相同，也不得用“最新/首条”悄悄代选。首版若文本无法明确确定版本，则返回 clarification + 服务端候选标签，下一次用户选择再生成新 Turn；没有任何合格事实则 needs_human_review。不能把已有 fact_id 当 bearer token。

确认事实工具适配层：query_financial_facts 仅发现候选身份（`app/agent/revenue_confirmation.py:863–905`）；按冻结 document/revision、企业、期间、metric、披露版本过滤；唯一且明确的选项才 admit_reference，检查 fact.source.document_id 与完整身份。比较交给 analyze；commit 使用 `recheck_financial_fact_sets_in` 在同一数据库事务重新验证组，不能只复验 source。单指标读取也要做最终 admission。撤销只改事实有效性时，source hash 未必变化。

首版“它/上一年/同比/现金流也这样吗”用小型焦点结构 `{company_id,metric,periods,disclosure_choice,comparison_mode,source_turn_id}` 和严格消歧。同范围多企业、缺基期、年份含义不明，均澄清。用户说“换一家”只能引导新建会话。焦点来自已提交对话/明确用户选择；摘要、PDF、偏好不能授予范围。

P0 回复只有原文证据、确定性财务卡、澄清/拒绝/核对链接。可选解释放新 DTO 的 `interpretation_status=pending_human_semantic_review`，默认关闭；ID 校验不能证明解释语义正确，简单扫描数字也不够验证定量结论。若开启自由解释则需单列 A4/G 人工语义审查，不扩大成“所有结论已核验”。

所有来源/PDF/核对跳转由服务端身份构建，打开时再次验证。历史 GET 可附只读的有效性投影，但不能修改历史正文或把历史计算重算为当前值。标记为历史快照；纯 DB 投影只代表 DB 当前资格，不宣称重新读过 PDF 字节。

## 5. 最窄 API 合同

统一 extra=forbid、strict=True；workspace/principal/source_revision/可信 fact ID 不允许由任意客户端字段授予权限。所有写都需要操作身份，补齐交接设计中 create/PATCH/DELETE 漏掉 operation_id 的部分。

| API | 请求/行为 |
| --- | --- |
| POST /conversations | `{operation_id,document_ids:[1..4],title?}`；后端冻结完整身份；首次 201，重复返回既有结果 |
| GET /conversations | 有界分页/签名 cursor；服务器 workspace；no-store |
| GET /conversations/{id} | 来源、历史、焦点、动态有效性标签；只读，无模型/工具/恢复写 |
| POST /conversations/{id}/turns | `{operation_id,text}`；可扩展有限的用户明确选择 DTO，但服务端复验映射；先持久登记，完成200/运行202，冲突409 |
| GET /conversations/{id}/turns/by-operation/{op} | 严格绑定同 conversation；只读查证；不存在404/不可用503，不触发重发 |
| GET /conversation-operations/{op} | 查 create/delete 丢响应；仅服务端 scope；避免 create 已成功但 ID 丢失无从查证 |
| DELETE /conversations/{id} | operation_id（header 或严格 body）、expected_revision；running 时409最简单；事务删除正文/摘要/事件并留最小墓碑，不删 ResearchRun |
| GET/POST /memories | POST `{operation_id,type,key,value,confirmed:true,source_turn_id?}`；有界类型/长度/数量；confirmed 仍需独立用户 action，禁止工具调用 |
| PATCH/DELETE /memories/{id} | operation_id + expected_revision；修改/删除冲突409；删除后最小审计与 op tombstone 不保存 value |
| GET /memory-operations/{op} | 只读确认丢响应的创建/修改/删除结果 |

推荐 Turn answer DTO 为 tagged union：`source_quote`（旧 Result）、`confirmed_metric`、`financial_analysis`（既有服务原结果）、`clarification`、`needs_human_review`、`refusal`。服务端生成 evidence_refs/fact_refs，模型只输出受限候选选择；禁止客户端/模型任意 URL 或任意财务 payload。DTO 包含 schema/config version 与解析出来的企业/指标/期间，方便 UI 展示“本轮按……理解”。

## 6. Runtime 与依赖

`app/api/runtime_factory.py:195–198` 必需模型配置和 BGE warmup 在初始化前；不能为读历史调用完整 runtime。现有 `app/api/research_history_app.py:28–63` 提供无模型/检索恢复部署；新 Conversation 读路由也须可注入仅 repository 的方式挂载，启动恢复在 owner 下进行，不在 GET。

常规 runtime 在同一 `ResearchOwner` 生命周期中构造 conversation repository/service；复用 selection_preparer、selected_scope_search、rag、revenue_service，并显式实例化 FinancialAnalysisService。owner 获取失败、启动失败、关闭都要释放；不能加第二个不相干锁导致同库多 writer。生产多 worker 不在本地单进程承诺范围。

依赖核实（公开 PyPI 元数据和 wheel 源码在线只读检查，未安装、未执行 saver）：

- 本地 `pyproject.toml` 固定 langgraph=1.2.13/langchain-core=1.5.0；`uv.lock:2063–2091` 锁 checkpoint=4.2.0；没有 sqlite saver/aiosqlite 显式依赖。
- [SQLite saver 3.1.3 元数据](https://pypi.org/pypi/langgraph-checkpoint-sqlite/3.1.3/json)：要求 checkpoint>=4.3.1,<5。3.1.2 要求>=4.3.0。均需要改变当前 checkpoint 锁定结果，不是“零影响增依赖”。
- [3.1.1 元数据](https://pypi.org/pypi/langgraph-checkpoint-sqlite/3.1.1/json)：requires aiosqlite>=0.20、checkpoint>=4.1.0,<5、sqlite-vec>=0.1.6；其版本范围包含4.2.0，属于可供隔离验证的候选，不等于已证明 runtime 兼容。
- 3.1.1 wheel `langgraph/checkpoint/sqlite/aio.py` 的 async context manager `from_conn_string:133–144` 使用 aiosqlite；`aget_tuple:346`、`aput:509`、`aput_writes:561`、`adelete_thread:602`；put/write/delete 分别独立 commit（552/600/620），无法与主仓储自动原子提交。
- [官方持久化概念](https://docs.langchain.com/oss/python/langgraph/persistence)区分 thread checkpoint 和跨 thread store；没有规定应用应把它们当作已提交业务结果。

选择推荐的主表重建方案无需新增 saver 包。若改选3.1.1，主控需隔离 lock resolution、异步两轮+重启、pending write/cancel/delete、序列化允许类型和故障注入测试；不接受仅 import 成功就宣布兼容。

## 7. 阶段范围与旧 UX 回归

| 阶段 | 最窄可交付内容 | 不可省的闸口 |
| --- | --- | --- |
| A1 | v10、严格 DTO、create/list/detail/register/read-op/delete、确定性 fake handler、owner 恢复 | 双 op/同 op、冲突、partial unique、提交不明只读、终态不可变、损坏拒绝、迁移回滚/旧 checksum |
| A2 | 每轮无 saver StateGraph，有限焦点、3指标与三个只读工具、预算、最终同事务 admission | 供应商0 retry、来源/事实撤销竞态、模糊消歧、多版本澄清、失败无候选公开 |
| A3 | /conversations 独立页面、1–4来源、历史/消息/明确发送/只读恢复；旧问答深链保留 | 路由身份、响应迟到、UNKNOWN 不POST、原文 PDF、移动抽屉/键盘 |
| A4 | fake 全状态 + 有限真实年报/模型 smoke + 旧合同回归 | fake 不冒充真实；真人确认缺失时 blocked 是正确结果；记录未覆盖 |
| B1 | 明确保存的研究偏好 CRUD、revision/op查证、删除审计 | 模型/PDF无写入口；本地固定principal；删除不留正文副本 |
| B2 | token有界近期历史+可回查摘要、当前偏好注入 | 20+轮；摘要来源digest；不保存金额真值；删除后缓存/摘要不可复活偏好 |
| G | 独立审计、有限live日志、截图/演示、文档与交付证据 | 回答/工具/模型次数、真实/替身标记、真人语义审核边界；无证据不声称上线/生产验收 |

B2 最窄摘要建议先使用确定性焦点/进度摘要，记录覆盖 seq 与未决问题，不另增模型调用。偏好只在每次 Prompt 构造时从当前 MemoryStore 读，不嵌入永久摘要/Graph checkpoint；删除/修改递增 memory_epoch，后续请求废弃旧缓存。历史用户原话可以依法定产品删除策略保留为历史，但不能再把其中已删除偏好当活跃指令自动提取；source_turn_id 非事实授权。已发给供应商的请求无法撤回，删除后的未来调用必须不再注入旧值；UI 对历史和备份边界应如实描述。

前端修改点：`frontend/src/product/productRoutes.ts` 的 Page/URL/parser/pathFor，`AppShell.tsx:10–15,31,43–61,110` 的导航/active/焦点，实际页面装配入口；只改标签无法新增路由。目前 `/research?mode=qa` 仍由 `ResearchWorkbench.tsx:24–43,84–92` 管理 return_task 与独立问答，必须保留。会话选来源不写全局企业选择、不改变旧 task scope。

`QADialog.tsx:8–18` 与 AppShell 已处理 modal close、overflow、returnFocus；新抽屉关闭/卸载/切宽/来源失效都要清理，避免两个独立抽屉互相恢复错误的 overflow。切路由后迟到的 POST 响应不能插入另一个会话；网络 Abort 不等于服务端已取消。pending operation 应保留按会话查证的身份。

旧 UX 证据 `product/ux-simplification/verification.md` 记录184 PASS/25 SKIP、161后端、57不同浏览器用例以及一次真实QA；这些是**既有文档报告，本审查没有重跑**，不能算V1.2通过。`.github/workflows/quality.yml:25–27` 只覆盖部分旧后端，不等于完整V1.2安全回归。

## 8. 主控必须新增的高风险验证

在主控拥有实施/隔离测试授权时执行；本审查不运行会写数据库的测试。

1. 每个 crash point：登记前后、reservation后发请求前、供应商返回后commit前、commit成功响应丢失、checkpoint成功主表失败、主表成功checkpoint失败；同 op 请求和 GET 的模型次数不增长。
2. 同会话不同 operation 双标签互斥；重复旧 operation 在新轮运行时仍返回原状态；事务登记失败0模型；旧 claim 迟到结果不覆盖新轮。
3. Graph 候选含虚构引用/页码/fact_id、跨workspace/thread checkpoint、破坏 payload/hash；均不发布、不触发补跑。
4. 字节/metadata变化、来源纠错、事实接受撤销发生在工具后/commit前；最后一次同事务 admission 阻断数值。数据库锁竞争时仍不向客户端泄露候选。
5. 全新库与保留旧行的v9隔离副本升级；v10 DDL中途注错全部回滚；1–9 checksum/原ResearchRun规范payload/旧资料SHA前后相等。使用备份副本，不在原资料/正式DB验证迁移。
6. 断网重开、无模型依赖历史入口、GET0写/0模型/0检索；原run/task/report链接保留；READ失效不重算历史。
7. confirmed事实多版本、报告年≠财务期间、零基数/负基数/非相邻年、无local_operator；只用现有Decimal服务并保留partial。
8. 删除偏好/改值后新旧会话下一轮不注入旧值；摘要、checkpoint、缓存不恢复；重复DELETE可查证，重放POST不能复活；会话删除不删旧Run且说明保留范围。
9. 390/1440与旧七宽度关键路径；焦点、滚动锁、Esc/Tab、PDF失效撤下、迟到响应、双击与0自动ACCEPT/SAVE/RESUME。

现有测试入口可复用断言模式：`tests/test_d17_history.py`（三状态、并发、提交失败、旧checksum、取消、0retry），`tests/test_d19_tasks.py`（claim、checkpoint损坏、release撤销/提交失败），`tests/test_d11_financial_analysis.py`，`tests/test_runtime_startup.py`；前端 `frontend/e2e/ux-simplification-*.spec.ts`、财务边界与报告既有套件。不能以新增fake测试替代旧流程回归。

## 9. 证据限度与最终处置

本轮执行了目标HEAD/branch/status读取、交接/源码/测试定义/锁文件审阅、官方PyPI元数据及指定wheel内存只读检查；只写此报告。**未运行业务测试、迁移、live模型、浏览器或真实财务核对；未读取或改写实际runtime数据库；未验证供应商可用性、旧验收文件当前存在性或正式资料SHA。**这些均不是PASS。

审查时发现主控并行新增 baseline.md/orchestration.md，未覆盖。A0可结束并交主控推进；首选路线无须为普通实现选择再次询问用户。若主控坚持“Graph自动续跑中断轮”或“模型自动确认/保存财务事实”，必须作为违反已定边界拦截，而不是隐藏实现。

主控收敛确认（报告完成时）：主控已采纳“主表权威、每轮重建 Graph、不升级 saver 依赖”。因此第 3 节双存储矩阵是备用设计边界，不是当前 A1 的额外实现任务；第 5 节供主控冻结前后端 API。G 全量独立复审留待主控后续安排。末次 git status 显示其他执行者正在新增 Conversation 前端与修改路由/弹窗；这些并发变更不属于本审查写入，也未在本 A0 重新审计。本报告对旧源码的行号结论以所读基线为准。
