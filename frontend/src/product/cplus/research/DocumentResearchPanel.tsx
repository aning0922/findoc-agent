import { useEffect, useRef, useState } from 'react';
import { listDocuments, type DocumentRow } from '../../documentLibraryApi.ts';
import { ResearchMemoryPanel } from '../../researchMemory/ResearchMemoryPanel.tsx';
import type { ResearchDraft } from '../actions/researchDraft.ts';
import './documentResearch.css';

type Source = { kind: 'fast'|'ocr'; document_id:string; company_id:string; source_revision:string; artifact_id?:string; [key:string]:unknown };
type Focus={schema_version:'financial-point-focus-v1';collection_id:string;cell_id:string;cell_revision:number;payload_sha256:string;metric_key:string;time:Record<string,string>;normalized_decimal:string;normalized_unit:string;source_ref:Source;financial_authority:false};
type Context = { context_id:string; revision:number; context_sha256:string; selected_sources:Source[];financial_focus?:Focus|null };
type Evidence = { source_ref:Source; evidence_id:string; physical_page:number; text:string; line_index?:number };
type Answer = { answer_id:string; context_id:string; state:string; question:string; interpretation:string|null;current_source_status?:string; findings:{text:string;evidence_ref:Evidence;transcription_review_status:string}[] };
type Quality = { artifact_id:string; source_revision:string; output_sha256:string; state:string; source_status:string; pages:{physical_page:number;status:string;method:string}[] };
type Pending = { id:string; kind:'enrollment'|'build'|'context'|'answer'|'memory' };
type Operation = { state:string; result?:unknown };
const key='findoc:cplus-research:operation';
async function read<T>(path:string,signal?:AbortSignal):Promise<T>{
 const response=await fetch('/api'+path,{signal,cache:'no-store'});
 if(!response.ok)throw Error(`读取未完成（${response.status}）`);
 return response.json() as Promise<T>;
}
function stored():Pending|null{
 const raw=sessionStorage.getItem(key);if(!raw)return null;
 const value=JSON.parse(raw) as Pending;
 if(!/^[a-f0-9-]{36}$/.test(value.id)||!['enrollment','build','context','answer','memory'].includes(value.kind))throw Error('操作线索无法读取');
 return value;
}
export function DocumentResearchPanel(){
 const [docs,setDocs]=useState<DocumentRow[]>([]),[documentId,setDocumentId]=useState('');
 const [draft,setDraft]=useState<ResearchDraft|null>(null),[extraSources,setExtraSources]=useState<Source[]>([]);
 const [focus,setFocus]=useState<Focus|null>(null);
 const [kind,setKind]=useState<'fast'|'ocr'>('fast'),[source,setSource]=useState<Source|null>(null),[quality,setQuality]=useState<Quality|null>(null);
 const [pages,setPages]=useState<number[]>([]),[context,setContext]=useState<Context|null>(null),[answer,setAnswer]=useState<Answer|null>(null);
 const [question,setQuestion]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[location,setLocation]=useState<{ref:Evidence;mode:string;url:string}|null>(null);
 const [pending,setPending]=useState<Pending|null>(null),[storageError,setStorageError]=useState(false),[notRegistered,setNotRegistered]=useState(false);
 const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{const controller=new AbortController();alive.current=true;try{setPending(stored())}catch{setStorageError(true)}
  const q=new URLSearchParams(window.location.search).get('question');if(q)setQuestion(q.slice(0,2000));
  const draftId=new URLSearchParams(window.location.search).get('cplus_draft');
  if(draftId&&/^[a-f0-9-]{36}$/.test(draftId)){try{const value=JSON.parse(sessionStorage.getItem(`findoc:cplus-research:draft:${draftId}`)||'null') as ResearchDraft;if(!value||!Array.isArray(value.documentIds)||value.documentIds.length<1||value.documentIds.length>4||value.documentIds.length!==value.sourceRevisions.length||!value.sourceRevisions.every(r=>/^[a-f0-9]{64}$/.test(r)))throw Error();setDraft(value);setDocumentId(value.documentIds[0]);setMessage('已带入来源绑定的研究草稿，尚未执行；请读取资料身份后核对范围。')}catch{setMessage('研究草稿无法核验，请重新选择资料。')}}
  void listDocuments(controller.signal).then(setDocs).catch(()=>{if(!controller.signal.aborted)setMessage('资料目录暂不可用')});
  return()=>{alive.current=false;controller.abort()};},[]);
 const disabled=busy||!!pending||storageError;
 async function apply(operationKind:Pending['kind'],result:unknown){
  if(!result||typeof result!=='object')throw Error('回执结构无效');
  if(operationKind==='enrollment')setSource((result as {source_ref:Source}).source_ref);
  if(operationKind==='context'){const value=result as Context;setContext(value);setFocus(value.financial_focus||null);setSource(value.selected_sources[0]);setExtraSources(value.selected_sources.slice(1));setDocumentId(value.selected_sources[0].document_id)}
  if(operationKind==='answer'){const value=result as Answer;setAnswer(await read<Answer>(`/cplus/research/answers/${encodeURIComponent(value.answer_id)}`))}
  if(operationKind==='build')setMessage('混合检索索引已建立，请固定研究范围后提问。');
  if(operationKind==='memory'){setContext(null);setMessage('证据已收藏；可在下方记忆中查询与删除。')}
 }
 async function write(operationKind:Pending['kind'],path:string,body:object){
  if(lock.current||disabled)throw Error('请先查询未完成操作');
  const intent:Pending={id:crypto.randomUUID(),kind:operationKind};
  sessionStorage.setItem(key,JSON.stringify(intent));setPending(intent);lock.current=true;setBusy(true);setNotRegistered(false);
  try{const response=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation_id:intent.id,...body})});
   if(!response.ok)throw Error(`操作响应（${response.status}），请只读查询原操作`);
   const value=await response.json() as Operation;
   if(value.state!=='completed')throw Error('操作结果尚未确定');
   if(alive.current){await apply(operationKind,operationKind==='memory'?value:value.result);sessionStorage.removeItem(key);setPending(null)}
  }finally{lock.current=false;if(alive.current)setBusy(false)}
 }
 async function recover(){if(!pending||busy)return;setBusy(true);try{
  const path=pending.kind==='memory'?'/research-memories/operations/':'/cplus/research/operations/';
  const response=await fetch('/api'+path+pending.id,{cache:'no-store'});
  if(response.status===404){setNotRegistered(true);setMessage('服务端未登记该编号。可保留后再查询，或显式放弃本机线索。');return}
  if(!response.ok)throw Error('原操作暂不可查询');
  const value=await response.json() as Operation;if(value.state!=='completed')throw Error('仍为 UNKNOWN，未重新执行');
  await apply(pending.kind,pending.kind==='memory'?value:value.result);sessionStorage.removeItem(key);setPending(null);
 }catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
 function changeScope(id:string,mode=kind){setDocumentId(id);setKind(mode);setDraft(null);setFocus(null);setExtraSources([]);setSource(null);setQuality(null);setPages([]);setContext(null);setAnswer(null);setLocation(null)}
 async function inspect(){setBusy(true);setMessage('');try{
  if(kind==='fast'){const ids=draft?.documentIds||[documentId];const values=await Promise.all(ids.map(id=>read<Source>(`/cplus/documents/${encodeURIComponent(id)}/research-source`)));if(values.some((v,i)=>v.kind!=='fast'||v.document_id!==ids[i]||(draft&&(v.company_id!==draft.companyId||v.source_revision!==draft.sourceRevisions[i]))))throw Error('资料身份或版本与草稿不同，请重新选择范围');
   if(draft?.point){const point=draft.point;if(!point.cell_id||!point.cell_revision||!point.payload_sha256)throw Error('图表点位缺少可核验的单元格身份，请返回原图重新选择。');const f=await read<Focus>(`/cplus/financial/cells/${encodeURIComponent(point.cell_id)}/research-focus?${new URLSearchParams({revision:String(point.cell_revision),payload_sha256:point.payload_sha256})}`);if(f.metric_key!==draft.metricKey||f.normalized_decimal!==point.value_decimal||Object.entries(point.time).some(([k,v])=>v!==f.time[k])||!values.some(v=>v.document_id===f.source_ref.document_id&&v.source_revision===f.source_ref.source_revision))throw Error('图表点位或实际财务期间已变化');setFocus(f);const period=f.time.kind==='instant'?f.time.as_of_date:`${f.time.period_start} 至 ${f.time.period_end}`;setQuestion(`${draft.question}\n研究焦点：${f.metric_key}，实际期间 ${period}。图中数据是待核对观察，不代表财务核准。`)}
   setSource(values[0]);setExtraSources(values.slice(1))}
  else{const value=await read<Quality>(`/documents/${encodeURIComponent(documentId)}/parse-quality`);if(value.state!=='completed'||value.source_status!=='current')throw Error('尚无当前完整OCR产物，请先到资料页执行真实OCR');setQuality(value);setPages(value.pages.filter(p=>p.status==='completed').map(p=>p.physical_page))}
 }catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
 async function locate(ref:Evidence){if(!answer)return;setBusy(true);try{
  const base=`/cplus/research/answers/${encodeURIComponent(answer.answer_id)}/evidence/${encodeURIComponent(ref.evidence_id)}`;
  const value=await read<{location_mode:string}>(base+'/location');setLocation({ref,mode:value.location_mode,url:'/api'+base+'/image'});
 }catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
 async function favorite(ref:Evidence){try{await write('memory','/research-memories',{type:'saved_evidence',confirmed:true,
  company_id:ref.source_ref.company_id,document_id:ref.source_ref.document_id,source_revision:ref.source_ref.source_revision,
  evidence_id:ref.source_ref.kind==='fast'?ref.evidence_id:null,artifact_id:ref.source_ref.artifact_id||null,
  physical_page:ref.source_ref.kind==='ocr'?ref.physical_page:null,source_line_index:ref.source_ref.kind==='ocr'?ref.line_index??null:null,text:null});}catch(e){setMessage((e as Error).message)}}
 async function action(fn:()=>Promise<unknown>){try{await fn()}catch(e){setMessage((e as Error).message)}}
 return <section className="cplus-document-research" aria-label="原文与OCR研究">
  <header><span>固定资料 · 原文研究</span><h2>让每个判断，都能回到原文</h2><p>选择完整年报或真实 OCR 转录，固定研究范围后提问。解释始终待审，财务核准独立进行。</p></header>
  {message&&<p role="status">{message}</p>}{storageError&&<p role="alert">浏览器存储不可用，尚未发送新操作。</p>}
  {pending&&<aside role="alert">操作结果待核对 · {pending.kind} <button disabled={busy} onClick={()=>void recover()}>查询原操作</button>{notRegistered&&<button onClick={()=>{sessionStorage.removeItem(key);setPending(null);setNotRegistered(false);setMessage('仅放弃未登记的本机线索；没有重发原操作。')}}>放弃未登记线索</button>}</aside>}
  <div className="cplus-research-controls"><label>资料<select aria-label="资料" value={documentId} disabled={disabled||!!context} onChange={e=>changeScope(e.target.value)}><option value="">选择研究资料</option>{docs.map(d=><option key={d.document_id} value={d.document_id}>{d.source_file} · {d.status==='ready'?'全文就绪':'需查看解析质量'}</option>)}</select></label>
   <label>研究方式<select aria-label="研究方式" value={kind} disabled={disabled||!!context} onChange={e=>changeScope(documentId,e.target.value as 'fast'|'ocr')}><option value="fast">已核验身份的完整年报</option><option value="ocr">OCR 文件转录 · 身份未核验</option></select></label>
   <button disabled={!documentId||disabled||!!context} onClick={()=>void inspect()}>读取资料身份</button></div>
  {quality&&!source&&<article><h3>选择转录页面</h3><p>只将所选 OCR 行加入研究；不会将旧文档改成 READY，也不授予财务准入。</p>{quality.pages.map(p=><label className="cplus-page-choice" key={p.physical_page}><input type="checkbox" checked={pages.includes(p.physical_page)} disabled={disabled||p.status!=='completed'} onChange={e=>setPages(old=>e.target.checked?[...old,p.physical_page]:old.filter(n=>n!==p.physical_page))}/>第 {p.physical_page} 页 · {p.method}</label>)}<button disabled={!pages.length||disabled} onClick={()=>void action(()=>write('enrollment','/cplus/research/enrollments',{document_id:documentId,artifact_id:quality.artifact_id,expected_source_revision:quality.source_revision,expected_artifact_sha256:quality.output_sha256,selected_pages:pages,confirmed:true}))}>明确加入转录研究</button></article>}
  {focus&&<p>已核验图表焦点：{focus.metric_key} · {focus.time.as_of_date||`${focus.time.period_start} 至 ${focus.time.period_end}`} · 待核对</p>}{source&&!context&&<article>{answer&&<p>研究记忆已更新。请重新固定范围后继续提问，历史答案仍可阅读。</p>}<p>{source.kind==='ocr'?'OCR 转录待核对 · 企业身份未核验':'完整来源已复验 · 内容仍需审阅'}</p><button disabled={disabled} onClick={()=>void action(()=>write('build','/cplus/retrieval/builds',{sources:[source,...extraSources]}))}>建立混合检索索引</button> <button disabled={disabled} onClick={()=>void action(()=>write('context','/cplus/research/contexts',{title:'固定资料研究',selected_sources:[source,...extraSources],financial_focus:focus}))}>固定范围，开始研究</button></article>}
  {context&&<article><p>研究范围已固定 · {context.selected_sources.length} 份资料 · {source?.kind==='ocr'?'OCR转录':'完整年报'} · 跨问题保持同一资料版本</p><label>研究问题<textarea value={question} maxLength={2000} disabled={disabled} onChange={e=>setQuestion(e.target.value)} placeholder="例如：主要经营风险是什么？"/></label><button disabled={!question.trim()||disabled} onClick={()=>void action(()=>write('answer','/cplus/research/answers',{context_id:context.context_id,context_revision:context.revision,context_sha256:context.context_sha256,question:question.trim()}))}>提交研究问题</button> <button disabled={disabled} onClick={()=>changeScope(documentId)}>重新选择范围</button></article>}
  {answer&&<article><h3>{answer.question}</h3>{answer.current_source_status==='stale_or_unavailable'&&<p role="alert">历史快照：当前来源已变化或无法复验；不能据此继续执行或确认财务。</p>}<p>{answer.state==='completed'?'AI 解释已生成 · 待审核':answer.state==='provider_unconfigured'?'模型未配置 · 展示真实检索原文':answer.state==='insufficient_evidence'?'证据不足 · 未强行生成':answer.state}</p>{answer.interpretation&&<p className="cplus-interpretation">{answer.interpretation}</p>}{answer.findings.map((f,i)=><section className="cplus-finding" key={f.evidence_ref.evidence_id}><small>资料 {i+1} · 第 {f.evidence_ref.physical_page} 页 · {f.evidence_ref.source_ref.kind==='ocr'?'OCR 转录待核对':'PDF 原文摘录'}</small><blockquote>{f.text}</blockquote><button disabled={disabled} onClick={()=>void locate(f.evidence_ref)}>定位原文</button> <button disabled={disabled} onClick={()=>void favorite(f.evidence_ref)}>收藏这条证据</button></section>)}</article>}
  {location&&<section aria-label="原文高亮预览"><h3>原 PDF 第 {location.ref.physical_page} 页</h3><p>{location.mode==='exact_excerpt_quads'?'已匹配原文并高亮':location.mode==='verified_ocr_line_bbox'?'已按核验 OCR 行坐标高亮 · 转录待审':'未取得精确坐标，降级显示原页，请对照摘录核查'}</p><img src={location.url} alt="所选原 PDF 页面与可用的精确引用高亮"/><button onClick={()=>setLocation(null)}>关闭原文预览</button></section>}
  <details><summary>研究收藏与跨会话记忆</summary><ResearchMemoryPanel companyId={source?.company_id}/></details>
 </section>;
}
