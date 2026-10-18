import test from 'node:test';
import assert from 'node:assert/strict';
import { compareReportFields } from '../src/product/reportComparison.ts';
import { canEditReport, editorDirty } from '../src/product/reportState.ts';
import { readExactReport, validateReport, type ReportDetail } from '../src/product/reportPersistence.ts';
import { fetchMarkdown } from '../src/product/reportExport.ts';
function value(revision = 1): ReportDetail {
  return { schema_version: 'report-detail-v1', payload_sha256: 'a'.repeat(64), current_revision: 2, current_eligibility: { status: 'current_at_read', reason: null }, report: { schema_version: 'report-revision-v1', report_id: 'report-A', revision, parent_revision: revision === 1 ? null : revision - 1, operation_id: 'op', created_at: 'today', persisted: true, editor_revision: { title: '标题', conclusions: ['第一项', '第二项'], origin: 'user_edit', validation_status: 'pending_semantic_review', verified_operating_attribution: false, qualification_limit: 'user_assertions_unverified' }, trusted_snapshot: { schema_version: 'report-draft-v1', task_id: 'task', task_revision: 4, persisted: false, status: 'simulated_draft', test_mode: 'simulated_test', watermark: 'simulated_test', financial_facts: Array(6).fill({ raw_value: '100', source_revision: 'source-A' }), financial_analysis: Array(3).fill({ absolute_change: '10' }), evidence_appendix: { a: 'source-A', b: 'source-B' }, field_verification: [], operating_information: [], model_interpretations: [] } } } as unknown as ReportDetail;
}
test('S5 edit gate separates historical identity, latest revision and current eligibility', () => {
  assert.equal(canEditReport(value(1)), false); assert.equal(canEditReport(value(2)), true);
  const d = value(2); d.current_eligibility.status = 'invalidated'; assert.equal(canEditReport(d), false);
  assert.equal(editorDirty('标题', ['第一项', '第二项'], '标题', ['第一项', '第二项']), false);
  assert.equal(editorDirty('标题', ['第一项', '变更'], '标题', ['第一项', '第二项']), true);
});
test('S5 field equality does not merge conclusions, imply accuracy or depend on object key order', () => {
  const a = value(1), b = value(2); b.report.editor_revision.conclusions[1] = '新断言';
  b.report.trusted_snapshot.evidence_appendix = { b: 'source-B', a: 'source-A' };
  const diff = compareReportFields(a, b); assert.equal(diff.conclusions[0].changed, false); assert.equal(diff.conclusions[1].changed, true);
  assert.equal(diff.financialEqual, true); assert.equal(diff.sourcesEqual, true); assert.equal(diff.frozenEqual, true);
  b.report.trusted_snapshot.financial_facts[0] = { ...b.report.trusted_snapshot.financial_facts[0], raw_value: '200' };
  assert.equal(compareReportFields(a, b).financialEqual, false);
  b.report.report_id = 'report-B'; assert.throws(() => compareReportFields(a, b));
  assert.throws(() => compareReportFields(a, a));
});
test('S5 exact GET rejects wrong report, revision, immutable hash and unqualified editor metadata', async () => {
  const old = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response(JSON.stringify(value(1)), { headers: { 'Content-Type': 'application/json' } }); };
  try {
    assert.equal((await readExactReport('report-A', 1, true, new AbortController().signal)).report.revision, 1);
    await assert.rejects(readExactReport('report-B', 1, true, new AbortController().signal));
    await assert.rejects(readExactReport('report-A', 2, true, new AbortController().signal));
    await assert.rejects(readExactReport('report-A', 1, true, new AbortController().signal, 'b'.repeat(64)));
    const d = value(1); (d.current_eligibility as any).status = 'qualified'; assert.throws(() => validateReport(d, true));
    const invalid = value(1); invalid.current_eligibility.status = 'invalidated'; const before = calls;
    await assert.rejects(fetchMarkdown(invalid, true, new AbortController().signal)); assert.equal(calls, before);
  } finally { globalThis.fetch = old; }
});
