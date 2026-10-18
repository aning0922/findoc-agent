import { test } from 'node:test';
import assert from 'node:assert/strict';
import { json, ProductError } from '../src/product/api.ts';
import { correctionInvalidates, currentSource, verificationFailure, VerificationInvalidated, invalidFactReason } from '../src/product/researchVerification.ts';
import { researchChapters } from '../src/product/researchChapters.ts';
const source = { company_id: 'co', document_id: 'doc', source_revision: 'a'.repeat(64), content_sha256: 'b'.repeat(64), attempt: 1, parser_version: 'v1', physical_pages: 10, report_year: 2024, metadata_status: 'confirmed' };

test('failed HTTP reads preserve uncertainty even with a source-related code', async () => {
  const original = globalThis.fetch;
  try {
    for (const [status, code, state] of [[503, 'source_changed', 'unavailable'], [503, 'source_temporarily_unavailable', 'unavailable'], [404, 'resource_not_found', 'unavailable'], [409, 'source_changed', 'invalidated'], [409, 'acceptance_revoked', 'invalidated']] as const) {
      globalThis.fetch = (async () => new Response(JSON.stringify({ detail: { code } }), { status })) as typeof fetch;
      await assert.rejects(json('/source', new AbortController().signal), e => verificationFailure(e) === state);
    }
  } finally { globalThis.fetch = original; }
});
test('network failure and unparseable JSON are unavailable, never invalidated', async () => {
  const original = globalThis.fetch;
  try {
    for (const impl of [async () => { throw new TypeError('network'); }, async () => new Response('broken JSON')]) {
      globalThis.fetch = impl as typeof fetch;
      await assert.rejects(json('/source', new AbortController().signal), e => verificationFailure(e) === 'unavailable');
    }
  } finally { globalThis.fetch = original; }
});
test('formal D6 string detail source_changed is reliable only on a client conflict, not a 5xx', async () => {
  const original = globalThis.fetch;
  try {
    for (const status of [409, 503]) {
      globalThis.fetch = (async () => new Response(JSON.stringify({ detail: 'source_changed' }), { status })) as typeof fetch;
      await assert.rejects(json('/source', new AbortController().signal), e => verificationFailure(e) === (status === 409 ? 'invalidated' : 'unavailable'));
    }
  } finally { globalThis.fetch = original; }
});
test('version mismatch requires a fully validated source; malformed and wrong identity responses remain unavailable', () => {
  assert.deepEqual(currentSource(source, 'co', 'doc', source.source_revision), source);
  assert.throws(() => currentSource({ ...source, source_revision: 'c'.repeat(64) }, 'co', 'doc', source.source_revision), e => e instanceof VerificationInvalidated && verificationFailure(e) === 'invalidated');
  for (const value of [{ source_revision: 'c'.repeat(64) }, { ...source, company_id: 'foreign' }, null])
    assert.throws(() => currentSource(value as typeof source, 'co', 'doc', source.source_revision), e => verificationFailure(e) === 'unavailable');
  assert.equal(verificationFailure(new ProductError('source unavailable', true)), 'unavailable');
});
test('explicit revocation/integrity evidence cannot grant current fact eligibility', () => {
  for (const code of ['source_changed', 'acceptance_revoked', 'confirmation_integrity_error']) assert.equal(invalidFactReason(code), true);
  for (const code of [null, 'source_temporarily_unavailable', 'facts_not_found']) assert.equal(invalidFactReason(code), false);
});
test('chapter matrix offers only sections rendered in each route and task state', () => {
  for (const status of ['awaiting_human_confirmation', 'completed', 'failed']) {
    assert.deepEqual(researchChapters('sources', status).map(c => c.id), ['research-facts', 'research-history']);
    assert.deepEqual(researchChapters('financial', status).map(c => c.id), ['research-results', 'research-history']);
    assert.deepEqual(researchChapters('operating', status).map(c => c.id), status === 'completed' ? ['research-facts', 'research-results', 'research-history'] : ['research-facts', 'research-history']);
  }
});

test('not-ready alone is unavailable; immutable corrections must match the exact frozen attempt and scope', () => {
  const frozen = { ...source, basis: 'PRC_GAAP', report_type: 'annual', period_start: '2024-01-01', period_end: '2024-12-31' };
  const t = { snapshot: { documents: [frozen] } } as any;
  const row = { document_id: 'doc', action_kind: 'explicit_user_request', correction_id: '12345678-1234-1234-1234-123456789012', created_at: '2026-10-14T12:00:00Z', old_attempt: 1, new_attempt: 2, old_metadata_json: frozen };
  assert.equal(verificationFailure(new ProductError('not ready', true, 'source_not_ready', 409)), 'unavailable');
  assert.equal(correctionInvalidates([row], t, 'co', 'doc', source.source_revision), true);
  for (const history of [[], null, [ { ...row, document_id: 'foreign' } ], [ { ...row, old_attempt: 2, new_attempt: 3 } ], [ { ...row, old_metadata_json: { ...frozen, basis: 'unknown' } } ], [ { ...row, old_metadata_json: { ...frozen, company_id: 'foreign' } } ]])
    assert.equal(correctionInvalidates(history, t, 'co', 'doc', source.source_revision), false);
  assert.equal(correctionInvalidates([row], t, 'co', 'doc', 'c'.repeat(64)), false);
});
