import { useEffect, useRef, useState } from 'react';
import { conversationJSON, ConversationHTTPError } from './conversationApi.ts';
import { listMemories, memoryOperationNotice, preferenceKeys, preferenceValues, readMemoryOperation, readPendingMemory, storePendingMemory, validPreference, validateMemoryItem, validateMemoryOperation } from './memoryApi.ts';
import type { MemoryItem, MemoryOperation, PendingMemory } from './memoryApi.ts';
import type { MemoryCandidate, MemoryKey } from './conversationTypes.ts';
import { StatusNotice } from './StatusNotice.tsx';
import styles from './Conversations.module.css';
export function ResearchPreferences({ candidate }: { candidate?: MemoryCandidate }) {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [initial] = useState(() => { try { return { pending: readPendingMemory(sessionStorage), error: '' }; } catch { return { pending: null, error: '本机偏好操作线索无法读取，请先核对记录。' }; } });
  const [error, setError] = useState(initial.error);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingMemory | null>(initial.pending);
  const [key, setKey] = useState<MemoryKey>(candidate?.key || 'analysis_focus');
  const [value, setValue] = useState(candidate?.value || 'cash_flow');
  const [editing, setEditing] = useState<MemoryItem | null>(null);
  const [deleting, setDeleting] = useState<MemoryItem | null>(null);
  const active = useRef<AbortController | null>(null);
  const writeLock = useRef(false);
  useEffect(() => {
    const c = new AbortController(); active.current = c;
    void listMemories(c.signal).then(v => { if (!c.signal.aborted) { setItems(v.items); setLoaded(true); } })
      .catch(() => { if (!c.signal.aborted) setError('偏好服务暂不可用。未保存任何新偏好，请稍后重新读取。'); });
    return () => { c.abort(); active.current?.abort(); };
  }, []);
  async function reload() {
    if (busy) return;
    const c = new AbortController(); active.current?.abort(); active.current = c; setBusy(true); setError('');
    try { const v = await listMemories(c.signal); if (!c.signal.aborted) { setItems(v.items); setLoaded(true); } }
    catch { if (!c.signal.aborted) setError('偏好列表读取失败，未改变已保存偏好。'); }
    finally { if (!c.signal.aborted) setBusy(false); }
  }
  async function recover() {
    if (!pending || busy) return;
    const c = new AbortController(); active.current?.abort(); active.current = c; setBusy(true); setError('');
    try {
      const receipt = await readMemoryOperation(pending, c.signal);
      if (c.signal.aborted) return;
      storePendingMemory(sessionStorage, null); setPending(null); setEditing(null); setDeleting(null);
      setNotice(memoryOperationNotice(receipt));
      window.dispatchEvent(new Event('findoc-preferences-updated'));
      // A tombstone never carries a value. Remove any stale list/editor before
      // reading current items, so a failed list GET cannot revive old content.
      if (receipt.resource_deleted) { setItems(old => old.filter(i => i.memory_id !== receipt.memory_id)); setLoaded(false); }
      const v = await listMemories(c.signal); if (!c.signal.aborted) { setItems(v.items); setLoaded(true); }
    } catch { if (!c.signal.aborted) setError('偏好操作或当前列表暂不可读取，请只读重试。未重新提交。'); }
    finally { if (!c.signal.aborted) setBusy(false); }
  }
  async function write(kind: PendingMemory['kind']) {
    if (writeLock.current || busy || pending || !loaded || initial.error) return;
    if (kind !== 'delete_memory' && !validPreference(key, value)) return;
    const target = kind === 'delete_memory' ? deleting : editing;
    if (kind !== 'create_memory' && !target) return;
    const op: PendingMemory = { operationId: crypto.randomUUID(), kind, memoryId: target?.memory_id || null };
    writeLock.current = true;
    try { storePendingMemory(sessionStorage, op); } catch { writeLock.current = false; setError('无法保留本次操作身份，尚未提交。'); return; }
    const c = new AbortController(); active.current?.abort(); active.current = c;
    setPending(op); setBusy(true); setError(''); setNotice('');
    try {
      let completedReceipt: MemoryOperation;
      if (kind === 'delete_memory') {
        const receipt = await conversationJSON<MemoryOperation>(`/memories/${target!.memory_id}`, c.signal, 'DELETE', { operation_id: op.operationId, expected_revision: target!.revision });
        completedReceipt = validateMemoryOperation(receipt, op);
      } else {
        const body = kind === 'create_memory'
          ? { operation_id: op.operationId, type: 'research_preference', key, value, confirmed: true, ...(candidate && candidate.key === key && candidate.value === value ? { source_turn_id: candidate.source_turn_id } : {}) }
          : { operation_id: op.operationId, expected_revision: target!.revision, value, confirmed: true };
        const item = validateMemoryItem(await conversationJSON<MemoryItem>(kind === 'create_memory' ? '/memories' : `/memories/${target!.memory_id}`, c.signal, kind === 'create_memory' ? 'POST' : 'PATCH', body));
        if (item.key !== key || item.value !== value || target && item.memory_id !== target.memory_id) throw new Error();
        completedReceipt = await readMemoryOperation(op, c.signal);
      }
      if (c.signal.aborted) return;
      storePendingMemory(sessionStorage, null); setPending(null); setEditing(null); setDeleting(null);
      setNotice(completedReceipt.resource_deleted ? memoryOperationNotice(completedReceipt) : '研究偏好已明确保存。');
      window.dispatchEvent(new Event('findoc-preferences-updated'));
      if (completedReceipt.resource_deleted) { setItems(old => old.filter(i => i.memory_id !== completedReceipt.memory_id)); setLoaded(false); }
      const v = await listMemories(c.signal); if (!c.signal.aborted) { setItems(v.items); setLoaded(true); }
    } catch (e) {
      if (!c.signal.aborted) {
        if (e instanceof ConversationHTTPError && e.status === 409 && ['memory_revision_conflict', 'memory_key_conflict'].includes(e.code || '')) {
          // These frozen errors reject registration. This is not a transport UNKNOWN or GET 404.
          try { storePendingMemory(sessionStorage, null); setPending(null); } catch { /* Keep the recovery block if storage is unavailable. */ }
          setEditing(null); setDeleting(null); setLoaded(false);
          setError('偏好版本或类型存在冲突，本次修改未登记。请重新读取偏好，再明确选择要编辑的最新条目。');
        } else setError('本次结果尚未确认。请先查询操作状态；未重复提交或覆盖偏好。');
      }
    }
    finally { writeLock.current = false; if (!c.signal.aborted) setBusy(false); }
  }
  return <div className={styles.preferences}>
    <p>仅保存你明确确认的研究偏好，展示单位不会改变计算单位。删除后不再用于后续请求；已保存历史回复、备份及已发给供应商的内容仍可能保留。</p>
    <button disabled={busy} onClick={() => void reload()}>重新读取偏好</button>
    {error && <StatusNotice state={pending ? 'unknown' : 'failed'} title={pending ? '偏好操作结果待查证' : '偏好暂不可读取'}>{error}</StatusNotice>}
    {notice && <p role="status">{notice}</p>}
    {pending && <StatusNotice state="unknown" action={<button disabled={busy} onClick={() => void recover()}>查询偏好操作状态</button>}>不会自动重复保存、修改或删除。若操作因冲突未登记，保留查询线索并核对最新列表。</StatusNotice>}
    {!loaded && !error && <p role="status">正在读取研究偏好…</p>}
    {loaded && items.length === 0 && <p>暂无已确认研究偏好。</p>}
    {items.map(item => <section key={item.memory_id} className={styles.option}><strong>{preferenceKeys[item.key]}：{preferenceValues[item.key][item.value]}</strong>
      <div className={styles.actions}><button disabled={busy || !!pending} onClick={() => { setEditing(item); setKey(item.key); setValue(item.value); setDeleting(null); }}>编辑{preferenceKeys[item.key]}</button>
        <button disabled={busy || !!pending} onClick={() => { setDeleting(item); setEditing(null); }}>删除{preferenceKeys[item.key]}</button></div></section>)}
    {deleting ? <section><p>确认删除“{preferenceKeys[deleting.key]}：{preferenceValues[deleting.key][deleting.value]}”？</p><button disabled={busy || !!pending} onClick={() => void write('delete_memory')}>确认删除偏好</button><button disabled={busy} onClick={() => setDeleting(null)}>取消删除</button></section>
      : loaded && <fieldset disabled={busy || !!pending}><legend>{editing ? '修改研究偏好' : candidate ? '确认建议的研究偏好' : '新增研究偏好'}</legend>
        <label className={styles.filter}>偏好类型<select aria-label="偏好类型" value={key} disabled={!!editing} onChange={e => { const k = e.target.value as MemoryKey; setKey(k); setValue(Object.keys(preferenceValues[k])[0]); }}>{Object.entries(preferenceKeys).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label>
        <label className={styles.filter}>偏好内容<select aria-label="偏好内容" value={value} onChange={e => setValue(e.target.value)}>{Object.entries(preferenceValues[key]).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>
        <button disabled={!validPreference(key, value) || !editing && items.some(i => i.key === key)} onClick={() => void write(editing ? 'update_memory' : 'create_memory')}>{editing ? '确认修改偏好' : '保存偏好'}</button>
        {editing && <button onClick={() => setEditing(null)}>取消编辑</button>}
        {!editing && items.some(i => i.key === key) && <p>此类偏好已存在，请使用对应条目的编辑入口。</p>}
      </fieldset>}
  </div>;
}
