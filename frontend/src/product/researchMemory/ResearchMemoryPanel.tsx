import { useEffect, useRef, useState } from 'react';
import { conversationJSON } from '../conversationApi.ts';
import { ResearchPreferences } from '../ResearchPreferences.tsx';
import './ResearchMemoryPanel.css';

type Item = { memory_id: string; revision: number; type: string; text: string; source_status: string; source_kind: string; document_id?: string | null; source_conversation_id?: string | null; embedding_revision: number | null };
type Result = { items: Item[]; memory_generation: number };
type Receipt = { operation_id: string; memory_id: string; revision: number; state: string };
type Pending = { id: string; kind: 'create' | 'patch' | 'delete'; target?: string };
function pendingFromStorage(key: string): Pending | null {
  const raw = sessionStorage.getItem(key); if (!raw) return null;
  const p: unknown = JSON.parse(raw);
  if (!p || typeof p !== 'object' || !('id' in p) || typeof p.id !== 'string' || !('kind' in p) || !['create', 'patch', 'delete'].includes(String(p.kind))) throw Error('invalid');
  return p as Pending;
}
export function ResearchMemoryPanel(props: { companyId?: string; conversationId?: string }) {
  const scope = JSON.stringify([props.companyId ?? null, props.conversationId ?? null]);
  return <ScopedPanel key={scope} companyId={props.companyId} scope={scope} />;
}
function ScopedPanel({ companyId, scope }: { companyId?: string; scope: string }) {
  const key = `findoc:research-memory-operation:v1:${encodeURIComponent(scope)}`;
  const epoch = useRef(0); const alive = useRef(true);
  const [items, setItems] = useState<Item[]>([]); const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState(''); const [text, setText] = useState(''); const [kind, setKind] = useState('note');
  const [editing, setEditing] = useState<Item | null>(null); const [deleting, setDeleting] = useState<Item | null>(null);
  const [confirmed, setConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [initial] = useState(() => { try { return { pending: pendingFromStorage(key), error: false }; } catch { return { pending: null, error: true }; } });
  const [storageError, setStorageError] = useState(initial.error); const [pending, setPending] = useState<Pending | null>(initial.pending); const lock = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; epoch.current++; }; }, []);
  async function load(q = '') {
    const request = ++epoch.current;
    setBusy(true); setError(''); setItems([]); setLoaded(false);
    try {
      const params = new URLSearchParams(); if (q.trim()) params.set('q', q.trim()); if (companyId) params.set('company_id', companyId);
      const result = await conversationJSON<Result>(`/research-memories${params.size ? `?${params}` : ''}`, new AbortController().signal);
      if (!Array.isArray(result.items) || !Number.isSafeInteger(result.memory_generation) || !result.items.every(i => typeof i.memory_id === 'string' && Number.isSafeInteger(i.revision) && typeof i.text === 'string')) throw Error('invalid');
      if (request === epoch.current) { setItems(result.items); setLoaded(true); }
    } catch { if (request === epoch.current) setError('记忆读取失败，请稍后重试。'); } finally { if (request === epoch.current) setBusy(false); }
  }
  useEffect(() => { void load(); }, [companyId]); // eslint-disable-line react-hooks/exhaustive-deps
  async function recover() {
    if (!pending || busy) return; setBusy(true); setError('');
    try {
      const r = await conversationJSON<Receipt>(`/research-memories/operations/${encodeURIComponent(pending.id)}`, new AbortController().signal);
      if (!alive.current) return;
      if (r.operation_id !== pending.id || r.state !== 'completed' || typeof r.memory_id !== 'string' || !Number.isSafeInteger(r.revision)) throw Error('unknown');
      if (pending.kind === 'delete') setItems(old => old.filter(i => i.memory_id !== r.memory_id));
      sessionStorage.removeItem(key); setPending(null); setEditing(null); setDeleting(null); setText(''); setConfirmed(false); setNotice('操作已确认，正在刷新记忆。');
      await load(query);
    } catch { if (alive.current) setError('结果尚未确认，请查询操作状态；不会重复提交。'); } finally { if (alive.current) setBusy(false); }
  }
  async function write(action: Pending['kind']) {
    if (lock.current || busy || pending || storageError || (action !== 'delete' && (!confirmed || !text.trim()))) return;
    const target = action === 'delete' ? deleting : editing; if (action !== 'create' && !target) return;
    const p: Pending = { id: crypto.randomUUID(), kind: action, target: target?.memory_id }; lock.current = true;
    try { sessionStorage.setItem(key, JSON.stringify(p)); } catch { setStorageError(true); lock.current = false; return; }
    setPending(p); setBusy(true); setError('');
    try {
      const body = action === 'create' ? { operation_id: p.id, type: kind, text: text.trim(), confirmed: true, ...(companyId ? { company_id: companyId } : {}) } : action === 'patch' ? { operation_id: p.id, expected_revision: target!.revision, text: text.trim(), confirmed: true } : { operation_id: p.id, expected_revision: target!.revision };
      const r = await conversationJSON<Receipt>(action === 'create' ? '/research-memories' : `/research-memories/${encodeURIComponent(target!.memory_id)}`, new AbortController().signal, action === 'create' ? 'POST' : action === 'patch' ? 'PATCH' : 'DELETE', body);
      if (!alive.current) return;
      if (r.operation_id !== p.id || r.state !== 'completed' || (target && r.memory_id !== target.memory_id)) throw Error('unknown');
      if (action === 'delete') setItems(old => old.filter(i => i.memory_id !== target!.memory_id));
      sessionStorage.removeItem(key); setPending(null); setEditing(null); setDeleting(null); setText(''); setConfirmed(false); setNotice('记忆操作已保存。'); await load(query);
    } catch { if (alive.current) setError('结果尚未确认，请查询操作状态；不会重复提交。'); } finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  return <details className="research-memory"><summary>研究记忆与偏好</summary><div className="research-memory__body">
    <p>保存你确认的研究问题或笔记，供以后研究参考；笔记不是财务签核。删除后不再用于未来召回。</p>
    <form onSubmit={e => { e.preventDefault(); void load(query); }}><label>搜索研究记忆<input value={query} onChange={e => setQuery(e.target.value)} placeholder="上次现金流还有哪些问题" /></label><button className="research-memory__button" disabled={busy}>搜索</button><button className="research-memory__button" type="button" disabled={busy} onClick={() => { setQuery(''); void load(); }}>显示全部</button></form>
    {error && <p role="alert">{error}</p>}{storageError && <p role="alert">本机操作线索不可用，保存已停用。</p>}{notice && <p role="status">{notice}</p>}
    {pending && <p>操作结果待查证。<button className="research-memory__button" disabled={busy} onClick={() => void recover()}>查询操作状态</button></p>}
    {loaded && !items.length && <p>没有找到研究记忆。</p>}
    {items.map(i => <article key={i.memory_id}><strong>{i.type === 'research_question' ? '研究问题' : i.type === 'saved_evidence' ? '收藏证据' : '研究笔记'}</strong><p>{i.text}</p><small>来源：{i.document_id ? '文档引用' : i.source_conversation_id ? '会话' : '用户笔记'} · {i.source_status === 'current' ? '当前有效' : '来源已失效或不可用'}{i.embedding_revision === null ? ' · 尚未建立语义索引' : ''}</small><div><button className="research-memory__button" disabled={busy || !!pending || i.type === 'saved_evidence'} onClick={() => { setEditing(i); setDeleting(null); setText(i.text); setConfirmed(false); }}>编辑</button><button className="research-memory__button" disabled={busy || !!pending} onClick={() => { setDeleting(i); setEditing(null); }}>删除</button></div></article>)}
    {deleting ? <div><p>确认删除这条记忆？{deleting.text}</p><button className="research-memory__button" disabled={busy || !!pending} onClick={() => void write('delete')}>确认删除</button><button className="research-memory__button" onClick={() => setDeleting(null)}>取消</button></div> : <fieldset disabled={busy || !!pending || storageError}><legend>{editing ? '修改记忆' : '新增记忆'}</legend>{!editing && <label>类型<select value={kind} onChange={e => setKind(e.target.value)}><option value="note">研究笔记</option><option value="research_question">研究问题</option></select></label>}<label>内容<textarea maxLength={2000} value={text} onChange={e => setText(e.target.value)} /></label><label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我确认保存这条研究记忆</label><div><button className="research-memory__button" disabled={!confirmed || !text.trim()} onClick={() => void write(editing ? 'patch' : 'create')}>保存记忆</button>{editing && <button className="research-memory__button" onClick={() => { setEditing(null); setText(''); setConfirmed(false); }}>取消编辑</button>}</div></fieldset>}
    <h3>研究偏好</h3><ResearchPreferences />
  </div></details>;
}
