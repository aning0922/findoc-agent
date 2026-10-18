import { StatusNotice } from './StatusNotice.tsx';
import { canEditReport } from "./reportState.ts";
import { reportPath } from './productRoutes.ts';
import { ReportContextHeader } from './TaskContextHeader.tsx';
import { useEffect, useRef, useState } from "react";
import { json } from "./api.ts";
import { ReportPaper } from "./ReportPaper.tsx";
import { readExactReport, validateReport } from "./reportPersistence.ts";
import { reportContext } from "./researchContext.ts";
import type { HistoryItem, ReportDetail } from "./reportPersistence.ts";
import { ReportExport } from "./ReportExport.tsx";
import { storedOperation, rememberOperation as remember } from './reportOperation.ts';
import { ReportSaveControls } from './ReportEditor.tsx';
export { ReportSaveControls } from './ReportEditor.tsx';
import { useReportNavigation } from './reportNavigationContext.ts';
import { ReportVersionComparison } from './ReportVersionComparison.tsx';

export function ReportHistory({ simulated, onOpen, draftActive = false }: { simulated: boolean; onOpen?: () => void; draftActive?: boolean }) {
  const [items, setItems] = useState<HistoryItem[]>([]), [before, setBefore] = useState<number | null>(null), [detail, setDetail] = useState<ReportDetail | null>(null), [error, setError] = useState("");
  const [listError, setListError] = useState('');
  const [revision, setRevision] = useState(1), [operation, setOperation] = useState(storedOperation);
  const { requestLeave } = useReportNavigation();
  const [comparing, setComparing] = useState(false), [sourceBlocked, setSourceBlocked] = useState(false);
  const sequence = useRef(0), listSequence = useRef(0), alive = useRef(true);
  const [summaries, setSummaries] = useState<Record<string, ReportDetail | null>>({}), [editing, setEditing] = useState(false), [loading, setLoading] = useState(true);
  useEffect(() => { if (draftActive) { sequence.current++; setDetail(null); setEditing(false); } }, [draftActive]);
  async function list(cursor?: number) {
    const n = ++listSequence.current; setLoading(true);
    try {
      const p = await json<{ schema_version: string; items: HistoryItem[]; next_before: number | null }>(`/reports?limit=20${cursor ? `&before=${cursor}` : ""}`, new AbortController().signal);
      if (p.schema_version !== "report-history-v1") throw new Error();
      const reads = await Promise.allSettled(p.items.map(async item => {
        const value = validateReport(await json<ReportDetail>(`/reports/${encodeURIComponent(item.report_id)}/revisions/${item.current_revision}`, new AbortController().signal), simulated);
        if (value.report.report_id !== item.report_id || value.report.revision !== item.current_revision) throw new Error('列表版本身份不一致');
        return value;
      }));
      if (alive.current && n === listSequence.current) {
        setItems(old => cursor ? [...old, ...p.items.filter(item => !old.some(o => o.report_id === item.report_id))] : p.items); setBefore(p.next_before);
        setSummaries(old => ({ ...(cursor ? old : {}), ...Object.fromEntries(p.items.map((item, i) => [item.report_id, reads[i].status === 'fulfilled' ? reads[i].value : null])) }));
        setListError('');
      }
    } catch { if (alive.current && n === listSequence.current) setListError("报告历史读取失败，请重试读取。"); }
    finally { if (alive.current && n === listSequence.current) setLoading(false); }
  }
  async function open(id: string, rev: number, navigate = true) {
    const n = ++sequence.current; setDetail(null); setEditing(false); setComparing(false); setSourceBlocked(false); setError("");
    try { const value = await readExactReport(id, rev, simulated, new AbortController().signal);
      if (value.report.report_id !== id || value.report.revision !== rev) throw new Error("历史身份不一致");
      if (alive.current && n === sequence.current) { onOpen?.(); setDetail(value); setRevision(rev); if (navigate) history.pushState(null, "", reportPath(id, rev)); }
    } catch (e) { if (alive.current && n === sequence.current) setError(`报告历史无法读回：${e instanceof Error ? e.message : "读取失败"}`); }
  }
  useEffect(() => {
    alive.current = true; void list(); const q = new URLSearchParams(location.search), id = q.get("report"), rev = Number(q.get("revision"));
    if (id && Number.isInteger(rev) && rev > 0) void open(id, rev, false);
    return () => { alive.current = false; };
    // Only identities restore on mount; no POST.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!detail) return;
    const c = new AbortController(); let n = 0;
    async function check() {
      const current = ++n, owner = sequence.current;
      try { const value = await readExactReport(detail!.report.report_id, detail!.report.revision, simulated, c.signal, detail!.payload_sha256);
        if (value.payload_sha256 !== detail!.payload_sha256) throw new Error("不可变版本内容变化");
        if (!c.signal.aborted && current === n && owner === sequence.current) setDetail(value);
      } catch { if (!c.signal.aborted && current === n && owner === sequence.current) { setDetail(null); setError("历史完整性或资格无法读回，请重试读取。"); } }
    }
    const timer = window.setInterval(check, 30000); window.addEventListener("focus", check);
    return () => { c.abort(); clearInterval(timer); window.removeEventListener("focus", check); };
  }, [detail, simulated]);
  async function findOperation() {
    const n = ++sequence.current; setError(""); setDetail(null);
    try { const value = validateReport(await json<ReportDetail>(`/reports/by-operation/${encodeURIComponent(operation)}`, new AbortController().signal), simulated);
      if (value.report.operation_id !== operation) throw new Error("操作身份不一致");
      if (alive.current && n === sequence.current) { if (storedOperation() === operation) remember(""); window.location.assign(reportPath(value.report.report_id, value.report.revision)); }
    } catch { if (alive.current && n === sequence.current) setError("操作尚未查证或读取失败；结果仍未知，只能按 operation GET 查询。"); }
  }
  return <>
    <details className="surface report-library-disclosure" open={!detail && !draftActive}><summary>已保存报告历史</summary><section className="report-history" aria-label="已保存报告历史">
      <div className="report-library-heading"><div><h2>报告库</h2><p>全空间已保存报告 · 企业与期间来自冻结快照</p></div><button disabled={loading} onClick={() => void list()}>刷新报告历史</button></div>
      {loading && <p role="status">正在读取已保存报告与范围…</p>}{listError && <p role="alert">{listError}</p>}
      {!loading && !items.length && !listError && <p>尚无已保存报告。可从下方已完成研究整理草稿，明确保存后加入报告库。</p>}
      <ul className="report-library-list">{items.map(item => {
        const value = summaries[item.report_id], context = value && reportContext(value.report.trusted_snapshot);
        return <li key={item.report_id} data-report-id={item.report_id}>
          <div><h3><button onClick={() => requestLeave(() => void open(item.report_id, item.current_revision))}>{value ? value.report.editor_revision.title || value.report.trusted_snapshot.title : item.title} · v{item.current_revision}</button></h3>
            <p>{context ? context.scopes.map(s => `${s.name} · ${s.year} 年`).join(' / ') : '冻结范围无法核验，请重新读取'}</p>
            <p className="muted">{value ? `保存于 ${new Date(value.report.created_at).toLocaleString('zh-CN')}` : '保存时间待读回核验'} · {value ? value.current_eligibility.status === 'invalidated' ? '来源已失效 · 仅供历史审计' : '当前来源可用 · 人工语义待审' : '版本未核验'}</p>
            {item.watermark && <p className="report-test-note">{item.watermark}</p>}
          </div><button onClick={() => requestLeave(() => void open(item.report_id, item.current_revision))}>阅读报告</button>
        </li>;
      })}</ul>{before && <button disabled={loading} onClick={() => void list(before)}>加载更多报告</button>}
    </section></details>
    {(!detail || !!operation) && <details className="report-operation" open={!!storedOperation()}><summary>待查证的保存操作</summary><section aria-label="待查证的保存"><label>按 operation 查询<input value={operation} onChange={e => setOperation(e.target.value)} /></label><button disabled={!operation} onClick={() => requestLeave(() => void findOperation())}>查询历史操作（GET）</button></section></details>}
    {error && <p role="alert" className="operating-alert">{error}</p>}
    {detail && <section className="report-detail" aria-label="报告阅读工作区">
      <ReportContextHeader draft={detail.report.trusted_snapshot} saved={detail} compact />
      <div className="surface report-version-bar"><p className="report-badge">正在阅读 v{detail.report.revision} · {detail.report.revision === detail.current_revision ? '最新版本' : `历史版本只读 / 最新 v${detail.current_revision}`}</p>
        <label>报告版本<select aria-label="报告版本" value={revision} onChange={e => { const rev = Number(e.target.value); requestLeave(() => void open(detail.report.report_id, rev)); }}>{Array.from({ length: detail.current_revision }, (_, i) => <option key={i+1} value={i+1}>v{i+1}{i+1 === detail.current_revision ? ' · 最新版本' : ' · 历史版本'}</option>)}</select></label>
        {!editing && <button disabled={detail.current_revision < 2} onClick={() => setComparing(true)}>比较版本</button>}
        {!editing && <ReportExport key={`${detail.report.report_id}:${detail.report.revision}:${detail.payload_sha256}:${detail.current_eligibility.status}`} detail={detail} simulated={simulated} sourceBlocked={sourceBlocked} compact />}
        {detail.current_eligibility.status === 'current_at_read' && !sourceBlocked && !editing && (detail.report.revision === detail.current_revision ? <button className="primary-button" onClick={() => setEditing(true)}>编辑为新版本</button> : <button onClick={() => requestLeave(() => void open(detail.report.report_id, detail.current_revision))}>打开最新版本后编辑</button>)}
      </div>
      {editing && canEditReport(detail) && !sourceBlocked && <ReportSaveControls key={`${detail.report.report_id}:${detail.report.revision}`} draft={detail.report.trusted_snapshot} saved={detail} simulated={simulated} onCancel={() => requestLeave(() => setEditing(false))} onSaved={value => { sequence.current++; setEditing(false); setDetail(value); setRevision(value.report.revision); void list(); history.replaceState(null, "", reportPath(value.report.report_id, value.report.revision)); }} />}
      {comparing && !editing && <ReportVersionComparison detail={detail} simulated={simulated} close={() => setComparing(false)} />}
      {sourceBlocked && <StatusNotice state="invalidated" title="原 PDF 核验失败">当前文件暂不可核验，已撤下编辑与下载入口。请查阅来源状态；报告仍保留只读审计。</StatusNotice>}
      <ReportPaper draft={detail.report.trusted_snapshot} saved={detail} sourceBlocked={sourceBlocked} onSourceInvalid={() => setSourceBlocked(true)} />
    </section>}
  </>;
}
