import { useEffect, useRef, useState } from 'react';
import type { Company, Fact } from './api.ts';
import { formatDecimal } from './api.ts';
import { conversationPath, qaPath } from './productRoutes.ts';
import { QADialog } from './QADialog.tsx';
import { ResearchPdfDialog } from './ResearchPdfDialog.tsx';
import type { PdfCitation } from './ResearchPdfDialog.tsx';
import { ResearchPreferences } from './ResearchPreferences.tsx';
import { ResearchMemoryPanel } from './researchMemory/ResearchMemoryPanel.tsx';
import { ShowcaseResearchPanel } from './showcaseResearch/ShowcaseResearchPanel.tsx';
import { preferenceKeys, preferenceValues, validPreference } from './memoryApi.ts';
import { StatusNotice } from './StatusNotice.tsx';
import { DiagnosticDetails } from './DiagnosticDetails.tsx';
import { VerifiedExcerpt } from './VerifiedExcerpt.tsx';
import { METRICS } from '../evidence/contracts.ts';
import { readConversationSources, selectableConversationScope } from './conversationSources.ts';
import type { ConversationSourceOptions } from './conversationSources.ts';
import { ConversationHTTPError, createConversation, isUnregisteredConversationCreate, isUnregisteredConversationDelete, isUnregisteredConversationTurn, listConversations, readConversation, readConversationOperation, readConversationTurn, sendConversationTurn, conversationJSON, validateConversationOperation } from './conversationApi.ts';
import type { Action, ConversationDetail, ConversationSummary, EvidenceRef, MemoryCandidate, Turn } from './conversationTypes.ts';
import { conversationScopeState, readConversationOperations, rememberConversationOperation, resolveConversationOperation } from './conversationState.ts';
import type { ConversationOperation } from './conversationState.ts';
import { conversationFactSelection, readConversationFacts } from './conversationFacts.ts';
import { conversationActionPdfLocation, readConversationActionPdf, verifyConversationPdf } from './conversationPdf.ts';
import styles from './Conversations.module.css';
const examples = ['这份年报中的营业收入原文是什么？', '经营活动现金流有哪些说明？', '请找到主要业务风险的原文出处。'];
const labels = { running: '执行中', completed: '已保存', refused: '已保存拒答', failed: '执行失败', interrupted: '执行已中断' };
export default function Conversations({ companies }: { companies: Company[] }) {
  const [panel, setPanel] = useState<'sources' | 'history' | 'facts' | 'preferences' | 'delete' | null>(null);
  const [researchMode, setResearchMode] = useState<'quick' | 'synthesis' | 'deep'>('quick');
  const [entryResearch] = useState(() => {
    const params = new URLSearchParams(location.search);
    return { conversationId: params.get('conversation'), jobId: params.get('job'), mode: params.get('research_mode') };
  });
  const [candidate, setCandidate] = useState<MemoryCandidate | undefined>();
  const [options, setOptions] = useState<ConversationSourceOptions | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [filter, setFilter] = useState(() => new URLSearchParams(location.search).get('company') || '');
  const [sourceError, setSourceError] = useState('');
  const [sourceLoading, setSourceLoading] = useState(true);
  const [sourceReload, setSourceReload] = useState(0);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listError, setListError] = useState('');
  const [listBusy, setListBusy] = useState(false);
  const [listReload, setListReload] = useState(0);
  // Homepage navigation only fills a draft. It never selects source authority,
  // creates a conversation, or sends a provider request.
  const [question, setQuestion] = useState(() => {
    const value = new URLSearchParams(location.search).get('question') || '';
    return value.length <= 1000 ? value : '';
  });
  const [busy, setBusy] = useState(false);
  const [conversationNeedsRefresh, setConversationNeedsRefresh] = useState(false);
  const [createNeedsRefresh, setCreateNeedsRefresh] = useState(false);
  const [deletedElsewhere, setDeletedElsewhere] = useState(false);
  const [message, setMessage] = useState('');
  const [storageError, setStorageError] = useState('');
  const [pending, setPending] = useState<ConversationOperation[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [chosenFacts, setChosenFacts] = useState<string[]>([]);
  const [factError, setFactError] = useState('');
  const [factBusy, setFactBusy] = useState(false);
  const [pdf, setPdf] = useState<PdfCitation | null>(null);
  const [invalidPdf, setInvalidPdf] = useState<string[]>([]);
  const input = useRef<HTMLTextAreaElement>(null);
  const active = useRef<AbortController | null>(null);
  const listing = useRef<AbortController | null>(null);
  const factReading = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const pdfReading = useRef<AbortController | null>(null);
  const initialId = useRef(new URLSearchParams(location.search).get('conversation'));
  const listNext = useRef<string | null>(null);
  const companyName = (id: string) => companies.find(c => c.company_id === id)?.name || '企业名称暂不可读取';
  useEffect(() => {
    mounted.current = true;
    try { setPending(readConversationOperations(sessionStorage)); } catch { setStorageError('本机操作线索无法读取，写入暂不可用。请先核对服务端历史。'); }
    if (initialId.current) void loadDetail(initialId.current);
    return () => { mounted.current = false; active.current?.abort(); active.current = null; pdfReading.current?.abort(); listing.current?.abort(); factReading.current?.abort(); factReading.current = null; };
    // Route changes remount this workspace and revoke all prior callbacks.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const c = new AbortController(); listing.current?.abort(); listing.current = c;
    setListBusy(true); setListError('');
    const next = listNext.current; listNext.current = null;
    void listConversations(c.signal, next || undefined).then(v => {
      if (!c.signal.aborted) { setItems(old => next ? [...old, ...v.items.filter(i => !old.some(o => o.conversation_id === i.conversation_id))] : v.items); setCursor(v.next_cursor); }
    }).catch(() => { if (!c.signal.aborted) setListError('会话列表暂不可读取，请重新读取。'); })
      .finally(() => { if (!c.signal.aborted) setListBusy(false); });
    return () => c.abort();
  }, [listReload]);
  useEffect(() => {
    const c = new AbortController();
    void readConversationSources(c.signal).then(v => { if (!c.signal.aborted) { setOptions(v); setSourceError(''); setSourceLoading(false); setCreateNeedsRefresh(false); } })
      .catch(() => { if (!c.signal.aborted) { setSourceError('年报目录暂不可读取，请重新读取。'); setSourceLoading(false); } });
    return () => c.abort();
  }, [sourceReload]);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1099px)');
    const close = () => { pdfReading.current?.abort(); setPanel(null); setPdf(null); };
    const nav = (e: MouseEvent) => { if ((e.target as Element | null)?.closest?.('[aria-controls="product-navigation"]')) close(); };
    media.addEventListener('change', close); document.addEventListener('click', nav, true);
    return () => { media.removeEventListener('change', close); document.removeEventListener('click', nav, true); };
  }, []);
  function openPanel(value: typeof panel) { pdfReading.current?.abort(); setPdf(null); setPanel(value); }
  async function openPdf(evidence: EvidenceRef) {
    pdfReading.current?.abort(); const c = new AbortController(); pdfReading.current = c;
    setPanel(null); setPdf(null); setMessage('正在核验引用的完整 PDF 来源身份…');
    try {
      await verifyConversationPdf(evidence, c.signal);
      if (!c.signal.aborted && mounted.current) { setInvalidPdf(old => old.filter(id => id !== `${evidence.document_id}:${evidence.source_revision}`)); setPdf(evidence); setMessage(''); }
    } catch { if (!c.signal.aborted && mounted.current) { setInvalidPdf(old => [...new Set([...old, `${evidence.document_id}:${evidence.source_revision}`])]); setMessage('原 PDF 来源无法核验，保留历史原文供阅读。'); } }
  }
  async function openFinancialPdf(action: Action) {
    if (!detail) return;
    // Validate the action/scope before starting IO, without fabricating EvidenceRef.
    let location;
    try { location = conversationActionPdfLocation(action, detail); }
    catch { setMessage('原 PDF 动作与冻结来源不匹配，未打开文件。'); return; }
    pdfReading.current?.abort(); const c = new AbortController(); pdfReading.current = c;
    setPanel(null); setPdf(null); setMessage('正在核验财务结果的原 PDF 来源…');
    try {
      const citation = await readConversationActionPdf(action, detail, c.signal);
      if (!c.signal.aborted && mounted.current) {
        setInvalidPdf(old => old.filter(id => id !== `${location.document_id}:${location.source_revision}`));
        setPdf(citation); setMessage('');
      }
    } catch {
      if (!c.signal.aborted && mounted.current) {
        setInvalidPdf(old => [...new Set([...old, `${location.document_id}:${location.source_revision}`])]);
        setMessage('财务结果的原 PDF 来源或物理页无法核验。保留历史结果，未重新查询或计算财务事实。');
      }
    }
  }
  function syncPending() { try { setPending(readConversationOperations(sessionStorage)); } catch { setStorageError('本机操作线索无法读取，请核对历史。'); } }
  function remember(op: ConversationOperation): boolean {
    try { rememberConversationOperation(sessionStorage, op); syncPending(); return true; }
    catch { setStorageError('无法保留操作身份，尚未发送请求。'); return false; }
  }
  function resolve(op: string) { resolveConversationOperation(sessionStorage, op); syncPending(); }
  function showConversation(v: ConversationDetail) {
    if (detail?.conversation_id !== v.conversation_id) {
      // Revoke old readers before publishing B: their late callbacks check the
      // aborted signals and cannot restore A's choices or PDF failure markers.
      factReading.current?.abort(); factReading.current = null;
      pdfReading.current?.abort(); pdfReading.current = null;
      const state = conversationScopeState(detail?.conversation_id || null, v.conversation_id, { facts, chosenFacts, factError, invalidPdf });
      setFacts(state.facts); setChosenFacts(state.chosenFacts); setFactError(state.factError); setInvalidPdf(state.invalidPdf);
      setFactBusy(false); setPdf(null);
    }
    setDetail(v);
    const reading = new URLSearchParams({ conversation: v.conversation_id });
    if (entryResearch.conversationId === v.conversation_id) {
      if (entryResearch.jobId) reading.set('job', entryResearch.jobId);
      if (entryResearch.mode === 'deep' || entryResearch.mode === 'synthesis') reading.set('research_mode', entryResearch.mode);
    }
    history.replaceState(null, '', '/conversations?' + reading);
    setConversationNeedsRefresh(false);
    setDeletedElsewhere(false);
    // Running turns discovered in another tab also block a new local submission.
    for (const t of v.turns.filter(t => t.status === 'running')) remember({ operationId: t.operation_id, conversationId: v.conversation_id, kind: 'send' });
    // A validated read of the exact committed turn also resolves its pending
    // hint, including the other tab's active turn discovered during refresh.
    try {
      const operations = readConversationOperations(sessionStorage);
      for (const t of v.turns.filter(t => t.status !== 'running')) {
        if (operations.some(op => op.kind === 'send' && op.conversationId === v.conversation_id && op.operationId === t.operation_id)) resolve(t.operation_id);
      }
    } catch { setStorageError('无法更新本机操作线索，请先核对记录。'); }
  }
  async function loadDetail(id: string, before?: number) {
    if (active.current) return;
    const c = new AbortController(); active.current = c; setBusy(true); setMessage('');
    try {
      const v = await readConversation(id, c.signal, before);
      if (c.signal.aborted) return;
      if (before) setDetail(old => old && old.conversation_id === v.conversation_id ? { ...v, turns: [...v.turns, ...old.turns.filter(t => !v.turns.some(n => n.turn_id === t.turn_id))] } : v);
      else showConversation(v);
    } catch (e) { if (!c.signal.aborted) setMessage((e as Error).message); }
    finally { if (!c.signal.aborted) { active.current = null; setBusy(false); } }
  }
  async function create() {
    if (active.current || storageError || createNeedsRefresh || pending.length || !selectableConversationScope(options, selected)) return;
    const op: ConversationOperation = { operationId: crypto.randomUUID(), conversationId: null, kind: 'create' };
    if (!remember(op)) return;
    const c = new AbortController(); active.current = c; setBusy(true); setMessage('');
    let awaitingCreateResponse = true;
    try {
      const v = await createConversation({ operation_id: op.operationId, document_ids: [...selected].sort() }, c.signal);
      awaitingCreateResponse = false;
      const receipt = await readConversationOperation(op.operationId, c.signal);
      if (receipt.kind !== 'create_conversation' || receipt.conversation_id !== v.conversation_id || receipt.status !== 'completed' || receipt.resource_deleted) throw new Error();
      if (c.signal.aborted) return;
      resolve(op.operationId); showConversation(v); setPanel(null); setListReload(n => n + 1);
    } catch (error) {
      if (!c.signal.aborted) {
        if (awaitingCreateResponse && isUnregisteredConversationCreate(error)) {
          setCreateNeedsRefresh(true);
          try { resolve(op.operationId); } catch { setStorageError('无法更新本机操作线索，创建暂不可用。'); }
          setMessage('本次创建未登记，所选年报和问题草稿已保留。请先重新读取年报状态，再明确选择有效来源并点击创建。');
          setSourceError('来源资格已变化，请重新读取年报状态后再创建会话。');
        } else setMessage('创建结果尚未确认，请按本次操作查询。未重复创建，也未发送问题。');
      }
    }
    finally { if (!c.signal.aborted) { active.current = null; setBusy(false); } }
  }
  function mergeTurn(turn: Turn) {
    setDetail(old => old ? { ...old, turns: [...old.turns.filter(t => t.turn_id !== turn.turn_id), turn].sort((a, b) => a.seq - b.seq),
      last_turn_seq: Math.max(old.last_turn_seq, turn.seq), active_turn_id: turn.status === 'running' ? turn.turn_id : null,
      source_states: turn.source_states } : old);
  }
  const scopeCurrent = !!detail && detail.source_states.every(s => s.status === 'current_at_read') && !invalidPdf.length;
  const localPending = pending.some(p => p.conversationId === detail?.conversation_id || p.kind === 'create');
  async function send() {
    if (active.current || storageError || conversationNeedsRefresh || !detail || localPending || detail.active_turn_id || !scopeCurrent || !question.trim()) return;
    const text = question.trim(); const selections = facts.filter(f => chosenFacts.includes(f.fact_id)).map(conversationFactSelection);
    const op: ConversationOperation = { operationId: crypto.randomUUID(), conversationId: detail.conversation_id, kind: 'send' };
    if (!remember(op)) return;
    const c = new AbortController(); active.current = c; setBusy(true); setMessage('');
    try {
      const turn = await sendConversationTurn(detail, { operation_id: op.operationId, text, fact_selections: selections }, c.signal);
      if (c.signal.aborted) return;
      mergeTurn(turn); setQuestion(current => current.trim() === text ? '' : current);
      if (turn.status !== 'running') resolve(op.operationId);
      setListReload(n => n + 1);
    } catch (error) {
      if (!c.signal.aborted) {
        if (isUnregisteredConversationTurn(error)) {
          // Only this rejected POST's own hint may be removed. Do not retry,
          // consume the draft, or clear any other tab/operation identity.
          setConversationNeedsRefresh(true);
          try { resolve(op.operationId); }
          catch { setStorageError('无法更新本机操作线索，发送暂不可用。'); }
          setMessage('本次问题未登记，草稿已保留。会话可能正由其他标签处理，或来源资格已变化；请先只读刷新会话。确认无执行中任务且来源可用后，再由你明确点击发送。');
        } else setMessage('结果尚未确认。请查询本次操作状态；未再次发送或重新运行模型。');
      }
    }
    finally { if (!c.signal.aborted) { active.current = null; setBusy(false); } }
  }
  async function recover(op: ConversationOperation) {
    if (active.current) return;
    const c = new AbortController(); active.current = c; setBusy(true); setMessage('');
    try {
      const receipt = await readConversationOperation(op.operationId, c.signal);
      const kind = { create: 'create_conversation', send: 'send_turn', delete: 'delete_conversation' }[op.kind];
      if (receipt.kind !== kind || op.conversationId && receipt.conversation_id !== op.conversationId) throw new Error('操作回执身份不匹配。');
      if (c.signal.aborted) return;
      if (receipt.status === 'running') { setMessage('服务端仍在处理。可稍后继续只读查询。'); return; }
      if (receipt.resource_deleted) {
        resolve(op.operationId); setMessage('操作已查明，会话内容已删除。');
        if (detail?.conversation_id === receipt.conversation_id) { setDetail(null); history.replaceState(null, '', conversationPath()); }
      } else if (op.kind === 'send') {
        // Fetch using the originating scope, never graft an A result into visible B.
        const origin = detail?.conversation_id === receipt.conversation_id ? detail : await readConversation(receipt.conversation_id, c.signal);
        const turn = await readConversationTurn(origin, op.operationId, c.signal);
        if (turn.turn_id !== receipt.turn_id || turn.status !== receipt.status) throw new Error('操作与消息终态不一致。');
        if (c.signal.aborted) return;
        if (detail?.conversation_id === receipt.conversation_id) mergeTurn(turn);
        resolve(op.operationId); setMessage('本次操作已只读查明。');
      } else if (op.kind === 'create' && receipt.status === 'completed') {
        const v = await readConversation(receipt.conversation_id, c.signal);
        if (c.signal.aborted) return;
        resolve(op.operationId);
        if (!detail) { showConversation(v); setPanel(null); } else setMessage('新会话已创建，可在会话列表中打开。');
      } else { resolve(op.operationId); setMessage('本次操作已查明，未发布新的成功结果。'); }
      setListReload(n => n + 1);
    } catch (e) { if (!c.signal.aborted) setMessage((e as Error).message || '暂不能查明本次操作，请继续只读查询。'); }
    finally { if (!c.signal.aborted) { active.current = null; setBusy(false); } }
  }
  async function deleteConversation() {
    if (active.current || conversationNeedsRefresh || !detail || detail.active_turn_id || localPending || storageError) return;
    const op: ConversationOperation = { kind: 'delete', conversationId: detail.conversation_id, operationId: crypto.randomUUID() };
    if (!remember(op)) return;
    const c = new AbortController(); active.current = c; setBusy(true); setMessage('');
    try {
      const receipt = validateConversationOperation(await conversationJSON(`/conversations/${detail.conversation_id}`, c.signal, 'DELETE', { operation_id: op.operationId }), op.operationId);
      if (receipt.kind !== 'delete_conversation' || receipt.conversation_id !== detail.conversation_id || !receipt.resource_deleted || receipt.status !== 'completed') throw new Error();
      if (c.signal.aborted) return;
      resolve(op.operationId); setDetail(null); history.replaceState(null, '', conversationPath()); setPanel(null); setListReload(n => n + 1); setMessage('会话内容已删除。');
    } catch (error) {
      if (!c.signal.aborted) {
        if (isUnregisteredConversationDelete(error)) {
          setConversationNeedsRefresh(true); setPanel(null);
          try { resolve(op.operationId); } catch { setStorageError('无法更新本机操作线索，删除暂不可用。'); }
          if (error instanceof ConversationHTTPError && error.status === 410) {
            setDeletedElsewhere(true);
            setMessage('会话已由其他操作删除，本次删除未登记。问题草稿已保留；可只读确认状态或返回会话列表，不会再次删除或创建会话。');
          } else setMessage('本次删除未登记，问题草稿已保留。另一标签正在处理会话，请先只读刷新；确认没有执行中任务后，再明确决定是否删除。');
        } else setMessage('删除结果尚未确认，请只读查询本次操作。');
      }
    }
    finally { if (!c.signal.aborted) { active.current = null; setBusy(false); } }
  }
  async function discoverFacts() {
    if (!detail || factReading.current) return;
    const c = new AbortController(); factReading.current = c; setFactBusy(true); setFactError('');
    try { const v = await readConversationFacts(detail, c.signal); if (!c.signal.aborted) { setFacts(v); setChosenFacts(old => old.filter(id => v.some(f => f.fact_id === id))); } }
    catch { if (!c.signal.aborted) { setFacts([]); setChosenFacts([]); setFactError('事实读取失败或资格无法核验，未展示金额。'); } }
    finally { if (!c.signal.aborted) { factReading.current = null; setFactBusy(false); } }
  }
  const historyList = <><h2>我的会话</h2><button onClick={() => setListReload(n => n + 1)} disabled={listBusy}>重新读取会话</button>
    {listBusy && <p role="status">正在读取会话列表…</p>}{listError && <p role="alert">{listError}</p>}
    {!listBusy && !listError && !items.length && <p>暂无已保存会话。</p>}
    <ul className={styles.conversationList}>{items.map(item => <li key={item.conversation_id}><a href={conversationPath(item.conversation_id)} aria-current={item.conversation_id === detail?.conversation_id ? 'page' : undefined}>{item.title}</a><small>{item.sources.map(s => `${companyName(s.company_id)} ${s.report_year}`).join(' / ')}{item.active_turn_id ? ' · 执行中' : ''}</small></li>)}</ul>
    {cursor && <button disabled={listBusy} onClick={() => { listNext.current = cursor; setListReload(n => n + 1); }}>更多会话</button>}
    <a href={conversationPath()}>新建会话</a></>;
  const sourcePanel = detail ? <><p>当前会话的来源范围已冻结。更换来源请明确新建会话。</p>{detail.sources.map(s => <section key={s.document_id} className={styles.option}><strong>{companyName(s.company_id)} · {s.report_year} 年报</strong><p>{detail.source_states.find(x => x.document_id === s.document_id)?.status === 'current_at_read' ? '数据库读取时资格有效；打开引用将核验真实 PDF。' : '当前来源资格已失效或无法确认。'}</p><DiagnosticDetails label="冻结来源身份" fields={{ document: s.document_id, revision: s.source_revision, sha256: s.content_sha256, parser: s.parser_version }} /></section>)}<a href={conversationPath()}>选择其他来源并新建会话</a></> : <>
    <p>选择 1–4 份年报。创建后来源范围固定，不会自动发送问题。</p>
    <label className={styles.filter}>筛选企业<select value={filter} onChange={e => setFilter(e.target.value)}><option value="">全部企业</option>{companies.map(c => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}</select></label>
    <p>已选择 {selected.length} / {Math.min(4, options?.max_selected_documents ?? 4)} 份</p><button disabled={sourceLoading} onClick={() => { setOptions(null); setSourceLoading(true); setSourceError(''); setSourceReload(n => n + 1); }}>重新读取年报状态</button>
    {sourceLoading && <p role="status">正在读取年报…</p>}{sourceError && <p role="alert">{sourceError}</p>}
    {options?.documents.filter(d => !filter || filter === d.company_id).map(d => <section key={d.document_id} className={styles.option}><label><input type="checkbox" checked={selected.includes(d.document_id)} disabled={busy || !selected.includes(d.document_id) && (!d.selectable || d.report_type !== 'annual' || selected.length >= Math.min(4, options.max_selected_documents))} onChange={e => setSelected(old => e.target.checked ? [...new Set([...old, d.document_id])] : old.filter(id => id !== d.document_id))} /><span>{companyName(d.company_id)} · {d.report_year} 年报<br /><small>{d.source_file}</small></span></label><p>{d.selectable ? '可选择' : '当前不可用，请核对来源'}</p></section>)}
    {options && !options.documents.length && <p>暂无可选择年报。<a href="/companies?view=documents">前往企业与年报</a></p>}
    {!!selected.length && <section className={styles.selection}><h3>已选年报（包括筛选外的选择）</h3>{selected.map(id => { const s = options?.documents.find(d => d.document_id === id); return <div key={id}><span>{s ? `${companyName(s.company_id)} · ${s.report_year} · ${s.source_file}` : '资料待重新核验'}</span><button disabled={busy} onClick={() => setSelected(old => old.filter(v => v !== id))} aria-label={`移除${s?.source_file || '待核验资料'}`}>移除</button></div>; })}</section>}
    <button disabled={busy || createNeedsRefresh || !!storageError || !!pending.length || !selectableConversationScope(options, selected)} onClick={() => void create()}>{busy ? '正在创建…' : '创建会话'}</button>
  </>;
  function renderTurn(turn: Turn) {
    const r = turn.result;
    return <article className={styles.turn} key={turn.turn_id} aria-label={`第 ${turn.seq} 轮对话`}><h3>你</h3><p className={styles.answer}>{turn.user_text}</p><h3>研究助手 · {labels[turn.status]}</h3>
      {turn.resolved_query && <p className={styles.muted}>解析问题：{turn.resolved_query.text} · {turn.resolved_query.company_id ? companyName(turn.resolved_query.company_id) : '企业待明确'} · 财务年度 {turn.resolved_query.periods.join(' / ') || '待明确'}</p>}
      {!r ? <p role="status">正在处理并核验，请通过操作查询读取结果。</p> : <>
        <p className={styles.muted}>{r.kind === 'source_quote' ? '已保存原文摘录 · 人工语义审读待完成' : r.verified_financial_fact_refs.length ? '已确认数据 · 仅表示完成时已验证，历史读取不重新核准' : r.kind === 'clarification' ? '请明确讨论对象后继续提问' : '研究状态说明'}</p>
        {r.kind !== 'source_quote' && <p className={styles.answer}>{r.answer_text}</p>}
        {r.evidence_refs.map(e => <section key={e.ref_id} className={styles.option}><strong>[{e.number}] {e.report_year} 年报《{e.source_file}》 · 物理第 {e.physical_page} 页</strong><VerifiedExcerpt text={e.text} /><button onClick={() => void openPdf(e)}>查看原 PDF [{e.number}]</button></section>)}
        {r.verified_financial_fact_refs.map(f => <p key={f.ref_id}>{METRICS[f.metric_key]} · {f.period} 财务年度：{formatDecimal(f.value_cny_yuan)} 元 · {f.report_year} 年报 · 完成时验证于 {f.validated_at}</p>)}
        {r.analysis && <section><p>服务端比较结果：差额 {formatDecimal(r.analysis.absolute_change)} 元；变化比例 {r.analysis.percentage_change === null ? '不可计算' : `${r.analysis.percentage_change}%`}</p>{r.analysis.percentage_reason && <p>{r.analysis.percentage_reason}</p>}{r.analysis.warnings.map((w, i) => <p key={i}>{w}</p>)}</section>}
        {r.actions.map((a, i) => a.kind === 'open_source'
          ? <button className={i === 0 ? styles.primaryAction : undefined} key={`${a.kind}:${i}`} onClick={() => void openFinancialPdf(a)}>{a.label}</button>
          : <a className={i === 0 ? styles.primaryAction : undefined} key={`${a.kind}:${i}`} href={a.href}>{a.label}</a>)}
        {r.memory_candidates.filter(c => c.type === 'research_preference' && c.confirmation_required === true && c.source_turn_id === turn.turn_id && validPreference(c.key, c.value)).map((c, i) => <p key={i}>建议保存偏好：{preferenceKeys[c.key]} · {preferenceValues[c.key][c.value]} <button onClick={() => { setPdf(null); setCandidate(c); openPanel('preferences'); }}>查看并确认偏好</button></p>)}
        {r.interpretation_status === 'pending_human_review' && <p>AI 分析待人工语义审核</p>}
      </>}
      <details><summary>工具与技术详情</summary><p>模型尝试 {turn.usage.model_attempts} 次，业务工具 {turn.usage.tool_calls} 次</p>{turn.tool_events.map(e => <p key={e.sequence}>{e.tool_name} · {e.status} · {e.summary}</p>)}<DiagnosticDetails label="消息身份" fields={{ operation: turn.operation_id, turn: turn.turn_id, provider_outcome: turn.provider_outcome, integrity: turn.integrity_sha256 }} /></details>
    </article>;
  }
  return <div className={styles.page}><header className={styles.heading}><div><h1>财报研究助手</h1><p>围绕明确选择的年报连续研究，回到原文核对每条回答。</p></div><a href={qaPath()}>单次原文核验 / 历史问答</a></header>
    <div className={styles.mobileTools}><button onClick={() => { setPdf(null); openPanel('history'); }}>我的会话</button><button onClick={() => { setPdf(null); openPanel('sources'); }}>当前来源</button></div>
    <div className={styles.layout}><aside className={styles.history} aria-label="会话列表">{historyList}</aside><section className={styles.main} aria-label="连续对话">
      <header className={styles.context}><div><strong>{detail?.title || '开始新的研究'}</strong><p>{detail ? detail.sources.map(s => `${companyName(s.company_id)} · ${s.report_year} 年报`).join(' / ') : '先选择 1–4 份年报并创建会话'}</p></div><div className={styles.actions}><button onClick={() => { setPdf(null); openPanel('sources'); }}>{detail ? '查看冻结来源' : '选择年报'}</button><button onClick={() => { setPdf(null); setCandidate(undefined); openPanel('preferences'); }}>我的研究偏好</button>{detail && <button disabled={busy} onClick={() => void loadDetail(detail.conversation_id)}>只读刷新会话</button>}</div></header>
      {storageError && <StatusNotice state="failed">{storageError}</StatusNotice>}{message && <StatusNotice state={pending.length ? 'unknown' : 'waiting'} title="会话状态">{message}</StatusNotice>}
      {deletedElsewhere && <StatusNotice state="invalidated" title="会话已由其他操作删除" action={<a href={conversationPath()}>返回会话列表</a>}>本次删除未登记。历史内容仅供当前页面阅读，发送和删除入口保持关闭。</StatusNotice>}
      {busy && <p role="status">正在等待服务端读回，尚未确认新的结果…</p>}
      {pending.map(op => <StatusNotice key={op.operationId} state="unknown" title={`${op.kind === 'create' ? '创建会话' : op.kind === 'delete' ? '删除会话' : '发送问题'}待查证`} action={<button disabled={busy} onClick={() => void recover(op)}>查询本次操作状态</button>}><p>恢复只读取状态，不会再次提交。</p><DiagnosticDetails label="操作身份" fields={{ operation: op.operationId, conversation: op.conversationId }} /></StatusNotice>)}
      {detail && !scopeCurrent && <StatusNotice state="invalidated" title="来源已失效或暂不能核验">保留历史内容供阅读。当前不能发送新问题，请重新读取状态；更换来源需另建会话。</StatusNotice>}
      {initialId.current && !detail && !busy && <p>历史读取不会重新生成回答。<button onClick={() => void loadDetail(initialId.current!)}>重试读取历史</button></p>}
      {detail && scopeCurrent && <ShowcaseResearchPanel conversationId={detail.conversation_id} onModeChange={setResearchMode} initialQuestion={question} initialMode={entryResearch.conversationId === detail.conversation_id && entryResearch.mode === "deep" ? "deep" : entryResearch.conversationId === detail.conversation_id && entryResearch.mode === "synthesis" ? "synthesis" : "quick"} initialJobId={entryResearch.conversationId === detail.conversation_id ? entryResearch.jobId || undefined : undefined} />}
      <ResearchMemoryPanel conversationId={detail?.conversation_id} companyId={detail && new Set(detail.sources.map(s => s.company_id)).size === 1 ? detail.sources[0]?.company_id : undefined} />
      <div className={styles.messages} aria-label="消息记录">{detail?.next_before_seq && <button disabled={busy} onClick={() => void loadDetail(detail.conversation_id, detail.next_before_seq!)}>读取更早消息</button>}{detail?.turns.map(renderTurn)}{researchMode === 'quick' && !detail?.turns.length && <><h2>{detail ? '年报范围已确定，可以开始提问' : '从年报原文开始'}</h2><p>示例只填入草稿，不自动发送。</p><div className={styles.examples}>{examples.map(e => <button key={e} onClick={() => { setQuestion(e); input.current?.focus(); }}>{e}</button>)}</div></>}</div>
      {(!detail || researchMode === 'quick') && <div className={styles.composer}><label htmlFor="conversation-question">研究问题</label><textarea ref={input} id="conversation-question" value={question} onChange={e => setQuestion(e.target.value)} rows={3} maxLength={1000} placeholder="例如：那上一年呢？" aria-describedby="conversation-send-help" />
        <div className={styles.sendRow}><p id="conversation-send-help">{detail ? `已明确选择 ${chosenFacts.length} 项财务事实；发送才会创建新一轮。` : '先创建会话，再明确发送问题。'}</p><button disabled={busy || conversationNeedsRefresh || !detail || !scopeCurrent || !!detail.active_turn_id || localPending || !!storageError || !question.trim()} onClick={() => void send()}>发送</button></div>
        {detail && <button onClick={() => { setPdf(null); openPanel('facts'); void discoverFacts(); }}>选择已确认财务事实</button>}
      </div>}<p className={styles.muted}>本地单人研究空间。必要的问题与证据会发送给所配置的模型供应商；来源资格与计算时验证不代替人工语义审读。</p>
      {detail && <button disabled={busy || conversationNeedsRefresh || localPending || !!detail.active_turn_id || !!storageError} onClick={() => openPanel('delete')}>删除此会话</button>}
    </section></div>
    {panel && <QADialog title={{ sources: detail ? '当前冻结来源' : '选择会话年报', history: '会话历史', facts: '选择已确认财务事实', preferences: '我的研究偏好', delete: '确认删除会话' }[panel]} close={() => setPanel(null)} className={styles.dialog}>
      {panel === 'sources' ? sourcePanel : panel === 'history' ? historyList : panel === 'preferences' ? <ResearchPreferences candidate={candidate} /> : panel === 'delete' ? <><p>删除会话消息及其新会话来源记录。旧原文问答、财务事实、PDF、研究任务及长期偏好仍保留。此操作不能撤销。</p><button disabled={busy || conversationNeedsRefresh || localPending} onClick={() => void deleteConversation()}>确认删除会话</button></> : <>
        <p>仅展示当前所选年报范围内、具备有效核准资格的事实。请明确勾选披露版本，系统不会自动选取唯一或最新记录。最多 6 项。</p><button disabled={factBusy || busy} onClick={() => void discoverFacts()}>重新读取事实</button>{factBusy && <p role="status">正在读取已确认事实…</p>}{factError && <p role="alert">{factError}</p>}
        {!factBusy && !factError && !facts.length && <p>尚无可用的已确认事实。<a href="/research?mode=operating">前往经营研究准备与核对</a>；进入不会自动接受、保存或继续任务。</p>}
        {facts.map(f => <section className={styles.option} key={f.fact_id}><label><input type="checkbox" checked={chosenFacts.includes(f.fact_id)} disabled={busy || !chosenFacts.includes(f.fact_id) && chosenFacts.length >= 6} onChange={e => setChosenFacts(old => e.target.checked ? [...old.filter(id => !facts.some(other => other.fact_id === id && other.company_id === f.company_id && other.metric_key === f.metric_key && other.period === f.period)), f.fact_id] : old.filter(id => id !== f.fact_id))} /><span>{companyName(f.company_id)} · {METRICS[f.metric_key]} · {f.period} 财务年度 · {formatDecimal(f.value_cny_yuan)} 元</span></label><p>披露版本：{f.disclosure_version}</p><DiagnosticDetails label="事实与来源身份" fields={{ fact: f.fact_id, document: f.document_id, revision: f.source_revision }} /></section>)}<button onClick={() => setPanel(null)}>完成事实选择</button>
      </>}
    </QADialog>}
    {pdf && <ResearchPdfDialog citation={pdf} close={() => setPdf(null)} invalid={() => setInvalidPdf(old => [...new Set([...old, `${pdf.document_id}:${pdf.source_revision}`])])} drawer />}
  </div>;
}
