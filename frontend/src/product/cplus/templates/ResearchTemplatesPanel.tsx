import {useEffect,useRef,useState} from 'react';
import type {Company} from '../../api.ts';
import type {AnnualSourceRef} from '../insights/AnnualDiffPanel.tsx';
import type {ResearchDraft} from '../actions/researchDraft.ts';
import {TemplateRunResult} from './TemplateRunResult.tsx';
import {readJSON,sameSources,templates,uuid,type TemplateId,type TemplateResult} from './templateTypes.ts';
import './templates.css';
type Body={template_id:TemplateId;template_version:'cplus-template-v1';question:string;selected_sources:AnnualSourceRef[];generate_explanation:boolean};
type Pending={id:string;body:Body};
type Operation={operation_id:string;state:string;result?:TemplateResult|null};
type Props={companyId:string;companies?:Company[];sources:AnnualSourceRef[];onResearchDraft?:(draft:ResearchDraft)=>void};
export function ResearchTemplatesPanel(props:Props){return <Templates key={props.companyId} {...props}/>}
function Templates({companyId,companies=[],sources,onResearchDraft}:Props){
 const key='findoc:cplus-template-run:'+companyId;
 const [template,setTemplate]=useState<TemplateId>('overview'),[docs,setDocs]=useState<string[]>([]),[question,setQuestion]=useState(templates[0].question),[generate,setGenerate]=useState(false),[confirmed,setConfirmed]=useState(false);
 const [pending,setPending]=useState<Pending|null>(null),[storageError,setStorageError]=useState(false),[busy,setBusy]=useState(false),[notFound,setNotFound]=useState(false),[message,setMessage]=useState(''),[result,setResult]=useState<TemplateResult|null>(null);
 const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{alive.current=true;try{const raw=sessionStorage.getItem(key);if(raw){const p=JSON.parse(raw) as Pending;if(!uuid.test(p.id)||!p.body||!Array.isArray(p.body.selected_sources))throw Error();setPending(p)}}catch{setStorageError(true)}return()=>{alive.current=false}},[key]);
 const options=sources.filter(s=>s.kind==='fast'&&s.identity_status==='fast_source_verified'&&s.report_type==='annual'&&(template==='peer'||s.company_id===companyId));
 const selected=options.filter(s=>docs.includes(s.document_id)),years=new Set(selected.map(s=>s.report_year)),ids=new Set(selected.map(s=>s.company_id));
 const valid=template==='overview'?selected.length===1:template==='peer'?selected.length>=2&&selected.length<=3&&ids.size===selected.length&&years.size===1&&ids.has(companyId):selected.length===2&&ids.size===1&&years.size===2;
 const locked=busy||!!pending||storageError;const name=(id:string)=>companies.find(c=>c.company_id===id)?.name||id.slice(0,8);
 function changed(){setConfirmed(false);setResult(null);setMessage('')}
 async function consume(value:Operation,p:Pending){
  if(value.operation_id!==p.id)throw Error('原操作身份不一致');
  if(value.state!=='completed'||!value.result)throw Error('结果仍为 UNKNOWN，未重新发送。');
  const v=await readJSON<TemplateResult>('/cplus/template-runs/'+encodeURIComponent(value.result.run_id));
  if(v.schema_version!=='template-run-v1'||!uuid.test(v.run_id)||v.run_id!==value.result.run_id||v.revision!==1||v.financial_authority!==false||v.template_version!==p.body.template_version||v.template_id!==p.body.template_id||v.question!==p.body.question||!sameSources(v.selected_sources,p.body.selected_sources)||!Array.isArray(v.financial_points)||!Array.isArray(v.topics)||!Array.isArray(v.findings))throw Error('模板结果范围或版本无法核验');
  if(alive.current){sessionStorage.removeItem(key);setResult(v);setConfirmed(false);setPending(null);setNotFound(false);setMessage('结构化模板结果已保存。')}
 }
 async function submit(){if(lock.current||locked||!valid||!confirmed||!question.trim())return;lock.current=true;
  const p:Pending={id:crypto.randomUUID(),body:{template_id:template,template_version:'cplus-template-v1',question:question.trim(),selected_sources:selected,generate_explanation:generate}};
  try{try{sessionStorage.setItem(key,JSON.stringify(p))}catch{setStorageError(true);throw Error('操作线索无法保存，尚未发送。')}setPending(p);setBusy(true);setNotFound(false);
   const r=await fetch('/api/cplus/template-runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation_id:p.id,...p.body})});
   if(!r.ok)throw Error('操作响应（'+r.status+'），请只读查询原操作。');await consume(await r.json() as Operation,p);
  }catch(e){if(alive.current)setMessage((e as Error).message)}finally{lock.current=false;if(alive.current)setBusy(false)}
 }
 async function recover(){if(!pending||busy)return;setBusy(true);try{const r=await fetch('/api/cplus/template-runs/operations/'+pending.id,{cache:'no-store'});if(r.status===404){setNotFound(true);setMessage('原编号未登记；可保留查询，或明确放弃本机线索。没有重发。');return}if(!r.ok)throw Error('原操作暂不可查询');await consume(await r.json() as Operation,pending)}catch(e){setMessage((e as Error).message)}finally{if(alive.current)setBusy(false)}}
 return <section className="cplus-templates"><h2>四类结构化研究模板</h2><p>cplus-template-v1 · 固定资料后运行真实工具。候选数值始终待核对，AI 解释默认关闭。</p>
 {message&&<p role="status">{message}</p>}{storageError&&<p role="alert">操作线索存储不可用，尚未发送新操作。</p>}
 {pending&&<aside role="alert">模板操作结果待核对 <button disabled={busy} onClick={()=>void recover()}>查询原模板操作</button>{notFound&&<button disabled={busy} onClick={()=>{sessionStorage.removeItem(key);setPending(null);setNotFound(false);setMessage('仅放弃未登记的本机线索。')}}>放弃未登记线索</button>}</aside>}
 <label>模板 <select aria-label="研究模板" disabled={locked} value={template} onChange={e=>{const id=e.target.value as TemplateId;setTemplate(id);setQuestion(templates.find(t=>t.id===id)!.question);setDocs([]);changed()}}>{templates.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
 <fieldset disabled={locked}><legend>{template==='peer'?'明确选择当前企业与第二/第三企业的同年报告（2–3份）':template==='overview'?'明确选择一份年度报告':'明确选择同一企业两份不同年度报告'}</legend>{options.map(s=><label key={s.document_id}><input type="checkbox" checked={docs.includes(s.document_id)} onChange={e=>{setDocs(v=>e.target.checked?[...v,s.document_id]:v.filter(id=>id!==s.document_id));changed()}}/>{name(s.company_id)} · {s.report_year} 年报 · {s.document_id.slice(0,8)}</label>)}{!options.length&&<p>尚无当前可核验来源；请由企业资料页刷新来源。</p>}</fieldset>
 {!valid&&<p>{template==='peer'?'需要包含当前企业的2–3家公司，各一份同年报告；不会自动选择最新报告。':template==='overview'?'请选择一份来源。':'需要同公司两份不同年度报告。'}</p>}
 <label className="cplus-templates__question">研究问题 <textarea disabled={locked} value={question} maxLength={2000} onChange={e=>{setQuestion(e.target.value);changed()}}/></label>
 <label><input type="checkbox" disabled={locked} checked={generate} onChange={e=>{setGenerate(e.target.checked);setConfirmed(false)}}/> 明确请求一次 AI 解释（可能产生模型调用，解释待审）</label>
 <label><input type="checkbox" disabled={locked} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> 我已核对模板、问题与所选来源，确认运行</label>
 <button disabled={locked||!valid||!confirmed||!question.trim()} onClick={()=>void submit()}>运行结构化模板</button>
 {onResearchDraft&&<button disabled={locked||!valid||!question.trim()} onClick={()=>onResearchDraft({companyId,question,documentIds:selected.map(s=>s.document_id),sourceRevisions:selected.map(s=>s.source_revision)})}>另准备研究助手问题</button>}
 {result&&<TemplateRunResult value={result} name={name}/>}
 <details><summary>同比与常用指标释义</summary><p>同比：与上年同期相比的变化率，公式为（本期－上年同期）÷上年同期。分母非正、口径未知或不同、缺少同期输入时不计算；不相邻年份只称期间变化。</p><p>经营现金流是期间经营活动产生的现金流量净额；归母净利润不能与合并净利润混用。方向差异只是程序观察，不能据此推断原因。金额、期间、币种与合并范围仍须本人核对。</p></details>
 </section>
}
