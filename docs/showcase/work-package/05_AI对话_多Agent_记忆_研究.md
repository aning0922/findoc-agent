# 05｜AI 核心升级：对话、自然语言理解、Multi-Agent、记忆和深度研究

## 5.1 V1.2 的真实基础（不要从零再造）
- `app/conversations/graph.py`：LangGraph 有限状态图、当前 `checkpointer=None`，每轮从 Conversation 主表重构上下文；不是任意任务规划。
- `app/conversations/context.py`：关键词/语法规则恢复企业、年份、指标和有限指代；复杂自然语义未支持。
- `app/conversations/tools.py`：真实原文引用、已确认事实和确定性比较，旧严格 ResearchRun 内容不变。
- `app/memory/`：目前是用户明确保存的少量枚举研究偏好，不是任意自然语言语义记忆。
- `app/agent/operating_research_graph.py`：固定经营研究流程的 durable checkpointer/人类确认；不要复用 TaskCheckpointer 作为对话记忆表。
- 新版应**添加新能力并组合**，不要修改既有不可变研究记录或直接删除既有迁移。

## 5.2 三种研究模式（前端可见，底层共享服务）
| 模式 | 用途 | 工具与限制 | 预计模型调用 |
|---|---|---|---|
| 快速问答 | 原文/指标/追问 | LLM 意图识别 + 原文 RAG / 已核准数值 | 0–2 次为上限建议 |
| 综合分析 | 某公司经营、财务、风险摘要 | 多路只读查证+综合解释草稿+图表 | 2–5 次建议 |
| 深度研究 | 多企业/多年度复杂研究 | Supervisor + 若干子 Agent + 报告整合 | 约 4–10 次建议（真实需预算控制） |

**注意**：上述次数是目标预算，不承诺实时必然达到。简单题不要启用 Multi-Agent；“缺财务确认”可以返回行动卡，不能生成看似确定的同比。

## 5.3 LLM 意图解析层（最值得增强）
- 输入：本轮用户文本、当前会话冻结资料范围、最多 8 轮相关历史结构摘要、用户已确认偏好；不从前端接受 workspace/fact authority。
- 输出 `IntentV2` 结构：`mode`、`goal`、`company_ids`、`periods`、`metric_keys`、`actions`、`confidence`、`clarifying_question`、`source_turn_ids`、`requires_confirmed_facts`。公司/年份/指标必须程序二次解析与核对，模型提议不是权限。
- 支持示例：“刚才讲的那一年呢”“把那两家公司按现金流比较一下”“我只关心风险，不要计算比例”“根据已有证据整理成报告草稿”。
- 失败降级：模型格式不合格→有限规则解析→仍不可靠则澄清；不凭概率过低的猜测执行复杂工具。
- 用户消息与 PDF 原文均当不可信指令，prompt 注入不得改工具范围/模型预算。
- 关键测试：错误公司、超过四份报告、财务年度/报告年度混用、因果解释/原文摘录意图区分、删除偏好后的旧上下文影响。

## 5.4 可信综合分析新协议
**定义统一的 `ResearchFindingV2` 输出**，每条 finding 包含：
- `finding_type: confirmed_financial | sourced_excerpt | model_interpretation | unresolved_question`。
- `claim_text`（中文可读内容）、`fact_refs[]`（服务端核实的财务实体）、`evidence_refs[]`（文档/源版本/物理页/段落）、`interpretation_review_status`（unreviewed/reviewed_by_user）。
- `origin: tool | verified_rag | model_draft | user_note`、`confidence_label` 为状态提示，不把自报置信度当真值。
- AI 解释可以自由写文字，但涉及金额/比率/百分数的断言必须关联后端确定性结果或明确降级为“未核实”；建议使用程序级数值渲染和 LLM 只输出解释字段。

流程：冻结选择→检索实际原文→读取已核准事实（若无则保留空/请用户核对）→结构分析→LLM 整理解释草稿→程序核验引用/数字→历史保存→报告输入。
- 不用覆盖旧 `ResearchRun` `content == 原文拼接` 的严格约束；新综合解释使用新模型/表/接口，旧历史仍可读。
- **演示案例**：2025 年收入变化与经营现金流、近年风险披露、实际 PDF 引用和“解释未经审核”标签。

## 5.5 Multi-Agent 方案（真分工、少角色）
- `Supervisor`（主控）：以目标输出可编辑/确认计划；校验预算/授权；分配任务，合并各子代理结果，决定是否请求用户核对。
- `EvidenceResearchAgent`：根据冻结来源调用检索工具，输出引用和相关原文，不能算财务数据。
- `FinanceAgent`：查询已核准事实和既有 Decimal 工具，输出数据变化和待核对需求，不能修改确认数据。
- `RiskOperationsAgent`：从年报中整理经营/风险段落，给出证据与未验证解释。
- `ReportAgent`（可选轻量）：将结构化 findings 生成摘要/章节顺序，不直接创建已审核正式报告。
- `Verifier`（程序组件，不一定是 Agent）：验证工具归属、source revision、数值、引用及预算；另一个 LLM “说没问题”不能替代。
- Graph 状态按 `plan→delegate→collect→verify→draft→save`；至少一处是真正根据计划条件选择不同子任务，而非所有角色每轮都跑。
- 子 Agent 间交接传结构化结果和可追溯 id，不传无限原始聊天或 PDF 全文；保存任务事件供 UI 可视化。
- **演示要求**：同一研究任务，切换 `快速单 Agent` 与 `深度 Multi-Agent` 对比任务调用次数、耗时、输出范围及命中引用。Multi-Agent 不好时如实展示而非美化。

## 5.6 记忆层：保留偏好 + 新增语义研究线索
- 目前已确认的记忆：关注哪个指标、偏好的显示单位和证据优先；要让首页图表顺序、推荐问题和报告视觉优先级明显受它影响。
- 新 `ResearchMemory` 范围只选择：收藏引用、用户主动记下的结论、后续研究问题、对某家公司分析的历史研究进度；**不是用户私人账户/敏感资料的万能画像**。
- 触发保存：用户明确收藏、点击保存研究笔记、对话中明确“记住这次未完成的问题”；AI 可提议候选但不能无确认自动写入长期记忆。
- 存储字段：`memory_id / scope / type / text / source_conversation_id / source_turn_ids / company_id / document_id / source_revision / created_at / confirmed_at / revoked_at / embedding_model_version` 等。
- 使用复用现有 BGE/Milvus 或小规模 SQLite+embedding adapter；数据量很小，优先低成本。每次召回先按企业/来源过滤再语义排序；必须判断 source changed/edited/deleted。
- 用户可列表管理、删除或更新；删除后未来新的上下文不可召回，即使向量索引有残留，也需在最终数据库授权层过滤。
- **真实 Demo**：“上次研究美的现金流时还有哪些问题没解决？” → 返回上一条已保存研究笔记及关联报告/原文；删除后不再返回。

## 5.7 执行可视化和流式状态
- 不是展示真实链式思维（CoT），而是用户可解释的任务节点：`资料准备 / 证据检索 / 财务核验 / Agent 分工 / 解释生成 / 引用审核 / 保存结果`。
- 建议 SSE 事件 `task_id / event_seq / event_type / label / state / public_summary / timestamp`；事件来自持久化审计，客户端重连按 `last_event_id` GET 读取，刷新不能重调模型。
- 如果实现逐字流式解释，必须标“生成中草稿，未经核验”，最终结果由已保存、通过验证的版本覆盖；更简便的 Demo 是阶段式 SSE + 最终答案完整展示。
- Agent 执行面板能展开每个子任务、耗时、工具名、文档来源与错误；默认收起难懂的原始 schema。

## 5.8 与经营研究工作流联动
- 对话在新建研究时传 **研究意图**，不直接提交事实/receipt/金额。
- 用户确认目标/企业/期间 → 现有 Task 模块根据当前资料重建合法研究请求 → 等待人工接受和保存数据 → 明确 resume → 输出结果/报告 → 原会话追加一个“关联研究任务”链接。
- 缺少指标、来源未就绪、错期年份时，尽量返回“缺少哪一步”而不是通用 error。
- 旧会话、已保存研究与报告只读历史保持不变；与新多 Agent 结果另用 v2 合同，不要往 v1 表硬塞新数据类型。

## 5.9 真实面试考点映射
| 功能 | 候选人应能讲清楚 |
|---|---|
| 意图解析与工具调用 | LLM 提议/程序授权分离；Pydantic / 白名单 / 参数校验 |
| 多轮上下文 | 线程级短期记忆、摘要、意图切换、不混公司年度 |
| Multi-Agent | 分工理由、Graph 路由、共享状态、预算与退出条件 |
| 语义记忆 | 写入时机、召回排序、源失效、删除防复活 |
| RAG/财务 | 引用真实页码、版本冻结、人工确认、Decimal 算术 |
| 失败处理 | 幂等/UNKNOWN、双击重试、后台任务取消边界 |
| 评测 | 任务成功率、引用正确率、拒答、单/多 Agent 对比和成本 |
