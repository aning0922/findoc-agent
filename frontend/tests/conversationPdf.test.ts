import { test } from 'node:test';
import assert from 'node:assert/strict';
import { conversationActionPdfLocation, readConversationActionPdf } from '../src/product/conversationPdf.ts';
import type { Action, ConversationSummary } from '../src/product/conversationTypes.ts';
const revision = 'a'.repeat(64);
function scope(): ConversationSummary {
  return { conversation_id: '00000000-0000-4000-8000-000000000001', title: '历史计算', status: 'active', source_scope_sha: 'b'.repeat(64),
    sources: [{ workspace_id: 'demo', document_id: 'doc one', company_id: 'c', report_year: 2025, report_type: 'annual', period_start: '2025-01-01', period_end: '2025-12-31', basis: 'PRC_GAAP', source_revision: revision, content_sha256: 'c'.repeat(64), attempt: 2, parser_version: 'p' }],
    source_states: [{ document_id: 'doc one', source_revision: revision, status: 'current_at_read' }], created_at: '2026-11-02T00:00:00Z', updated_at: '2026-11-02T00:00:00Z', last_turn_seq: 2, active_turn_id: null };
}
function action(): Action {
  return { kind: 'open_source', label: '查看原 PDF · 营业收入', href: `/api/documents/doc%20one/file?source_revision=${revision}#page=7`, document_id: 'doc one', source_revision: revision, physical_page: 7, research_run_id: null };
}
test('financial source action produces a PDF location from the full frozen snapshot without fake excerpt fields', () => {
  const s = scope(), location = conversationActionPdfLocation(action(), s);
  assert.deepEqual(location, { ...s.sources[0], physical_page: 7 });
  for (const field of ['ref_id', 'text', 'chunk_id', 'number']) assert.equal(Object.hasOwn(location, field), false);
  for (const bad of [
    { ...action(), document_id: 'foreign' }, { ...action(), source_revision: 'd'.repeat(64) },
    { ...action(), physical_page: 0 }, { ...action(), href: 'https://foreign.test/file' },
  ]) assert.throws(() => conversationActionPdfLocation(bad, s));
});
test('historical confirmed calculation opens its PDF with GET-only metadata and no current fact dependency', async () => {
  const prior = globalThis.fetch, calls: { url: string; method: string }[] = [];
  const s = scope();
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), method: init?.method || 'GET' });
    const value = String(url).includes('/source?') ? { ...s.sources[0], physical_pages: 20, metadata_status: 'confirmed' }
      : { document_id: 'doc one', source_file: '2025年报.pdf', status: 'ready' };
    return Response.json(value);
  };
  try {
    const pdf = await readConversationActionPdf(action(), s, new AbortController().signal);
    assert.deepEqual(pdf, { document_id: 'doc one', company_id: 'c', report_year: 2025, source_revision: revision, physical_page: 7, parser_version: 'p', source_file: '2025年报.pdf' });
    assert.equal(Object.hasOwn(pdf, 'number'), false);
    assert.equal(calls.length, 4);
    assert.ok(calls.every(c => c.method === 'GET'));
    assert.ok(calls.every(c => !c.url.includes('financial-facts') && !c.url.includes('/analyses') && !c.url.includes('/file?')));
    assert.ok(calls.some(c => c.url === '/api/documents/doc%20one'));
  } finally { globalThis.fetch = prior; }
});
test('wrong frozen bytes, metadata or physical page prevents financial PDF display', async () => {
  const prior = globalThis.fetch, s = scope();
  try {
    for (const changed of [{ content_sha256: 'd'.repeat(64) }, { attempt: 3 }, { parser_version: 'foreign' }, { report_year: 2024 }, { period_start: '2024-01-01' }, { basis: 'foreign' }, { physical_pages: 6 }]) {
      let calls = 0;
      globalThis.fetch = async () => { calls++; return Response.json({ ...s.sources[0], physical_pages: 20, metadata_status: 'confirmed', ...changed }); };
      await assert.rejects(readConversationActionPdf(action(), s, new AbortController().signal));
      assert.equal(calls, 1, 'reject before filename lookup or PDF load');
    }
  } finally { globalThis.fetch = prior; }
});
