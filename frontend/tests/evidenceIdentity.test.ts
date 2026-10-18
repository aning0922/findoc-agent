import assert from 'node:assert/strict'
import test from 'node:test'
import { sameSource, validateSource, validateEvidence } from '../src/evidence/contracts.ts'
import type { Source, Evidence } from '../src/evidence/contracts.ts'
const source: Source = { company_id: 'c', document_id: 'd', source_revision: 'a'.repeat(64), content_sha256: 'b'.repeat(64), attempt: 1, parser_version: 'v2', physical_pages: 10, report_year: 2025, metadata_status: 'pending_verification' }
test('company, document, revision, SHA, attempt, parser version and physical page fail closed', () => {
  assert.equal(validateSource(source, 'c', 'd', source.source_revision), source)
  for (const [company, doc, rev] of [['wrong', 'd', ''], ['c', 'wrong', ''], ['c', 'd', 'c'.repeat(64)]]) {
    assert.throws(() => validateSource(source, company, doc, rev))
  }
  for (const patch of [{ attempt: 2 }, { parser_version: 'v3' }, { content_sha256: '0'.repeat(64) }, { physical_pages: 11 }]) {
    assert.equal(sameSource(source, { ...source, ...patch }), false)
  }
  const e: Evidence = { ...source, evidence_id: 'e', physical_page: 3, text: '原文', layout: null }
  assert.equal(validateEvidence(e, source, 'e', 3), e)
  for (const patch of [{ company_id: 'wrong' }, { document_id: 'wrong' }, { source_revision: '0'.repeat(64) }, { physical_page: 11 }, { evidence_id: 'old' }]) {
    assert.throws(() => validateEvidence({ ...e, ...patch }, source, 'e', 3))
  }
  assert.throws(() => validateEvidence(e, source, 'e', 4))
})
