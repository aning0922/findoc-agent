// Root-invoked finite evaluation through the actual gateway. No provider key in this process.
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { runFixedIntentEval } from './showcase-intent-eval.mjs';
const base=process.env.DEMO_CHECK_ORIGIN,out=process.env.DEMO_CHECK_OUTPUT;
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage();page.setDefaultTimeout(45000);let financial=0;
 page.on('request',r=>{if(r.method()==='POST'&&/confirmations|persisted|\/resume$/.test(new URL(r.url()).pathname))financial++;});
 await page.goto(base);await page.getByLabel('账号',{exact:true}).fill(process.env.DEMO_CHECK_USERNAME);await page.getByLabel('密码',{exact:true}).fill(process.env.DEMO_CHECK_PASSWORD);await page.getByRole('button',{name:'进入演示',exact:true}).click();await page.getByRole('heading',{name:'研究概览',exact:true}).waitFor();
 const api=async(path,method='GET',body)=>page.evaluate(async({path,method,body})=>{const r=await fetch('/api'+path,{method,...(body?{headers:{'Content-Type':'application/json','X-Operation-ID':body.operation_id||crypto.randomUUID()},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(`HTTP${r.status}: ${JSON.stringify(value)}`);return value;},{path,method,body});
 const companies=await api('/companies'),sources=await api('/research/sources');
 api.sourceFixtures={};api.evidenceTier='REAL_HTTP_PUBLIC_PDF_REAL_BGE_REAL_LLM_INTENT_ONLY';
 for(const doc of sources.documents.filter(d=>d.selectable)){const code=companies.find(c=>c.company_id===doc.company_id)?.security_code;const alias=code==='000651'?'gree':code==='000333'?'midea':null;if(alias)api.sourceFixtures[`${alias}-${doc.report_year}`]=doc.document_id;}
 const result=await runFixedIntentEval(page,base,api,out);
 const cid=(await api('/conversations','POST',{operation_id:randomUUID(),document_ids:[api.sourceFixtures['gree-2025']],title:'财务任务交接真实HTTP验证'})).conversation_id;
 const intent=await api('/research/intent','POST',{operation_id:randomUUID(),conversation_id:cid,text:'比较格力2025和2024年营业收入，准备研究任务。',requested_mode:'synthesis'});
 const op=randomUUID();let handoff;
 try{handoff=await api('/research/handoffs','POST',{operation_id:op,conversation_id:cid,intent_id:intent.intent_id,confirmed:true});const recovered=await api(`/research/operations/${op}`);if(recovered.result?.task_id!==handoff.task_id)throw Error('handoff recovery mismatch');}
 catch(e){handoff={state:'failed_or_unknown',error:String(e),operation_id:op};}
 await writeFile(`${out}/c02-real-handoff.json`,JSON.stringify({intent,handoff,human_financial_approvals:financial},null,2));
 if(financial!==0)throw Error('Financial signer boundary violated');
 const output={evidence:api.evidenceTier,denominators:result.denominators,handoff,human_financial_approvals:0};await writeFile(`${out}/browser-result.json`,JSON.stringify(output,null,2));console.log(JSON.stringify(output));
}finally{await browser.close();}
