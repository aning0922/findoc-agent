import { test } from 'node:test';
import assert from 'node:assert/strict';
import { taskReviewPath, validateReviewContext, nextAction } from '../src/product/researchJourney.ts';
import { annualMetadata, uploadReport, UploadError, readUploaded, listDocuments } from '../src/product/documentLibraryApi.ts';
import type { Task, TemplateInput } from '../src/product/operatingResearch.ts';
const hash = 'a'.repeat(64), uuid = '12345678-1234-1234-1234-123456789012';
function task(): Task {
  const side = (year: number) => ({ company_id: 'company', period: { year, start: `${year}-01-01`, end: `${year}-12-31`, period_type: 'annual' as const }, choices: ['revenue', 'net_profit_parent', 'operating_cash_flow'].map(metric_key => ({ metric_key, document_id: 'doc', disclosure_version: `disclosure-v1:${hash}`, fact_set_id: null, fact_id: null })) });
  const input: TemplateInput = { schema_version: 'operating-research-input-v1', template: 'company_period_change', direction: 'business_overview', first: side(2025), second: side(2024), reports: [{ document_id: 'doc', expected_source_revision: hash }] };
  return { schema_version: 'persistent-template-task-v1', graph_version: 'd19-operating-graph-v1', task_id: uuid, operation_id: uuid, revision: 20, created_at: '2026-10-10T12:00:00Z', status: 'awaiting_human_confirmation', execution_status: 'idle', input, active_input: input, budget: { schema_version: 'template-budget-v1', limits: { steps: 32, tool_calls: 24, retrieval_total: 24, model_calls: 4 }, used: { steps: 16, tool_calls: 13, retrieval_total: 0, model_calls: 0 }, elapsed_seconds: 1, error_code: null }, trace: [], snapshot: null, waiting_checkpoint: true, error_code: null, persistence: 'persisted', checkpointer: true, final_research_content: null };
}
test('comparison-year deep link verifies frozen side/company/PDF/revision/disclosure before reading PDF', () => {
  const t = task(), q = new URLSearchParams(taskReviewPath(t, 'second', 'revenue').split('?')[1]);
  assert.equal(validateReviewContext(t, q).year, 2024);
  for (const [key, value] of [['task', uuid.replace('1', '2')], ['company', 'foreign'], ['document', 'foreign'], ['revision', 'b'.repeat(64)], ['period', '2025'], ['side', 'third'], ['metric_key', 'invented'], ['disclosure', `disclosure-v1:${'b'.repeat(64)}`], ['return_to', 'https://evil.example']]) {
    const tampered = new URLSearchParams(q); tampered.set(key, value); assert.throws(() => validateReviewContext(t, tampered), /./, key);
  }
});
test('waiting, running, unknown, refused, failed and exhausted instructions stay distinct', () => {
  const t = task(); assert.match(nextAction(t), /逐项核对/);
  t.execution_status = 'running'; assert.match(nextAction(t), /等待读回/);
  t.execution_status = 'idle'; t.waiting_checkpoint = false; t.status = 'failed'; assert.match(nextAction(t), /未完成/);
  t.error_code = 'budget_model_calls_exhausted'; assert.match(nextAction(t), /预算已耗尽/);
  t.error_code = null; t.status = 'refused'; assert.match(nextAction(t), /证据不足/);
  t.publication_eligibility = { status: 'invalidated', reason: 'source_changed' }; assert.match(nextAction(t), /已失效/);
});
test('multipart upload uses strict metadata and native boundary; 202 is a query identity only', async () => {
  const old = globalThis.fetch; let calls = 0;
  globalThis.fetch = (async (url, init) => {
    calls++; assert.equal(url, '/api/report-documents'); assert.equal(init?.method, 'POST'); assert.equal(init?.headers, undefined);
    assert.ok(init?.body instanceof FormData); const meta = JSON.parse(String(init.body.get('metadata')));
    assert.deepEqual(meta, { ...annualMetadata('company', '2025'), source_url: null });
    assert.equal((init.body.get('file') as File).name, 'report.pdf');
    return new Response(JSON.stringify({ document_id: 'doc', duplicate: false, document_status: 'queued' }), { status: 202 });
  }) as typeof fetch;
  try { const v = await uploadReport(new File(['%PDF'], 'report.pdf'), annualMetadata('company', '2025'), new AbortController().signal); assert.deepEqual(v, { document_id: 'doc', duplicate: false }); assert.equal(calls, 1); }
  finally { globalThis.fetch = old; }
});
test('lost upload response is unknown and never automatically retried', async () => {
  const old = globalThis.fetch; let calls = 0;
  globalThis.fetch = (async () => { calls++; throw new TypeError('lost response'); }) as typeof fetch;
  try { await assert.rejects(() => uploadReport(new File(['%PDF'], 'report.pdf'), annualMetadata('company', '2025'), new AbortController().signal), e => e instanceof UploadError && e.unknown); assert.equal(calls, 1); }
  finally { globalThis.fetch = old; }
});
test('binding readback mismatch cannot publish source readiness; metadata 5xx stays visible', async () => {
  const old = globalThis.fetch;
  globalThis.fetch = (async url => new Response(JSON.stringify(String(url).endsWith('/metadata') ? annualMetadata('foreign', '2025') : { document_id: 'doc', status: 'ready' }), { status: 200 })) as typeof fetch;
  try { await assert.rejects(() => readUploaded('doc', annualMetadata('company', '2025'), new AbortController().signal), /绑定不一致/); }
  finally { globalThis.fetch = old; }
  globalThis.fetch = (async url => String(url).endsWith('/metadata') ? new Response('{}', { status: 503 }) : new Response(JSON.stringify([{ document_id: 'doc', source_file: 'report.pdf', status: 'ready' }]), { status: 200 })) as typeof fetch;
  try { await assert.rejects(() => listDocuments(new AbortController().signal), /绑定读取失败/); }
  finally { globalThis.fetch = old; }
});
