import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readResearchCandidates } from '../src/product/researchCandidates.ts';
const revision = 'a'.repeat(64), sha = 'b'.repeat(64), disclosure = `disclosure-v1:${'c'.repeat(64)}`;
const source = { company_id: 'co', document_id: 'doc', source_revision: revision, content_sha256: sha, attempt: 1, parser_version: 'v1', physical_pages: 10, report_year: 2025, metadata_status: 'confirmed' };
const task = { input: { reports: [{ document_id: 'doc', expected_source_revision: revision }] }, active_input: Object.fromEntries(['first', 'second'].map((side, i) => [side, { company_id: 'co', period: { year: 2025 - i }, choices: ['revenue', 'net_profit_parent', 'operating_cash_flow'].map(metric_key => ({ metric_key, document_id: 'doc', disclosure_version: disclosure })) }])) } as any;
test('candidate preview uses only source-bound GET and rejects ambiguous disclosures', async () => {
  const original = globalThis.fetch;
  let ambiguous = false; const methods: string[] = [];
  try {
    globalThis.fetch = (async (input, init) => {
      methods.push(init?.method || 'GET');
      const url = new URL(String(input), 'http://example.test');
      if (url.pathname.endsWith('/source')) return Response.json(source);
      if (url.pathname.includes('/research/disclosures/')) return Response.json({ schema_version: 'research-disclosure-options-v1', source, disclosure_versions: ambiguous ? [disclosure, `disclosure-v1:${'d'.repeat(64)}`] : [disclosure], automatic_selection: false });
      if (url.pathname.endsWith('/financial-candidates')) return Response.json({ source, candidates: url.searchParams.getAll('metric_keys').map(metric_key => ({ ...source, metric_key, period: Number(url.searchParams.get('periods')), raw_value: '123', raw_unit: '元', status: 'candidate', evidence: [] })) });
      throw new Error(`unexpected ${url.pathname}`);
    }) as typeof fetch;
    const rows = await readResearchCandidates(task, new AbortController().signal);
    assert.equal(Object.keys(rows).length, 6);
    assert.equal(rows['second:revenue'].period, 2024);
    assert.ok(methods.every(m => m === 'GET'));
    ambiguous = true;
    await assert.rejects(readResearchCandidates(task, new AbortController().signal), /披露来源/);
  } finally { globalThis.fetch = original; }
});
