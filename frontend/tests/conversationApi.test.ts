import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createConversation, readConversationOperation, safeConversationAction, validateConversationDetail, validateConversationOperation, validateConversationTurn } from '../src/product/conversationApi.ts';
import { conversationFactEligible, conversationFactSelection } from '../src/product/conversationFacts.ts';
import { validPreference, validateMemoryItem, validateMemoryOperation } from '../src/product/memoryApi.ts';
import type { ConversationDetail, Turn, EvidenceRef } from '../src/product/conversationTypes.ts';
import type { Fact } from '../src/product/api.ts';
const cid = '00000000-0000-4000-8000-000000000001';
const op = '00000000-0000-4000-8000-000000000002';
const tid = '00000000-0000-4000-8000-000000000003';
const now = '2026-11-02T00:00:00Z';
function conversation(): ConversationDetail {
  return { schema_version: 'conversation-v1', conversation_id: cid, title: '年报研究', status: 'active', source_scope_sha: 'a'.repeat(64),
    sources: [{ workspace_id: 'demo', document_id: 'd', company_id: 'c', report_year: 2025, report_type: 'annual', period_start: '2025-01-01', period_end: '2025-12-31', basis: 'PRC_GAAP', source_revision: 'b'.repeat(64), content_sha256: 'c'.repeat(64), attempt: 1, parser_version: 'p' }],
    source_states: [{ document_id: 'd', source_revision: 'b'.repeat(64), status: 'current_at_read' }], created_at: now, updated_at: now, last_turn_seq: 1, active_turn_id: null, turns: [], next_before_seq: null };
}
function turn(): Turn {
  const c = conversation();
  const evidence: EvidenceRef = { ...c.sources[0], ref_id: 'e', number: 1, chunk_id: 'chunk', physical_page: 1, source_file: 'r.pdf', text: '原文', kind: 'paragraph', verification: 'exact_original_with_context' };
  return { schema_version: 'conversation-turn-v1', conversation_id: cid, turn_id: tid, operation_id: op, seq: 1, status: 'completed', user_text: '问题', resolved_query: null, fact_selections: [], research_run_id: null, tool_events: [], created_at: now, ended_at: now, provider_outcome: 'returned', usage: { model_attempts: 1, tool_calls: 1 }, historical_snapshot: true, source_states: c.source_states, financial_fact_validity: 'not_applicable', integrity_sha256: 'd'.repeat(64), result: { kind: 'source_quote', answer_text: '2025年报《r.pdf》原文：\n原文\n[1]', evidence_refs: [evidence], verified_financial_fact_refs: [], analysis: null, interpretation_status: 'not_generated', reason_code: null, error_code: null, actions: [], memory_candidates: [] } };
}
test('conversation result validates frozen bytes/attempt/parser identity and exact original excerpts', () => {
  const c = conversation(), t = turn(); c.turns = [t];
  assert.equal(validateConversationDetail(c, cid), c);
  for (const mutate of [
    (v: Turn) => { v.result!.answer_text = '自由生成解释'; },
    (v: Turn) => { v.result!.evidence_refs[0].content_sha256 = 'e'.repeat(64); },
    (v: Turn) => { v.result!.evidence_refs[0].attempt = 2; },
    (v: Turn) => { v.result!.evidence_refs[0].parser_version = 'foreign'; },
    (v: Turn) => { v.result!.interpretation_status = 'pending_human_review'; },
    (v: Turn) => { v.result!.evidence_refs[0].physical_page = 0; },
  ]) { const bad = turn(); mutate(bad); assert.throws(() => validateConversationTurn(bad, c)); }
  c.source_states[0].status = 'expired'; assert.equal(validateConversationDetail(c), c, 'expired history remains readable');
});
test('running cannot publish answer; corrupt/duplicate history cannot masquerade as committed', () => {
  const c = conversation(), t = turn(); t.status = 'running'; assert.throws(() => validateConversationTurn(t, c));
  c.turns = [turn(), turn()]; assert.throws(() => validateConversationDetail(c));
  assert.throws(() => validateConversationTurn(turn(), c, tid));
});
test('explicit confirmed selection has a usable positive result without requiring fact period to equal report year', () => {
  const c = conversation(), t = turn();
  const selection = { company_id: 'c', metric_key: 'revenue' as const, period: 2024, fact_set_id: 'set', fact_id: 'fact', disclosure_version: `disclosure-v1:${'a'.repeat(64)}` };
  t.fact_selections = [selection]; t.financial_fact_validity = 'validated_at_completion_only';
  t.result = { ...t.result!, kind: 'confirmed_metric', answer_text: '2024 年营业收入为 100 元。', evidence_refs: [],
    verified_financial_fact_refs: [{ ...selection, ref_id: 'f', receipt_id: 'receipt', document_id: 'd', source_revision: c.sources[0].source_revision, report_year: 2025, value_cny_yuan: '100', currency: 'CNY', unit: 'CNY_YUAN', confirmation_kind: 'local_operator', validated_at: now }] };
  assert.equal(validateConversationTurn(t, c), t);
  t.fact_selections = []; assert.throws(() => validateConversationTurn(t, c), 'result cannot claim a fact the user never selected');
});
test('privileged actions reject external URLs and auto-execution intents', () => {
  const action = { kind: 'review_facts' as const, label: '核对', href: '/research?mode=operating', document_id: null, source_revision: null, physical_page: null, research_run_id: null };
  assert.equal(safeConversationAction(action), true);
  for (const href of ['https://evil.test', '//evil.test', '/\\evil.test', '/research?mode=operating&new=1', '/research?mode=operating&mode=qa', '/research?mode=operating&resume=1']) assert.equal(safeConversationAction({ ...action, href }), false);
  assert.equal(safeConversationAction({ ...action, kind: 'open_source', document_id: 'd', source_revision: 'a'.repeat(64), physical_page: 1, href: `/api/documents/d/file?source_revision=${'a'.repeat(64)}#page=1` }), true);
});
test('operation receipts bind ID, kind and lifecycle instead of using HTTP success alone', () => {
  const receipt = { schema_version: 'conversation-operation-v1' as const, operation_id: op, kind: 'send_turn' as const, status: 'completed' as const, conversation_id: cid, turn_id: tid, resource_deleted: false, created_at: now, ended_at: now, error_code: null };
  assert.equal(validateConversationOperation(receipt, op), receipt);
  assert.throws(() => validateConversationOperation(receipt, tid));
  assert.throws(() => validateConversationOperation({ ...receipt, ended_at: null }, op));
});
test('failed create and 404 operation lookup each send exactly one request with no replay', async () => {
  const prior = globalThis.fetch;
  const calls: RequestInit[] = [];
  globalThis.fetch = async (_url, init) => { calls.push(init!); return new Response('{}', { status: calls.length === 1 ? 503 : 404 }); };
  try {
    await assert.rejects(createConversation({ operation_id: op, document_ids: ['d'] }, new AbortController().signal));
    await assert.rejects(readConversationOperation(op, new AbortController().signal));
    assert.equal(calls.length, 2); assert.equal(calls[0].method, 'POST'); assert.equal(calls[1].method, 'GET'); assert.equal(calls[1].body, undefined);
    assert.deepEqual(JSON.parse(calls[0].body as string), { operation_id: op, document_ids: ['d'] });
  } finally { globalThis.fetch = prior; }
});
test('confirmed fact choices preserve comparison-column years and exclude simulated/foreign source versions', () => {
  const c = conversation();
  const f = { ...c.sources[0], current_valid: true, production_calculable: true, confirmation_kind: 'local_operator', calculable: true, confirmation_status: 'confirmed', integrity: 'verified', fact_id: 'f', fact_set_id: 'set', metric_key: 'revenue', period: 2024, disclosure_version: `disclosure-v1:${'d'.repeat(64)}` } as unknown as Fact;
  assert.equal(conversationFactEligible(f, c), true);
  assert.equal(conversationFactSelection(f).period, 2024);
  assert.equal(Object.hasOwn(conversationFactSelection(f), 'value_cny_yuan'), false);
  assert.equal(conversationFactEligible({ ...f, confirmation_kind: 'simulated_test' }, c), false);
  assert.equal(conversationFactEligible({ ...f, attempt: 2 }, c), false);
  assert.equal(conversationFactEligible({ ...f, current_valid: false }, c), false);
});
test('memory accepts only frozen enum preferences and validates deleted operation identity', () => {
  assert.equal(validPreference('analysis_focus', 'cash_flow'), true);
  assert.equal(validPreference('analysis_focus', '营收一亿元'), false);
  assert.equal(validPreference('__proto__', 'constructor'), false);
  const item = { schema_version: 'memory-item-v1' as const, memory_id: tid, type: 'research_preference' as const, key: 'analysis_focus' as const, value: 'cash_flow', source_turn_id: null, revision: 1, confirmed_at: now, created_at: now, updated_at: now };
  assert.equal(validateMemoryItem(item), item);
  assert.throws(() => validateMemoryItem({ ...item, value: '财务金额' }));
  const pending = { operationId: op, kind: 'delete_memory' as const, memoryId: tid };
  const receipt = { schema_version: 'memory-operation-v1' as const, operation_id: op, memory_id: tid, kind: 'delete_memory' as const, status: 'completed' as const, revision: 1, resource_deleted: true, created_at: now };
  assert.equal(validateMemoryOperation(receipt, pending), receipt);
  assert.throws(() => validateMemoryOperation({ ...receipt, resource_deleted: false }, pending));
  assert.throws(() => validateMemoryOperation({ ...receipt, memory_id: cid }, pending));
});
