// Frozen wire contract: docs/conversation-v12/backend-a0.md §3.1–3.3.
export type UUID = string;
export type Hash = string;
export type Instant = string;
export type Metric = "revenue" | "net_profit_parent" | "operating_cash_flow";

export interface SourceSnapshot {
  workspace_id: string; document_id: string; company_id: string;
  report_year: number; report_type: string; period_start: string; period_end: string;
  basis: string; source_revision: Hash; content_sha256: Hash;
  attempt: number; parser_version: string;
}
export interface SourceState {
  document_id: string; source_revision: Hash;
  status: "current_at_read" | "expired" | "unavailable";
}
export interface EvidenceRef extends SourceSnapshot {
  ref_id: string; number: number; chunk_id: string; physical_page: number;
  source_file: string; text: string; kind: "paragraph" | "table";
  verification: "exact_original_with_context";
}
// EvidenceRef 去掉 ref_id 后等于现有 research.models.Citation。
export interface FinancialFactRef {
  ref_id: string; fact_set_id: string; fact_id: string; receipt_id: string;
  document_id: string; company_id: string; source_revision: Hash;
  disclosure_version: string; report_year: number; period: number; metric_key: Metric;
  value_cny_yuan: string; currency: "CNY"; unit: "CNY_YUAN";
  confirmation_kind: "local_operator"; validated_at: Instant;
}
// fact refs 只表示在 validated_at 已验证；历史 GET 不是再次核准。
export interface Action {
  kind: "open_source" | "review_facts" | "open_research_run" | "new_conversation";
  label: string;
  href: string; // 服务端允许的相对站内 URL，拒绝模型/调用者提供的 URL
  document_id: string | null; source_revision: Hash | null;
  physical_page: number | null; research_run_id: string | null;
}
export interface FactSelection {
  company_id: string; metric_key: Metric; period: number;
  fact_set_id: string; fact_id: string; disclosure_version: string;
}

export interface CreateTurnRequest {
  operation_id: UUID;
  text: string; // trim 后非空，原值保存；最大 1000 字符
  fact_selections?: FactSelection[]; // 缺省 []，最多 6；只允许明确选择
}
export type TurnStatus = "running" | "completed" | "refused" | "failed" | "interrupted";
export type Intent = "source_quote" | "confirmed_metric" | "compare_metric" | "clarify" | "unsupported";
export interface ResolvedQuery {
  text: string;
  intent: Intent;
  company_id: string | null;
  metric_key: Metric | null;
  periods: number[];
  resolution: "explicit" | "context" | "ambiguous";
  context_turn_ids: UUID[]; // 真实已提交 turn，不能由模型伪造
}
export interface Analysis {
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
export type MemoryKey = "analysis_focus" | "display_unit" | "research_habit";
export interface MemoryCandidate {
  type: "research_preference"; key: MemoryKey;
  value: string; source_turn_id: UUID;
  confirmation_required: true;
}
export interface TurnResult {
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
export interface ToolEvent {
  sequence: number;
  tool_name: "search_annual_report" | "get_confirmed_metric" | "compare_confirmed_metrics";
  status: "started" | "completed" | "refused" | "failed" | "unknown";
  summary: string; evidence_ref_ids: string[]; created_at: Instant;
}
export interface Turn {
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

export interface CreateConversationRequest {
  operation_id: UUID; document_ids: string[]; title?: string;
}
export interface ConversationSummary {
  conversation_id: UUID; title: string;
  status: "active";
  source_scope_sha: Hash; // 使用既有 selection_id 的确切序列化，不另算不兼容 hash
  sources: SourceSnapshot[]; source_states: SourceState[];
  created_at: Instant; updated_at: Instant;
  last_turn_seq: number; active_turn_id: UUID | null;
}
export interface ConversationDetail extends ConversationSummary {
  schema_version: "conversation-v1";
  turns: Turn[]; // 最近一页，按 seq 升序显示
  next_before_seq: number | null;
}
export interface ConversationList {
  schema_version: "conversation-list-v1";
  items: ConversationSummary[]; next_cursor: string | null;
}
export interface DeleteRequest {operation_id: UUID}
export interface OperationRecord {
  schema_version: "conversation-operation-v1";
  operation_id: UUID; kind: "create_conversation" | "send_turn" | "delete_conversation";
  status: "running" | "completed" | "refused" | "failed" | "interrupted";
  conversation_id: UUID; turn_id: UUID | null;
  resource_deleted: boolean; created_at: Instant; ended_at: Instant | null;
  error_code: string | null;
}
export interface APIError {detail: string} // 与现有 HTTPException 一致；不回显 provider/raw SQL
