import { useId, useMemo, useState } from 'react';
import { reportLimitations } from './reportState.ts';
import { METRICS } from '../evidence/contracts.ts';
import type { Draft, FactRow } from './reportDraft.ts';
import type { ReportDetail } from './reportPersistence.ts';
import { ResearchPdfDialog, type PdfCitation } from './ResearchPdfDialog.tsx';
import { ReportOutline } from './ReportOutline.tsx';
import { ReportExcerpt } from './ReportExcerpt.tsx';
import { reportDecimalDisplay, reportRateLabel, reportSummaryDisplay } from './reportReading.ts';
import { reportReviewTarget } from './externalReview.ts';
import { reportContext } from './researchContext.ts';
import { StatementReviewReading } from './ExternalReviewReading.tsx';
import { useOperatingReviews } from './useExternalReviews.ts';
export function ReportPaper({ draft, saved, sourceBlocked = false, onSourceInvalid }: { draft: Draft; saved?: ReportDetail; sourceBlocked?: boolean; onSourceInvalid?: () => void }) {
  const prefix = useId();
  const { scopes } = reportContext(draft);
  const reviews = useOperatingReviews(reportReviewTarget(draft));
  const [pdfLocation, setPdfLocation] = useState<PdfCitation | null>(null), [pdfFailed, setPdfFailed] = useState(false);
  function factLocation(f: FactRow): PdfCitation | null {
    const sources = draft.evidence_appendix.selected_reports;
    const source = Array.isArray(sources) ? sources.find((s: Record<string, unknown>) => s.document_id === f.document_id && s.company_id === f.company_id && s.source_revision === f.source_revision) : undefined;
    if (!source || !Number.isSafeInteger(source.report_year)) return null;
    const original = draft.operating_information.find(d => d.citation.document_id === f.document_id)?.citation;
    return { document_id: f.document_id, company_id: f.company_id, source_revision: f.source_revision, physical_page: f.physical_page, report_year: Number(source.report_year), source_file: String(original?.source_file || '冻结年报原文'), parser_version: typeof source.parser_version === 'string' ? source.parser_version : undefined };
  }
  const openFact = (f: FactRow) => { const citation = factLocation(f); if (citation) setPdfLocation(citation); };
  const openOperating = (c: Record<string, unknown>) => setPdfLocation({ number: Number(c.number), document_id: String(c.document_id), company_id: String(c.company_id), source_revision: String(c.source_revision), physical_page: Number(c.physical_page), report_year: Number(c.report_year), source_file: String(c.source_file), parser_version: typeof c.parser_version === 'string' ? c.parser_version : undefined });
  const sections = useMemo(() => ['执行摘要', '财务变化', '已确认财务事实', '经营原文与来源', '待审解释', '未解决问题', '证据及审计附录'].map((title, i) => ({ title, id: `${prefix}-section-${i}` })), [prefix]);
  const heading = (index: number) => <h2 id={sections[index].id} tabIndex={-1}><span>{String(index + 1).padStart(2, '0')}</span>{sections[index].title}</h2>;
  const available = !sourceBlocked && !pdfFailed && (!saved || saved.current_eligibility.status === 'current_at_read');
  return <div className="report-reading-layout"><ReportOutline sections={sections} /><article className="surface report-paper" data-task-id={draft.task_id} data-report-id={saved?.report.report_id} data-revision={saved?.report.revision} aria-label={saved ? '已保存报告版本' : '报告草稿预览'}>
    <header className="report-cover"><p className="report-badge">{saved ? `已保存 v${saved.report.revision} · ${saved.report.revision === saved.current_revision ? '最新版本' : '历史版本 · 只读'}` : '报告草稿 · 尚未保存'}</p><h1>{saved?.report.editor_revision.title || draft.title}</h1>
      {saved?.report.editor_revision.title && <details><summary>标题来源 · 用户编辑，待人工语义审阅</summary><p>原系统标题：{draft.title}</p></details>}
      <p className="report-frozen-scope">{new Set(scopes.map(s => s.company_id)).size === 1 ? `${scopes[0].name} · ${draft.side_labels.first}；${draft.side_labels.second}` : scopes.map((s, i) => `企业 ${i === 0 ? "A" : "B"}：${s.name} · ${s.year} 年`).join(" / ")}</p><p>全年 · 中国企业会计准则 · 合并口径 · 人民币</p>
      {saved && <p className="report-history-notice">历史报告读取 · 不会重新运行模型</p>}
      <p className="muted">{saved ? `保存于 ${new Date(saved.report.created_at).toLocaleString('zh-CN')}` : `生成于 ${new Date(draft.generated_at).toLocaleString('zh-CN')}`} · 人工语义审阅待完成</p>
      {draft.watermark && <p className="report-test-note">{draft.watermark}</p>}
      {!available && <p className="operating-alert">来源已失效，仅供历史审计。此版本暂不可编辑或导出。{saved?.current_eligibility.reason}</p>}
    </header>
    <section className="report-executive-summary">{heading(0)}<ul>{draft.executive_summary.map((s, i) => <li key={i}>{reportSummaryDisplay(s, draft)}</li>)}</ul><details><summary>研究问题与摘要来源</summary><p>研究问题：{draft.research_question}</p><p>系统摘要来自冻结的确定性财务分析；下方用户结论单独待审。</p></details>
      {saved && <div className="report-user-conclusions"><h3>用户结论 · 待人工语义审阅</h3>{saved.report.editor_revision.conclusions.length ? saved.report.editor_revision.conclusions.map((text, i) => <p key={i}>{text}</p>) : <p>此版本未添加用户结论。</p>}<p className="muted">用户新增断言尚未核准，经营归因未验证。</p></div>}
    </section>
    <section>{heading(1)}<p>金额与变化来自已保存的确定性分析。金额仅添加千分位，保留全部小数位；服务端未格式化字符串可在下方审计记录读取。</p><div className="report-table-scroll" role="region" aria-label="财务变化表，可横向滚动" tabIndex={0}><table><thead><tr><th scope="col">指标</th><th scope="col">差额 · 人民币元</th><th scope="col">变化比例</th></tr></thead><tbody>{draft.financial_analysis.map(r => <tr key={r.metric_key}><th scope="row">{METRICS[r.metric_key]}</th><td className="report-number"><data value={r.absolute_change}>{reportDecimalDisplay(r.absolute_change)}</data><small>{r.direction === 'B_minus_A' ? 'B−A 差额' : '本期−上期差额'}</small></td><td className="report-number">{r.percentage_change === null ? `未定义（${r.percentage_reason}）` : `${r.percentage_change}%`}<small>{reportRateLabel(draft)}</small></td></tr>)}</tbody></table></div>
      <details><summary>服务端精确值 · 未格式化字符串</summary>{draft.financial_analysis.map(r => <p key={r.metric_key}>{METRICS[r.metric_key]}：差额 {r.absolute_change} 人民币元；变化比例 {r.percentage_change === null ? `未定义（${r.percentage_reason}）` : `${r.percentage_change}%`}</p>)}</details>
      <details><summary>查看公式及计算限制</summary>{draft.financial_analysis.map(r => <section key={r.metric_key}><h3>{METRICS[r.metric_key]}</h3><p>{r.absolute_formula_id} · {r.absolute_expression}</p><p>{r.percentage_formula_id} · {r.percentage_expression}</p>{r.limitations.map((l, i) => <p key={i}>{l.message}</p>)}</section>)}</details>
    </section>
    <section>{heading(2)}<p>原值与原单位完整保留；规范金额为人民币元。每项事实包含来源和接受凭证。</p><div className="report-table-scroll" role="region" aria-label="已确认财务事实表，可横向滚动" tabIndex={0}><table><thead><tr><th scope="col">企业 / 财务年度</th><th scope="col">指标</th><th scope="col">原值 / 原单位</th><th scope="col">规范金额 · 元</th><th scope="col">来源</th></tr></thead><tbody>{draft.financial_facts.map(f => <tr key={f.fact_id} data-fact-id={f.fact_id}><td>{f.company_name}<br />{f.period} 年 · {draft.side_labels[f.side]}</td><th scope="row">{METRICS[f.metric_key]}</th><td className="report-number">{f.raw_value} {f.raw_unit}</td><td className="report-number"><data value={f.value_cny_yuan}>{reportDecimalDisplay(f.value_cny_yuan)}</data></td><td>{available ? <button disabled={!factLocation(f)} onClick={() => openFact(f)}>原 PDF · 物理 {f.physical_page} 页</button> : <span>来源已失效 · 物理 {f.physical_page} 页</span>}<details><summary>披露及接受凭证</summary><p>披露版本 {f.disclosure_version}</p><p>接受凭证 {f.receipt_id}</p><p>事实 {f.fact_id}</p><p>来源版本 {f.source_revision}</p></details></td></tr>)}</tbody></table></div></section>
    <section>{heading(3)}<p>以下为保存时的经营原文，引用只证明出处存在。阅读视图与完整原文分别保留。</p>{draft.operating_information.map(d => <article className="report-excerpt" key={String(d.citation.number)} id={`${prefix}-cite-${d.citation.number}`} tabIndex={-1} data-document-id={String(d.citation.document_id)} data-source-revision={String(d.citation.source_revision)} data-physical-page={String(d.citation.physical_page)}><ReportExcerpt description={d} companyName={draft.financial_facts.find(f => f.company_id === d.citation.company_id)?.company_name || `企业 ${String(d.citation.company_id)}`} available={available} openPdf={() => openOperating(d.citation)} /></article>)}</section>
    <section>{heading(4)}<p>模型原句 · 原生语义待审（pending）。经营因果未验证（false）。</p><p className="external-review-reading">下方人工审阅附注来自独立只读 sidecar，是针对冻结 Task 的外部证据。历史报告正文未被修改，也不是产品原生签核结果。用户编辑内容保持独立待审；历史 Markdown 导出仍为原版本正文。</p>{draft.model_interpretations.length ? draft.model_interpretations.map((item, i) => <article className="report-interpretation" key={i}><h3>待审解释 {i + 1}</h3><p data-model-statement={i + 1}>{item.text}</p><StatementReviewReading match={reviews} index={i} /><p>参考原文 {item.citations.map(c => <button key={c} onClick={() => { const target = document.getElementById(`${prefix}-cite-${c}`); target?.focus(); target?.scrollIntoView({ block: 'center' }); }}>原文 [{c}]</button>)}</p></article>) : <p>本次没有模型解释；经营归因仍未验证。</p>}</section>
    <section>{heading(5)}{draft.unresolved_questions.length ? <ul>{draft.unresolved_questions.map((q, i) => <li key={i}>{q}</li>)}</ul> : <p>本次未另列问题；原文充分性与解释语义仍待人工审阅。</p>}<details><summary>研究限制</summary><ul>{reportLimitations(draft.limitations, Boolean(saved)).map((l, i) => <li key={i}>{l}</li>)}</ul></details></section>
    <section>{heading(6)}<details className="report-appendix"><summary>完整证据附录与字段级核验</summary><p>来源、原文、财务证据、公式和冻结字段均保留。</p>{saved && <p>报告 {saved.report.report_id} · 父版本 {saved.report.parent_revision ?? '无'} · 当前最新 v{saved.current_revision} · 内容 SHA256 {saved.payload_sha256}</p>}<pre>{JSON.stringify({ task_id: draft.task_id, evidence: draft.evidence_appendix, verification: draft.field_verification, saved_revision: saved?.report }, null, 2)}</pre></details></section>
  </article>{pdfLocation && <ResearchPdfDialog key={`${pdfLocation.document_id}:${pdfLocation.source_revision}:${pdfLocation.physical_page}`} citation={pdfLocation} readingContext="报告" close={() => setPdfLocation(null)} invalid={() => { setPdfFailed(true); onSourceInvalid?.(); }} />}</div>;
}
