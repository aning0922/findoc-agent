import { test } from 'node:test';
import assert from 'node:assert/strict';
import { conversationPath, pathFor, qaPath, readProductRoute } from '../src/product/productRoutes.ts';
import { selectableConversationScope, validateConversationSources } from '../src/product/conversationSources.ts';
import { ownsConversationView, readConversationOperations, rememberConversationOperation, resolveConversationOperation } from '../src/product/conversationState.ts';

const operationId = '00000000-0000-4000-8000-000000000001';
const conversationId = '00000000-0000-4000-8000-000000000002';
function catalog() {
  return validateConversationSources({ schema_version: 'research-source-options-v1', max_selected_documents: 6,
    documents: Array.from({ length: 5 }, (_, i) => ({ document_id: `d${i}`, company_id: `c${i}`, report_year: 2025,
      report_type: 'annual', source_file: `${i}.pdf`, status: 'ready', selectable: true, reason: null })) });
}
test('conversation navigation keeps old QA run and return-task deep links readable', () => {
  assert.equal(pathFor('conversations', 'foreign-company'), '/conversations');
  const route = readProductRoute(new URL(conversationPath(conversationId), 'https://local.test'));
  assert.equal(route.page, 'conversations'); assert.equal(route.company, '');
  const old = readProductRoute(new URL(`${qaPath('c', 't')}&run=${operationId}`, 'https://local.test'));
  assert.equal(old.page, 'research'); assert.equal(old.mode, 'qa'); assert.equal(old.run, operationId);
  assert.equal(new URL(qaPath('c', 't'), 'https://local.test').searchParams.get('return_task'), 't');
  assert.throws(() => readProductRoute(new URL('/conversations?conversation=a&conversation=b', 'https://local.test')));
});
test('scope requires unique selectable annual reports and enforces four even when catalog permits more', () => {
  const options = catalog();
  assert.equal(selectableConversationScope(options, []), false);
  assert.equal(selectableConversationScope(options, ['d0']), true);
  assert.equal(selectableConversationScope(options, ['d0', 'd1', 'd2', 'd3']), true);
  assert.equal(selectableConversationScope(options, ['d0', 'd1', 'd2', 'd3', 'd4']), false);
  assert.equal(selectableConversationScope(options, ['d0', 'd0']), false);
  options.documents[0].selectable = false;
  assert.equal(selectableConversationScope(options, ['d0']), false);
  options.documents[0].selectable = true; options.documents[0].report_type = 'quarterly';
  assert.equal(selectableConversationScope(options, ['d0']), false);
  assert.equal(selectableConversationScope(null, ['d1']), false);
});
test('catalog rejects duplicate identities and malformed eligibility instead of granting selection', () => {
  const options = catalog(); options.documents.push(options.documents[0]);
  assert.throws(() => validateConversationSources(options));
  assert.throws(() => validateConversationSources({ ...catalog(), max_selected_documents: 0 }));
  assert.throws(() => validateConversationSources({ ...catalog(), documents: [null] }));
});
test('recovery hints keep each operation across views, reject identity reuse and contain no answer content', () => {
  let data: string | null = null;
  const storage = { getItem: () => data, setItem: (_key: string, value: string) => { data = value; } };
  const create = { operationId, conversationId: null, kind: 'create' as const };
  rememberConversationOperation(storage, { ...create, ...{ user_text: 'must not persist' } }); rememberConversationOperation(storage, create);
  assert.deepEqual(readConversationOperations(storage), [create]);
  const compatibleWithBody = { ...create, user_text: 'must not persist', answer: 'must not persist' };
  rememberConversationOperation(storage, compatibleWithBody);
  assert.equal(data!.includes('must not persist'), false);
  assert.throws(() => rememberConversationOperation(storage, { operationId, conversationId, kind: 'send' }));
  rememberConversationOperation(storage, { operationId: conversationId, conversationId, kind: 'send' });
  resolveConversationOperation(storage, operationId);
  assert.deepEqual(readConversationOperations(storage), [{ operationId: conversationId, conversationId, kind: 'send' }]);
  assert.equal(ownsConversationView({ conversationId, epoch: 2 }, { conversationId, epoch: 1 }), false);
  assert.equal(ownsConversationView({ conversationId: operationId, epoch: 2 }, { conversationId, epoch: 2 }), false);
  assert.equal(ownsConversationView({ conversationId, epoch: 2 }, { conversationId, epoch: 2 }), true);
  data = 'invalid'; assert.throws(() => readConversationOperations(storage));
});
