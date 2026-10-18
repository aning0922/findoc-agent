import { useEffect, useRef, useState } from "react";
import type { Company, Report } from "./api.ts";
import { json } from "./api.ts";
import { ResearchRuns } from "./ResearchRuns.tsx";
import { QADialog } from "./QADialog.tsx";
import { DiagnosticDetails } from "./DiagnosticDetails.tsx";
import { StatusNotice } from "./StatusNotice.tsx";
import styles from "./ResearchQA.module.css";

type Option = Report & { selectable: boolean; reason: string | null };
type Options = { schema_version: string; max_selected_documents: number; documents: Option[] };
type Receipt = { schema_version: string; selection_id: string;
  documents: { document_id: string }[]; retrieval_ready: false; research_started: false };

// Remount on current-company changes: pending requests and selections cannot cross companies.
export function ResearchSourceSelection({ company, companies }: { company: string; companies: Company[] }) {
  return <SelectionSession key={company} company={company} companies={companies} />;
}
function SelectionSession({ company, companies }: { company: string; companies: Company[] }) {
  const [options, setOptions] = useState<Options | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [crossCompany, setCrossCompany] = useState(!company);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [question, setQuestion] = useState("");
  const [choosing, setChoosing] = useState(false);
  const [reload, setReload] = useState(0);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const c = new AbortController();
    json<Options>("/research/sources", c.signal).then(value => {
      if (c.signal.aborted) return;
      if (value.schema_version !== "research-source-options-v1" || !Array.isArray(value.documents)
        || !Number.isSafeInteger(value.max_selected_documents) || value.max_selected_documents < 1)
        throw new Error("来源目录合同不完整");
      setOptions(value);
    }).catch(() => { if (!c.signal.aborted) setMessage("来源读取失败，请刷新资料状态。"); });
    return () => { c.abort(); request.current?.abort(); };
  }, [reload]);
  function detachRun() { const q = new URLSearchParams(location.search); q.delete('run'); history.replaceState(null, '', `/research?${q}`); window.dispatchEvent(new Event('findoc:fixed-context')); }
  function clear() { detachRun(); request.current?.abort(); setPending(false); setSelected([]); setMessage(""); }
  async function prepare() {
    if (!options || pending || !selected.length) return;
    const c = new AbortController(); request.current = c; setPending(true); setMessage("");
    try {
      const result = await json<Receipt>("/research/selections/prepare", c.signal, { document_ids: selected });
      if (c.signal.aborted) return;
      if (result.schema_version !== "research-selection-v1" || result.research_started !== false
          || result.retrieval_ready !== false || !/^[a-f0-9]{64}$/.test(result.selection_id)
          || JSON.stringify(result.documents.map(d => d.document_id).sort()) !== JSON.stringify([...selected].sort()))
        throw new Error("范围响应不一致");
      setMessage(`已核验 ${selected.length} 份资料的来源范围。开始研究时将重新核验所选来源与完整索引版本；未启动研究。`);
    } catch { if (!c.signal.aborted) { setSelected([]); setOptions(null); setMessage("所选范围已失效或核验失败，已清空；请刷新资料状态。"); } }
    finally { if (!c.signal.aborted) setPending(false); }
  }
  const visible = options?.documents.filter(d => crossCompany || d.company_id === company) || [];
  const canStart = !!options && selected.length > 0 && selected.every(id => options.documents.some(d => d.document_id === id && d.selectable));
  const name = (id: string) => companies.find(c => c.company_id === id)?.name || '企业名称暂不可读取';
  return <section className={styles.workspace} aria-label="研究资料选择">
    <ResearchRuns company={company} companies={companies} selected={selected} question={question}
      disabled={pending || !canStart} selectedSources={selected.flatMap(id => options?.documents.filter(d => d.document_id === id) || [])}
      manageSources={() => setChoosing(true)}
      editRun={run => { setQuestion(run.query); setSelected(run.document_ids.filter(id => options?.documents.some(d => d.document_id === id && d.selectable))); }}
      composer={<>
        <div className={styles.range} aria-label="所选资料摘要">{selected.map(id => {
          const d = options?.documents.find(d => d.document_id === id);
          return d && <span key={id}>{name(d.company_id)} · {d.report_year} 年报</span>;
        })}</div>
        <div className={styles.question}><label htmlFor="qa-question">研究问题</label>
          <textarea id="qa-question" value={question} maxLength={1000} rows={3} placeholder="例如：列出年报中的营业收入原值，不计算同比。"
            onChange={e => { detachRun(); setQuestion(e.target.value); }} />
        </div>
        {!selected.length && <p className={styles.hint}>先选择 1–4 份可用年报，再输入问题。</p>}
        {selected.length > 0 && !canStart && <StatusNotice state="invalidated" title="所选资料需要重新核验">请刷新资料状态，并明确选择当前可用的来源。</StatusNotice>}
      </>} />
    {choosing && <QADialog title="选择问答资料" close={() => setChoosing(false)}>
      <p>选择 1–4 份年报。更改资料后，旧回答会收起；需要明确查找才会保存新的问答。</p>
      <div className={styles.actions}>
        <label><input type="checkbox" checked={crossCompany} onChange={e => { clear(); setCrossCompany(e.target.checked); }} />显示全部企业，允许共同选择</label>
        <button onClick={() => { clear(); setOptions(null); setReload(n => n + 1); }}>刷新资料状态</button>
      </div>
      <p>已选择 {selected.length} / {options?.max_selected_documents ?? "—"} 份</p>
      {!options && !message && <p role="status">正在读取年报资料…</p>}
      {options && !visible.length && <p>当前没有可展示的年报资料。<a href={`/companies?${new URLSearchParams({ view: 'documents', ...(company ? { company } : {}) })}`}>前往资料库</a></p>}
      <div className={styles.sourceOptions}>{visible.map(d => <div className={styles.sourceOption} key={d.document_id} data-document-id={d.document_id}>
        <label><input type="checkbox" checked={selected.includes(d.document_id)} aria-label={`${name(d.company_id)} · ${d.report_year} 年报`}
          disabled={pending || !d.selectable || (!selected.includes(d.document_id) && selected.length >= (options?.max_selected_documents || 0))}
          onChange={e => { detachRun(); setMessage(""); setSelected(ids => e.target.checked ? [...ids, d.document_id].sort() : ids.filter(id => id !== d.document_id)); }} />
          <span>{name(d.company_id)} · {d.report_year} 年报</span>
        </label>
        <p>{d.selectable ? "可用于原文问答" : "暂不可选择，请查看资料状态或核对来源"}</p>
        <DiagnosticDetails label="资料状态与身份" fields={{ document: d.document_id, status: d.status, reason: d.reason }} />
      </div>)}</div>
      <div className={styles.actions}>
        <button disabled={pending || !canStart} onClick={() => void prepare()}>{pending ? "正在核验…" : "核验所选范围"}</button>
        <button className={styles.primary} onClick={() => setChoosing(false)}>完成资料选择</button>
      </div>
      {message && <p role="status">{message}</p>}
    </QADialog>}
  </section>;
}
