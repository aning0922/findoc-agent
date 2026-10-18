import type { ReportDetail } from './reportPersistence.ts';
/** Stable field equality only. No numeric calculations or semantic interpretation. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical((value as Record<string, unknown>)[k])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}
export function compareReportFields(left: ReportDetail, right: ReportDetail) {
  if (left.report.report_id !== right.report.report_id || left.report.revision === right.report.revision) throw new Error('必须读取同一报告的两个不同已保存版本');
  const a = left.report, b = right.report;
  const conclusions = Array.from({ length: Math.max(a.editor_revision.conclusions.length, b.editor_revision.conclusions.length) }, (_, i) => ({
    field: `用户结论 ${i + 1}`, left: a.editor_revision.conclusions[i] ?? null, right: b.editor_revision.conclusions[i] ?? null,
    changed: a.editor_revision.conclusions[i] !== b.editor_revision.conclusions[i],
  }));
  return {
    title: { field: '用户编辑标题', left: a.editor_revision.title, right: b.editor_revision.title, changed: a.editor_revision.title !== b.editor_revision.title },
    conclusions,
    financialEqual: canonical({ facts: a.trusted_snapshot.financial_facts, formulas: a.trusted_snapshot.financial_analysis }) === canonical({ facts: b.trusted_snapshot.financial_facts, formulas: b.trusted_snapshot.financial_analysis }),
    sourcesEqual: canonical({ evidence: a.trusted_snapshot.evidence_appendix, verification: a.trusted_snapshot.field_verification, operating: a.trusted_snapshot.operating_information }) === canonical({ evidence: b.trusted_snapshot.evidence_appendix, verification: b.trusted_snapshot.field_verification, operating: b.trusted_snapshot.operating_information }),
    frozenEqual: canonical({ ...a.trusted_snapshot, generated_at: undefined }) === canonical({ ...b.trusted_snapshot, generated_at: undefined }),
    generationTimeEqual: a.trusted_snapshot.generated_at === b.trusted_snapshot.generated_at,
  };
}
