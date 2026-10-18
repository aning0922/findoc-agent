import { useEffect, useRef, useState } from 'react';
import { json } from './api.ts';
import { reportPath } from './productRoutes.ts';
import { StatusNotice } from './StatusNotice.tsx';
import { DiagnosticDetails } from './DiagnosticDetails.tsx';
import { assertSavedOwner, canEditReport, editorDirty } from './reportState.ts';
import type { Draft } from './reportDraft.ts';
import { saveReport, SaveRejected, validateReport, readExactReport, type ReportDetail } from './reportPersistence.ts';
import { storedOperation, rememberOperation } from './reportOperation.ts';
import { useReportNavigation } from './reportNavigationContext.ts';
export function ReportSaveControls({ draft, saved, simulated, onSaved, onCancel }: { draft: Draft; saved?: ReportDetail; simulated: boolean; onSaved?: (detail: ReportDetail) => void; onCancel?: () => void }) {
  const [title, setTitle] = useState(saved?.report.editor_revision.title || '');
  const [conclusions, setConclusions] = useState(saved?.report.editor_revision.conclusions.length ? saved.report.editor_revision.conclusions : ['']);
  const [pending, setPending] = useState(storedOperation), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const lock = useRef(false), alive = useRef(true), titleInput = useRef<HTMLInputElement>(null);
  const { setEditorState } = useReportNavigation();
  const savedEditor = useRef(Boolean(saved));
  const dirty = editorDirty(title, conclusions, saved?.report.editor_revision.title || null, saved?.report.editor_revision.conclusions || []);
  useEffect(() => { alive.current = true; const opener = document.activeElement as HTMLElement | null; if (savedEditor.current) titleInput.current?.focus(); return () => { alive.current = false; if (opener?.isConnected) opener.focus({ preventScroll: true }); }; }, []);
  useEffect(() => { setEditorState({ dirty, pending: !!pending || busy }); return () => setEditorState({ dirty: false, pending: false }); }, [dirty, pending, busy, setEditorState]);
  async function accept(value: ReportDetail, op: string, edits: { title: string | null; conclusions: string[] }) {
    const detail = validateReport(value, simulated);
    if (detail.report.operation_id !== op) throw new Error('保存操作身份不一致');
    assertSavedOwner(detail, draft, saved);
    const read = validateReport(await json<ReportDetail>(`/reports/by-operation/${op}`, new AbortController().signal), simulated);
    if (read.payload_sha256 !== detail.payload_sha256 || read.report.operation_id !== op || read.report.editor_revision.title !== edits.title || JSON.stringify(read.report.editor_revision.conclusions) !== JSON.stringify(edits.conclusions)) throw new Error('保存读回的操作、内容或编辑字段不一致');
    assertSavedOwner(read, draft, saved);
    if (storedOperation() === op) rememberOperation('');
    if (alive.current) { setEditorState({ dirty: false, pending: false }); setPending(''); onSaved?.(read); }
  }
  async function save() {
    if (lock.current || pending || storedOperation() || (saved && (!canEditReport(saved) || !dirty))) return;
    lock.current = true; setBusy(true); setError('');
    let op = '';
    try {
      if (saved) {
        const current = await readExactReport(saved.report.report_id, saved.report.revision, simulated, new AbortController().signal, saved.payload_sha256);
        if (!canEditReport(current)) throw new SaveRejected('此版本已不是最新有效版本，请取消编辑并重新读取最新版本');
      }
      op = crypto.randomUUID(); rememberOperation(op); setPending(op);
      const edits = { title: title.trim() || null, conclusions: conclusions.map(c => c.trim()).filter(Boolean) };
      const body = { operation_id: op, task_id: draft.task_id, expected_task_revision: draft.task_revision, edits, ...(saved ? { expected_report_revision: saved.current_revision } : {}) };
      await accept(await saveReport(saved ? `/reports/${saved.report.report_id}/revisions` : '/reports', body, new AbortController().signal), op, edits);
    } catch (e) {
      if (e instanceof SaveRejected || !op) {
        if (storedOperation() === op) rememberOperation('');
        if (alive.current) { setPending(''); setError(`保存被拒绝或未提交：${e instanceof Error ? e.message : '资格读取失败'}`); }
      } else if (alive.current) setError('保存结果未知。已保留原操作身份，请仅查询保存结果。');
    } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  async function recover() {
    if (lock.current || !pending) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const value = validateReport(await json<ReportDetail>(`/reports/by-operation/${encodeURIComponent(pending)}`, new AbortController().signal), simulated);
      if (value.report.operation_id !== pending) throw new Error('操作身份不一致');
      if (alive.current) {
        if (storedOperation() === pending) rememberOperation('');
        setEditorState({ dirty: false, pending: false });
        window.location.assign(reportPath(value.report.report_id, value.report.revision));
      }
    } catch { if (alive.current) setError('操作尚未查证或读取失败，结果仍未知；保留 operation，仅允许再次 GET 查询。'); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  return <section className="surface report-editor" aria-label="编辑报告">
    <h2>{saved ? `基于已保存 v${saved.report.revision} 编辑` : '报告草稿 · 尚未保存'}</h2>
    {saved && <p>已保存 v{saved.report.revision} · 新修改需明确保存为 v{saved.current_revision + 1}</p>}
    <StatusNotice state={dirty ? 'dirty' : saved ? 'saved' : 'dirty'} title={dirty ? '当前编辑尚未保存' : saved ? '尚无新增修改' : '报告草稿尚未保存'} />
    <label>报告标题<input ref={titleInput} maxLength={200} value={title} placeholder={draft.title} disabled={busy || !!pending} onChange={e => setTitle(e.target.value)} /></label>
    {conclusions.map((text, i) => <label key={i}>用户结论 {i + 1}（待人工语义审阅）<textarea aria-label={`用户结论 ${i + 1}（待人工语义审阅）`} maxLength={2000} value={text} disabled={busy || !!pending} onChange={e => setConclusions(old => old.map((c, n) => n === i ? e.target.value : c))} /></label>)}
    {conclusions.length < 4 && <button disabled={busy || !!pending} onClick={() => setConclusions(old => [...old, ''])}>添加用户结论</button>}
    <p>仅修改标题与用户结论；原金额、公式、来源与可信证据保留冻结快照。用户新增解释尚未核准。</p>
    <div className="report-editor-actions"><button className="primary-button" disabled={busy || !!pending || (saved && (!canEditReport(saved) || !dirty))} onClick={() => void save()}>{busy ? '正在核验并保存…' : saved ? `保存为 v${saved.current_revision + 1}` : '保存第 1 版'}</button>{onCancel && <button disabled={busy} onClick={onCancel}>取消编辑</button>}</div>
    {pending && <><StatusNotice state="unknown">已保留待查证的保存操作。结果可能属于另一项研究；查证成功后打开其真实报告版本。</StatusNotice><DiagnosticDetails fields={{ operation: pending }} /><button disabled={busy} onClick={() => void recover()}>查询保存操作结果（GET）</button></>}
    {error && <p role="alert" className="operating-alert">{error}</p>}
  </section>;
}
