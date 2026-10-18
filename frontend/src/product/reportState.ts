export function reportPersistenceText(saved: boolean): string {
  return saved ? "已保存报告版本；模型判断维持 pending_semantic_review。" : "报告草稿尚未保存；模型判断维持 pending_semantic_review。";
}
export function reportLimitations(items: string[], saved: boolean): string[] {
  return saved ? items.filter(item => !item.startsWith("草稿尚未保存") && !item.startsWith("报告草稿尚未保存")) : items;
}
export function editorDirty(title: string, conclusion: string | string[], savedTitle: string | null, savedConclusions: string[]): boolean {
  return (title.trim() || null) !== savedTitle || JSON.stringify((Array.isArray(conclusion) ? conclusion : [conclusion]).map(c => c.trim()).filter(Boolean)) !== JSON.stringify(savedConclusions);
}
import type { Draft } from './reportDraft.ts';
import type { ReportDetail } from './reportPersistence.ts';

export function assertSavedOwner(detail: ReportDetail, draft: Draft, previous?: ReportDetail): void {
  const snapshot = detail.report.trusted_snapshot;
  if (snapshot.task_id !== draft.task_id || snapshot.task_revision !== draft.task_revision ||
      (previous && (detail.report.report_id !== previous.report.report_id || detail.report.revision !== previous.current_revision + 1)))
    throw new Error('保存结果不属于当前研究与报告版本');
}

export function canEditReport(detail: ReportDetail): boolean {
  return detail.current_eligibility.status === 'current_at_read' && detail.report.revision === detail.current_revision;
}
