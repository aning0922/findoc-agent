# 07｜最小必要架构、DTO/API 和新旧合同边界

本文件描述**提案合同**，M0 需由 Codex 从实际源码进一步核实并冻结。用户要完整演示而非生产 SaaS：允许采用 SQLite、单进程/本地 worker、固定演示资料，但不可牺牲演示隔离与核心数据真实性。

## 7.1 推荐模块切分
```text
DemoShell / AuthGateway (独立控制层) ─── DemoLease / ResetManager / SeedManager
           │ 代际授权+路径路由
           ▼
React Dashboard + Conversation / Sources / Tasks / Reports
           │
FastAPI runtime_factory (主控唯一集成点)
           ├── Existing DocumentService/SourceService ── OfficialDisclosure adapter
           │                                           └─ ParseRouter (fast/OCR/quality)
           ├── Existing RAG + Milvus/BGE ── EvidenceService/QuoteValidator
           ├── Existing FinancialReview + FinancialAnalysis (Decimal)
           │                                   └─ ExtendedMetricService (V2)
           ├── Existing ConversationService/MemoryService
           │         ├─ IntentRouterV2 / ResearchHandoff
           │         └─ ResearchMemoryStore
           ├── DeepResearchSupervisor ── [EvidenceAgent, FinanceAgent, RiskAgent]
           ├── SynthesisService / StructuredFindings / ReportRenderer
           └── PublicExecutionEvents / EvaluationRunner
```

## 7.2 数据归属和迁移
| 数据 | 权威位置 | 是否重置 | 说明 |
|---|---|---|---|
| 演示密码/lease/generation | `demo_control` 独立持久库 | 不随会话重置 | owner 对外不泄密 |
| 可复原种子文件/原始 PDF/静态索引 | `demo/seed/vN` 只读 | 永不用户写入 | 有 SHA256 manifest |
| 访客临时业务库/会话/笔记/报告 | `demo/active/<generation>` | 每次会话结束重建 | old-generation write 无法污染新 runtime |
| V1.2 原数据库、ResearchRun、Task 和 Memory | 现有隔离 runtime | 不迁移历史时不改 | 迁移只追加版本，不改旧校验和 |
| 官方目录候选 | `disclosure_candidates`/只读缓存 | 可清 | 按来源和公告时间版本 |
| 下载文件引用 | `document_imports` | 复位归位 | 含原始 sha/官方来源URL |
| OCR 解析产物 | `parse_artifacts_v2` | 按来源版本保留/种子化 | 引用原 PDF 和 parser version |
| 扩展指标 | `extended_metric_facts` | 归位/新增 | 状态 candidate/confirmed/unsupported |
| 深度研究 | `deep_research_jobs`, `agent_steps`, `findings` | 归位/新增 | 保存公开事件和结构化结果 |
| 研究记忆 | `research_memory_items` | 归位/新增 | 来源指针、删除墓碑、检索 generation |

不得从公开登录 API 接收 `runtime_root`、`workspace_id`、`source_revision`、数据库表名、文件路径等授权参数；请求携带业务键只作为查找线索，服务端重新验证。

## 7.3 主要 API 提案
```
# Demo controller
GET    /api/demo/status
POST   /api/demo/login
GET    /api/demo/session
POST   /api/demo/logout
POST   /api/demo/takeover
GET    /api/demo/resets/{reset_id}

# Homepage
GET    /api/dashboard/overview          # KPIs, recent tasks, seed/real metadata
GET    /api/dashboard/charts?company_id=...&metric=...  # eligible rows only

# Documents
GET    /api/disclosures/search?code=...&report_year=...
POST   /api/disclosures/import           # stable candidate identity, explicit import
GET    /api/documents/{id}/parse-quality
POST   /api/documents/{id}/parse-retry    # explicit action, isolated work

# Research / Agent
POST   /api/research/intent              # proposal only (no side effects)
POST   /api/research/handoffs            # explicit user permission → existing task
POST   /api/synthesis/jobs               # source-qualified AI draft
GET    /api/synthesis/jobs/{id}
POST   /api/deep-research/jobs           # explicit user approval
GET    /api/deep-research/jobs/{id}
GET    /api/deep-research/jobs/{id}/events?after_seq=...

# Finance & Memory
GET    /api/financial/extended-metrics?company_id=...
POST   /api/financial/extended-analyses
POST   /api/research-memories            # explicit save of user research note
GET    /api/research-memories?company_id=...&q=...
PATCH  /api/research-memories/{id}
DELETE /api/research-memories/{id}

# Export/evaluation
GET    /api/reports/{id}/revisions/{rev}/export.pdf
GET    /api/evaluations/runs
POST   /api/evaluations/runs              # dev/demo administrator only
```

## 7.4 核心输出 DTO 草案
```json
{
  "schema_version": "research-finding-v2",
  "finding_id": "...",
  "kind": "confirmed_financial | sourced_excerpt | model_interpretation | unresolved",
  "text": "年报研究中的业务发现",
  "financial_refs": [],
  "evidence_refs": [{"document_id": "...", "source_revision": "...", "physical_page": 12}],
  "review_status": "verified_data | unreviewed_interpretation | pending_source_check",
  "origin": "deterministic_tool | rag_quote | model_draft | user_note"
}
```
这是说明字段集合的示意，正式 DTO 应采用枚举/多类型分支，不要直接将包含 `|` 的字符串用作 API 合法值。

```json
{
  "schema_version": "demo-session-v1",
  "state": "active",
  "expires_at": "2026-11-03T11:03:00+08:00",
  "remaining_seconds": 1199,
  "lease_generation": 22,
  "viewer_can_takeover": false
}
```
`viewer_can_takeover` 仅是 UI 展示提示，真正权限必须在服务端再次校验。拒绝/过期时不应泄漏其他访客身份。

## 7.5 数据合同必须冻结的问题（M0）
1. Demo Controller 是否独立于当前固定 workspace 的 FastAPI app？**建议独立**，否则 reset 当前 SQLite/Milvus 进程长期引用容易损坏。
2. Seed runtime 文件如何复制、BGE/Milvus warmup 需多久？先做一次真实重启 Spike，再确定快速 reset 优化必要性。
3. 官方文档是否有稳定且合规的发现/下载入口？不能假设第三方 JSON API 恒定可用。
4. OCR 引擎版本、输出 token/chunk/page metadata 与旧 `DocChunk` 如何映射？存两份解析版本还是只存最新？
5. 新扩展指标如何允许数据未核验时展示，又不进 V1.2 的 3-metric 既有事实服务？
6. 语义记忆与现有结构化偏好记忆是两个库还是共享 memory manager？删除与来源失效如何可靠联动？
7. 深度研究任务与现有 `research/tasks` 是独立 v2 数据表还是通过 adapter 组合？推荐 v2 独立，低风险复用旧工具。
8. 所有模型和 OCR 调用如何记录费用/成功状态并避免重置旧 generation 结果污染新环境？

## 7.6 工程兼容约束
- 旧 ResearchRun `Result.content` 是原文摘录，不许直接变成自由解释正文；新摘要用独立 schema。
- 旧 `TaskCheckpointer` 绑定任务 ID，ConversationGraph 当前无 saver；Multi-Agent 应用自己的 job state/持久记录，不绑定错误的旧 graph_id。
- 原财务三指标和原证据核验原封保留；扩展指标新表/新 adapter，不在首轮直接修改旧 immutable migration 或既有 receipts。
- 多 Agent 的工具来源/授权来自固定 server scope；agent_tool 的 `company_id`/`document_id` 输入不可作为最终授权凭证。
- 浏览器图表只消费服务端已明确身份的结果 DTO；不要在 React 中执行财务业务计算并发布为正式结果。

## 7.7 失败和重试要求（求职项目的最小必要值）
- 前端双击提交/网络超时：同一个 `operation_id` 不重复创建研究/下载/报告；GET 只读查询状态，未知不偷偷再 POST。
- 资料源失效：旧历史保留、后续引用/财务计算阻断或重新核验；不要拿老 SHA 当新源。
- OCR 超时：记录该文档 `partial_or_failed`，可以人工改用文本层/上传另份；不阻断全站。
- 单 Agent 执行异常：显示错误原因与建议操作，其他模块继续可用。
- 演示接管：属于必须正确的可信操作，旧 generation 请求不能写新环境；完整实现见 `03_`。
