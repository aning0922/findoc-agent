import test from 'node:test';
import assert from 'node:assert/strict';
import { taskContext, reportContext } from '../src/product/researchContext.ts';
import type { Task } from '../src/product/operatingResearch.ts';
import type { Draft } from '../src/product/reportDraft.ts';
test('two-company task preserves both financial years and only matching frozen sources', () => {
  const task = { input: { first: { company_id: 'A', period: { year: 2024 }, choices: [{ document_id: 'docA' }] }, second: { company_id: 'B', period: { year: 2024 }, choices: [{ document_id: 'docB' }] }, reports: [{ document_id: 'docA', expected_source_revision: 'oldA' }, { document_id: 'docB', expected_source_revision: 'oldB' }] }, snapshot: { documents: [{ company_id: 'A', document_id: 'docA', source_revision: 'oldA', report_year: 2025 }, { company_id: 'B', document_id: 'docB', source_revision: 'newB', report_year: 2026 }] } } as unknown as Task;
  const c = taskContext(task, [{ company_id: 'A', name: '企业甲' }, { company_id: 'B', name: '企业乙' }] as any);
  assert.deepEqual(c.scopes.map(s => [s.name, s.year]), [['企业甲', 2024], ['企业乙', 2024]]);
  assert.equal(c.sources.length, 1); assert.equal(c.sources[0].report_year, 2025);
});
test('saved report names and financial/report years come only from frozen snapshot', () => {
  const draft = { financial_facts: [{ side: 'first', company_id: 'A', company_name: '保存时甲', period: 2024, document_id: 'doc', source_revision: 'old' }, { side: 'second', company_id: 'B', company_name: '保存时乙', period: 2024, document_id: 'b', source_revision: 'b-old' }], evidence_appendix: { selected_reports: [{ company_id: 'A', document_id: 'doc', source_revision: 'old', report_year: 2025 }] } } as unknown as Draft;
  const c = reportContext(draft); assert.equal(c.scopes[0].name, '保存时甲'); assert.equal(c.scopes[1].name, '保存时乙'); assert.equal(c.sources[0].report_year, 2025);
});
