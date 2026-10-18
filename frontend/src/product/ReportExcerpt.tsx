import type { Draft } from './reportDraft.ts';
import { reportExcerptReading } from './reportReading.ts';
import { ExcerptTable, VerifiedExcerpt } from './VerifiedExcerpt.tsx';
export function ReportExcerpt({ description, companyName, available, openPdf }: {
  description: Draft['operating_information'][number]; companyName: string; available: boolean; openPdf: () => void;
}) {
  const { text, citation } = description;
  const reading = reportExcerptReading(text, typeof citation.parser_version === 'string' ? citation.parser_version : undefined);
  return <>
    <h3>原文 [{String(citation.number)}] · {companyName} · {String(citation.report_year)} 年报 · 物理 {String(citation.physical_page)} 页</h3>
    <p className="report-source-file">{String(citation.source_file)} · {citation.verification === 'exact_original_with_context' ? '保存时原文匹配已核验' : '保存时的原文引用'} · 人工语义待审</p>
    {reading.tables.length > 0 ? <div className="report-original-navigation">
      <p className="muted">表格导航视图 · 展示本条引用中的完整年度原表。经营正文、口径、周边文字及重复内容均保留在下方完整原文中，请展开核对。此视图不新增摘要或解释。</p>
      <p className="muted">原表保留全部年度列；窄屏可在表格内横向滚动。</p>
      {reading.tables.map((block, i) => <ExcerptTable block={block} key={i} />)}
      {reading.duplicates > 0 && <p className="muted">完全相同的原表在导航中只显示一次；完整原文保留全部重复。</p>}
    </div> : <details className="report-complete-excerpt">
      <summary>{reading.literal ? '完整原文 · 无法可靠结构化，按原样阅读' : '完整经营原文 · 按保存时的段落与原表阅读'}</summary>
      {reading.reason && <p>{reading.reason}</p>}
      <VerifiedExcerpt text={text} allowTables={!reading.literal} />
    </details>}
    <div className="report-citation-actions">
      {available ? <button onClick={openPdf}>打开经营原文 PDF</button> : <p>此来源已失效，仅保留原文审计快照。</p>}
    </div>
    <details className="report-saved-excerpt">
      <summary>完整已保存原文 [{String(citation.number)}] · 含口径、周边文字与重复内容</summary>
      <p className="muted">逐字保留保存时的完整原文；包含原始表格标记。阅读结构不改写报告快照或导出内容。</p>
      <pre data-saved-excerpt={String(citation.number)}>{text}</pre>
    </details>
    <details><summary>原文来源身份</summary><pre>{JSON.stringify(citation, null, 2)}</pre></details>
  </>;
}
