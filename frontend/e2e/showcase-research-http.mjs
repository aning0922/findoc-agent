// Explicit real provider validation. Server-only config and one shared 5 CNY ledger.
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
import { preparePublicSeed } from './showcase-seed-prep.mjs';
const base=process.env.DEMO_CHECK_ORIGIN,out=process.env.DEMO_CHECK_OUTPUT;
const assert=(v,m)=>{if(!v)throw Error(m);};
const browser=await chromium.launch({headless:true});
const evidence={evidence:'REAL_CHROMIUM_HTTP_REAL_PDF_BGE_LLM',jobs:[],human_financial_approvals:0,browser_errors:[]};
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000},recordVideo:{dir:out,size:{width:1280,height:720}}});page.setDefaultTimeout(45000);
 page.on('pageerror',e=>evidence.browser_errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&/confirmations|persisted|\/resume$/.test(new URL(r.url()).pathname))evidence.human_financial_approvals++;});
 await page.goto(base);await page.getByLabel('账号',{exact:true}).fill(process.env.DEMO_CHECK_USERNAME);await page.getByLabel('密码',{exact:true}).fill(process.env.DEMO_CHECK_PASSWORD);await page.getByRole('button',{name:'进入演示',exact:true}).click();await page.getByRole('heading',{name:'研究概览',exact:true}).waitFor();
 async function api(path,body){return page.evaluate(async({path,body})=>{const r=await fetch(`/api${path}`,{...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Operation-ID':body.operation_id||crypto.randomUUID()},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(`${path} HTTP${r.status}: ${JSON.stringify(value)}`);return value;},{path,body});}
 const sources=await api('/research/sources');const doc=sources.documents.find(d=>d.selectable&&d.report_year===2025);assert(doc,'public ready source');
 const cid=(await api('/conversations',{operation_id:crypto.randomUUID(),document_ids:[doc.document_id]})).conversation_id;
 const text='请根据格力2025年报总结主要经营风险，只要原文与解释，不要计算。';
 const ui=process.env.DEMO_CHECK_RESEARCH_UI==='1';
 for(const mode of ['synthesis','deep']){
  const start=Date.now();const op=crypto.randomUUID();
  let workflow;
  async function uiPost(path,button){const [r]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`/api${path}`),button.click()]);const value=await r.json();assert(r.ok(),`UI ${path} HTTP${r.status()}`);return value;}
  if(ui){await page.goto(`${base}/conversations?${new URLSearchParams({conversation:cid,question:text})}`);await page.locator('.sr-modes button').filter({hasText:mode==='deep'?'深度研究':'综合研究'}).click();workflow=page.locator('.sr-workflow');await workflow.getByLabel('研究问题',{exact:true}).fill(text);}
  const intent=ui?await uiPost('/research/intent',workflow.getByRole('button',{name:'明确解析意图',exact:true})):await api('/research/intent',{operation_id:op,conversation_id:cid,text,requested_mode:mode});
  const record={mode,intent};evidence.jobs.push(record);await writeFile(`${out}/research-progress.json`,JSON.stringify(evidence,null,2));
  assert(intent.mode===mode&&!intent.clarifying_question,'explicit mode and resolved source');
  const plan=ui?await uiPost('/synthesis/plans',workflow.getByRole('button',{name:'明确准备研究计划',exact:true})):await api('/synthesis/plans',{operation_id:crypto.randomUUID(),intent_id:intent.intent_id});record.plan=plan;
  if(ui)await workflow.getByRole('checkbox',{name:'我已阅读并确认此计划',exact:true}).check();
  const started=ui?await uiPost(mode==='deep'?'/deep-research/jobs':'/synthesis/jobs',workflow.getByRole('button',{name:'确认并开始研究',exact:true})):await api(mode==='deep'?'/deep-research/jobs':'/synthesis/jobs',{operation_id:crypto.randomUUID(),approved_plan_id:plan.plan_id,approved_plan_revision:plan.revision,approved_plan_sha256:plan.plan_sha256,confirmed:true});
  const prefix=mode==='deep'?'/deep-research/jobs':'/synthesis/jobs';let job;
  for(let n=0;n<600;n++){job=await api(`${prefix}/${started.job_id}`);if(!['queued','running'].includes(job.state))break;await page.waitForTimeout(400);}
  record.job=job;record.events=await api(`${prefix}/${started.job_id}/events?after_seq=0`);record.elapsed_ms=Date.now()-start;
  await writeFile(`${out}/research-progress.json`,JSON.stringify(evidence,null,2));
  assert(job.state==='completed',`${mode} must publish verified completed job; ${job.state}/${job.error_code}`);
  assert(job.result.findings.some(f=>f.kind==='sourced_excerpt'),'exact source quote exists');
  assert(job.result.findings.some(f=>f.kind==='model_interpretation'),'real interpretation exists');
  assert(!job.result.findings.some(f=>f.kind==='confirmed_financial'),'no invented human confirmation');
  assert(record.events.events.length>=3,'durable actual stages');
  if(mode==='deep')assert(job.steps.length===2&&new Set(job.steps.map(s=>s.agent_id)).size===2&&job.steps.every(s=>s.tools.length),'two actual role tool handoffs');
  if(ui){
   await workflow.getByRole('button',{name:'准备报告草稿',exact:true}).waitFor();
   for(const width of [1440,1280,390]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:`${out}/${mode}-${width}.png`,fullPage:false});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${mode} overflow ${width}`);}
   await page.setViewportSize({width:1440,height:1000});
   await uiPost('/showcase-reports/drafts',workflow.getByRole('button',{name:'准备报告草稿',exact:true}));
   await workflow.getByLabel('报告标题',{exact:true}).fill(`格力2025经营风险 · ${mode==='deep'?'双 Agent':'单 Agent'}真实研究`);
   await workflow.getByLabel('备注',{exact:true}).fill('公开年报实际模型运行。AI解释待审，无财务真人确认。');
   record.report=await uiPost('/showcase-reports',workflow.getByRole('button',{name:'明确创建报告',exact:true}));
  }

 }
 const deep=evidence.jobs[1].job;
 let report=evidence.jobs[1].report;
 if(!report){const draft=await api('/showcase-reports/drafts',{operation_id:crypto.randomUUID(),job_id:deep.job_id});report=await api('/showcase-reports',{operation_id:crypto.randomUUID(),draft_id:draft.draft_id,title:'格力2025经营风险研究 · 实际模型候选',notes:'真实公开年报；AI解释待审核，未产生财务人工确认。'});}
 const revision=await api(`/showcase-reports/${report.report_id}/revisions/1`);
 const edit=await api(`/showcase-reports/${report.report_id}/revisions`,{operation_id:crypto.randomUUID(),expected_revision:1,title:report.title,notes:report.notes+'\n演示备注版本2。'});
 assert(edit.revision===2&&(await api(`/showcase-reports/${report.report_id}/revisions/1`)).notes===report.notes,'immutable historical version');
 evidence.report={report_id:report.report_id,revision:edit.revision,current_source_status:revision.current_source_status};
 const printUrl=`${base}/api/showcase-reports/${report.report_id}/revisions/2/print`;await page.goto(printUrl);await page.getByRole('heading',{level:1,name:report.title}).waitFor();
 const sourceHref=await page.getByRole('link',{name:/原 PDF/}).first().getAttribute('href');assert(sourceHref&&sourceHref.includes(doc.document_id),'print link source');
 const pdfSource=await page.request.get(new URL(sourceHref,base).href);assert(pdfSource.status()===200&&pdfSource.headers()['content-type'].includes('pdf'),'real source PDF access');
 await page.screenshot({path:`${out}/report-print-1440.png`,fullPage:true});await page.pdf({path:`${out}/real-research-report.pdf`,format:'A4',printBackground:true});
 if(ui){
  await page.goto(`${base}/conversations?${new URLSearchParams({conversation:cid,research_mode:'synthesis',question:'比较格力2025和2024年营业收入，准备研究任务。'})}`);
  const workflow=page.locator('.sr-workflow');
  const awaitPost=async(path,button)=>{const [response]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===`/api${path}`),button.click()]);const value=await response.json();assert(response.ok(),`C02 ${path} HTTP${response.status()}`);return value;};
  await awaitPost('/research/intent',workflow.getByRole('button',{name:'明确解析意图',exact:true}));
  const handoff=await awaitPost('/research/handoffs',workflow.getByRole('button',{name:'明确准备财务核对任务',exact:true}));assert(handoff.task_status==='awaiting_human_confirmation'&&handoff.automatic_confirmation===false&&handoff.automatic_resume===false,'old real task waits for human');evidence.handoff=handoff;
  await workflow.getByRole('link',{name:'进入研究任务，由真人核对 →',exact:true}).click();await page.waitForURL(/task=/);await page.screenshot({path:`${out}/c02-task-human-boundary.png`,fullPage:false});
 }
 if(process.env.DEMO_CHECK_PREPARE_SEED==='1')evidence.seed_preparation=await preparePublicSeed(page,base,api,out);
 assert(evidence.human_financial_approvals===0&&evidence.browser_errors.length===0,'no signing/browser errors');
 evidence.completed=true;await writeFile(`${out}/browser-result.json`,JSON.stringify(evidence,null,2));console.log(JSON.stringify({evidence:evidence.evidence,completed:true,job_ids:evidence.jobs.map(x=>x.job.job_id),calls:evidence.jobs.map(x=>x.job.usage),report:evidence.report,human_financial_approvals:0}));
}catch(e){const current=browser.contexts()[0]?.pages()[0];if(current){await current.screenshot({path:`${out}/failure-ui.png`,fullPage:true}).catch(()=>{});await writeFile(`${out}/failure-ui.txt`,await current.locator('body').innerText().catch(()=>''));}evidence.completed=false;evidence.failure=String(e);await writeFile(`${out}/research-progress.json`,JSON.stringify(evidence,null,2));throw e;}finally{await browser.close();}
