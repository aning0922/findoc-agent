import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ConversationHTTPError, conversationJSON, createConversation, isUnregisteredConversationCreate, isUnregisteredConversationDelete, readConversation, validateConversationOperation } from '../src/product/conversationApi.ts';
import { readConversationSources } from '../src/product/conversationSources.ts';
import { readConversationOperations, rememberConversationOperation, resolveConversationOperation } from '../src/product/conversationState.ts';
import { listMemories, memoryOperationNotice, readMemoryOperation, readPendingMemory, storePendingMemory, validateMemoryOperation } from '../src/product/memoryApi.ts';
import type { MemoryOperation, PendingMemory } from '../src/product/memoryApi.ts';
const cid = '00000000-0000-4000-8000-000000000001', op = '00000000-0000-4000-8000-000000000002', mid = '00000000-0000-4000-8000-000000000003';
const nextOp = '00000000-0000-4000-8000-000000000004';
const now = '2026-11-02T00:00:00Z';
function storage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}
function detail() {
  return { schema_version: 'conversation-v1', conversation_id: cid, title: '研究', status: 'active', source_scope_sha: 'a'.repeat(64), sources: [{ workspace_id: 'demo', document_id: 'd', company_id: 'c', report_year: 2025, report_type: 'annual', period_start: '2025-01-01', period_end: '2025-12-31', basis: 'PRC_GAAP', source_revision: 'b'.repeat(64), content_sha256: 'c'.repeat(64), attempt: 1, parser_version: 'p' }], source_states: [{ document_id: 'd', source_revision: 'b'.repeat(64), status: 'current_at_read' }], created_at: now, updated_at: now, last_turn_seq: 0, active_turn_id: null, turns: [], next_before_seq: null };
}
test('create/delete have separate narrow non-registration classifiers; uncertain errors retain hints', () => {
  for (const code of ['source_changed', 'source_not_ready', 'report_identity_unverified']) {
    assert.equal(isUnregisteredConversationCreate(new ConversationHTTPError(409, code)), true);
    assert.equal(isUnregisteredConversationDelete(new ConversationHTTPError(409, code)), false);
  }
  assert.equal(isUnregisteredConversationDelete(new ConversationHTTPError(409, 'conversation_busy', 'DELETE')), true);
  assert.equal(isUnregisteredConversationCreate(new ConversationHTTPError(409, 'conversation_busy')), false);
  for (const error of [new ConversationHTTPError(409, 'operation_request_conflict'), new ConversationHTTPError(404, 'source_changed'),
    new ConversationHTTPError(503, 'source_changed'), new ConversationHTTPError(503, 'conversation_busy'), new SyntaxError(), new TypeError()]) {
    for (const classify of [isUnregisteredConversationCreate, isUnregisteredConversationDelete]) {
      const local = storage(); rememberConversationOperation(local, { operationId: op, conversationId: null, kind: 'create' });
      if (classify(error)) resolveConversationOperation(local, op);
      assert.equal(readConversationOperations(local).length, 1);
    }
  }
});
test('stale source create rejection permits only a catalog GET before explicit new creation', async () => {
  const local = storage(), prior = globalThis.fetch, calls: string[] = [];
  const selection = ['d'], draft = '仍保留的问题';
  rememberConversationOperation(local, { operationId: op, conversationId: null, kind: 'create' });
  globalThis.fetch = async (_url, init) => {
    const method = init?.method || 'GET'; calls.push(method);
    if (calls.length === 1) return Response.json({ detail: 'source_changed' }, { status: 409 });
    if (method === 'GET') return Response.json({ schema_version: 'research-source-options-v1', max_selected_documents: 4, documents: [{ document_id: 'd', company_id: 'c', report_year: 2025, report_type: 'annual', source_file: 'r.pdf', status: 'ready', selectable: true, reason: null }] });
    return Response.json(detail(), { status: 201 });
  };
  try {
    await assert.rejects(createConversation({ operation_id: op, document_ids: selection }, new AbortController().signal), error => {
      assert.ok(isUnregisteredConversationCreate(error)); resolveConversationOperation(local, op); return true;
    });
    assert.deepEqual(readConversationOperations(local), []); assert.equal(draft, '仍保留的问题'); assert.deepEqual(selection, ['d']);
    await readConversationSources(new AbortController().signal); assert.deepEqual(calls, ['POST', 'GET']);
    await createConversation({ operation_id: mid, document_ids: selection }, new AbortController().signal);
    assert.deepEqual(calls, ['POST', 'GET', 'POST']);
  } finally { globalThis.fetch = prior; }
});
test('busy delete rejection clears only that op; a read precedes the next explicit DELETE', async () => {
  const local = storage(), prior = globalThis.fetch, calls: string[] = [];
  rememberConversationOperation(local, { operationId: op, conversationId: cid, kind: 'delete' });
  rememberConversationOperation(local, { operationId: mid, conversationId: cid, kind: 'send' });
  globalThis.fetch = async (_url, init) => {
    const method = init?.method || 'GET'; calls.push(method);
    if (calls.length === 1) return Response.json({ detail: 'conversation_busy' }, { status: 409 });
    if (method === 'GET') return Response.json(detail());
    return Response.json({ schema_version: 'conversation-operation-v1', operation_id: nextOp, kind: 'delete_conversation', status: 'completed', conversation_id: cid, turn_id: null, resource_deleted: true, created_at: now, ended_at: now, error_code: null });
  };
  try {
    await assert.rejects(conversationJSON(`/conversations/${cid}`, new AbortController().signal, 'DELETE', { operation_id: op }), error => {
      assert.ok(isUnregisteredConversationDelete(error)); resolveConversationOperation(local, op); return true;
    });
    assert.deepEqual(readConversationOperations(local).map(p => p.operationId), [mid]);
    const current = await readConversation(cid, new AbortController().signal); assert.equal(current.active_turn_id, null);
    assert.deepEqual(calls, ['DELETE', 'GET']);
    // The user explicitly confirms deletion after the read, with a new operation.
    const receipt = await conversationJSON(`/conversations/${cid}`, new AbortController().signal, 'DELETE', { operation_id: nextOp });
    validateConversationOperation(receipt as Parameters<typeof validateConversationOperation>[0], nextOp);
    assert.deepEqual(calls, ['DELETE', 'GET', 'DELETE']);
  } finally { globalThis.fetch = prior; }
});
test('only the original DELETE 410 conversation_deleted releases its hint; GET 410 and other kinds stay unknown', async () => {
  const local = storage(), prior = globalThis.fetch, methods: string[] = [];
  rememberConversationOperation(local, { operationId: op, conversationId: cid, kind: 'delete' });
  rememberConversationOperation(local, { operationId: mid, conversationId: cid, kind: 'send' });
  globalThis.fetch = async (_url, init) => {
    methods.push(init?.method || 'GET');
    return Response.json({ detail: 'conversation_deleted' }, { status: 410 });
  };
  try {
    await assert.rejects(conversationJSON(`/conversations/${cid}`, new AbortController().signal, 'DELETE', { operation_id: op }), error => {
      assert.equal(isUnregisteredConversationDelete(error), true);
      assert.equal(isUnregisteredConversationCreate(error), false);
      resolveConversationOperation(local, op); return true;
    });
    assert.deepEqual(readConversationOperations(local).map(p => p.operationId), [mid]);
    await assert.rejects(conversationJSON(`/conversation-operations/${mid}`, new AbortController().signal), error => {
      assert.equal(isUnregisteredConversationDelete(error), false, 'GET has no authority to clear any pending write'); return true;
    });
    assert.deepEqual(readConversationOperations(local).map(p => p.operationId), [mid]);
    assert.deepEqual(methods, ['DELETE', 'GET']);
    for (const method of ['GET', 'POST', 'PATCH', null]) assert.equal(isUnregisteredConversationDelete(new ConversationHTTPError(410, 'conversation_deleted', method)), false);
    assert.equal(isUnregisteredConversationDelete(new ConversationHTTPError(410, 'resource_not_found', 'DELETE')), false);
    assert.equal(isUnregisteredConversationDelete(new ConversationHTTPError(503, 'conversation_deleted', 'DELETE')), false);
  } finally { globalThis.fetch = prior; }
});
for (const kind of ['create_memory', 'update_memory'] as const) test(`${kind} lost response can recover a later deletion via GET-only tombstone without restoring value`, async () => {
  const prior = globalThis.fetch, calls: string[] = [], local = storage();
  const pending: PendingMemory = { operationId: op, kind, memoryId: kind === 'create_memory' ? null : mid };
  storePendingMemory(local, pending);
  const receipt: MemoryOperation = { schema_version: 'memory-operation-v1', operation_id: op, memory_id: mid, kind, status: 'completed', revision: 1, resource_deleted: true, created_at: now };
  globalThis.fetch = async (_url, init) => {
    const method = init?.method || 'GET'; calls.push(method);
    if (calls.length === 1) throw new TypeError('committed response lost');
    if (method === 'DELETE') return Response.json({ ...receipt, kind: 'delete_memory', operation_id: cid });
    if (String(_url).includes('/memory-operations/')) return Response.json(receipt);
    return Response.json({ schema_version: 'memory-list-v1', items: [], generation: 2 });
  };
  try {
    const body = kind === 'create_memory'
      ? { operation_id: op, type: 'research_preference', key: 'analysis_focus', value: 'cash_flow', confirmed: true }
      : { operation_id: op, expected_revision: 1, value: 'cash_flow', confirmed: true };
    await assert.rejects(conversationJSON(kind === 'create_memory' ? '/memories' : `/memories/${mid}`, new AbortController().signal, kind === 'create_memory' ? 'POST' : 'PATCH', body));
    assert.deepEqual(readPendingMemory(local), pending);
    await conversationJSON(`/memories/${mid}`, new AbortController().signal, 'DELETE', { operation_id: cid, expected_revision: 1 });
    const recovered = await readMemoryOperation(pending, new AbortController().signal);
    assert.match(memoryOperationNotice(recovered), /原操作已查明，偏好后来已删除/);
    storePendingMemory(local, null);
    assert.equal(readPendingMemory(local), null);
    assert.deepEqual((await listMemories(new AbortController().signal)).items, []);
    assert.deepEqual(calls, [kind === 'create_memory' ? 'POST' : 'PATCH', 'DELETE', 'GET', 'GET']);
    assert.equal(Object.hasOwn(recovered, 'value'), false);
    assert.throws(() => validateMemoryOperation({ ...receipt, memory_id: cid }, { ...pending, memoryId: mid }));
    assert.throws(() => validateMemoryOperation({ ...receipt, kind: 'delete_memory', resource_deleted: false }, { ...pending, kind: 'delete_memory' }));
  } finally { globalThis.fetch = prior; }
});
