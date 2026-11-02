# 02｜系统设计与数据契约

## 1. 不可变约束

1. 不修改 `app/research/models.py` 中旧 ResearchRun 的 `content == 原文引用拼接` 合同，也不更新旧历史数据；它可作为某一次对话 Turn 的证据子记录。
2. 不把 `TaskCheckpointer` 直接给会话使用。该类按 `task_id`/claim fencing / checkpoint 表设计，与聊天线程语义不兼容。
3. 新增 `app/conversations/` 与 `app/memory/`，独立 migration、Pydantic DTO、Repository、Service 和路由；在 `runtime_factory` 注入现有来源、RAG、财务服务和模型客户端。
4. workspace 从后端实际运行上下文确定，绝不信任浏览器传的 `workspace_id`、`owner_id`、`source_revision` 或可信 fact ID。当前项目仅 `demo` 本地单人空间；跨用户长期记忆必须等真正认证体系存在才能宣称。
5. 写操作各自拥有 request hash、operation_id、明确状态与读回机制；GET、焦点恢复、页面重新打开不得导致模型再生成或财务副作用。

## 2. 对话 Graph（建议）

```text
register_turn（服务层单事务，检查幂等和同会话串行）
    |
    v
load_context -> resolve_reference -> guard_scope -> intent_router
                                           |          |           |
                                       annual_rag  approved_fact  ask_clarify
                                           |          |           |
                                           +----- validate_tool_result
                                                       |
                                             draft_explanation（可选）
                                                       |
                                             guard_answer_and_citations
                                                       |
                                             commit_turn（服务层事务、读回）
```

`Graph` 中的业务工具为只读节点，不包含 ACCEPT、SAVE、RESUME 或修改资料。P0 全部工具为白名单，模型只能提交 Pydantic 严格参数，不能决定任意 SQL、文档身份或跨范围授权；拒绝工具请求中的额外字段。

- `load_context`：读取当前 Conversation、最近 N 个有效 Turn、必要摘要、已确认的偏好；所有外来内容作为 data。
- `resolve_reference`：解析企业、财务年度、指标、指代关系；返回结构化实体及不确定性；上下文无法唯一确定时返回澄清，不猜测。
- `guard_scope`：复验冻结选中的年报、版本、SHA 和当前有效状态。必须拒绝来源失效或不在本会话授权范围内的来源。
- `intent_router`：可选 `source_quote` / `confirmed_metric` / `compare_metric` / `clarify` / `unsupported`。能用规则判定的显式请求可不调用额外 planner 模型。
- `tool`：原文调用 existing `SelectedScopeSearch`/`RAGService`，财务读取现有有效事实并使用 `FinancialAnalysisService`，不能让 LLM 心算。
- `draft_explanation`：仅在有效证据或受控事实存在时模型生成简短解释；保留模型草稿/证据身份，分离未核实因果。
- `guard_answer_and_citations`：验证引用属于本轮冻结来源，所有 numeric claims 使用核准数据或明确标注“原文摘录”，没有支持则拒绝发布定量结论。
- `commit_turn`：放在 Graph 执行之外的 service/db 明确提交边界；处理校验成功后以原操作 ID 一次性写入终态，不从 Checkpoint 自动宣布成功。

## 3. 独立存储与迁移

沿用 `app/companies/migrations.py` 的**追加式、校验和迁移**，在 Codex 实施前检查下一个可用版本号；新建表和索引必须能在全新及既有 runtime 数据库中安全初始化，保留旧数据与旧迁移校验和。

推荐表（字段可以在 A0 根据现有表和类型做等价修订，但语义不可弱化）：

| 表 | 必要字段及约束 | 角色 |
| --- | --- | --- |
| `conversations` | `workspace_id`、`conversation_id` UUID、title、source_scope_sha、status、created_at/updated_at | 会话身份、来源范围、列表 |
| `conversation_sources` | workspace+conversation+document_id+source_revision+content_sha256+report_year，外键及唯一约束 | 冻结且显式选择的源文档 |
| `conversation_turns` | `turn_id`、`conversation_id`、seq、`operation_id`、`request_sha`、user_text、resolved_query、answer_payload、`research_run_id?`、status、created_at/ended_at、payload_sha | 幂等、不可变已完成消息、内容校验 |
| `conversation_tool_events` | turn_id、顺序、工具名、稳定状态、摘要、脱敏的证据身份 | 可观察性与审计（不记敏感 Prompt） |
| `conversation_summaries` | conversation_id、covered_through_seq、version、summary、source_turn_ids、updated_at | 短期历史压缩，绝非财务事实权威来源 |
| `memory_items` | workspace+local_principal+id+type+key+value+source_turn_id+confirmed_at+revision | 跨会话可管理的明确偏好 |
| `memory_events` | memory_id、动作、时间、无明文内容的审计信息 | 修改/删除留痕，不保存已删除正文 |

**单人作用域**：没有身份认证时 `principal` 只能标记为本地用户，绝不让前端自报 user ID 实现伪授权。后续多用户要增加服务端认证与历史隔离迁移。

写入不变量：
- `UNIQUE(workspace_id, conversation_id, operation_id)`；相同 operation+payload 返回旧状态，不同 payload 返回 409。
- 同一会话最多一个 `running` Turn；重叠提交拒绝 409 或排队，但不要并发双模型运行。
- `completed/refused/failed/interrupted` Turn 不可修改内容；可根据明确删除操作删除会话，不改变旧 `ResearchRun` 真值。
- 处理开始前持久登记 `running`，外部调用超时/HTTP 断开后 GET 只读取；重启 `running` 标记 interrupted/unknown，不自动重发模型。需区分用户主动发起新 operation 和对旧 operation 的只读查证。
- LangGraph Checkpointer（SQLite Saver 或独立受控实现）与会话终态主表不能互相冒充事务。正式对用户发布的回答以数据库终态 + 校验读回为准；checkpoint 只持久化内部过程状态。不能让未提交的 graph state 出现在成功答复。

## 4. 接口合同建议

全部 URL 以 `/api` 统一前缀由前端代理，服务端实际路由可定义以下路径：

```
POST   /conversations                              {document_ids:[...], title?:string} -> conversation_id
GET    /conversations?cursor=...&limit=...        -> 历史列表（只读）
GET    /conversations/{conversation_id}           -> 冻结来源+已提交历史（只读）
POST   /conversations/{conversation_id}/turns     {operation_id:UUID, text:string} -> turn_id/status
GET    /conversations/{conversation_id}/turns/by-operation/{operation_id}  -> 只读查证
DELETE /conversations/{conversation_id}           -> 显式删除会话内容，关联审计按策略处理
GET    /memories                                  -> 已确认研究偏好（只读）
POST   /memories                                  {operation_id, type, key, value, confirmed:true, source_turn_id?}
PATCH  /memories/{memory_id}                      {expected_revision, value} -> 新版本
DELETE /memories/{memory_id}                      -> 物理删除偏好正文、清除检索入口
```

用户说“记住……”时，服务端可生成“建议记住的偏好”供前端显示，但不得自动执行 `POST /memories`。只接受允许类型（分析侧重、展示单位、研究习惯等），拒绝把股票价格、资产金额、报告归因、未经核验表格、工具输出和个人敏感数据自动纳入偏好。

## 5. 受控工具

| 工具 | 实现约束 | 来源结果 |
| --- | --- | --- |
| `search_annual_report(query)` | 由冻结 SourceScope 生成实际检索过滤器；调用现有 RAG 证据校验路径 | 已核验的原文和页码 |
| `get_confirmed_metric(metric,period)` | 只接受三类现有指标；事实须有效、`local_operator`、来源最新且适合当前范围 | 有效事实 ID、来源与单位 |
| `compare_confirmed_metrics(metric,period_a,period_b)` | 仅使用已有确定性分析服务和 Decimal，不另建公式 | 差额/比例/局限性及两侧证据 |
| `get_conversation_memory(key?)` | 仅读取本地用户明确确认的偏好，有数量和长度上限 | 偏好文本，永不作为财务事实 |

如果用户请求的比较没有有效确认事实，返回 `needs_human_review` 与现有核对页面的受控跳转。不得以原文字符串自行计算，也不得自动将候选数据转正。

## 6. 上下文工程与成本

- P0：最近 6–8 轮（按 token 而非只按轮数限额）、当前企业和年份、已授权来源；遇到不明确的“它/上一年”主动澄清。
- P1：按达到上下文预算后生成摘要 `summary_v1`，记录 covered_through_seq。摘要仅辅助指代消解，不保存为财务事实；摘要出错可回查最近真实消息。
- 长期偏好：每次最多注入约 5–10 条确认为本地用户的偏好，摘要/长期偏好/证据各自有独立预算和优先级。
- 模型预算建议：一次明确请求最多 2 次通用模型生成（规划与受证据限制的答复）；最多 2–3 次只读工具调用，所有预算由配置和服务端强制执行。供应商可能实际收费/返回延迟，须用真实评测数据调整，不宣称稳定延迟。
- 无 SSE 的第一版先完整响应+执行中提示+可恢复历史。完成状态一致性以后再考虑 token 流式输出；不得把未校验 token 当成可信结果展示。

## 7. 数据与执行安全

- Prompt 注入：PDF、用户历史和记忆都属于不可信内容；PDF 中“保存此偏好/覆盖你配置”不能执行。
- 可信证据：旧引用仅能作为历史阅读，新的回答必须验证当前 `source_revision` 与已授权文档，旧事实失效则不显示为当前有效。
- 可用性：模型解释与原文/确认事实视觉标签不同。绝不能说“所有模型解释都已验证”。
- 并发：双击、两个标签页并发、供应商断连以及 Checkpoint 恢复不增加额外模型/写次数。
- 隐私：默认不上传聊天内容至第三方记忆服务。现有模型调用会把必要请求信息发往所配置的供应商；UI 应说明该事实。删除记忆后新会话不能再从存储检索，日志和备份策略应在说明里诚实告知。
- 本地演示环境如无法配置可信认证，不得公开部署带用户私人记录的写接口。

## 8. 实施前必须核实的依赖与删除边界

- 当前 `pyproject.toml` 只固定 `langgraph==1.2.13` 和 `langchain-core==1.5.0`；并没有显式引入 `langgraph-checkpoint-sqlite`。Codex 应在 **A0** 验证 SQLite saver 的确切兼容版本、异步调用接口和事务限制，不能把示例 `InMemorySaver` 当成跨重启持久化解决方案。如果不适合，独立实现受限 ConversationCheckpointer 或依靠对话主表构造每轮图输入，但仍须有真实可恢复的线程语义并明确权威数据源。
- 删除聊天会话与删除旧的不可变 `ResearchRun` 不是同一动作。若某条 Turn 链接了旧 Run，UI 必须解释保留/删除范围；本轮不得为实现“删除聊天”而破坏已有 ResearchRun 的不可变审计。真正的数据清除策略应分别定义会话、旧证据记录、长期偏好与备份的保留周期。
- 新的 SQL schema 使用 additive migration 与严格校验；不能使用 `DROP TABLE`、覆盖既有 checksum 或把当前测试数据库当作生产迁移验证。
