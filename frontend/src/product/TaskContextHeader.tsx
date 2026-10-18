import { verificationText } from './researchVerification.ts';
import type { VerificationState } from './researchVerification.ts';
import type { ReactNode } from 'react';
import type { Company } from './api.ts';
import type { Task } from './operatingResearch.ts';
import { taskLabels } from './operatingResearch.ts';
import type { Draft } from './reportDraft.ts';
import type { ReportDetail } from './reportPersistence.ts';
import { taskContext, reportContext, type ContextScope, type ContextSource } from './researchContext.ts';
import { taskSectionPath, qaPath, type ResearchSection } from './productRoutes.ts';
import { taskUserStatus, statusPresentation } from './userStatus.ts';
import { DiagnosticDetails } from './DiagnosticDetails.tsx';

function Scope({ scopes, sources }: { scopes: ContextScope[]; sources: ContextSource[] }) {
  const single = new Set(scopes.map(s => s.company_id)).size === 1;
  const label = (id: string) => single ? '' : scopes.findIndex(s => s.company_id === id) === 0 ? '企业 A · ' : '企业 B · ';
  return <div className="context-scope"><p>财务年度：{scopes.map(s => `${label(s.company_id)}${s.year} 年`).join(' / ')} · 全年 · 合并口径</p>
    <p>报告年度：{sources.length ? sources.map(s => `${label(s.company_id)}${s.report_year} 年报`).join(' / ') : '当前记录未提供完整报告年度，请查阅来源详情'}</p>
    <DiagnosticDetails label="冻结来源与身份" fields={Object.fromEntries(sources.map((s, i) => [`来源 ${i + 1} · ${s.report_year} 年报`, `${s.document_id} / ${s.source_revision}`]))} />
  </div>;
}
export function ResearchContextNav({ task, section = 'operating', report = false }: { task: Pick<Task, 'task_id' | 'input'>; section?: ResearchSection; report?: boolean }) {
  const company = task.input.first.company_id;
  return <nav className="research-context-nav" aria-label="当前研究功能">
    {([['sources', '资料与核对'], ['financial', '财务分析'], ['operating', '经营研究']] as const).map(([key, label]) =>
      <a key={key} aria-current={!report && section === key ? 'page' : undefined} href={taskSectionPath(task.task_id, company, key) + (key === 'sources' ? '#research-facts' : key === 'financial' ? '#research-results' : '')}>{label}</a>)}
    <a href={qaPath(company, task.task_id)}>原文问答</a>
    <a aria-current={report ? 'page' : undefined} href={`/reports?${new URLSearchParams({ task: task.task_id })}`}>报告</a>
  </nav>;
}
export function TaskContextHeader({ task, companies, unknown = false, executing = false, section = 'operating', children, verification, compact = false }: {
  task: Task; companies: Company[]; unknown?: boolean; executing?: boolean; section?: ResearchSection; children?: ReactNode; verification?: VerificationState; compact?: boolean;
}) {
  const context = taskContext(task, companies), state = executing ? 'waiting' : taskUserStatus(task, unknown);
  return <header className="task-context-header" role="region" aria-label="研究上下文" data-task-id={task.task_id} data-task-revision={task.revision}>
    <a className="context-back" href="/">← 返回我的研究</a>
    <div className="context-title-row"><p className="eyebrow">企业经营研究</p><span className="context-state" data-user-state={verification && verification !== 'current' ? verification : state || 'preparation'}>{verification && verification !== 'current' ? verificationText[verification] : executing ? '正在执行经营研究' : state ? statusPresentation[state].title : taskLabels[task.status]}</span></div>
    {verification && !compact && <p className="context-note">历史任务状态：{taskLabels[task.status]} · 当前资格：{verificationText[verification]}</p>}
    <h1>{context.scopes[0].name}{task.input.template === 'company_period_change' ? ` · ${context.scopes[1].year}—${context.scopes[0].year} 经营变化` : ` × ${context.scopes[1].name} · ${context.scopes[0].year} 年经营比较`}</h1>
    {compact ? <details><summary>期间、口径与冻结来源</summary><Scope {...context} /></details> : <Scope {...context} />}
    {compact && <p className="context-note">历史结果读取 · 不会重新运行模型 · 当前资格：{verificationText[verification || "checking"]}</p>}
    {children}
    <ResearchContextNav task={task} section={section} />
  </header>;
}
export function ReportContextHeader({ draft, saved, compact = false }: { draft: Draft; saved?: ReportDetail; compact?: boolean }) {
  const context = reportContext(draft);
  const sourceTask = { task_id: draft.task_id, input: { first: { company_id: context.scopes[0]?.company_id || '' } } } as Task;
  return <header className="task-context-header" role="region" aria-label="报告冻结上下文" data-task-id={draft.task_id}>
    <a href={taskSectionPath(draft.task_id, context.scopes[0]?.company_id || '', 'operating')}>← 返回来源研究</a>
    {!compact && <p className="eyebrow">{saved ? `已保存报告 · v${saved.report.revision}` : '报告草稿 · 尚未保存'}</p>}
    {!compact && <h2>{new Set(context.scopes.map(s => s.company_id)).size === 1 ? `${context.scopes[0].name} · ${context.scopes.map(s => `${s.year} 年`).join(' / ')}` : context.scopes.map(s => `${s.name} · ${s.year} 年`).join(' / ')}</h2>}
    {compact ? <details><summary>报告期间与冻结来源</summary><Scope {...context} /></details> : <Scope {...context} />}
    {!compact && <p className="context-note">范围来自报告冻结快照 · 模型解释与用户断言待人工语义审阅</p>}
    {!compact && <ResearchContextNav task={sourceTask} report />}
  </header>;
}
