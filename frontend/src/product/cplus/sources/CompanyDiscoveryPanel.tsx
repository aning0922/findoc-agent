import { useEffect, useRef, useState } from 'react';
import type { Company } from '../../api.ts';
import './companyDiscovery.css';

type Security = { security_id:string; security_code:string; exchange:string|null; provider_category?:string; provider_security_type?:string; display_name:string; official_name:string|null; supported:boolean };
type Announcement = { candidate_id:string; candidate_digest:string; title_raw:string; report_year:number; kind:string; language:string; revision_kind:string|null; official_page_url:string; security_identity:Security };
type Receipt = { schema_version:string; operation_id:string; state:'unknown'|'failed'|'completed'; phase:string; error_code?:string|null; items?:unknown[]; partial?:boolean; company_id?:string; document_id?:string; document_state?:string };
type Pending = { id:string; kind:'search'|'import'; mode?:'companies'|'announcements' };
type Imported = {companyId:string;documentId:string;state:string};
const opKey='findoc:cplus-discovery-operation', importKey='findoc:cplus-discovery-import';
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const statuses:Record<string,string>={queued:'已上传 · 等待处理',parsing:'正在解析 PDF',indexing:'正在建立索引',ready:'资料已就绪',failed:'资料处理失败',unknown:'等待处理状态',uploaded:'上传完成',reserved:'已登记',downloading:'正在下载',validating:'正在核对来源',binding:'正在绑定企业',company_created:'企业资料已建立',uploading:'正在上传'};
function official(url:string){try{const u=new URL(url);return u.protocol==='https:'&&u.hostname==='www.cninfo.com.cn'&&!u.username&&!u.password?u.href:null}catch{return null}}
function parsePending():Pending|null{try{const v=JSON.parse(sessionStorage.getItem(opKey)||'null');if(v===null)return null;if(!uuid.test(v.id)||!['search','import'].includes(v.kind)||(v.kind==='search'&&!['companies','announcements'].includes(v.mode)))throw Error();return v}catch{return {id:'',kind:'import'}}}
function parseImport():Imported|null{try{const v=JSON.parse(sessionStorage.getItem(importKey)||'null');return v&&typeof v.companyId==='string'&&typeof v.documentId==='string'?{...v,state:'unknown'}:null}catch{return null}}
export function CompanyDiscoveryPanel({companies=[],onImported}:{companies?:Company[];onImported?:(companyId:string,documentId:string)=>void}){
 const [query,setQuery]=useState(''),[year,setYear]=useState('2025'),[kind,setKind]=useState<'annual_fulltext'|'summary'>('annual_fulltext');
 const [securities,setSecurities]=useState<Security[]>([]),[security,setSecurity]=useState<Security|null>(null),[announcements,setAnnouncements]=useState<Announcement[]>([]),[chosen,setChosen]=useState<Announcement|null>(null);
 const [pending,setPending]=useState<Pending|null>(parsePending),[imported,setImported]=useState<Imported|null>(parseImport),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[partial,setPartial]=useState(false);
 const active=useRef(true), request=useRef(0), locked=useRef(false);
 useEffect(()=>{active.current=true;return()=>{active.current=false;++request.current}},[]);
 function apply(r:Receipt,p:Pending){
  if(r.operation_id!==p.id||r.schema_version!==(p.kind==='search'?'cplus-discovery-search-v1':'cplus-import-v1')||!['completed','failed','unknown'].includes(r.state))throw Error('回执身份无法核验');
  if(r.state==='unknown'){setMessage(`操作结果尚未确认 · ${statuses[r.phase]||r.phase||'正在核对'}。请查询原操作。`);return}
  if(r.state==='failed'){sessionStorage.removeItem(opKey);setPending(null);setMessage(`操作未完成：${r.error_code||'来源暂不可用'}。可前往官方查询或手动上传。`);return}
  if(p.kind==='search'){
   if(!Array.isArray(r.items))throw Error('搜索回执不完整');
   if(p.mode==='companies'){if(!r.items.every((x:unknown)=>{const v=x as Security;return v&&typeof v.security_id==='string'&&typeof v.security_code==='string'&&typeof v.display_name==='string'&&typeof v.supported==='boolean'}))throw Error('证券候选身份不完整');setSecurities(r.items as Security[]);setSecurity(null);setAnnouncements([]);setChosen(null)}
   else {if(!r.items.every((x:unknown)=>{const v=x as Announcement;return v&&uuid.test(v.candidate_id)&&/^[a-f0-9]{64}$/.test(v.candidate_digest)&&typeof v.title_raw==='string'&&!!v.security_identity&&typeof v.security_identity.security_id==='string'}))throw Error('公告候选身份不完整');const entries=r.items as Announcement[];if(entries.some(a=>a.security_identity.security_id!==entries[0]?.security_identity.security_id))throw Error('公告证券身份不一致');setAnnouncements(entries);if(entries.length)setSecurity(entries[0].security_identity);setChosen(null);setPartial(!!r.partial)}
  }else{
   if(typeof r.company_id!=='string'||!r.company_id||typeof r.document_id!=='string'||!r.document_id)throw Error('导入回执不完整');
   const value={companyId:r.company_id,documentId:r.document_id,state:'unknown'};sessionStorage.setItem(importKey,JSON.stringify(value));setImported(value);
  }
  sessionStorage.removeItem(opKey);setPending(null);setMessage(p.kind==='import'?'导入已登记，正在只读查询资料处理状态。':'搜索完成，请明确选择候选。');
 }
 async function submit(p:Omit<Pending,'id'>,body:object){
  if(pending||locked.current)return;const value:Pending={...p,id:crypto.randomUUID()};try{sessionStorage.setItem(opKey,JSON.stringify(value))}catch{setMessage('无法保存操作编号，尚未发送请求。');return}
  setPending(value);setBusy(true);locked.current=true;const n=++request.current;
  try{const r=await fetch(`/api/cplus/discovery/${p.kind==='search'?'searches':'imports'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation_id:value.id,...body})});if(!r.ok)throw Error(`响应 ${r.status}，请查询原操作`);const data=await r.json() as Receipt;if(active.current&&n===request.current)apply(data,value)}catch(e){if(active.current&&n===request.current)setMessage(`操作结果未知：${(e as Error).message}。不会自动重发。`)}finally{locked.current=false;if(active.current)setBusy(false)}
 }
 async function recover(){if(!pending||!uuid.test(pending.id)||locked.current)return;setBusy(true);locked.current=true;const n=++request.current;try{const r=await fetch(`/api/cplus/discovery/${pending.kind==='search'?'searches':'imports'}/${pending.id}`,{cache:'no-store'});if(!r.ok)throw Error(`查询未完成（${r.status}）`);const value=await r.json() as Receipt;if(active.current&&n===request.current)apply(value,pending)}catch(e){if(active.current&&n===request.current)setMessage(`${(e as Error).message}，请稍后只读查询。`)}finally{locked.current=false;if(active.current)setBusy(false)}}
 useEffect(()=>{if(!imported||imported.state==='ready'||imported.state==='failed')return;let alive=true,busyRead=false;const controller=new AbortController();async function read(){if(busyRead)return;busyRead=true;try{const r=await fetch(`/api/documents/${encodeURIComponent(imported!.documentId)}`,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error();const v=await r.json();if(v.document_id!==imported!.documentId||!['queued','parsing','indexing','ready','failed'].includes(v.status))throw Error();if(v.status==='ready'){const meta=await fetch(`/api/documents/${encodeURIComponent(imported!.documentId)}/metadata`,{signal:controller.signal,cache:'no-store'});if(!meta.ok||(await meta.json()).company_id!==imported!.companyId)throw Error()}if(alive){const next={...imported!,state:v.status};sessionStorage.setItem(importKey,JSON.stringify(next));setImported(next);if(v.status==='failed')setMessage(v.safe_error_message||'资料处理失败，请核对后使用手动上传。')}}catch{if(alive&&!controller.signal.aborted)setMessage('资料状态暂时无法读取；请稍后查看资料目录。')}finally{busyRead=false}}void read();const timer=window.setInterval(()=>void read(),2500);return()=>{alive=false;controller.abort();window.clearInterval(timer)}},[imported?.documentId,imported?.companyId,imported?.state]);
 async function openReady(){
  if(!imported||!onImported)return;
  setBusy(true);
  try{
   const root=`/api/documents/${encodeURIComponent(imported.documentId)}`;
   const [doc,meta]=await Promise.all([fetch(root,{cache:'no-store'}),fetch(`${root}/metadata`,{cache:'no-store'})]);
   if(!doc.ok||!meta.ok)throw Error();
   const [document,binding]=await Promise.all([doc.json(),meta.json()]);
   if(document.document_id!==imported.documentId||document.status!=='ready'||binding.company_id!==imported.companyId)throw Error();
   if(active.current)onImported(imported.companyId,imported.documentId);
  }catch{if(active.current){setImported({...imported,state:'unknown'});setMessage('资料状态发生变化，请重新核对。')}}finally{if(active.current)setBusy(false)}
 }
 const matches=security?companies.filter(c=>c.security_code===security.security_code&&c.exchange===security.exchange):[];const disabled=busy||!!pending;
 const allowed=!!chosen&&chosen.kind==='annual_fulltext'&&chosen.language==='zh'&&!!security?.supported&&chosen.security_identity.security_id===security.security_id&&matches.length<=1;
 return <section className="company-discovery" aria-label="官方年报查找"><header><p>企业与资料</p><h2>查找并导入年报</h2><p>选择证券和公告后再导入；候选信息不等于财务核准。</p></header>
 {message&&<p role="status">{message}</p>}{pending&&<p role="alert">存在待核对操作。{uuid.test(pending.id)?<button type="button" onClick={()=>void recover()} disabled={busy}>查询原操作</button>:'浏览器存储不可用，请先恢复存储。'}</p>}
 <section><h3>1 · 查找企业</h3><label>代码、简称或拼音 <input value={query} maxLength={80} onChange={e=>setQuery(e.target.value)} placeholder="例如 600690 或 hezj" /></label><button disabled={!query.trim()||disabled} onClick={()=>void submit({kind:'search',mode:'companies'},{mode:'companies',query:query.trim()})}>搜索企业</button>
 <div className="discovery-list">{securities.map(s=><button type="button" key={s.security_id} aria-pressed={security?.security_id===s.security_id} onClick={()=>{setSecurity(s);setAnnouncements([]);setChosen(null);setPartial(false)}}><strong>{s.display_name} · {s.security_code}</strong><span>{s.exchange||s.provider_category||s.provider_security_type||'市场待核验'} {s.supported?'':'· 暂不支持导入'}</span><small>{s.official_name||'法定全称待封面核验'}</small></button>)}</div></section>
 <section><h3>2 · 选择公告</h3>{security?<p>已选 {security.display_name} · {security.security_code} · {security.exchange||security.provider_category}。{security.supported?'':'此证券暂不支持导入。'}</p>:<p>请先选择证券及市场。</p>}
 <label>报告年度 <input type="number" min="1990" max="2100" value={year} onChange={e=>setYear(e.target.value)} /></label><label>公告类型 <select value={kind} onChange={e=>setKind(e.target.value as 'summary'|'annual_fulltext')}><option value="annual_fulltext">年度报告全文</option><option value="summary">摘要</option></select></label><button disabled={!security?.supported||disabled||!/^(19\d\d|20\d\d|2100)$/.test(year)} onClick={()=>void submit({kind:'search',mode:'announcements'},{mode:'announcements',security_id:security!.security_id,report_year:Number(year),kind})}>查找公告</button>
 {partial&&<p>结果可能不完整，请到官方站继续核对。</p>}<div className="discovery-list">{announcements.map(a=><button type="button" key={a.candidate_id} aria-pressed={chosen?.candidate_id===a.candidate_id} onClick={()=>setChosen(a)}><strong>{a.title_raw}</strong><span>{a.report_year} · {a.kind==='summary'?'摘要':'全文'} · {a.language==='zh'?'中文':'英文'} · {a.revision_kind?'标注修订':'更正状态未知'}</span></button>)}</div></section>
 <section><h3>3 · 确认导入</h3>{chosen?<><p>已选：{chosen.title_raw}</p><p>{matches.length===1?`将导入已有企业 ${matches[0].name}。`:matches.length>1?'已有企业身份存在歧义，请先核对企业目录。':'将从报告封面核验法定全称及证券代码，再建立企业资料。'}</p>{!allowed&&<p>当前仅支持已选证券的中文年度全文；摘要、英文版或身份不一致不能导入。</p>}<button disabled={!allowed||disabled} onClick={()=>void submit({kind:'import'},{candidate_id:chosen.candidate_id,candidate_digest:chosen.candidate_digest,company_id:matches.length===1?matches[0].company_id:null,create_company:matches.length===0,confirmed:true})}>{matches.length===1?'确认下载并导入':'导入并建立企业资料'}</button>{official(chosen.official_page_url)&&<p><a href={official(chosen.official_page_url)!} target="_blank" rel="noreferrer">查看官方公告</a></p>}</>:<p>请先选择公告。不会自动下载。</p>}
 {imported&&<div className="discovery-status"><strong>{statuses[imported.state]||'处理状态待查询'}</strong><p>文件处理就绪不代表财务数据已确认。</p>{imported.state==='ready'&&onImported&&<button disabled={busy} onClick={()=>void openReady()}>查看已就绪资料</button>}{imported.state==='failed'&&<a href="/companies">前往企业与资料手动上传</a>}</div>}
 <p><a href="https://www.cninfo.com.cn/" target="_blank" rel="noreferrer">前往官方站查询</a> · <a href="/companies">手动上传资料</a></p></section></section>;
}
