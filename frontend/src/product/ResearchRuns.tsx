import { qaFailureMessage, qaRefusalMessage, qaFailureTitle, qaRefusalTitle } from "./recoveryMessages.ts";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Company } from "./api.ts";
import { ResearchAnswerView } from "./ResearchAnswerView.tsx";
import { RunReviewReading } from './ExternalReviewReading.tsx';
import { ResearchPdfDialog } from "./ResearchPdfDialog.tsx";
import type { ResearchCitation } from "./researchAnswer.ts";
import { researchPdfUrl } from "./researchAnswer.ts";
import { validateHistory, validateRun } from "./researchHistory.ts";
import styles from "./ResearchQA.module.css";
import type { HistoryItem, ResearchRun } from "./researchHistory.ts";
import { WaitingNotice } from "./WaitingNotice.tsx";
import { StatusNotice } from './StatusNotice.tsx';
import { DiagnosticDetails } from './DiagnosticDetails.tsx';

const labels = { running: "执行中", answered: "已保存回答", refused: "已保存拒答", system_error: "已保存系统错误" };
// Only the operation identity is kept locally; every result comes from the server database.
function pendingKey(company: string) { return `findoc:pending-operation:${company}`; }
function readPending(company: string) { try { return sessionStorage.getItem(pendingKey(company)); } catch { return null; } }
function remember(company: string, op: string | null) {
  try { if (op) sessionStorage.setItem(pendingKey(company), op); else sessionStorage.removeItem(pendingKey(company)); } catch { /* server history remains recoverable */ }
}
export function ResearchRuns({ company, companies, selected, question, disabled, composer, selectedSources, manageSources, editRun }: {
  company: string; companies: Company[]; selected: string[]; question: string; disabled: boolean;
  composer: ReactNode; selectedSources: { document_id: string; company_id: string; report_year: number; source_revision?: string }[];
  manageSources: () => void; editRun: (run: ResearchRun) => void;
}) {
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState("");
  const [busy, setBusy] = useState(false);
  const [waitingFor, setWaitingFor] = useState<"read" | "research">("read");
  const [waitingIdentity, setWaitingIdentity] = useState(0);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState<string | null>(() => readPending(company));
  const [missing, setMissing] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const [pdf, setPdf] = useState<ResearchCitation | null>(null);
  const [unavailable, setUnavailable] = useState<string[]>([]);
  const historyPanel = useRef<HTMLDetailsElement>(null);
  const [readIdentity, setReadIdentity] = useState<{ identity: string; byOperation: boolean } | null>(null);
  const active = useRef<AbortController | null>(null);
  const listing = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const viewEpoch = useRef(0);
  const selectionKey = JSON.stringify(selected);
  const initialRun = useRef(new URLSearchParams(location.search).get('run'));
  function runRoute(value: ResearchRun, push = false) {
    const q = new URLSearchParams(location.search);
    for (const name of ['task', 'new', 'section', 'report', 'revision']) q.delete(name);
    q.set('mode', 'qa'); q.set('run', value.run_id);
    history[push ? 'pushState' : 'replaceState'](null, '', `/research?${q}`);
    window.dispatchEvent(new Event('findoc:fixed-context'));
  }
  function clearView() { viewEpoch.current++; active.current?.abort(); active.current = null; setBusy(false); setRun(null); setMessage(""); setPdfError(""); setPdf(null); setUnavailable([]); }
  useLayoutEffect(() => {
    // Request ownership changes revoke in-flight display, including non-abortable PDF checks.
    // oxlint-disable-next-line react/set-state-in-effect
    clearView();
  }, [selectionKey, question]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; active.current?.abort(); listing.current?.abort(); };
  }, []);
  function resolvePending(value: ResearchRun) {
    if (value.status === "running" && !readPending(company)) { remember(company, value.operation_id); setPending(value.operation_id); }
    if (value.status !== "running" && readPending(company) === value.operation_id) {
      remember(company, null); setPending(null);
    }
  }
  const loadHistory = useCallback(async (next: string | null = null) => {
    listing.current?.abort(); const c = new AbortController(); listing.current = c;
    setListBusy(true); setListError("");
    try {
      const query = new URLSearchParams({ limit: "5", ...(company ? { company_id: company } : {}) });
      if (next) query.set("cursor", next);
      const response = await fetch(`/api/research/runs?${query}`, { signal: c.signal, cache: "no-store" });
      if (!response.ok) throw new Error();
      const value = validateHistory(await response.json());
      if (c.signal.aborted) return;
      setItems(old => next ? [...old, ...value.items.filter(i => !old.some(o => o.run_id === i.run_id))] : value.items);
      setCursor(value.next_cursor);
    } catch { if (!c.signal.aborted) setListError("研究历史读取失败，请重试读取。"); }
    finally { if (!c.signal.aborted) setListBusy(false); }
  }, [company]);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => { if (!cancelled) void loadHistory(); });
    return () => { cancelled = true; };
  }, [loadHistory]); // parent remounts on company changes
  async function open(identity: string, byOperation = false, push = true) {
    clearView(); setReadIdentity({ identity, byOperation }); const c = new AbortController(); active.current = c; setBusy(true); setMissing(false);
    setWaitingFor("read");
    setWaitingIdentity(value => value + 1);
    try {
      const response = await fetch(`/api/research/runs/${byOperation ? "by-operation/" : ""}${encodeURIComponent(identity)}`, { signal: c.signal, cache: "no-store" });
      if (c.signal.aborted) return;
      if (response.status === 404 && byOperation) {
        setMissing(true); setMessage("已按操作身份查询，服务端未找到记录。没有再次提交；如需新研究，请明确结束本次查询。"); return;
      }
      if (!response.ok) throw new Error();
      const value = validateRun(await response.json(), identity, byOperation);
      if (c.signal.aborted) return;
      setRun(value); resolvePending(value); runRoute(value, push); if (historyPanel.current) historyPanel.current.open = false;
    } catch { if (!c.signal.aborted) setMessage("研究历史读取失败或结果损坏。未重新运行模型，请重试读取。"); }
    finally { if (!c.signal.aborted) { setBusy(false); active.current = null; } }
  }
  useEffect(() => {
    if (initialRun.current) void open(initialRun.current, false, false);
    // Restore this mounted route once; selection changes only revoke display.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function start() {
    if (active.current || pending || disabled || !selected.length || !question.trim()) return;
    clearView(); const c = new AbortController(); active.current = c; setBusy(true); setMissing(false);
    setWaitingFor("research");
    setWaitingIdentity(value => value + 1);
    const op = crypto.randomUUID(); remember(company, op); setPending(op);
    try {
      const response = await fetch("/api/research/runs", { method: "POST", signal: c.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operation_id: op, document_ids: selected, query: question.trim() }) });
      const body = await response.json();
      if (c.signal.aborted) return;
      if (!response.ok) {
        if ([404, 409, 422].includes(response.status)) {
          remember(company, null); setPending(null); setMessage("资料未获核准或请求冲突，本次未执行新研究，请刷新资料。");
        } else setMessage(body.detail === "research_save_failed"
          ? "研究保存失败，未发布成功答案。请按操作身份查询；系统不会重复执行模型。"
          : "服务未能确认研究结果，请按操作身份查询。系统没有重复提交。");
        return;
      }
      const value = validateRun(body, op, true);
      if (value.query !== question.trim() || JSON.stringify([...value.document_ids].sort()) !== JSON.stringify([...selected].sort())) throw new Error("保存的请求身份不一致");
      setRun(value); resolvePending(value); runRoute(value); void loadHistory();
    } catch { if (!c.signal.aborted) setMessage("连接中断或响应无法确认，执行状态未知。请按操作身份恢复；系统没有重复提交。"); }
    finally { if (!c.signal.aborted) { setBusy(false); active.current = null; } }
  }
  function markUnavailable(c: ResearchCitation) {
    setUnavailable(old => [...new Set([...old, `${c.document_id}:${c.source_revision}`])]);
  }
  function openTab(c: ResearchCitation) {
    const popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    const owner = viewEpoch.current; setPdfError('');
    void fetch(researchPdfUrl(c).split('#')[0], { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error();
      if (!mounted.current || viewEpoch.current !== owner) { popup?.close(); return; }
      if (popup) popup.location.href = researchPdfUrl(c);
      else setPdfError('浏览器未允许新标签。可使用引用旁的查看原 PDF 在此页阅读。');
    }).catch(() => {
      popup?.close();
      if (mounted.current && viewEpoch.current === owner) { markUnavailable(c); setPdfError('原 PDF 不可打开：来源可能已变化或无权访问，请刷新历史状态。'); }
    });
  }
  const result = run?.result;
  const name = (id: string) => companies.find(c => c.company_id === id)?.name || '企业名称暂不可读取';
  const displayedSources = run?.documents || selectedSources;
  return <section aria-label="原文问答">
    {pdf && <ResearchPdfDialog key={`${pdf.document_id}:${pdf.source_revision}:${pdf.number}`} citation={pdf} close={() => setPdf(null)} invalid={() => markUnavailable(pdf)} />}
    <header className={styles.toolbar}><h2>{run ? "阅读已保存问答" : "向原文提问"}</h2><div className={styles.actions}>
      <button onClick={manageSources}>管理来源</button><button onClick={() => { if (historyPanel.current) { historyPanel.current.open = true; historyPanel.current.querySelector('summary')?.focus(); historyPanel.current.scrollIntoView({ block: 'start' }); } }}>历史问答</button>
    </div></header>
    <div className={styles.grid}>
      <div className={styles.main}>
        {!run && <section className={styles.card} aria-label="新问题">
          <p className={styles.hint}>在所选资料中查找可核验的原文。财务计算需要先核对并独立保存事实。</p>{composer}
          <button className={styles.primary} onClick={() => void start()} disabled={disabled || busy || !!pending || !selected.length || !question.trim()}>{busy ? "正在读取或研究…" : "查找原文"}</button>
        </section>}
        {busy && <WaitingNotice key={waitingIdentity} message={waitingFor === "research" ? "正在查找年报原文，服务端会核验来源并按证据决定回答或拒答。" : "正在只读查询已保存的研究结果。"} stop={() => { clearView(); setMessage("已停止本页等待，服务端任务可能仍在执行。原操作身份已保留，请只读恢复或打开研究历史。"); }} />}
        {pending && !busy && <StatusNotice state="unknown" title="研究结果暂时无法确认" action={<button onClick={() => void open(pending, true)}>查看这次操作的结果</button>}>
          <p>{message || "已保留原操作；刷新后仍可只读查询，系统不会自动重新提问。"}</p><DiagnosticDetails label="高级诊断：待确认的操作" fields={{ operation: pending }} />
          {missing && <button onClick={() => { remember(company, null); setPending(null); setMissing(false); }}>结束查询，允许明确发起新研究</button>}
        </StatusNotice>}
        {message && !pending && <StatusNotice state={pending ? "unknown" : "failed"} title={pending ? "研究结果暂时无法确认" : "问答记录暂时无法读取"}>
          <p>{message}</p>{!pending && readIdentity && <button disabled={busy} onClick={() => void open(readIdentity.identity, readIdentity.byOperation)}>重新读取这条问答</button>}
        </StatusNotice>}
        {run && <section className={styles.card} aria-label="研究历史详情" data-run-id={run.run_id}>
          <header className={styles.savedHeader}>
            <p className={styles.meta}>历史问答读取 · 阅读不会重新运行模型</p>
            <p className={styles.meta}>{labels[run.status]} · <time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString("zh-CN")}</time> · {run.documents.length} 份资料</p>
            <p className={styles.meta}>原问题</p><h2 className={styles.savedQuestion} aria-label="原问题">{run.query}</h2>
            <div className={styles.range} aria-label="独立问答上下文">{[...new Set(run.documents.map(d => d.company_id))].map(id => <span key={id}>{name(id)} · {run.documents.filter(d => d.company_id === id).map(d => d.report_year).join(' / ')} 年报</span>)}</div>
            <button onClick={() => { editRun(run); clearView(); const q = new URLSearchParams(location.search); q.delete('run'); history.replaceState(null, '', `/research?${q}`); window.dispatchEvent(new Event('findoc:fixed-context')); requestAnimationFrame(() => document.getElementById('qa-question')?.focus()); }}>修改问题或资料</button>
          </header>
          {run.status === "running" && <StatusNotice state="unknown" title="研究结果暂时无法确认" action={<button onClick={() => void open(run.operation_id, true)}>查看这次操作的结果</button>}>服务端记录仍为执行中；再次读取不会重新执行模型。</StatusNotice>}
          {run.source_states.some(s => s.status === "expired") && <StatusNotice state="invalidated" title="来源已过期或绑定已纠错">以下内容仅为历史审计快照，旧证据不能作为当前有效来源，原 PDF 入口已禁用。</StatusNotice>}
          {result?.outcome === "refused" && <StatusNotice state="refused" title={qaRefusalTitle(result.reason, run.query)}>{qaRefusalMessage(result.reason, run.query)}</StatusNotice>}
          {result?.outcome === "system_error" && <><StatusNotice state="failed" title={qaFailureTitle(result.error_code)}>{qaFailureMessage(result.error_code)}</StatusNotice><DiagnosticDetails label="高级诊断：已保存的错误身份" fields={{ error: result.error_code, run: run.run_id, operation: run.operation_id }} /></>}
          {run.result && <RunReviewReading run={run} />}
          {result?.outcome === "answered" && <ResearchAnswerView key={run.run_id} run={run} companies={companies} unavailable={unavailable} openPdf={setPdf} openTab={openTab} />}
          {pdfError && <StatusNotice state="invalidated" title="原 PDF 暂不可打开">{pdfError}</StatusNotice>}

        </section>}
      </div>
      <aside className={styles.sources} aria-label={run ? "本次回答来源" : "当前选择来源"}>
        <h3>{run ? "本次回答来源" : "当前选择来源"} · {displayedSources.length} 份</h3><p className={styles.hint}>{run ? "范围来自这条问答保存时的资料。" : "通过管理来源明确选择年报。"}</p>
        {displayedSources.map(d => <div className={styles.sourceCard} key={d.document_id} data-source-document={d.document_id}>
          <strong>{name(d.company_id)} · {d.report_year} 年报</strong>
          {run && <><p>{run.source_states.find(s => s.document_id === d.document_id)?.status === 'expired' ? '历史来源已失效' : '读取时来源有效'}</p>
            {run.result?.citations.filter(c => c.document_id === d.document_id && c.source_revision === d.source_revision).map(c => <a key={c.number} href={`#qa-citation-${c.number}`}>引用 [{c.number}] · 物理第 {c.physical_page} 页</a>)}
            <DiagnosticDetails label="来源版本与身份" fields={{ document: d.document_id, source_revision: d.source_revision }} />
          </>}
        </div>)}
        {run && <DiagnosticDetails label="高级诊断：问答身份与范围" fields={{ run: run.run_id, operation: run.operation_id, integrity_sha256: run.integrity_sha256 }}>
          <p>独立 ResearchRun；不归档为经营任务子对象。保存原文及引用内容不可修改，人工语义审读待完成。</p>
        </DiagnosticDetails>}
      </aside>
    </div>
    <details ref={historyPanel} className={styles.history}><summary>历史问答 · 只读打开</summary>
      <section aria-label="研究历史列表"><h3>研究历史</h3><p>{company ? "当前企业参与的已保存问答。" : "全部企业的已保存问答。"}打开历史只读取保存内容。</p>
        <button disabled={listBusy} onClick={() => void loadHistory()}>刷新研究历史</button>
        {listError && <StatusNotice state="failed" title="问答历史暂时无法读取">{listError}</StatusNotice>}
        {!items.length && !listBusy && !listError && <p>暂无研究记录。</p>}
        <ul>{items.map(i => <li key={i.run_id}><button onClick={() => void open(i.run_id)}>{i.query.length > 80 ? `${i.query.slice(0, 80)}…` : i.query}</button>
          <div className={styles.meta}><time dateTime={i.created_at}>{new Date(i.created_at).toLocaleString("zh-CN")}</time> · {i.documents.length} 份资料 · {labels[i.status]}</div>
        </li>)}</ul>
        {cursor && <button disabled={listBusy} onClick={() => void loadHistory(cursor)}>加载更多研究</button>}
      </section>
    </details>
  </section>;
}
