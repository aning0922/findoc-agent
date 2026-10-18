import { metrics, sides, validateTask } from './operatingResearch.ts';
import type { Side, Task } from './operatingResearch.ts';
import type { Fact } from './api.ts';

export function taskPath(t: Task) {
  return `/research?${new URLSearchParams({ company: t.input.first.company_id, mode: 'operating', task: t.task_id })}`;
}
export function taskReviewPath(t: Task, side: Side, metric: string, fact?: Fact) {
  const s = t.active_input[side], c = s.choices.find(c => c.metric_key === metric)!;
  const revision = t.input.reports.find(r => r.document_id === c.document_id)!.expected_source_revision;
  return `/evidence?${new URLSearchParams({ company: s.company_id, document: c.document_id, revision,
    task: t.task_id, side, period: String(s.period.year), metric_key: metric, disclosure: c.disclosure_version, return_to: 'operating',
    ...(fact ? { record: 'read', receipt: fact.fact_set_id, fact_set: fact.fact_set_id } : {}) })}`;
}
// URL/storage only carry navigation intent. Frozen identity always comes from validated task GET.
export function validateReviewContext(raw: unknown, q: URLSearchParams) {
  for (const key of q.keys()) if (q.getAll(key).length !== 1) throw new Error('审阅地址参数重复，请返回原任务。');
  const t = validateTask(raw as Task, q.get('task') || '');
  const side = q.get('side') as Side, metric = q.get('metric_key') || '';
  if (!sides.includes(side) || !metrics.includes(metric)) throw new Error('研究核对位置无效。');
  const s = t.active_input[side], c = s.choices.find(c => c.metric_key === metric)!;
  const r = t.input.reports.find(r => r.document_id === c.document_id)!;
  if (q.get('receipt') && (q.get('fact_set') && q.get('fact_set') !== q.get('receipt')
    || c.fact_set_id && c.fact_set_id !== q.get('receipt')))
    throw new Error('核对记录身份与任务事实组不一致。');
  if (q.get('company') !== s.company_id || q.get('document') !== c.document_id ||
      q.get('revision') !== r.expected_source_revision || q.get('period') !== String(s.period.year) ||
      q.get('disclosure') !== c.disclosure_version || q.get('return_to') !== 'operating')
    throw new Error('审阅地址与研究任务的期间、来源或披露版本不一致，请返回原任务。');
  return { task: t, side, metric, year: s.period.year, document: c.document_id, revision: r.expected_source_revision };
}
export function nextAction(t: Task): string {
  if (t.execution_status === 'running') return '执行结果正在等待读回，请刷新状态。';
  if (t.publication_eligibility?.status === 'invalidated') return '来源或事实已失效。核对新来源后明确新建研究。';
  if (t.error_code?.includes('budget')) return '本次研究预算已耗尽。查看执行详情，缩小研究范围后明确新建。';
  if (t.execution_outcome === 'interrupted/unknown') return '执行结果未知。先只读查询并查看执行详情，避免重复提交。';
  if (t.status === 'failed') return '研究未完成。查看失败原因并只读刷新；需要重做时明确新建。';
  if (t.status === 'refused') return '现有证据不足以回答。核对资料和研究范围后明确新建。';
  if (t.waiting_checkpoint) return '逐项核对下方财务事实，入库后返回，再复核并继续研究。';
  if (t.status === 'completed') return '阅读核准数字与经营原文，复核模型解释，然后进入报告草稿。';
  return '查看当前研究阶段与执行详情，刷新最新状态。';
}
