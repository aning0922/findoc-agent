import { useEffect, useRef, useState } from 'react';
import type { Company, Fact } from './api.ts';
import { queryFacts } from './operatingResearch.ts';
import { annualMetadata, listDocuments, readUploaded, uploadReport, UploadError } from './documentLibraryApi.ts';
import type { DocumentRow, Metadata } from './documentLibraryApi.ts';
import styles from './ResearchJourney.module.css';

function savedUpload(company: string): { id: string | null; metadata: Metadata } | null {
  try { const v = JSON.parse(sessionStorage.getItem(`findoc:upload-intent:${company}`) || "null");
    if (v && v.metadata?.company_id === company && (v.id === null || typeof v.id === "string" && /^[a-zA-Z0-9-]{1,200}$/.test(v.id))) return { id: v.id, metadata: annualMetadata(company, String(v.metadata.report_year)) };
  } catch { /* recovery hint only */ }
  return null;
}
function rememberUpload(company: string, value: { id: string | null; metadata: Metadata } | null) {
  try { if (value) sessionStorage.setItem(`findoc:upload-intent:${company}`, JSON.stringify(value)); else sessionStorage.removeItem(`findoc:upload-intent:${company}`); } catch { /* server directory remains accessible */ }
}
const labels: Record<string, string> = { ready: 'PDF 处理就绪', queued: '等待处理', parsing: '正在解析 PDF', indexing: '正在建立资料索引', processing: '正在处理', uploaded: '已上传 · 等待处理', failed: '处理失败' };
export function DocumentLibrary({ company, companies, onReady, returnHref, focusedPeriod, onContinue }: { company: string; companies: Company[]; onReady?: () => void; returnHref?: string; focusedPeriod?: number; onContinue?: () => void }) {
  const [savedFacts, setSavedFacts] = useState<Fact[]>([]), [factsMessage, setFactsMessage] = useState('财务事实正在核验');
  const [restored] = useState(() => savedUpload(company));
  const [rows, setRows] = useState<DocumentRow[]>([]), [error, setError] = useState(''), [reload, setReload] = useState(0);
  const [sourceUrl, setSourceUrl] = useState('');
  const [show, setShow] = useState(focusedPeriod !== undefined), [year, setYear] = useState(''), [file, setFile] = useState<File | null>(null), [checked, setChecked] = useState(false);
  const [message, setMessage] = useState(restored ? '发现上次上传待查证，正在只读查询绑定。没有再次上传。' : ''), [phase, setPhase] = useState(restored ? restored.id ? 'reading' : 'unknown' : 'idle');
  const [known, setKnown] = useState<{ id: string; metadata: Metadata } | null>(restored?.id ? { id: restored.id, metadata: restored.metadata } : null);
  const owner = useRef(0), active = useRef<AbortController | null>(null), locked = useRef(false), trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => () => { ++owner.current; active.current?.abort(); }, []);
  useEffect(() => {
    const c = new AbortController(); let timer: number | undefined;
    async function read() {
      try {
        const v = await listDocuments(c.signal);
        if (c.signal.aborted) return;
        setRows(v); setError('');
        if (company) {
          try {
            const facts = await queryFacts(company, c.signal);
            if (!c.signal.aborted) { setSavedFacts(facts.facts.filter(f => f.current_valid && f.integrity === 'verified' && f.confirmation_status === 'confirmed')); setFactsMessage(''); }
          } catch { if (!c.signal.aborted) { setSavedFacts([]); setFactsMessage('财务事实暂不可核验'); } }
        }
        // Reopened pages have no upload-intent identity. Schedule the next read
        // only after this one completes; never replay an upload from an effect.
        if (v.some(r => (r.metadata?.company_id === company || !r.metadata)
          && ['queued', 'parsing', 'indexing'].includes(r.status))) timer = window.setTimeout(() => void read(), 3000);
      } catch (e) { if (!c.signal.aborted) setError((e as Error).message); }
    }
    void read();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [reload, company]);
  function close() { setShow(false); trigger.current?.focus(); }
  async function submit() {
    if (locked.current || !file || !checked || phase === 'unknown') return;
    let meta: Metadata;
    try { meta = annualMetadata(company, year); } catch (e) { setMessage((e as Error).message); return; }
    locked.current = true; const own = ++owner.current, c = new AbortController(); active.current = c;
    rememberUpload(company, { id: null, metadata: meta });
    setPhase('sending'); setMessage('正在上传并申请可信绑定…');
    try {
      const receipt = await uploadReport(file, meta, c.signal, sourceUrl);
      if (own !== owner.current || c.signal.aborted) return;
      rememberUpload(company, { id: receipt.document_id, metadata: meta });
      setKnown({ id: receipt.document_id, metadata: meta }); setPhase('reading');
      setMessage(receipt.duplicate ? '服务端识别为重复文件，正在读回原资料与绑定。' : '上传已受理，正在读回资料与绑定。');
      setReload(n => n + 1);
    } catch (e) {
      if (own === owner.current && !c.signal.aborted) { if (!(e instanceof UploadError && e.unknown)) rememberUpload(company, null); setPhase(e instanceof UploadError && e.unknown ? 'unknown' : 'failed'); setMessage((e as Error).message); }
    } finally { if (own === owner.current) { locked.current = false; active.current = null; } }
  }
  const polling = !!known && !["ready", "read_failed"].includes(phase);
  // Poll known identity using GET only. Never retry upload from an effect.
  useEffect(() => {
    if (!known || !polling) return;
    const c = new AbortController(); let reading = false;
    async function read() {
      if (reading) return; reading = true;
      try {
        const v = await readUploaded(known!.id, known!.metadata, c.signal);
        if (c.signal.aborted) return;
        setMessage(v.source ? `上传与绑定已读回，财报处理就绪。${focusedPeriod ? '请返回财报选择，明确选择这份年报，再确认来源。' : '下一步核对财务事实。'}文件就绪不代表数据已接受或保存。` : `绑定已读回 · ${labels[v.status] || '等待处理状态读回'}。`);
        if (v.source) { rememberUpload(company, null); setPhase('ready'); setReload(n => n + 1); onReady?.(); }
      } catch (e) { if (!c.signal.aborted) { setPhase('read_failed'); setMessage(`读回未完成：${(e as Error).message} 请刷新查询。`); } }
      finally { reading = false; }
    }
    void read(); const timer = window.setInterval(() => void read(), 3000);
    return () => { c.abort(); clearInterval(timer); };
  }, [known, reload, onReady, polling, company, focusedPeriod]);
  const visible = rows.filter(r => focusedPeriod !== undefined ? r.metadata?.company_id === company && [focusedPeriod, focusedPeriod + 1].includes(r.metadata.report_year) : r.metadata?.company_id === company || !r.metadata);
  return <section className={styles.upload} aria-label="准备财报资料">
    <div className={styles.row}><div><h2>{focusedPeriod ? `上传 ${focusedPeriod} 年数据来源` : "准备财报资料"}</h2><p>{focusedPeriod ? `可使用 ${focusedPeriod} 或 ${focusedPeriod + 1} 年报。请按 PDF 实际报告年度填写；一份文件无需上传两次。` : "上传 PDF，核对企业与完整年度，再由服务端绑定和处理。"}</p></div><button ref={trigger} onClick={() => { setShow(true); }} disabled={phase === 'sending'}>上传并绑定年报</button></div>
    {returnHref && <a href={returnHref}>返回原研究 · 只读检查准备状态 →</a>}
    {show && <form onSubmit={e => { e.preventDefault(); void submit(); }} aria-label="上传年报表单">
      <div className={styles.formGrid}><label>绑定企业<input readOnly value={companies.find(c => c.company_id === company)?.name || '请先选择企业'} /></label><label>报告年度<input aria-label="报告年度" inputMode="numeric" maxLength={4} value={year} disabled={phase === 'sending' || !!known} onChange={e => { setYear(e.target.value); setChecked(false); }} /></label>
      <label>PDF 文件<input aria-label="PDF 文件" type="file" accept="application/pdf,.pdf" disabled={phase === 'sending' || !!known} onChange={e => { setFile(e.target.files?.[0] || null); setChecked(false); }} /></label><label>财务期间<input readOnly value={year ? `${year.padStart(4, '0')}-01-01 至 ${year.padStart(4, '0')}-12-31 · 中国企业会计准则` : '填写年度后显示完整期间'} /></label></div>
      <details><summary>来源网址（可选）</summary><label>用户声明的原财报网址<input aria-label="来源网址" type="url" maxLength={2000} value={sourceUrl} disabled={phase === "sending" || !!known} onChange={e => setSourceUrl(e.target.value)} /></label><p>网址仅作为你的来源声明，不代表服务端已验证官方网站。重复上传时需保持原来源声明一致。</p></details>
      <label className={styles.row}><input type="checkbox" aria-label="核对上传绑定" checked={checked} disabled={phase === 'sending' || !!known} onChange={e => setChecked(e.target.checked)} />我已核对 PDF 的企业、报告年度、全年期间与会计准则。</label>
      <div className={styles.row}><button type="button" disabled={phase === 'sending'} onClick={close}>{known ? '收起上传信息' : '取消上传'}</button><button type="submit" disabled={!company || !file || !checked || phase === 'sending' || !!known || phase === 'unknown'}>提交 PDF 并绑定</button></div>
    </form>}
    {message && <p role={['unknown', 'failed', 'read_failed'].includes(phase) ? 'alert' : 'status'}>{message}</p>}
    {phase === 'unknown' && <p>未取得可核验的资料身份。刷新目录后，手动选择候选资料核对；文件名不能证明是同一次上传。</p>}
    {error && <p role="alert">{error}</p>}
    <button onClick={() => { if (known && phase === "read_failed") setPhase("reading"); setReload(n => n + 1); }}>刷新资料与绑定（只读）</button>
    {known && phase === 'read_failed' && <button onClick={() => { rememberUpload(company, null); setKnown(null); setPhase('idle'); setFile(null); setChecked(false); setMessage('已结束当前读回。原资料可能已上传绑定，重新提交将是新的显式动作，请先核对目录。'); }}>结束当前读回，重新选择资料</button>}
    {phase === 'ready' && onContinue && <button className="operating-primary" onClick={onContinue}>继续选择财报</button>}
    {phase === 'ready' && !onContinue && <button onClick={() => { setKnown(null); setFile(null); setYear(''); setChecked(false); setPhase('idle'); setMessage(''); }}>准备另一份财报</button>}
    {phase === 'sending' && <button onClick={() => { ++owner.current; active.current?.abort(); active.current = null; locked.current = false; setPhase('unknown'); setMessage('已停止本页等待，上传结果未知。服务端可能仍在处理，请只读查证。'); }}>停止本页等待，转为只读查证</button>}
    {phase === 'unknown' && <button onClick={() => { rememberUpload(company, null); setPhase('idle'); setFile(null); setChecked(false); setMessage('已结束只读查证。重新选择文件后可显式提交，可能命中重复文件或遗留未绑定资料。'); }}>结束查证，重新选择文件</button>}
    {!error && !visible.length && <p>当前企业还没有年报。可在本页上传，完成后继续研究。</p>}
    {visible.map(r => <article className={styles.documentRow} key={r.document_id}><h3>{r.source_file}</h3><p>{r.metadata ? `${r.metadata.report_year} 年报 · ${r.metadata.period_start} 至 ${r.metadata.period_end}` : '尚未绑定企业与期间 · 不能用于研究'}</p><p>{labels[r.status] || '处理状态待查询'}</p>{r.status === 'ready' && <p>{factsMessage || (savedFacts.filter(f => f.document_id === r.document_id).length ? `已保存财务事实 ${savedFacts.filter(f => f.document_id === r.document_id).length} 项 · 来源已复验` : '财务事实待核对')}</p>}{r.metadata && r.status === 'ready' && <a href={`/evidence?${new URLSearchParams({ company, document: r.document_id })}`}>查看财务记录或开始新核对 →</a>}{r.status === "failed" && <RetryDocument row={r} refresh={() => setReload(n => n + 1)} />}
    {!r.metadata && <BindLegacy row={r} company={company} refresh={() => setReload(n => n + 1)} />}</article>)}
  </section>;
}
function BindLegacy({ row, company, refresh }: { row: DocumentRow; company: string; refresh: () => void }) {
  const [year, setYear] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  const lock = useRef(false);
  return <details><summary>核对并补绑定未绑定资料</summary><p>请打开原文件核对企业和年度。仅可绑定当前尚未绑定的资料，绑定后重新读回。</p><input aria-label={`补绑定年度 ${row.source_file}`} value={year} onChange={e => setYear(e.target.value)} /><button disabled={busy || !company} onClick={async () => {
    if (lock.current) return;
    try { const meta = annualMetadata(company, year); lock.current = true; setBusy(true);
      const r = await fetch(`/api/documents/${encodeURIComponent(row.document_id)}/metadata`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meta) });
      if (!r.ok) throw new Error(`补绑定未确认（${r.status}），请刷新目录核对，不能覆盖已有绑定。`);
      setMessage('绑定请求已返回，请刷新核对绑定。'); refresh();
    } catch (e) { setMessage((e as Error).message); } finally { lock.current = false; setBusy(false); }
  }}>我已核对，明确补绑定</button>{message && <p role="status">{message}</p>}</details>;
}
function RetryDocument({ row, refresh }: { row: DocumentRow; refresh: () => void }) {
  const [busy, setBusy] = useState(false), [unknown, setUnknown] = useState(false), [message, setMessage] = useState('');
  const lock = useRef(false);
  return <div><p>失败资料需要你明确重试；重试后应重新核对来源和财务事实。</p><button disabled={busy || unknown} onClick={async () => {
    if (lock.current) return; lock.current = true; setBusy(true);
    try {
      const r = await fetch(`/api/documents/${encodeURIComponent(row.document_id)}/retry`, { method: 'POST' });
      if (r.status >= 500) { setUnknown(true); throw new Error('重试处理结果未知，请只读刷新资料状态。'); }
      if (r.status !== 202) throw new Error('资料状态已变化或重试未受理，请只读刷新后核对。');
      setMessage('重试已受理，请只读刷新处理状态。'); refresh();
    } catch (e) {
      if (e instanceof TypeError) { setUnknown(true); setMessage('连接中断，重试处理结果未知，请只读刷新查证。'); }
      else setMessage((e as Error).message);
    } finally { lock.current = false; setBusy(false); }
  }}>明确重试处理</button>{message && <p role="status">{message}</p>}</div>;
}
