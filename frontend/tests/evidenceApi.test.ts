import test from 'node:test'
import assert from 'node:assert/strict'
import { checkSource, forgetPdf, loadDocument, loadEvidence, loadPdf } from '../src/evidence/api.ts'
import type { Source } from '../src/evidence/contracts.ts'
const bytes = new TextEncoder().encode('%PDF-fixture-test-only')
const digest = await crypto.subtle.digest('SHA-256', bytes)
const sha = Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('')
const source: Source = { company_id: 'c', document_id: 'd', source_revision: 'a'.repeat(64), content_sha256: sha, attempt: 1, parser_version: 'v2', physical_pages: 10, report_year: 2025, metadata_status: 'pending_verification' }
function json(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }) }
test('source precedes PDF/candidates; same version reuses verified bytes without transferring cache', async () => {
  const original = globalThis.fetch, calls: string[] = []
  globalThis.fetch = async input => {
    const path = String(input); calls.push(path)
    if (path.includes('/file?')) return new Response(bytes, { headers: { 'content-type': 'application/pdf' } })
    if (path.includes('/financial-candidates?')) return json({ source, candidates: [] })
    return json(source)
  }
  try {
    forgetPdf(source)
    const a = await loadDocument('c', 'd', source.source_revision, new AbortController().signal)
    assert.ok(calls[0].includes('/source?'))
    assert.ok(calls.filter(c => c.includes('/file?')).every(c => c.includes(`source_revision=${source.source_revision}`) && c.includes('company_id=c')))
    a.bytes.fill(0)
    const b = await loadDocument('c', 'd', source.source_revision, new AbortController().signal)
    assert.deepEqual(b.bytes, bytes)
    assert.equal(calls.filter(c => c.includes('/file?')).length, 1)
    assert.equal(calls.filter(c => c.includes('/source?')).length, 4)
  } finally { globalThis.fetch = original; forgetPdf(source) }
})
test('cached PDF cannot bypass source validation; mismatched candidates and wrong SHA are rejected', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: { code: 'source_changed', message: '来源已变化' } }), { status: 409 })
    await assert.rejects(() => loadDocument('c', 'd', source.source_revision, new AbortController().signal), /来源已变化/)
    globalThis.fetch = async input => String(input).includes('/file?')
      ? new Response('wrong', { headers: { 'content-type': 'application/pdf' } }) : json(source)
    await assert.rejects(() => loadPdf(source, new AbortController().signal), /PDF 校验失败/)
    globalThis.fetch = async input => {
      if (String(input).includes('/file?')) return new Response(bytes, { headers: { 'content-type': 'application/pdf' } })
      if (String(input).includes('/financial-candidates?')) return json({ source: { ...source, attempt: 2 }, candidates: [] })
      return json(source)
    }
    await assert.rejects(() => loadDocument('c', 'd', source.source_revision, new AbortController().signal), /版本不匹配/)
  } finally { globalThis.fetch = original; forgetPdf(source) }
})
test('source change between evidence read and final validation rejects the evidence', async () => {
  const original = globalThis.fetch
  let sourceReads = 0
  globalThis.fetch = async input => {
    if (String(input).includes('/evidence/')) return json({ ...source, evidence_id: 'e', physical_page: 3, text: '原文', layout: null })
    return ++sourceReads === 1 ? json(source) : new Response(JSON.stringify({ detail: { code: 'source_changed', message: '来源已变化' } }), { status: 409 })
  }
  try {
    await assert.rejects(() => loadEvidence(source, 'e', 3, new AbortController().signal), /来源已变化/)
    globalThis.fetch = async () => json({ ...source, attempt: 2 })
    await assert.rejects(() => checkSource(source, new AbortController().signal), /来源版本已变化/)
  } finally { globalThis.fetch = original }
})
