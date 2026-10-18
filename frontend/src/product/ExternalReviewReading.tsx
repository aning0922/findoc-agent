import { useReview } from './useExternalReviews.ts';
import type { ResearchRun } from './researchHistory.ts';
import type { ExternalReview, ReviewMatch } from './externalReview.ts';
import { matchRunReview } from './externalReview.ts';
import './ExternalReviewReading.css';

export function ReviewEvidence({ record }: { record: ExternalReview }) {
  return <details className="external-review-evidence"><summary>审阅来源、时间与适用范围</summary>
    <p>审阅原话：{record.original_words}</p><p>原始意见：{record.opinion}</p>
    <p>记录时间：<time dateTime={record.recorded_at}>{record.recorded_at}</time> · 审阅者：{record.reviewer_name || 'D28 本人（姓名未记录）'}</p>
    <p>{record.scope}</p><p>记录 {record.record_id} · 来源版本 d28-external-review-reading-v1</p>
    {record.evidence.map(e => <div key={e.path}><a href={`https://github.com/aning0922/findoc-analyst-v1/blob/${e.commit}/${e.path}`} target="_blank" rel="noreferrer">{e.path}</a><p>原始文件 SHA256：<code>{e.sha256}</code></p></div>)}
    <p>目标内容 SHA256：<code>{record.target_sha256}</code></p>
    <details><summary>完整外部审阅身份</summary><pre>{JSON.stringify(record, null, 2)}</pre></details>
  </details>;
}
function matchText(match: ReviewMatch | null) {
  return !match ? '外部人工审阅：正在核对本项记录' : match.status === 'mismatch'
    ? '外部人工审阅：记录不适用，身份无法精确匹配' : '外部人工审阅：无本项适用记录 · 待审';
}
export function RunReviewReading({ run }: { run: ResearchRun }) {
  const match = useReview(run, matchRunReview), record = match?.records[0];
  return <section className="external-review-reading" aria-label="问答审阅状态" data-review-run={run.run_id}>
    <p>原生语义状态：{run.result?.human_review === 'pending' ? '待审（pending）' : '无原生审阅结论（null）'}</p>
    {record ? <><p className="external-review-decision" data-external-review={record.record_id}>外部人工审阅：本题通过 · {record.question_id}</p>
      {run.status === 'refused' && <p>通过仅表示本人认可本次拒答处理与已显示提示，不表示所请求能力已实现。</p>}
      <ReviewEvidence record={record} /></> : <p>{matchText(match)}</p>}
    <p>外部 D28 记录为只读证据，不等于产品原生签核；不授予财务事实或经营因果资格。</p>
    {run.source_states.some(s => s.status === 'expired') && <p>针对历史版本的外部审阅；当前来源已变化，不授予当前资格。</p>}
  </section>;
}
export function StatementReviewReading({ match, index }: { match: ReviewMatch | null; index: number }) {
  const record = match?.records.find(r => r.statement_index === index);
  return <aside className="external-review-reading" aria-label={`解释 ${index + 1} 外部审阅`}>
    <p>原生语义状态：待审（pending） · 经营因果：未验证（false）</p>
    {record ? <><p className="external-review-decision" data-external-review={record.record_id}>外部人工审阅：{record.decision === 'approved_with_rewrite' ? '同意改写' : '接受原句'}</p>
      {record.rewrite && <div className="external-review-rewrite"><strong>外部人工审阅改写 · 有效阅读表述</strong><p>{record.rewrite}</p></div>}
      <ReviewEvidence record={record} /></> : <p>{matchText(match)}</p>}
  </aside>;
}
