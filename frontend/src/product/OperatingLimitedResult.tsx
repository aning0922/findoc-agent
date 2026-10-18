import { reportPersistenceText } from "./reportState.ts";
import { ResearchPdfDialog, type PdfCitation } from "./ResearchPdfDialog.tsx";
import { useId, useState } from "react";
import type { LimitedContent } from "./operatingResearch.ts";
import type { OperatingReviewTarget } from './externalReview.ts';
import { StatementReviewReading } from './ExternalReviewReading.tsx';
import { useOperatingReviews } from './useExternalReviews.ts';
export function OperatingLimitedResult({
  content,
  reportPreview = false,
  reportSaved = false,
  companyNames,
  compact = false,
  reviewTarget = null,
}: {
  compact?: boolean;
  reviewTarget?: OperatingReviewTarget | null;
  content: LimitedContent;
  reportPreview?: boolean;
  reportSaved?: boolean;
  companyNames?: Record<string, string>;
}) {
  const prefix = useId();
  const [pdf, setPdf] = useState<PdfCitation | null>(null), [pdfFailed, setPdfFailed] = useState(false);
  const companyLabel = (c: Record<string, unknown>) => companyNames?.[String(c.company_id)] || `企业 ${String(c.company_id)}`;
  const pdfActions = (c: Record<string, unknown>) => <div className="report-citation-actions">
    <button disabled={pdfFailed} onClick={() => setPdf({ number: Number(c.number), document_id: String(c.document_id), company_id: String(c.company_id), report_year: Number(c.report_year), source_revision: String(c.source_revision), physical_page: Number(c.physical_page), source_file: String(c.source_file), parser_version: typeof c.parser_version === 'string' ? c.parser_version : undefined })}>查看原 PDF [{String(c.number)}]</button>
    {!pdfFailed && <a target="_blank" rel="noreferrer" href={`/api/documents/${encodeURIComponent(String(c.document_id))}/file?${new URLSearchParams({ company_id: String(c.company_id), source_revision: String(c.source_revision) })}#page=${c.physical_page}`}>新标签打开原 PDF ↗</a>}
    {pdfFailed && <p role="status">原 PDF 暂不可核验，请只读刷新本项研究后再查看。</p>}
  </div>;
  const pdfDialog = pdf && <ResearchPdfDialog key={`${pdf.document_id}:${pdf.source_revision}:${pdf.physical_page}`} citation={pdf} readingContext="经营原文" close={() => setPdf(null)} invalid={() => setPdfFailed(true)} />;
  const reviews = useOperatingReviews(reviewTarget && { ...reviewTarget, task_id: content.task_id,
    descriptions: content.operating_descriptions, model_interpretations: content.model_interpretations,
    test_mode: content.test_mode });
  const [opened, setOpened] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState(0);
  function showCitation(number: string, interpretation: number) {
    setOpened(number); setReturnTo(interpretation);
    requestAnimationFrame(() => document.getElementById(`${prefix}-cite-${number}`)?.focus());
  }
  if (compact)
    return (
      <section className="operating-card" aria-label="有限经营研究结果">
        <div className="operating-heading">
          <h2>业务原文与待审线索</h2>
          <strong className="review-pending">待人工语义复核</strong>
        </div>
        {content.test_mode && (
          <p className="operating-alert">
            simulated_test · 自动化模拟财务接受 · 无真人确认 / 非生产结果
          </p>
        )}
        <p>本次整理业务原文与待审线索，未执行逐指标经营变化原因检索。模型原句与外部人工意见分别保留；原生语义待审（pending），经营因果未验证（false）。</p>
        {content.model_interpretations.length ? (
          content.model_interpretations.map((i, n) => (
            <article key={n} className="operating-result" id={`${prefix}-interpretation-${n}`} tabIndex={-1}>
              <strong>模型原句 {n + 1}</strong>
              <p data-model-statement={n + 1}>{i.text}</p>
              <StatementReviewReading match={reviews} index={n} />
              <p className="muted">
                参考原文 {i.citations.map(c => <button key={c} aria-expanded={opened === String(c)} onClick={() => showCitation(String(c), n)}>原文 [{c}]</button>)} ·
                待人工语义复核
              </p>
            </article>
          ))
        ) : (
          <p>当前没有可发布的经营解释；请审阅原文和证据限制。</p>
        )}
        <details open={opened !== null || undefined} onToggle={e => { if (!e.currentTarget.open) setOpened(null); }}>
          <summary>
            经营原文与完整引用 · {content.operating_descriptions.length} 项
          </summary>
          {content.operating_descriptions.map((d) => (
            <article
              key={String(d.citation.number)}
              className="operating-result"
              id={`${prefix}-cite-${d.citation.number}`} tabIndex={-1}
            >
              <h3>
                原文 [{String(d.citation.number)}] · {companyLabel(d.citation)} ·{" "}
                {String(d.citation.report_year)} 年报 · 物理第{" "}
                {String(d.citation.physical_page)} 页
              </h3>
              <p className="report-source-file">文件：{String(d.citation.source_file)}</p>
              {pdfActions(d.citation)}
              <p>{d.text}</p>
              <button onClick={() => { document.getElementById(`${prefix}-interpretation-${returnTo}`)?.focus(); setOpened(null); }}>返回待审解释</button>
              <details>
                <summary>高级审计：引用身份</summary>
                <pre>{JSON.stringify(d.citation, null, 2)}</pre>
              </details>
            </article>
          ))}
        </details>
        <details>
          <summary>未解决问题与研究限制</summary>
          <ul>
            {[...content.unresolved_questions, ...content.limitations].map(
              (q, n) => (
                <li key={n}>{q}</li>
              ),
            )}
          </ul>
          <p>human_review_status=pending · 经营归因尚未验证</p>
        </details>
      {pdfDialog}</section>
    );
  return (
    <section className="operating-card" aria-label="有限经营研究结果">
      <p className="eyebrow">持久化有限研究结果 · v2</p>
      <h2>业务原文与待审线索</h2>
      {content.test_mode && (
        <p className="operating-alert">
          simulated_test · 自动化模拟财务接受 · 无真人确认 / 非生产结果
        </p>
      )}
      <p className="operating-notice">
        财务数值见已完成的确定性分析。本次整理业务原文与待审线索，未执行逐指标经营变化原因检索；解释与推断单独待审。
      </p>
      {content.operating_descriptions.map((d) => (
        <article key={String(d.citation.number)} className="operating-result">
          <h3>
            经营原文 [{String(d.citation.number)}] ·{" "}
            {companyLabel(d.citation)} · {String(d.citation.report_year)} 年报 · 物理第 {String(d.citation.physical_page)} 页
          </h3>
          <p className="report-source-file">文件：{String(d.citation.source_file)}</p>
          {pdfActions(d.citation)}
          <p>
            {d.text.slice(0, 220)}
            {d.text.length > 220 ? "…" : ""}
          </p>
          <details>
            <summary>展开保存的完整原文与来源</summary>
            <pre>{d.text}</pre>
            <p>原 PDF：{String(d.citation.source_file)}</p>
            <p>来源版本 {String(d.citation.source_revision)}</p>
          </details>
        </article>
      ))}
      <h3>
        {reportPreview
          ? "待人工审阅的分析判断 · 待人工语义复核"
          : "模型解释 / 推断 · 待人工语义复核"}
      </h3>
      <p className="operating-notice">
        引用编号有效只证明出处存在，不能证明经营因果。归因验证状态为 false。
      </p>
      {content.model_interpretations.length ? (
        content.model_interpretations.map((i, n) => (
          <article key={n} className="operating-result">
            <strong>模型原句 {n + 1}</strong>
            <p data-model-statement={n + 1}>{i.text}</p>
            <StatementReviewReading match={reviews} index={n} />
            <p className="muted">
              参考原文 {i.citations.map((c) => `[${c}]`).join("、")} ·
              pending_semantic_review
            </p>
          </article>
        ))
      ) : (
        <p>模型未提出解释；经营归因仍未验证。</p>
      )}
      <h3>未解决问题</h3>
      {content.unresolved_questions.length ? (
        <ul>
          {content.unresolved_questions.map((q, n) => (
            <li key={n}>{q}</li>
          ))}
        </ul>
      ) : (
        <p>本次未另列问题；原文充分性与解释语义仍待人工审阅。</p>
      )}
      <h3>研究限制</h3>
      <ul>
        {content.limitations.map((l, n) => (
          <li key={n}>{l}</li>
        ))}
      </ul>
      <p className="muted">
        {reportPreview
          ? reportPersistenceText(reportSaved)
          : "研究执行已完成，human_review_status=pending。可前往研究报告生成未保存的草稿。"}
      </p>
    {pdfDialog}</section>
  );
}
