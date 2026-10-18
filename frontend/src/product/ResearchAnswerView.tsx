import type { Company } from './api.ts';
import type { ResearchRun } from './researchHistory.ts';
import type { ResearchCitation } from './researchAnswer.ts';
import { researchPdfUrl } from './researchAnswer.ts';
import { annualTables, citationGroups } from './qaReading.ts';
import { verifiedTableVersion } from './excerptBlocks.ts';
import { VerifiedExcerpt, ExcerptTable } from './VerifiedExcerpt.tsx';
import { StatusNotice } from './StatusNotice.tsx';
import { useAnswerFocus } from './TrustedAnswerFocus.tsx';
import styles from './ResearchQA.module.css';

export function ResearchAnswerView({ run, companies, unavailable, openPdf, openTab }: {
  run: ResearchRun; companies: Company[]; unavailable: string[];
  openPdf: (c: ResearchCitation) => void; openTab: (c: ResearchCitation) => void;
}) {
  const citations = run.result!.citations;
  const verification = useAnswerFocus(run);
  const projection = verification.focus;
  const focusedCitation = citations.find(c => c.number === projection?.citation_number);
  const currentCitation = (c: ResearchCitation) => verification.verified && !unavailable.includes(`${c.document_id}:${c.source_revision}`)
    && run.source_states.some(s => s.document_id === c.document_id && s.source_revision === c.source_revision && s.status === 'current_at_read');
  const focus = projection && focusedCitation && currentCitation(focusedCitation) ? projection : null;
  const historical = verification.invalidated || run.source_states.some(s => s.status === 'expired');
  return <section aria-label="有证据的回答" className={styles.answer}>
    {focus && focusedCitation ? <section className={styles.focusCard} aria-label="本题可信焦点"
      data-focus-version="trusted-answer-focus-v1" data-focus-run={run.run_id} data-focus-table={focus.table_id}
      data-focus-row={focus.row_index} data-focus-column={focus.column_index}>
      <div className={styles.focusHeading}><div><p className={styles.meta}>本题关注 · {focus.company_name} · {focus.financial_year} 财务年度</p>
        <h3>{focus.row_label}</h3><p className={styles.focusValue}><strong>{focus.raw_value}</strong> <span>{focus.raw_unit}</span></p></div>
        <button onClick={() => openPdf(focusedCitation)}>查看原 PDF [{focus.citation_number}]</button></div>
      <p className={styles.meta}>{focus.report_year} 年报《{focus.source_file}》 · 物理第 {focus.physical_page} 页 · 引用 [{focus.citation_number}]</p>
      <details className={styles.focusRow}><summary>核对本题原始表格行与年度列</summary>
        <div className={styles.excerpt}><ExcerptTable block={{ kind: 'table', header: focus.original_header, rows: [focus.original_row] }} /></div>
        <p className={styles.hint}>目标年度列：{focus.year_header}。保留同一行的全部年度、原值和原单位。</p></details>
      <p className={styles.hint}>来自已核验来源单元格的只读摘录，人工语义审读待完成。未写入财务事实。</p>
    </section> : <StatusNotice state="unknown" title="当前无法可靠定位本题数值">请继续阅读下方完整表格与已保存原文；本题焦点尚不可核验。</StatusNotice>}
    <h3>完整年报原文</h3>
    <StatusNotice state={historical ? 'invalidated' : verification.verified ? 'completed' : 'unknown'} title={historical ? '已保存的历史原文' : verification.verified ? '已找到可核验的原文' : '已保存的历史原文 · 当前来源暂不可核验'}>引用内容在保存时已核验，人工语义审读待完成。</StatusNotice>
    <p className={styles.hint}>按来源阅读完整年度表格，保留原值、原单位与原列。口径、说明及周边文字可在完整已保存原文中核对。此处不新增计算或解释。</p>
    {citationGroups(citations).map(group => <section key={`${group[0].document_id}:${group[0].source_revision}`} className={styles.sourceExcerpt}>
      <h3>{companies.find(c => c.company_id === group[0].company_id)?.name || '企业名称暂不可读取'} · {group[0].report_year} 年报</h3>
      <p className={styles.meta}>{group[0].source_file}</p>
      {group.map(c => {
        const current = currentCitation(c);
        const tables = annualTables(c);
        return <article key={c.number} id={`qa-citation-${c.number}`} tabIndex={-1} className={styles.citation}
          aria-label={`${c.report_year} 年报 ${c.source_file} 原文 [${c.number}]`} data-citation-number={c.number} data-document-id={c.document_id} data-source-revision={c.source_revision} data-physical-page={c.physical_page}>
          {tables.length > 0 ? <details className={styles.fullTable} open={focus ? undefined : true}>
            <summary>完整年度表格 [{c.number}] · 保留全部行列</summary><div className={styles.excerpt}>{tables.map((block, i) => block.kind === 'table' && <ExcerptTable key={i} block={block} />)}</div></details>
            : <div className={styles.excerpt}>
              {!verifiedTableVersion(c.parser_version) && c.text.includes('| ---') && <StatusNotice state="invalidated" title="表格列关系暂未通过核验">历史解析版本仅供原文审计，不能当作已核验的年度金额表。请明确重建来源后重新研究。</StatusNotice>}
              <VerifiedExcerpt text={c.text} allowTables={verifiedTableVersion(c.parser_version)} />
            </div>}
          <footer className={styles.citationActions}>
            <span>[{c.number}] · {c.report_year} 年报 · 物理第 {c.physical_page} 页</span>
            {current ? <><button onClick={() => openPdf(c)}>查看原 PDF [{c.number}]</button>
              <a href={researchPdfUrl(c)} target="_blank" rel="noreferrer" onClick={e => { e.preventDefault(); openTab(c); }}>打开原 PDF [{c.number}] · 新标签</a></>
              : <span className={styles.expired}>来源已过期或不可用，不可打开原 PDF</span>}
          </footer>
          {tables.length > 0 && <details className={styles.fullText}>
            <summary>完整已保存原文 [{c.number}] · 含口径与上下文</summary><pre data-saved-excerpt={c.number}>{c.text}</pre>
          </details>}
        </article>;
      })}
    </section>)}
  </section>;
}
