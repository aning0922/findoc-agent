import { useEffect, useRef, useState } from 'react';
import { checkSource, forgetPdf, getJson, loadPdf } from '../evidence/api.ts';
import { validateSource, type Source } from '../evidence/contracts.ts';
import { PdfPage } from '../evidence/PdfPage.tsx';
import { QADialog } from './QADialog.tsx';
import { StatusNotice } from './StatusNotice.tsx';
import { DiagnosticDetails } from './DiagnosticDetails.tsx';
import type { ResearchCitation } from './researchAnswer.ts';
import styles from './ResearchQA.module.css';
import '../evidence/evidence.css';

export type PdfCitation = Pick<ResearchCitation, 'document_id' | 'company_id' | 'report_year' | 'source_revision' | 'physical_page' | 'source_file' | 'parser_version'> & { number?: number };
export function ResearchPdfDialog({ citation, close, invalid, readingContext = '回答' }: {
  citation: PdfCitation; close: () => void; invalid: () => void; readingContext?: '回答' | '报告' | '经营原文';
}) {
  const [data, setData] = useState<{ source: Source; bytes: Uint8Array } | null>(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(citation.physical_page);
  const [zoom, setZoom] = useState<number | 'fit'>('fit');
  const [locationToken, setLocationToken] = useState(0);
  const invalidRef = useRef(invalid); invalidRef.current = invalid;
  const sourceRef = useRef<Source | null>(null);
  function fail(message: string) {
    if (sourceRef.current) forgetPdf(sourceRef.current);
    setData(null); setError(message); invalidRef.current();
  }
  useEffect(() => {
    const controller = new AbortController(); let checking = false;
    const validate = async () => {
      if (controller.signal.aborted || !sourceRef.current || checking || document.visibilityState === 'hidden') return;
      checking = true;
      try { await checkSource(sourceRef.current, controller.signal); }
      catch (e) { if (!controller.signal.aborted) fail((e as Error).message); }
      finally { checking = false; }
    };
    void (async () => {
      const q = new URLSearchParams({ company_id: citation.company_id, source_revision: citation.source_revision });
      const source = validateSource(await getJson<Source>(`/documents/${encodeURIComponent(citation.document_id)}/source?${q}`, controller.signal), citation.company_id, citation.document_id, citation.source_revision);
      if (source.report_year !== citation.report_year || citation.physical_page > source.physical_pages
        || (citation.parser_version && source.parser_version !== citation.parser_version)) throw new Error('引用与 PDF 来源或物理页不匹配。');
      sourceRef.current = source;
      const bytes = await loadPdf(source, controller.signal);
      await checkSource(source, controller.signal, citation.physical_page);
      if (!controller.signal.aborted) setData({ source, bytes });
    })().catch(e => { if (!controller.signal.aborted) fail((e as Error).message); });
    const onFocus = () => { void validate(); };
    window.addEventListener('focus', onFocus); document.addEventListener('visibilitychange', onFocus);
    const timer = window.setInterval(onFocus, 30000);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener('focus', onFocus); document.removeEventListener('visibilitychange', onFocus); };
    // Mounted by full citation identity. Display callbacks never grant source eligibility.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [citation]);
  return <QADialog title={citation.number === undefined ? '原 PDF · 财务事实' : `原 PDF · 引用 [${citation.number}]`} close={close} className={styles.pdfDialog}>
    <p className={styles.meta}>{citation.report_year} 年报《{citation.source_file}》 · 引用物理第 {citation.physical_page} 页</p>
    <button onClick={close}>返回{readingContext}阅读位置</button>
    {error ? <><StatusNotice state="invalidated" title="原 PDF 暂不可查看">来源可能已变化或文件无法核验。已撤下原 PDF，请只读刷新{readingContext}记录。</StatusNotice><DiagnosticDetails label="高级诊断：PDF 核验" fields={{ error }} /></>
      : !data ? <StatusNotice state="waiting" title="正在核验原 PDF">正在核验来源版本、文件字节和物理页。</StatusNotice>
      : <>
        <div className={styles.pdfTools} aria-label="PDF 阅读工具">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button><button disabled={page >= data.source.physical_pages} onClick={() => setPage(p => p + 1)}>下一页</button>
          <button onClick={() => { setPage(citation.physical_page); setLocationToken(n => n + 1); }}>返回引用页</button>
          <label>缩放<select aria-label="PDF 缩放" value={zoom} onChange={e => setZoom(e.target.value === 'fit' ? 'fit' : Number(e.target.value))}><option value="fit">适合宽度</option><option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option></select></label>
        </div>
        <p className={styles.hint}>真实原 PDF，按物理页定位。当前引用未提供可核验的金额坐标。</p>
        <PdfPage bytes={data.bytes} source={data.source} page={page} zoom={zoom} evidence={null} reference={null} locationToken={locationToken} onFatal={fail} onPage={setPage} onZoom={setZoom} />
      </>}
  </QADialog>;
}
