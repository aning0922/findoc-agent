import type { ConversationDetail, ConversationList, ConversationSummary, Turn, SourceSnapshot, SourceState, OperationRecord, CreateConversationRequest, CreateTurnRequest, Action } from './conversationTypes.ts';

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const hash = /^[a-f0-9]{64}$/;
const decimal = /^-?\d+(\.\d+)?$/;
const statuses = ['running', 'completed', 'refused', 'failed', 'interrupted'];
function require(value: unknown): asserts value { if (!value) throw new Error('会话响应身份或内容不完整，未展示未经核验的结果。'); }
const instant = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
export function validateSourceSnapshot(s: SourceSnapshot): void {
  require(s && typeof s.workspace_id === 'string' && s.workspace_id && typeof s.document_id === 'string' && s.document_id
    && typeof s.company_id === 'string' && s.company_id && Number.isSafeInteger(s.report_year)
    && s.report_type === 'annual' && typeof s.period_start === 'string' && typeof s.period_end === 'string'
    && typeof s.basis === 'string' && hash.test(s.source_revision) && hash.test(s.content_sha256)
    && Number.isSafeInteger(s.attempt) && s.attempt > 0 && typeof s.parser_version === 'string' && s.parser_version);
}
export function sameConversationSource(a: SourceSnapshot, b: SourceSnapshot): boolean {
  return ['workspace_id', 'document_id', 'company_id', 'report_year', 'report_type', 'period_start', 'period_end', 'basis', 'source_revision', 'content_sha256', 'attempt', 'parser_version'].every(key => a[key as keyof SourceSnapshot] === b[key as keyof SourceSnapshot]);
}
function validateStates(states: SourceState[], sources: SourceSnapshot[]): void {
  require(Array.isArray(states) && states.length === sources.length && new Set(states.map(s => s.document_id)).size === states.length);
  for (const s of states) require(s && ['current_at_read', 'expired', 'unavailable'].includes(s.status)
    && sources.some(d => d.document_id === s.document_id && d.source_revision === s.source_revision));
}
export function validateConversationSummary(v: ConversationSummary): ConversationSummary {
  require(v && uuid.test(v.conversation_id) && typeof v.title === 'string' && v.title.trim() && v.status === 'active'
    && hash.test(v.source_scope_sha) && Array.isArray(v.sources) && v.sources.length > 0 && v.sources.length <= 4
    && new Set(v.sources.map(s => s.document_id)).size === v.sources.length
    && instant(v.created_at) && instant(v.updated_at) && Number.isSafeInteger(v.last_turn_seq) && v.last_turn_seq >= 0
    && (v.active_turn_id === null || uuid.test(v.active_turn_id)));
  v.sources.forEach(validateSourceSnapshot); validateStates(v.source_states, v.sources); return v;
}
export function safeConversationAction(a: Action): boolean {
  if (!a || typeof a.label !== 'string' || typeof a.href !== 'string' || !a.href.startsWith('/') || a.href.startsWith('//')
    || a.href.includes('\\') || [...a.href].some(c => c.charCodeAt(0) <= 32)) return false;
  const url = new URL(a.href, 'https://findoc.invalid');
  if (url.origin !== 'https://findoc.invalid') return false;
  if (a.kind === 'new_conversation') return url.pathname === '/conversations' && !url.search && !url.hash;
  if (a.kind === 'review_facts') return url.pathname === '/research' && url.searchParams.get('mode') === 'operating'
    && [...url.searchParams.keys()].every(k => ['mode', 'company', 'task', 'section'].includes(k))
    && [...url.searchParams.keys()].every(k => url.searchParams.getAll(k).length === 1);
  if (a.kind === 'open_research_run') return !!a.research_run_id && uuid.test(a.research_run_id) && url.pathname === '/research'
    && url.searchParams.get('mode') === 'qa' && url.searchParams.get('run') === a.research_run_id
    && [...url.searchParams.keys()].every(k => ['mode', 'run', 'company'].includes(k) && url.searchParams.getAll(k).length === 1);
  if (a.kind === 'open_source') return !!a.document_id && !!a.source_revision && hash.test(a.source_revision)
    && Number.isSafeInteger(a.physical_page) && a.physical_page! > 0
    && url.pathname === `/api/documents/${encodeURIComponent(a.document_id)}/file`
    && url.searchParams.get('source_revision') === a.source_revision && url.hash === `#page=${a.physical_page}`
    && [...url.searchParams.keys()].every(k => ['company_id', 'source_revision'].includes(k) && url.searchParams.getAll(k).length === 1);
  return false;
}
export function validateConversationTurn(v: Turn, conversation: ConversationSummary, operation?: string): Turn {
  require(v && v.schema_version === 'conversation-turn-v1' && v.conversation_id === conversation.conversation_id
    && uuid.test(v.turn_id) && uuid.test(v.operation_id) && (!operation || v.operation_id === operation)
    && Number.isSafeInteger(v.seq) && v.seq > 0 && statuses.includes(v.status)
    && typeof v.user_text === 'string' && v.user_text.trim() && instant(v.created_at) && hash.test(v.integrity_sha256)
    && typeof v.historical_snapshot === 'boolean' && ['not_started', 'returned', 'unknown'].includes(v.provider_outcome)
    && ['not_applicable', 'validated_at_completion_only'].includes(v.financial_fact_validity)
    && v.usage && Number.isSafeInteger(v.usage.model_attempts) && v.usage.model_attempts >= 0
    && Number.isSafeInteger(v.usage.tool_calls) && v.usage.tool_calls >= 0 && Array.isArray(v.fact_selections)
    && (v.research_run_id === null || uuid.test(v.research_run_id)) && Array.isArray(v.tool_events));
  validateStates(v.source_states, conversation.sources);
  if (v.resolved_query !== null) require(v.resolved_query && typeof v.resolved_query.text === 'string'
    && ['source_quote', 'confirmed_metric', 'compare_metric', 'clarify', 'unsupported'].includes(v.resolved_query.intent)
    && ['explicit', 'context', 'ambiguous'].includes(v.resolved_query.resolution) && Array.isArray(v.resolved_query.periods)
    && v.resolved_query.periods.every(Number.isSafeInteger) && Array.isArray(v.resolved_query.context_turn_ids)
    && v.resolved_query.context_turn_ids.every(id => uuid.test(id)));
  require(v.tool_events.every((e, i) => e && Number.isSafeInteger(e.sequence) && (i === 0 || e.sequence > v.tool_events[i - 1].sequence)
    && ['search_annual_report', 'get_confirmed_metric', 'compare_confirmed_metrics'].includes(e.tool_name)
    && ['started', 'completed', 'refused', 'failed', 'unknown'].includes(e.status) && typeof e.summary === 'string'
    && Array.isArray(e.evidence_ref_ids) && instant(e.created_at)));
  require(v.fact_selections.length <= 6 && v.fact_selections.every(f => f && typeof f.company_id === 'string'
    && ['revenue', 'net_profit_parent', 'operating_cash_flow'].includes(f.metric_key) && Number.isSafeInteger(f.period)
    && typeof f.fact_set_id === 'string' && f.fact_set_id && typeof f.fact_id === 'string' && f.fact_id
    && /^disclosure-v1:[a-f0-9]{64}$/.test(f.disclosure_version)));
  if (v.status === 'running') { require(v.result === null && v.ended_at === null); return v; }
  require(instant(v.ended_at) && v.result);
  const r = v.result;
  require(['source_quote', 'confirmed_metric', 'comparison', 'clarification', 'needs_human_review', 'unsupported', 'error'].includes(r.kind)
    && typeof r.answer_text === 'string' && r.interpretation_status === 'not_generated'
    && Array.isArray(r.evidence_refs) && Array.isArray(r.verified_financial_fact_refs) && Array.isArray(r.actions)
    && r.actions.every(safeConversationAction) && Array.isArray(r.memory_candidates));
  require(new Set(r.evidence_refs.map(e => e.ref_id)).size === r.evidence_refs.length
    && new Set(r.evidence_refs.map(e => e.number)).size === r.evidence_refs.length);
  for (const e of r.evidence_refs) {
    validateSourceSnapshot(e);
    require(conversation.sources.some(s => sameConversationSource(s, e)) && e.ref_id && e.chunk_id && e.source_file
      && typeof e.text === 'string' && e.text && e.verification === 'exact_original_with_context'
      && ['paragraph', 'table'].includes(e.kind) && Number.isSafeInteger(e.number) && e.number > 0
      && Number.isSafeInteger(e.physical_page) && e.physical_page > 0);
  }
  for (const f of r.verified_financial_fact_refs) require(f && f.ref_id && f.fact_id && f.fact_set_id && f.receipt_id
    && f.confirmation_kind === 'local_operator' && f.unit === 'CNY_YUAN' && f.currency === 'CNY'
    && decimal.test(f.value_cny_yuan) && instant(f.validated_at) && Number.isSafeInteger(f.period)
    && ['revenue', 'net_profit_parent', 'operating_cash_flow'].includes(f.metric_key)
    && /^disclosure-v1:[a-f0-9]{64}$/.test(f.disclosure_version)
    && conversation.sources.some(s => s.document_id === f.document_id && s.company_id === f.company_id
      && s.source_revision === f.source_revision && s.report_year === f.report_year));
  require(new Set([...r.evidence_refs, ...r.verified_financial_fact_refs].map(f => f.ref_id)).size === r.evidence_refs.length + r.verified_financial_fact_refs.length);
  if (r.kind === 'source_quote') require(v.status === 'completed' && r.evidence_refs.length > 0 && !r.verified_financial_fact_refs.length
    && r.answer_text === r.evidence_refs.map(e => `${e.report_year}年报《${e.source_file}》原文：\n${e.text}\n[${e.number}]`).join('\n\n') && r.analysis === null);
  if (r.kind === 'confirmed_metric' || r.kind === 'comparison') require(v.status === 'completed'
    && !r.evidence_refs.length && r.verified_financial_fact_refs.length === (r.kind === 'confirmed_metric' ? 1 : 2)
    && v.financial_fact_validity === 'validated_at_completion_only'
    && r.verified_financial_fact_refs.every(f => v.fact_selections.some(s => s.company_id === f.company_id && s.metric_key === f.metric_key
      && s.period === f.period && s.fact_id === f.fact_id && s.fact_set_id === f.fact_set_id && s.disclosure_version === f.disclosure_version)));
  if (r.kind === 'confirmed_metric') require(r.analysis === null);
  if (r.kind === 'comparison') {
    const a = r.analysis;
    require(a && a.schema === 'financial-analysis-v1' && ['compared', 'partial'].includes(a.status)
      && decimal.test(a.absolute_change) && (a.percentage_change === null || decimal.test(a.percentage_change))
      && a.formula_id === 'financial_absolute_change_v1' && a.percentage_formula_id === 'financial_yoy_signed_base_v1'
      && Array.isArray(a.warnings) && [a.current_ref_id, a.previous_ref_id].every(id => r.verified_financial_fact_refs.some(f => f.ref_id === id)));
  }
  if (v.status === 'failed' || v.status === 'interrupted') require(r.kind === 'error' && !r.evidence_refs.length && !r.verified_financial_fact_refs.length && r.analysis === null);
  if (['clarification', 'needs_human_review', 'unsupported', 'error'].includes(r.kind)) require(!r.evidence_refs.length && !r.verified_financial_fact_refs.length && r.analysis === null);
  return v;
}
export function validateConversationDetail(v: ConversationDetail, id?: string): ConversationDetail {
  validateConversationSummary(v);
  require(v.schema_version === 'conversation-v1' && (!id || v.conversation_id === id) && Array.isArray(v.turns)
    && (v.next_before_seq === null || Number.isSafeInteger(v.next_before_seq) && v.next_before_seq > 0));
  v.turns.forEach((t, i) => { validateConversationTurn(t, v); require(t.seq <= v.last_turn_seq && (i === 0 || t.seq > v.turns[i - 1].seq)); });
  require(new Set(v.turns.map(t => t.turn_id)).size === v.turns.length);
  return v;
}
export function validateConversationOperation(v: OperationRecord, op: string): OperationRecord {
  require(v && v.schema_version === 'conversation-operation-v1' && v.operation_id === op && uuid.test(op)
    && uuid.test(v.conversation_id) && (v.turn_id === null || uuid.test(v.turn_id))
    && ['create_conversation', 'send_turn', 'delete_conversation'].includes(v.kind) && statuses.includes(v.status)
    && typeof v.resource_deleted === 'boolean' && instant(v.created_at)
    && (v.status === 'running' ? v.ended_at === null : instant(v.ended_at)));
  return v;
}
export class ConversationHTTPError extends Error {
  status: number;
  code: string | null;
  constructor(status: number, code: string | null = null) { super(status === 404 ? '暂未查到记录。未再次提交，请继续只读核对。' : status === 410 ? '会话内容已删除。' : status === 409 ? '请求冲突或来源状态已变化，请先只读查证本次操作。' : '服务暂不能确认结果，请只读查询。'); this.status = status; this.code = code; }
}
// Frozen pre-registration errors for a new Turn only. A matching code on a 5xx,
// an operation conflict, or a failed GET never proves execution did not start.
export function isUnregisteredConversationTurn(error: unknown): boolean {
  return error instanceof ConversationHTTPError && error.status === 409
    && ['conversation_busy', 'source_changed', 'source_not_ready', 'report_identity_unverified'].includes(error.code || '');
}
export async function conversationJSON<T>(path: string, signal: AbortSignal, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { method, signal, cache: 'no-store', ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
  if (!response.ok) {
    let code: string | null = null;
    try { const error = await response.json(); if (typeof error?.detail === 'string' && /^[a-z_]+$/.test(error.detail)) code = error.detail; } catch { /* An unreadable error is still uncertain. */ }
    throw new ConversationHTTPError(response.status, code);
  }
  return response.json() as Promise<T>;
}
export async function listConversations(signal: AbortSignal, cursor?: string): Promise<ConversationList> {
  const q = new URLSearchParams({ limit: '20', ...(cursor ? { cursor } : {}) });
  const v = await conversationJSON<ConversationList>(`/conversations?${q}`, signal);
  require(v && v.schema_version === 'conversation-list-v1' && Array.isArray(v.items) && (v.next_cursor === null || typeof v.next_cursor === 'string'));
  v.items.forEach(validateConversationSummary); require(new Set(v.items.map(i => i.conversation_id)).size === v.items.length); return v;
}
export async function readConversation(id: string, signal: AbortSignal, before?: number): Promise<ConversationDetail> {
  return validateConversationDetail(await conversationJSON(`/conversations/${encodeURIComponent(id)}?limit=50${before ? `&before_seq=${before}` : ''}`, signal), id);
}
export async function createConversation(body: CreateConversationRequest, signal: AbortSignal): Promise<ConversationDetail> {
  const v = validateConversationDetail(await conversationJSON('/conversations', signal, 'POST', body));
  require(JSON.stringify(v.sources.map(s => s.document_id).sort()) === JSON.stringify([...body.document_ids].sort())); return v;
}
export async function sendConversationTurn(conversation: ConversationSummary, body: CreateTurnRequest, signal: AbortSignal): Promise<Turn> {
  const v = validateConversationTurn(await conversationJSON(`/conversations/${conversation.conversation_id}/turns`, signal, 'POST', body), conversation, body.operation_id);
  const selections = (items: Turn['fact_selections']) => items.map(f => JSON.stringify([f.company_id, f.metric_key, f.period, f.fact_set_id, f.fact_id, f.disclosure_version])).sort();
  require(v.user_text === body.text && JSON.stringify(selections(v.fact_selections)) === JSON.stringify(selections(body.fact_selections || []))); return v;
}
export async function readConversationOperation(op: string, signal: AbortSignal): Promise<OperationRecord> {
  return validateConversationOperation(await conversationJSON(`/conversation-operations/${encodeURIComponent(op)}`, signal), op);
}
export async function readConversationTurn(conversation: ConversationSummary, op: string, signal: AbortSignal): Promise<Turn> {
  return validateConversationTurn(await conversationJSON(`/conversations/${conversation.conversation_id}/turns/by-operation/${encodeURIComponent(op)}`, signal), conversation, op);
}
