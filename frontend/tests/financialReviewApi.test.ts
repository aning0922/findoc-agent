import test from 'node:test'
import assert from 'node:assert/strict'
import { acceptReview, recoverReceipt, validateReview, validateReceipt, ReviewError } from '../src/evidence/reviewApi.ts'
import type { Review, AcceptanceRequest, Receipt } from '../src/evidence/reviewApi.ts'
import type { Source } from '../src/evidence/contracts.ts'
const source: Source = { company_id: 'c', document_id: 'd', source_revision: 'a'.repeat(64), content_sha256: 'b'.repeat(64), attempt: 1, parser_version: 'v2', physical_pages: 10, report_year: 2031, metadata_status: 'pending_verification' }
const q: AcceptanceRequest = { review_schema: 'financial-review-v1', company_id: 'c', document_id: 'd', source_revision: source.source_revision, metric_keys: ['revenue'], periods: [2031], accepted: true, snapshot_id: `financial-review-v1:${'c'.repeat(64)}`, request_id: 'explicit-test' }
const review: Review = { schema: 'financial-review-v1', source, company: { company_id: 'c', name: '测试公司' }, document: { document_id: 'd', source_file: 'real.pdf' }, selection: { metric_keys: ['revenue'], periods: [2031] }, snapshot_id: q.snapshot_id, review_status: 'ready_for_acceptance', facts_status: 'unconfirmed', source_evidence: [{ evidence_id: 'e', physical_page: 3, text: 'statement' }], candidates: [{ ...source, candidate_id: 'candidate', metric_key: 'revenue', period: 2031, status: 'candidate', raw_value: '12', raw_unit: '万元', value_cny_yuan: '120000', multiplier: '10000', currency: 'CNY', scope: 'consolidated', accounting_basis: 'PRC_GAAP', failure_reason: null, confirmation_status: 'pending', evidence: [{ evidence_id: 'e', physical_page: 3, role: 'statement', raw_value: '12', raw_unit: '万元', bbox: null, label: '营业收入' }], basis_evidence: [{ evidence_id: 'e', physical_page: 3, excerpt: 'basis' }] }] }
const receipt: Receipt = { schema: 'financial-acceptance-v1', receipt_id: 'r', request_id: q.request_id, snapshot_id: q.snapshot_id, accepted_at: '2026-10-09T12:00:00Z', company_id: 'c', document_id: 'd', source_revision: source.source_revision, confirmation_kind: 'simulated_test', review, status: 'acceptance_saved', facts_status: 'pending_d10', analysis_started: false }
function json(v: unknown, status = 200) { return new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } }) }
test('snapshot selection, source, candidate states and complete evidence must match', () => {
  assert.equal(validateReview(review, source, q), review)
  for (const changed of [ { ...review, schema: 'v2' }, { ...review, source: { ...source, attempt: 2 } }, { ...review, selection: { metric_keys: ['revenue'], periods: [2030] } }, { ...review, source_evidence: [] }, { ...review, candidates: review.candidates.map(c => ({ ...c, status: 'conflict', value_cny_yuan: null })) } ]) assert.throws(() => validateReview(changed as Review, source, q))
})
test('receipt must remain pending D10, with correct operation, evidence and no analysis', () => {
  assert.equal(validateReceipt(receipt, q, review), receipt)
  for (const changed of [{ ...receipt, facts_status: 'confirmed' }, { ...receipt, request_id: 'late' }, { ...receipt, company_id: 'wrong' }, { ...receipt, analysis_started: true }, { ...receipt, review: { ...review, candidates: [] } }]) assert.throws(() => validateReceipt(changed as Receipt, q, review), ReviewError)
})
test('lost or malformed acceptance response stays unknown, never auto retried', async () => {
  const original = globalThis.fetch
  try {
    for (const response of ['lost', 'bad', 'storage']) {
      let posts = 0
      globalThis.fetch = async (_url, init) => {
        if (init?.method !== 'POST') return json(source)
        posts++
        if (response === 'lost') throw new Error('offline')
        if (response === 'bad') return json({})
        return json({ detail: { code: 'financial_storage_error' } }, 500)
      }
      await assert.rejects(() => acceptReview(source, q, review, new AbortController().signal), (e: unknown) => e instanceof ReviewError && e.state === 'unknown')
      assert.equal(posts, 1)
    }
  } finally { globalThis.fetch = original }
})
test('source revalidation before sending blocks acceptance; recovery is GET only', async () => {
  const original = globalThis.fetch; const calls: RequestInit[] = []
  try {
    globalThis.fetch = async (url, init) => { calls.push(init || {}); return String(url).includes('/confirmations/') ? json(receipt) : json(source) }
    assert.equal((await recoverReceipt(source, q, review, new AbortController().signal)).receipt_id, 'r')
    assert.equal(calls.some(c => c.method === 'POST'), false)
    globalThis.fetch = async () => json({ detail: { code: 'source_changed' } }, 409)
    await assert.rejects(() => acceptReview(source, q, review, new AbortController().signal), (e: unknown) => e instanceof ReviewError && e.state === 'source')
  } finally { globalThis.fetch = original }
})
test('known receipt ID recovery reads accepted snapshot directly, without review POST', async () => {
  const { recoverReceiptById } = await import('../src/evidence/reviewApi.ts')
  const original = globalThis.fetch; const paths: string[] = []
  try {
    globalThis.fetch = async path => { paths.push(String(path)); return json(receipt) }
    const r = await recoverReceiptById(source, 'r', q, new AbortController().signal)
    assert.equal(r.receipt.receipt_id, 'r')
    assert.deepEqual(paths, ['/api/financial-facts/acceptances/r'])
  } finally { globalThis.fetch = original }
})
test('P1 auto recovery obtains snapshot by GET and rejects mismatched identity without POST', async () => {
  const { recoverAcceptance } = await import('../src/evidence/receiptRecovery.ts')
  const original = globalThis.fetch
  try {
    for (const mismatch of [false, true]) {
      const methods: string[] = []
      globalThis.fetch = async (url, init) => {
        methods.push(init?.method || 'GET')
        return String(url).includes('/confirmations/') ? json(mismatch ? { ...receipt, request_id: 'other-request' } : receipt) : json(source)
      }
      if (mismatch) await assert.rejects(() => recoverAcceptance(source, q, new AbortController().signal))
      else {
        const result = await recoverAcceptance(source, q, new AbortController().signal)
        assert.equal(result.review.snapshot_id, q.snapshot_id)
        assert.equal(result.review.candidates.length, 1)
      }
      assert.ok(methods.every(m => m === 'GET'))
    }
  } finally { globalThis.fetch = original }
})

test('P1 receipt hints cannot broaden a frozen task sub-group or switch its year', async () => {
  const { matchesReviewScope } = await import('../src/evidence/receiptRecovery.ts');
  assert.equal(matchesReviewScope(q, 2031, ['revenue']), true);
  assert.equal(matchesReviewScope(q, 2030, ['revenue']), false);
  assert.equal(matchesReviewScope({ ...q, metric_keys: ['revenue', 'net_profit_parent'] }, 2031, ['revenue']), false);
});
