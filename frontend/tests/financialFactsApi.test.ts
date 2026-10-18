import test from 'node:test'
import assert from 'node:assert/strict'
import { persistFacts, readFacts, validateFactSet } from '../src/evidence/factsApi.ts'
import type { FactSet } from '../src/evidence/factsApi.ts'
import type { Receipt } from '../src/evidence/reviewApi.ts'
import { ReviewError } from '../src/evidence/reviewApi.ts'
import type { Source, Candidate } from '../src/evidence/contracts.ts'
const source: Source = { company_id: 'c', document_id: 'd', source_revision: 'a'.repeat(64), content_sha256: 'b'.repeat(64), attempt: 1, parser_version: 'v2', physical_pages: 10, report_year: 2031, metadata_status: 'pending_verification' }
const candidate: Candidate = { ...source, candidate_id: 'candidate', metric_key: 'revenue', period: 2031, status: 'candidate', confirmation_status: 'pending', raw_value: '12', raw_unit: '万元', value_cny_yuan: '120000', currency: 'CNY', scope: 'consolidated', accounting_basis: 'PRC_GAAP', failure_reason: null, evidence: [{ evidence_id: 'e', physical_page: 3, role: 'statement', raw_value: '12', raw_unit: '万元', bbox: null, label: '营业收入' }], basis_evidence: [{ evidence_id: 'e', physical_page: 3, excerpt: 'basis' }] }
const receipt: Receipt = { schema: 'financial-acceptance-v1', receipt_id: 'r', request_id: 'q', snapshot_id: `financial-review-v1:${'c'.repeat(64)}`, accepted_at: '2026-10-10T12:00:00Z', company_id: 'c', document_id: 'd', source_revision: source.source_revision, confirmation_kind: 'simulated_test', status: 'acceptance_saved', facts_status: 'pending_d10', analysis_started: false, review: { schema: 'financial-review-v1', source, company: { company_id: 'c', name: '测试公司' }, document: { document_id: 'd', source_file: 'real.pdf' }, selection: { metric_keys: ['revenue'], periods: [2031] }, candidates: [candidate], source_evidence: [{ evidence_id: 'e', physical_page: 3, text: 'statement' }] } }
const facts: FactSet = { schema: 'financial-fact-set-v1', fact_set_id: 'r', receipt_id: 'r', snapshot_id: receipt.snapshot_id, confirmation_kind: 'simulated_test', accepted_at: receipt.accepted_at, saved_at: '2026-10-10T12:01:00Z', company_id: 'c', document_id: 'd', source_revision: source.source_revision, disclosure_version: `disclosure-v1:${'f'.repeat(64)}`, status: 'facts_saved', integrity: 'verified', current_valid: true, invalid_reason: null, calculable: true, production_calculable: false, review: receipt.review, facts: [{ ...candidate, fact_id: 'f', fact_set_id: 'r', unit: 'CNY_YUAN', confirmation_status: 'confirmed' }] }
function json(v: unknown, status = 200) { return new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } }) }
test('fact set requires complete accepted values, units, evidence, scope and identity', () => {
  assert.equal(validateFactSet(facts, receipt), facts)
  for (const changed of [{ ...facts, facts: [] }, { ...facts, receipt_id: 'wrong' }, { ...facts, current_valid: 'true' }, { ...facts, confirmation_kind: 'local_operator' }, { ...facts, facts: [{ ...facts.facts[0], value_cny_yuan: '1' }] }, { ...facts, facts: [{ ...facts.facts[0], raw_unit: '元' }] }, { ...facts, facts: [{ ...facts.facts[0], evidence: [] }] }, { ...facts, integrity: 'unverified' }, { ...facts, facts: [{ ...facts.facts[0], confirmation_status: 'pending' }] }]) assert.throws(() => validateFactSet(changed as FactSet, receipt), ReviewError)
  assert.throws(() => validateFactSet({ ...facts, current_valid: false, calculable: false, invalid_reason: 'source_changed' }, receipt), (e: unknown) => e instanceof ReviewError && e.state === 'source')
})
test('fact save sends only known receipt ID and displays success only after a matching GET', async () => {
  const original = globalThis.fetch; const calls: { path: string; method: string; body: unknown }[] = []
  try {
    globalThis.fetch = async (path, init) => { calls.push({ path: String(path), method: init?.method || 'GET', body: init?.body ? JSON.parse(String(init.body)) : null }); return json(String(path).includes('/persisted') ? facts : source) }
    assert.equal((await persistFacts(source, receipt, new AbortController().signal)).fact_set_id, 'r')
    assert.deepEqual(calls.filter(c => c.method === 'POST').map(c => c.body), [{ receipt_id: 'r' }])
    assert.equal(calls.filter(c => c.path.endsWith('/persisted/r')).length, 1)
  } finally { globalThis.fetch = original }
})
test('lost POST response or failed GET readback stays unknown; recovery never creates', async () => {
  const original = globalThis.fetch
  try {
    for (const failure of ['post', 'get', 'partial']) {
      let posts = 0
      globalThis.fetch = async (path, init) => {
        if (!String(path).includes('/persisted')) return json(source)
        if (init?.method === 'POST') { posts++; if (failure === 'post') throw new Error('lost'); return json(facts) }
        if (failure === 'get') return json({ detail: { code: 'financial_storage_error' } }, 500)
        return json({ ...facts, facts: [] })
      }
      await assert.rejects(() => persistFacts(source, receipt, new AbortController().signal), (e: unknown) => e instanceof ReviewError && e.state === 'unknown')
      assert.equal(posts, 1)
      globalThis.fetch = async path => json(String(path).includes('/persisted') ? facts : source)
      assert.equal((await readFacts(source, receipt, new AbortController().signal)).receipt_id, 'r')
      assert.equal(posts, 1)
    }
  } finally { globalThis.fetch = original }
})
test('fact read uses only the known-ID GET; no candidate or source parsing endpoint', async () => {
  const original = globalThis.fetch; const calls: string[] = []
  try {
    globalThis.fetch = async path => { calls.push(String(path)); return json(facts) }
    assert.equal((await readFacts(source, receipt, new AbortController().signal)).fact_set_id, 'r')
    assert.deepEqual(calls, ['/api/financial-facts/persisted/r'])
    await assert.rejects(() => readFacts({ ...source, attempt: 2 }, receipt, new AbortController().signal), (e: unknown) => e instanceof ReviewError && e.state === 'source')
    assert.equal(calls.length, 1)
  } finally { globalThis.fetch = original }
})
