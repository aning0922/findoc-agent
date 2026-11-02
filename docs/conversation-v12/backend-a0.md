# FinDoc V1.2 Backend A0 — 合同冻结提案与基线

日期：2026-11-02，Asia/Taipei。状态：**A0 完成；供主控冻结，尚未实现 API / schema / graph。**

仓库绝对路径：`/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`，是 `findoc-agent` 的独立 worktree。分支 `codex/conversation-memory-v12-20261102`，HEAD / 本地 main 均为 `1f0a3d4131480ac0ea742772127afac3c892fc7c`。未 fetch，未据此宣称远端当前状态。开始时 `docs/conversation-v12/` 已为 untracked。本聊天只新增此文档；不提交、不修改业务代码、实际 runtime 数据库、依赖或 Git 状态，不读取配置密钥。测试使用临时 fixture 数据库，不是实际 runtime。

已阅读交接目录五文件及以下实际代码：`app/research/{models,schema,repository,task_checkpointer}.py`、`app/api/{research_runs,research_qa,research_history_app,runtime_factory,financial_analyses}.py`、`app/documents/{preparation,source_repository,source_schema}.py`、`app/rag/{selected_scope,service,openai_compatible_llm}.py`、`app/agent/{runtime,financial_analysis,revenue_confirmation,sqlite_financial_facts,execution_budget}.py`、`app/companies/{migrations,sqlite_repository}.py`、`frontend/src/product/ResearchWorkbench.tsx`、`product/ux-simplification/verification.md`、现有 quality workflow 与相关测试。未发现适用的 AGENTS.md。

## 1. 建议主控直接冻结的决策

1. **主表权威 + 每轮重建输入**：独立 `ConversationRepository` 保存 thread / turn，LangGraph `compile(checkpointer=None)`；`thread_id=conversation_id` 只是运行配置，不冒充 durable saver。跨重启连续对话由主表恢复，进程中途失败的旧 turn 不续跑。主控已通过消息采纳此方向。
2. A1 先完成 DTO / migration 10 / repository / service / fake handler / 只读恢复入口；A2 再接真实 LangGraph 与现有服务；B1 追加 migration 11，B2 加受限摘要/召回。migration 号提交前重新核对，只由主控安排集成。
3. P0 输出是原文摘录或现有确定性财务结果；`interpretation_status="not_generated"`。自由解释不混入原文，也不声称已实现通用数值语义校验器。解释能力另经合同升级和单独闸口。
4. 保持现有**披露版本必须明确选择**：发送 DTO 增加可选 `fact_selections`。它们是用户选择的查找键，服务端逐一验证，绝非前端自报可信事实。没有明确选择时返回 `needs_human_review`，不自动选“最新/唯一/第一个”事实。不改变 ACCEPT / SAVE / RESUME。
5. 新增 `operation_id` 到创建、删除、记忆变更请求；相同 ID 不同载荷 409。创建/删除/记忆写也提供只读按 operation 查证，解决“创建响应丢失不知道 conversation_id”的缺口。
6. 同会话一条 running turn，DB partial unique index + `BEGIN IMMEDIATE`；新 operation 重叠 409，相同 operation 优先回读。固定来源不可 PATCH，换来源新建会话。
7. P0 同步 POST 等待完整结果；重复 POST 可得到 202 running；GET 一律 200 只读投影。浏览器遇 UNKNOWN 只轮询 GET。无 SSE、后台自动续跑或供应商重试。
8. 不强制每个 turn 新写 ResearchRun。直接调用 `RAGService.answer_selected` 并用现有 `Result` 验证嵌入结果，避免双仓储提交。`research_run_id` 为 nullable，仅指向真实已存在旧 Run；不生成伪链接。

## 2. 已核实的复用与影响面

| 现有入口 | 可以复用 | 必须保持的边界 |
| --- | --- | --- |
| `DocumentTaskPreparer.prepare_many/revalidate` | 全部选中文档、workspace、ready、封面正向核验、字节身份、selection hash | `manual_check` 不够；返回 `matches_cover` 才能采用；范围不能静默缩小 |
| `SelectedScopeSearch` | selection filters、表格上下文、原文证据、前后来源复验 | 不另建检索器；不支持复杂表格时维持现有拒绝 |
| `RAGService.answer_selected` | 单轮受控原文问答；传 `generate_once`，严格 `Result` 验证 | 本身不写历史；计算意图会拒绝，不绕过该规则让其心算 |
| `ResearchRepository` | 借鉴 canonical/hash、读回、分页、终态不可变、启动 interrupted | 不把聊天自由文本存进 `research-answer-v1`；不改旧 checksum/数据 |
| `FinancialAnalysisService.admit_reference/analyze` | 现有三指标、资格校验、Decimal、单位/口径/相邻年度/零基数处理 | `local_operator`；本地 simulated 测试不能升格为真人核准 |
| `RevenueConfirmationService.read/query/recheck_*` | 当前有效事实与来源复验，最终提交事务内复核 | `query_financial_facts` 明确 `automatic_selection=False`；不能替用户选披露版本 |
| `OpenAICompatibleLLMClient.generate_once` | SDK `max_retries=0` 单次调用 | 不用默认 `generate` 构成未知结果重试；不继承其他 workflow retry loop |
| `ResearchOwner` | 现有整个 runtime 单写进程 flock、启动恢复期间排他 | runtime 与 DB-only history app 均需相同 owner；不从 GET 触发 recovery |
| `runtime_factory` / `research_history_app` | 前者注入执行依赖，后者挂只读路由无模型/BGE/Milvus | 不在模块导入时启动 runtime；恢复入口不能要求供应商在线 |
| 旧 `/chat` / `AgentRuntimeService` | 异步边界、受控 registry 的代码模式 | 单文档、无线程历史，不能宣称已支持多轮或直接当新 graph |
| `TaskCheckpointer` | 仅作为 fencing 风险参考 | task_id + claim + template 表绑定；既不是 Conversation store，也不是跨会话 Memory |

A1/A2 的预期改动归属：新增 `app/conversations/{models,schema,repository,service,api,graph,tools}.py`（graph/tools 在 A2），仅在 `app/companies/migrations.py` 追加新 migration 引用；在 `runtime_factory.py` 注入新 service/router，在 `research_history_app.py` 加无执行依赖的读 router。B1 新增 `app/memory/`。不改旧 ResearchRun/TaskGraph 合同与财务公式。共享装配文件及迁移由主控串行集成，前端以本文 DTO 独立开发。

## 3. HTTP 与完整 DTO 提案（`conversation-v1` / `memory-v1`）

所有 JSON 请求 `strict=True, extra="forbid"`。UUID 是标准小写 canonical 字符串；时间为带 UTC offset 的 ISO 8601；hash 是 64 位小写十六进制；所有 key 明确存在，nullable 用 `null`，列表为空用 `[]`。`workspace_id/owner_id/source_revision/selection_id` 不能出现在写请求顶层；workspace/principal 固定来自运行上下文 `demo/local_operator`。下列 TypeScript 是语言中立 JSON 合同，后端用 Pydantic 实现。

### 3.1 共享来源、证据、动作

```ts
type UUID = string;
type Hash = string;
type Instant = string;
type Metric = "revenue" | "net_profit_parent" | "operating_cash_flow";

interface SourceSnapshot {
  workspace_id: string; document_id: string; company_id: string;
  report_year: number; report_type: string; period_start: string; period_end: string;
  basis: string; source_revision: Hash; content_sha256: Hash;
  attempt: number; parser_version: string;
}
interface SourceState {
  document_id: string; source_revision: Hash;
  status: "current_at_read" | "expired" | "unavailable";
}
interface EvidenceRef extends SourceSnapshot {
  ref_id: string; number: number; chunk_id: string; physical_page: number;
  source_file: string; text: string; kind: "paragraph" | "table";
  verification: "exact_original_with_context";
}
// EvidenceRef 去掉 ref_id 后等于现有 research.models.Citation。
interface FinancialFactRef {
  ref_id: string; fact_set_id: string; fact_id: string; receipt_id: string;
  document_id: string; company_id: string; source_revision: Hash;
  disclosure_version: string; report_year: number; period: number; metric_key: Metric;
  value_cny_yuan: string; currency: "CNY"; unit: "CNY_YUAN";
  confirmation_kind: "local_operator"; validated_at: Instant;
}
// fact refs 只表示在 validated_at 已验证；历史 GET 不是再次核准。
interface Action {
  kind: "open_source" | "review_facts" | "open_research_run" | "new_conversation";
  label: string;
  href: string; // 服务端允许的相对站内 URL，拒绝模型/调用者提供的 URL
  document_id: string | null; source_revision: Hash | null;
  physical_page: number | null; research_run_id: string | null;
}
interface FactSelection {
  company_id: string; metric_key: Metric; period: number;
  fact_set_id: string; fact_id: string; disclosure_version: string;
}
```

`FactSelection` 无金额、workspace、可信 revision；服务端从事实恢复 revision，并验证与该 conversation 的某个完整 source identity 一致。事实年度 `period` 与年报 `report_year` 是两个字段：2025 年报中的 2024 年比较列可以是合法 2024 事实，不强制 `period==report_year`。来源冻结不禁止同一份年报中的合法比较列；当前 scope 没有该期资料时不得扩展到未选文档。

`Action.href` 只能由服务端以已验证身份按现有前端路由和 PDF API 组装；来源打开仍经 D6 真实字节复验。前端不从模型文本提取链接为特权动作。新 conversation 页面链接是 `/conversations`；`review_facts` 复用既有核对入口，具体 path/query 必须在 A0 总合同中与前端确认后共用 builder，不能由后端猜测生成会自动写操作的 deep link。

### 3.2 Turn 请求与响应

```ts
interface CreateTurnRequest {
  operation_id: UUID;
  text: string; // trim 后非空，原值保存；最大 1000 字符
  fact_selections?: FactSelection[]; // 缺省 []，最多 6；只允许明确选择
}
type TurnStatus = "running" | "completed" | "refused" | "failed" | "interrupted";
type Intent = "source_quote" | "confirmed_metric" | "compare_metric" | "clarify" | "unsupported";
interface ResolvedQuery {
  text: string;
  intent: Intent;
  company_id: string | null;
  metric_key: Metric | null;
  periods: number[];
  resolution: "explicit" | "context" | "ambiguous";
  context_turn_ids: UUID[]; // 真实已提交 turn，不能由模型伪造
}
interface Analysis {
  schema: "financial-analysis-v1";
  status: "compared" | "partial";
  metric_key: Metric;
  current_ref_id: string; previous_ref_id: string;
  absolute_change: string; percentage_change: string | null;
  percentage_reason: string | null;
  warnings: string[];
  formula_id: "financial_absolute_change_v1";
  percentage_formula_id: "financial_yoy_signed_base_v1";
}
// 公式 ID 在 A2 从既有服务实际返回映射；不得重算或暗改其公式含义。
type MemoryKey = "analysis_focus" | "display_unit" | "research_habit";
interface MemoryCandidate {
  type: "research_preference"; key: MemoryKey;
  value: string; source_turn_id: UUID;
  confirmation_required: true;
}
interface TurnResult {
  kind: "source_quote" | "confirmed_metric" | "comparison" | "clarification"
      | "needs_human_review" | "unsupported" | "error";
  answer_text: string;
  evidence_refs: EvidenceRef[];
  verified_financial_fact_refs: FinancialFactRef[];
  analysis: Analysis | null;
  interpretation_status: "not_generated" | "pending_human_review";
  reason_code: string | null; error_code: string | null;
  actions: Action[]; // 按推荐顺序，前端最多突出一个主要动作
  memory_candidates: MemoryCandidate[]; // A1/A2 一律 []，B1 才启用
}
interface ToolEvent {
  sequence: number;
  tool_name: "search_annual_report" | "get_confirmed_metric" | "compare_confirmed_metrics";
  status: "started" | "completed" | "refused" | "failed" | "unknown";
  summary: string; evidence_ref_ids: string[]; created_at: Instant;
}
interface Turn {
  schema_version: "conversation-turn-v1";
  conversation_id: UUID; turn_id: UUID; operation_id: UUID; seq: number;
  status: TurnStatus; user_text: string;
  resolved_query: ResolvedQuery | null;
  fact_selections: FactSelection[];
  result: TurnResult | null;
  research_run_id: UUID | null;
  tool_events: ToolEvent[];
  created_at: Instant; ended_at: Instant | null;
  provider_outcome: "not_started" | "returned" | "unknown";
  usage: {model_attempts: number; tool_calls: number};
  historical_snapshot: boolean;
  source_states: SourceState[];
  financial_fact_validity: "not_applicable" | "validated_at_completion_only";
  integrity_sha256: Hash; // 权威 turn payload，不包含动态 source_states
}
```

状态不变量：running 的 `result/ended_at` 为 null；terminal 二者均非 null。clarification 是 completed，下一次澄清答复创建新 operation/turn，绝不覆盖旧 turn。缺确认事实是 refused + needs_human_review；错误是 failed/interrupted + error，answer_text 只能是服务端固定安全提示，refs/analysis 为空。source_quote 的 answer_text 严格等于旧 Result.content，evidence_refs 来自严格 Citation；confirmed_metric/comparison 的文本由服务端模板和已确认 Decimal 字符串产生。A2 不接受模型自由生成金额/页码/fact ID。`provider_outcome` 表示已预留的尝试是否返回；崩溃后的 unknown 不说明供应商没有处理或收费。

`financial_fact_validity=validated_at_completion_only` 避免只读历史将旧 fact ref 冒充“现在仍有效”；历史 UI 显示计算时已验证，当前有效资格仅在新 turn 发布前重新证明。`source_states` 是 DB 只读资格投影，不代表实际 PDF 字节再次验证，与旧历史契约一致。

### 3.3 创建、列表、详情、删除、operation 查证

```ts
interface CreateConversationRequest {
  operation_id: UUID; document_ids: string[]; title?: string;
}
interface ConversationSummary {
  conversation_id: UUID; title: string;
  status: "active";
  source_scope_sha: Hash; // 使用既有 selection_id 的确切序列化，不另算不兼容 hash
  sources: SourceSnapshot[]; source_states: SourceState[];
  created_at: Instant; updated_at: Instant;
  last_turn_seq: number; active_turn_id: UUID | null;
}
interface ConversationDetail extends ConversationSummary {
  schema_version: "conversation-v1";
  turns: Turn[]; // 最近一页，按 seq 升序显示
  next_before_seq: number | null;
}
interface ConversationList {
  schema_version: "conversation-list-v1";
  items: ConversationSummary[]; next_cursor: string | null;
}
interface DeleteRequest {operation_id: UUID}
interface OperationRecord {
  schema_version: "conversation-operation-v1";
  operation_id: UUID; kind: "create_conversation" | "send_turn" | "delete_conversation";
  status: "running" | "completed" | "refused" | "failed" | "interrupted";
  conversation_id: UUID; turn_id: UUID | null;
  resource_deleted: boolean; created_at: Instant; ended_at: Instant | null;
  error_code: string | null;
}
interface APIError {detail: string} // 与现有 HTTPException 一致；不回显 provider/raw SQL
```

| 方法与服务端路径（前端统一 `/api` 代理） | 成功 JSON 与 HTTP | 明确规则 |
| --- | --- | --- |
| POST `/conversations` | 201 ConversationDetail，重放 200 | 1–4 份去重、排序年报；title 1–120，不传固定“新会话”；create hash 含排序 IDs、title/null，不含实时 revision |
| GET `/conversations/by-operation/{op}` | 200 ConversationDetail | 专门查证创建会话；必须匹配 create_conversation；deleted 410；该静态路由注册在 `/{id}` 前 |
| GET `/conversations?limit=20&cursor=...` | 200 ConversationList | limit 1–50；按不可变创建 sequence DESC，游标绑定 workspace/filter/ceiling；不是 mutable updated_at 翻页 |
| GET `/conversations/{id}?limit=50&before_seq=...` | 200 ConversationDetail | limit 1–100；只读，历史分页；不做 source IO/摘要生成/LLM |
| POST `/conversations/{id}/turns` | 200 terminal Turn，202 running Turn | 首次同步执行；重放只读，不重新 prepare/re-run；同 op 不同 hash 409 |
| GET `/conversations/{id}/turns/by-operation/{op}` | 200 Turn（含 running） | 不存在 404；deleted 410；GET 不能回收 running 或恢复执行 |
| GET `/conversations/{id}/turns/{turn_id}` | 200 Turn | 同 conversation/workspace 绑定，错配 404 |
| DELETE `/conversations/{id}` + DeleteRequest JSON body | 200 OperationRecord | active turn 409；显式内容删除；重复 delete operation 同结果 |
| GET `/conversation-operations/{op}` | 200 OperationRecord | create/turn/delete 断连均可按原 ID 查证；无凭据和原文内容 |

通用错误码：422 invalid_request / workspace_is_server_owned；404 resource_not_found；409 operation_request_conflict / conversation_busy / source_changed / source_not_ready / report_identity_unverified；410 conversation_deleted；503 conversation_read_failed / conversation_save_failed / source_verification_unavailable / conversation_integrity_error。已登记 turn 的模型/引用/预算失败写 terminal Turn，HTTP 200 便于一套状态读取；登记前错误使用 HTTP 错误。保存或读回失败只能 503，绝不把未读回草稿当成功。

### 3.4 Memory DTO（B1/B2 的冻结提案，A1/A2 不挂假路由）

```ts
interface MemoryItem {
  schema_version: "memory-item-v1"; memory_id: UUID;
  type: "research_preference"; key: MemoryKey; value: string;
  source_turn_id: UUID | null; revision: number;
  confirmed_at: Instant; created_at: Instant; updated_at: Instant;
}
interface MemoryList {schema_version: "memory-list-v1"; items: MemoryItem[]; generation: number}
interface CreateMemoryRequest {
  operation_id: UUID; type: "research_preference"; key: MemoryKey;
  value: string; confirmed: true; source_turn_id?: UUID;
}
interface PatchMemoryRequest {
  operation_id: UUID; expected_revision: number;
  value: string; confirmed: true;
}
interface DeleteMemoryRequest {operation_id: UUID; expected_revision: number}
interface MemoryOperation {
  schema_version: "memory-operation-v1";
  operation_id: UUID; memory_id: UUID;
  kind: "create_memory" | "update_memory" | "delete_memory";
  status: "completed"; revision: number; resource_deleted: boolean;
  created_at: Instant;
}
```

GET `/memories` -> MemoryList；POST `/memories` -> 201 MemoryItem（重放当前版本 200）；PATCH `/memories/{id}` -> 200 MemoryItem；DELETE `/memories/{id}` -> 200 MemoryOperation；GET `/memory-operations/{op}` -> 200 MemoryOperation。item 已被后续更新/删除时，旧创建/编辑重放返回 409 memory_operation_superseded 或 410 memory_deleted，并指向 operation 的只读查证，绝不返还被删旧 value。GET 条目不存在 404，revision 不符 409 memory_revision_conflict，重复 key 409 memory_key_conflict。

只保留每个 local principal / key 一个有效值；value 1–200，最多 10 条（当前三 key 自然最多三条）。`analysis_focus` 限 `cash_flow/revenue/profitability/balanced`，`display_unit` 限 `CNY_YUAN/CNY_TEN_THOUSAND/CNY_HUNDRED_MILLION`，`research_habit` 限 `evidence_first/compare_periods_first`。UI 映射中文标签，显示单位不改变计算单位。拒绝任意自由文字、财务事实、敏感资料和 PDF 指令。用户自己的明确偏好表述可以生成 candidate，不能把模型/PDF文字视为用户授权；保存候选必须独立 confirmed action。source_turn_id 只表示出处，校验同 workspace，删除会话时可置 null。

## 4. SQLite schema 与迁移提案

当前迁移是连续 1–9；最新 REPORT_MIGRATION=9。建议 migration 10 `conversations_v1`，migration 11 `research_preferences_v1`。均在现有 `documents.db`，保持来源与财务最终复验和 turn 提交可以处于同一 SQLite 事务。独立新仓储不是另起独立 DB 文件；没有跨库原子提交承诺。

下表是精确逻辑 schema（TEXT JSON 用 canonical + SHA、严格 DTO 双重核验；实现 SQL 须添加下列 CHECK/FK/UNIQUE/trigger），不在 A0 执行。

| 表 | 字段与键 |
| --- | --- |
| `conversations` | `sequence INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT UNIQUE NOT NULL, workspace_id TEXT NOT NULL, title TEXT NOT NULL, source_scope_sha TEXT NOT NULL, source_payload TEXT NOT NULL, source_payload_sha TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, next_seq INTEGER NOT NULL DEFAULT 1`；`UNIQUE(workspace_id,conversation_id)` |
| `conversation_sources` | `workspace_id,conversation_id,document_id,company_id,source_revision,content_sha256,report_year,report_type,period_start,period_end,basis,attempt,parser_version`；`PRIMARY KEY(workspace_id,conversation_id,document_id)`；FK conversation composite ON DELETE CASCADE，FK documents composite，FK source_revision；完整 identities 与 source_payload 一致 |
| `conversation_operations` | `workspace_id,operation_id,kind,request_sha,conversation_id,turn_id NULL,status,resource_deleted,created_at,ended_at NULL,error_code NULL`；`PRIMARY KEY(workspace_id,operation_id)`；无指向可删除 conversation 的强 FK，以保留脱敏 tombstone；无正文 |
| `conversation_turns` | `workspace_id,conversation_id,turn_id TEXT UNIQUE,seq INTEGER,operation_id,request_sha,status,created_at,ended_at NULL,payload,payload_sha,execution_json,execution_sha,claim TEXT`；PK(workspace_id,conversation_id,turn_id)，UNIQUE(workspace_id,conversation_id,seq)，UNIQUE(workspace_id,operation_id)；FK conversation ON DELETE CASCADE；FK operations composite |
| `conversation_tool_events` | `workspace_id,conversation_id,turn_id,event_seq,tool_name,status,summary,evidence_ids_json,created_at`；PK(workspace_id,conversation_id,turn_id,event_seq)，FK turn composite ON DELETE CASCADE；事件追加，不存 prompt、provider 原始结果或 value |
| `conversation_summaries`（B2 在 migration 11 一并建立） | `workspace_id,conversation_id,version,covered_through_seq,source_turn_ids_json,focus_json,payload_sha,memory_generation,updated_at`；PK(workspace_id,conversation_id,version)，FK conversation cascade；只允许受限焦点，不存金融值/偏好正文 |
| `memory_items`（11） | `workspace_id,principal_id,memory_id TEXT UNIQUE,type,key,value,source_turn_id NULL,revision,confirmed_at,created_at,updated_at`；PK(workspace_id,principal_id,memory_id)，UNIQUE(workspace_id,principal_id,type,key)；principal 服务端固定；关联 turn 必须在 service 同 workspace 校验，无跨会话级联删除偏好 |
| `memory_operations`（11） | `workspace_id,principal_id,operation_id,kind,request_sha,memory_id,revision,resource_deleted,created_at`；PK(workspace_id,principal_id,operation_id)；无 value 和原始 request；不重放已删除 value |
| `memory_events`（11） | `workspace_id,principal_id,event_id,memory_id,action,revision,operation_id,created_at`；仅动作元数据，无正文、旧值或模型文本 |
| `memory_context_generation`（11） | `workspace_id,principal_id,generation INTEGER`；PK(workspace_id,principal_id)，每次 memory CRUD +1 |
| `conversation_context_exclusions`（11） | `workspace_id,conversation_id,turn_id,reason`；PK(workspace_id,conversation_id,turn_id)；FK turn cascade；偏好管理/已删除偏好出处不得重入 prompt |

必要 DDL：

```sql
CREATE UNIQUE INDEX conversation_one_running
ON conversation_turns(workspace_id, conversation_id) WHERE status='running';
CREATE INDEX conversation_history ON conversations(workspace_id, sequence DESC);
CREATE INDEX conversation_turn_history ON conversation_turns(workspace_id,conversation_id,seq);
```

- `status` conversation 只允许 active；删除为物理内容删除 + operations tombstone。turn status 固定五值；seq/next_seq>=1；布尔列只允许 0/1；SHA 长度/字符、title 长度、JSON 有效性、年份/attempt 与时间终态关系 CHECK；UUID canonical / JSON 子结构由 Pydantic 校验。
- identities 不可 UPDATE（source_scope_sha/source_payload/source_payload_sha、workspace/id/created_at）；sources 不可 UPDATE；terminal turn 不可 UPDATE；turn request identity 和 claim 不可变；events 不可 UPDATE，terminal turn 不能再插 events。明确删除允许新 conversation 表 cascade，不改旧历史不可变 trigger。
- `source_payload` 与 sources 子表须在同一事务生成及读回交叉核验；turn payload 的 seq/status/ID/hash 与索引列一致。损坏 fail closed，不静默修复。
- 同一 migration 使用既有 `migrate` 的单个 `BEGIN IMMEDIATE` + execute，不用 executescript、DROP、覆盖旧 checksum。测试旧 1–9 logs/表/数据字节不变、失败回滚、重复初始化、foreign_key_check。
- 列表游标可使用版本化 opaque canonical 编码并严格 workspace/ceiling 校验；游标不是授权。若采用现有 HMAC 签名模式，另建新 key 表，绝不复用/输出旧 research secret。

## 5. 写入、幂等、UNKNOWN 与删除

### 5.1 register → run → finish

1. 输入严格校验；根据服务端 workspace + operation 查 ledger。存在则比较 canonical request hash，同请求只读原状态；不同请求 409。该检查必须早于来源复验（旧 operation 不因新来源状态而重跑）。
2. 新会话先 `prepare_many` 对 1–4 源做实际 bytes/metadata 检查，再 `BEGIN IMMEDIATE` 复查 operation、`SQLiteSourceRepository.verify_selection_in`、写来源快照与 create operation；commit 后从仓储读回返回。新 turn 从已保存 scope 恢复完整 selection，prepare/revalidate 不得换 scope，事务内检查 active conversation、同会话互斥，分配 seq、生成 claim、登记 running turn 和 operation。
3. 释放 DB transaction 后才能模型/检索/PDF IO。每次物理调用前，claim + running 条件下事务持久预留预算/attempt；拿不到写权限就不调用。节点无 retry policy；供应商重试为 0；同一个 operation 绝不重建执行器。
4. graph 输出只是候选，不能作为 HTTP 成功响应。服务层先严格验证，再全源真实 bytes revalidate；`BEGIN IMMEDIATE` 中 fence claim/running、复核 scope；财务结果调用 `recheck_persisted_analysis_in` 并对比已采用事实组，再写一次 terminal turn + operation + updated_at。来源变化应改为无内容的失败终态，不能发布旧数字。
5. commit 后从数据库严格读回，同一权威 payload 验证 hash，再返回。读回失败 503；浏览器只按 operation GET。DB commit 失败不返回内存答案；旧 turn 仍 running，必须恢复收口，不能以新 invocation“补做”。

Turn hash = canonical `{conversation_id,text,fact_selections}`，缺省/显式空列表归一化，selections 去重并排序；字符串不做内容语义重写，空白原文在哈希内。相同 operation 按 workspace 全局唯一，不能跨会话复用。创建/删除的 action kind/目标/参数也进入 hash。

### 5.2 崩溃与断连矩阵

| 故障点 | 持久状态与恢复 |
| --- | --- |
| register commit 前失败 | 没有已知 operation；GET 404 只说明当前未找到。客户端不会自动 POST；用户明确重试动作才可以重新提交相同 op |
| register 后、provider 前崩溃 | startup under owner 标记 interrupted，provider_outcome 根据预约记录可能 unknown；不重跑 |
| provider timeout/断连 | 无法判断供应商处理/收费；终态 failed + provider_outcome unknown，不自动 retry，不回传猜测答案 |
| HTTP 客户端断开，但服务继续 | 已登记服务可完成保存；GET 返回最终结果。若 coroutine cancelled，持久 interrupted；to_thread 可能继续，但晚到结果无提交入口或被 claim/status 拒绝 |
| terminal commit 后 HTTP/读回丢失 | GET/by-operation 找到同一 terminal，0 次新模型/工具 |
| 进程被杀且 turn running | 下一次 writer 启动、取得同一 ResearchOwner 后一次性 recover_interrupted；只写状态，不执行 graph |

启动 recovery 是启动写阶段，不是 GET 副作用；history-only app 也可在取得 writer owner 后收口再挂只读 router。没有中途节点 resume / time travel / exactly-once provider 收费保证。可证明的是一个 operation 的一次受控执行登记、预算有限且无自动重发。

### 5.3 内容删除与长期偏好删除

会话删除只在非 running 时允许；事务内删除新表来源快照、turn、events、summaries、context exclusions，memory.source_turn_id 置 null，旧 turn operations 脱敏 tombstone 标 resource_deleted，新增 delete operation。旧 ResearchRun、财务事实、PDF、经营任务均保留；不能 cascade 到其旧表。旧 operation 重放/GET 不会创建新会话或重新生成被删 turn。审计可保留 UUID/时间/hash/动作，不保留明文；这不是备份、SQLite 空闲页或供应商端的取证级擦除承诺。

偏好删除在单事务内 physical DELETE value、清除新摘要/索引/缓存入口、写不含正文 audit，generation +1。偏好候选/管理 turn 及被删偏好的 source_turn 进入 context exclusions；新 summary 只存来源焦点/年份/指标/未澄清字段，禁止复制偏好或金融值。每轮从当前 store 注入，最多 5 条；不永久保存 assembled prompt。B2 的 context loader 不能把旧消息/摘要的偏好管理文本重新当偏好；删偏好后要继续读该历史消息不等于将其再注入模型。

在途 turn 记录 memory generation：delete/edit 后，若旧 generation 的模型调用尚未开始则中止；已经发给供应商的内容无法撤回。发布前比较 generation，变化则 interrupted/context_changed，绝不自动重发。后续调用仅使用新 generation。历史已提交回答不因删除偏好被改写；UI 如实说明历史/备份与偏好存储的边界。

## 6. LangGraph、来源和预算

`load_context → resolve_reference → guard_scope → intent_router → {source_quote, confirmed_metric, compare_metric, clarify, unsupported} → validate_result → END`。register/finish 均在 graph 外。每轮新的 State，不把 previous graph snapshot 当成功结果；State 包含 conversation/turn/claim、冻结 SourceSnapshot、最近已提交真实上下文、结构化 focus、用户原文、validated selection、预算、服务端 tool results。不给模型 arbitrary document_ids/SQL/URLs/写工具。

- 明确企业/期/指标先规则抽取；只在确有必要时至多一次结构化 resolver LLM。未知 JSON/extra 字段/多候选均澄清，不修复 JSON 再重调模型。焦点来自已提交成功/澄清 turn 的明确结构字段；模型置信度不是授权。双企业“它”无唯一绑定时澄清；“换一家”要求新会话。
- source_quote 调原 RAG 一次 + strict `Result`，完整复验；若只为相关年份重写检索问题，选择的完整 scope 不变。新回答不依赖旧 citations 有效；用户可以读旧历史但不能把其金额带入新工具。
- confirmed_metric 的选择走 `FinancialAnalysisService.admit_reference`，并做最终 `recheck_financial_analysis_sources` 与事务内组复核；compare 调同一个 `.analyze`，严格结果模板。任何 selection 越界、来源失效、simulated、revocation、口径不一致均阻断。
- **不实现“数字出现过就算已验证”**：数字 token 相同不能证明比较/归因正确。A2 无自由解释金额；后续可生成 `pending_human_review` 的独立解释，但须单独定义可发布边界。
- 图无循环，recursion_limit=16；每轮最大 2 次模型物理尝试（resolver 1 + RAG 1）、3 次业务只读工具、检索 top_k 12，最多 4 文档。source/fact security rechecks 单独计诊断，不让预算阻止最终安全检查；超预算直接错误，不自动恢复。
- 历史最多 8 turns 且最多 4096 context tokens；B2 summary 最多 512 tokens、memory 最多 256 tokens；总 prompt 上限 12288 tokens，另保留供应商 output budget。用已有 tiktoken 估算 token 并辅以字符硬限 32000，说明是服务端估算，不宣称与所有供应商 tokenizer 精确一致。按整条消息裁剪，绝不截断 JSON 身份；必需单项超预算则拒绝。证据遵守已有 RAG context budget，最终 assembled prompt 仍经过总预算。
- model timeout 复用现有配置，conversation 只在内存构造 `max_retries=0` adapter；240 秒 elapsed 是 soft limit，不能杀死同步线程。超时返回后禁止发布。运行元数据记录 model 名/配置版本/attempts，不记录 key/base_url 或 raw provider 错误。

## 7. 依赖实证（没有安装/升级任何包）

worktree 无 `.venv`；本轮只读使用 `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python`，模块/测试以当前 worktree cwd 导入。Python 3.12.13，已安装 langgraph 1.2.13、langchain-core 1.5.0、langgraph-checkpoint 4.2.0、Pydantic 2.13.4、FastAPI 0.139.0、httpx 0.28.1、OpenAI 2.44.0、pytest 9.1.1、tiktoken 0.13.0。uv.lock 同样锁定前三项。aiosqlite / langgraph-checkpoint-sqlite 未安装。

现场 `importlib.metadata.requires`：langgraph 1.2.13 要求 `langchain-core>=1.4.7,<2` 与 checkpoint `>=4.1.0,<5`，现有版本满足；`StateGraph.compile` 的 checkpointer 默认 None。离线内存 smoke 实际运行一节点 graph，`invoke` 带 thread_id 返回 `{'value':2}`；证明现有环境支持无 saver 的调用，不证明自动持久化。

2026-11-02 查询 PyPI 原始发布 metadata，仅读取 3.1.1 sdist 到内存以核对实现，未安装/解压到仓库：

| SQLite saver 发布版本 | 依赖条件 | 与当前 lock 的结论 |
| --- | --- | --- |
| 3.1.3（查询时 latest） | Python>=3.10，checkpoint>=4.3.1,<5；aiosqlite>=0.20；sqlite-vec>=0.1.6 | 不能保持 checkpoint 4.2.0 不变直接安装 |
| 3.1.2 | checkpoint>=4.3.0,<5，另两依赖同上 | 同样需要升级 checkpoint |
| 3.1.1 / 3.1.0 | checkpoint>=4.1.0,<5，另两依赖同上 | metadata 允许当前版本；**未安装、未做运行兼容测试** |

3.1.1 sdist 确认 `AsyncSqliteSaver.from_conn_string` 是 async context manager，`aget_tuple/aput/aput_writes` 存在，使用 aiosqlite、asyncio.Lock，自行 `await conn.commit()`；`SqliteSaver` 使用 threading.Lock 和自身 commit。它们的 commit 不能当作新业务主表事务的成功发布凭证。既然本版明确不恢复在途图，新增 saver 带来的双写与额外依赖无必要。

资料：[LangGraph 官方 persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 区分线程 checkpoint 与跨线程 store；[PyPI 3.1.1 metadata](https://pypi.org/pypi/langgraph-checkpoint-sqlite/3.1.1/json)、[3.1.3 metadata](https://pypi.org/pypi/langgraph-checkpoint-sqlite/3.1.3/json)、[官方源码](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-sqlite)。官方内存 saver 不是本方案的重启持久化实现；本项目主表语义是应用自己的设计。

## 8. 本轮原有后端基线与后续验证命令

执行（cwd 均为上述绝对 worktree）：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python -B -m pytest tests/test_companies_migrations.py tests/test_d10_migrations.py tests/test_d11_financial_analysis.py tests/test_d15_selection.py tests/test_d16_qa.py tests/test_d17_history.py tests/test_d19_tasks.py tests/test_d26_no_retry.py tests/test_chat_service.py tests/test_runtime_startup.py -q -p no:cacheprovider
```

**196 passed，0 failed，0 skipped，112.27 秒，5 条 SWIG DeprecationWarning。** 使用现有临时 fixture DB、fake/replay model/search；没有真实供应商、BGE/Milvus 验收或真人财务确认。本轮只执行此相关后端子集；完整 pytest、前端/浏览器与 quality CI 由主控汇总，不能把其他 worktree 的 UX 记录算作本次测试。主控报告先前全套缺三份 PDF 的失败记录须保留，此处不覆盖其记录。

A1 测试建议 `tests/test_conversation_models.py test_conversation_repository.py test_conversation_api.py`：新/旧 1–9 迁移/checksum/业务字节/失败回滚；1–4 源选择；重复 create/turn/delete、hash 冲突、跨会话 op 冲突；双线程/两连接登记只一 running；不同会话可独立执行；readback failure / commit failure；terminal 不可改；损坏 payload/hash 拒绝；startup interrupted；GET 0 writes/0 graph/0 model；delete tombstone 不重生、旧 Run 保留；DB-only app 不依赖模型。

A2 测试建议 `tests/test_conversation_graph.py test_conversation_tools.py`：C01–C13 指代/模糊范围/年份区分；resolver 严格 JSON；frozen scope 全身份及来源变更；页码和 fact ID 伪造拒绝；显式版本选择、缺确认事实、simulated 排除、同金额不同披露不猜；既有 Decimal 边界；call 预留/预算；断连/timeout/cancel/迟到结果/kill/restart 0 重发；供应商 max_retries=0。

B1/B2：confirmed action/allowlist/revision/duplicate key/idempotency；删偏好后 store/summary/cache/原 source turn 不再进入新 prompt；generation 与在途模型竞态；20+轮持久恢复、整消息 token budget、摘要无金融值/偏好正文。以上均是计划，尚未运行。

集成复跑：本节原 196 项 + 新 conversation/memory 测试 + CI 当前 controlled backend 列表，再由主控执行 frontend `npm test` / lint / build 与原 UX/browser 回归。无需为了 A0 再安装依赖或复制全套资产。G 阶段真实模型另记模型/年报 SHA/物理调用数/证据身份和人工语义审核范围，不能以 fake 通过替代。

## 9. 冻结时须保留的风险与实施顺序

| 风险 | 本提案处理 / 仍需证明 |
| --- | --- |
| 最新 saver 会升级 lock | 已选无 saver；3.1.1 只是 metadata 可兼容，未运行验证，不纳入交付 |
| 事实自动选择弱化旧合同 | fact_selections 明确 action；不选则 needs_human_review；前后端总合同必须同步此字段 |
| 数值解释无法靠引用存在证明 | P0 仅摘录/确定模板；自由解释延后，不承诺全语义自动验证 |
| 主表/graph 双重权威 | 每轮 graph 无 durable state；只有 commit + readback 可对用户发布 |
| runtime 重启误执行 | 同 owner 启动收口，不 auto resume；read-only app 也可读全部新历史 |
| DB 验证不等于真实 PDF bytes | 新 turn 前后 prepare/revalidate；历史仅 current_at_read DB 投影；打开 PDF 仍验 bytes |
| 删除偏好从原聊天复活 | B2 context exclusions + generation + 无正文摘要；在途已发送内容无法撤回，需明确说明 |
| 内容删后旧 op 重生 | 脱敏 operation tombstone，410 不重建；旧不可变审计不删 |
| 历史列表无限增长 | 分页/序列 ceiling；上下文独立预算；不在 GET 临时生成摘要 |
| source 快照重复存储漂移 | 子表 + canonical snapshot 在同一事务，读取交叉核验；不一致 fail closed |
| strict DTO 与字段映射漂移 | 前后端共享同一冻结文档；Analysis 字段从现有服务映射，A2 先验证真实键名再实现 |

顺序：主控统一整理 contracts/architecture/migration/journey/risk 文档并冻结上述接口 → A1 完成持久化和 fake handler 后独立审查 → A2 只读 graph/事实与来源闸口 → 与 A3 前端并行集成 → A4 原回归/新状态浏览器 → B1/B2 → G 真实运行与最终独立审查。后端聊天不擅自创建其他聊天或提交。

交付时主控最新调控要求本轮在 A0 合同落盘后结束，A1 的实际实施范围由下一次消息重新分派。因此本轮没有执行先前广义 A1–B2 授权中的业务修改。已阅读 `reviews/a0-architecture.md`；其第 3/4 节的完整来源身份、最终同事务事实撤销复核、调用前 reservation、claim/迟到隔离均已纳入上述方案。创建会话按 operation 查证的专用路径亦已对齐主控消息。
