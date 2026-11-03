// Actual UI cancel + one intentionally missing owned-generation PDF, no model calls.
import {chromium} from 'playwright';
import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import {randomUUID,createHash} from 'node:crypto';
const origin=process.env.CPLUS_ORIGIN||'http://127.0.0.1:14540';const aiFault=process.env.CPLUS_AI_FAULT==='1';
const out=new URL(`../../data/${process.env.CPLUS_BATCH_OUT||'cplus-batch-live-controls'}/`,import.meta.url);await mkdir(out,{recursive:true});
const root=new URL('../../',import.meta.url);
const config=Object.fromEntries((await readFile(new URL('data/showcase-local.env',root),'utf8')).split('\n').filter(x=>x&&!x.startsWith('#')).map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1)]}));
const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(45000);
const proof={tier:'REAL_CHROME_SOCKET_HTTP_PUBLIC_PDF_BGE_LIVE_CANCEL_AND_OWNED_FILE_FAULT',provider_calls:aiFault?null:0,provider_calls_allowed:aiFault?4:0,human_financial_approvals:0,checks:[]};
const save=()=>writeFile(new URL('result.json',out),JSON.stringify(proof,null,2));
function check(value,message){if(!value)throw Error(message);proof.checks.push(message);console.log('PASS',message)}
async function api(method,path,body){const response=await page.request.fetch(origin+'/api'+path,{method,data:body,headers:{Origin:origin},timeout:180000});if(!response.ok())throw Error(`${method} ${path}: ${response.status()} ${(await response.text()).slice(0,240)}`);return response.json()}
let held=null,original=null;
try{
 for(let i=0;i<240;i++){if((await api('GET','/demo/status')).service_state==='ready')break;await page.waitForTimeout(500)}
 await page.goto(origin);await page.getByLabel('账号',{exact:true}).fill(config.DEMO_USERNAME);await page.getByLabel('密码',{exact:true}).fill(config.DEMO_PASSWORD);await page.getByRole('button',{name:'进入演示',exact:true}).click();await page.locator('.sd-kpis').waitFor({timeout:120000});
 const session=await api('GET','/demo/session');const companies=await api('GET','/companies');const selected=companies.filter(c=>['000651','000333'].includes(c.security_code));const gree=selected.find(c=>c.security_code==='000651');
 const sources=[];for(const doc of await api('GET','/documents')){if(doc.status!=='ready')continue;const ref=await api('GET',`/cplus/documents/${doc.document_id}/research-source`);if(selected.some(c=>c.company_id===ref.company_id))sources.push(ref)}
 check(sources.length===4,'four current real company/year sources');
 await api('POST','/cplus/retrieval/builds',{operation_id:randomUUID(),sources});
 await page.goto(origin+'/conversations');await page.getByText('批量研究 · 两家公司 × 两类原文任务',{exact:true}).click();await page.getByRole('button',{name:'读取批量研究资料',exact:true}).click();const batch=page.locator('.cplus-batch');
 for(const company of selected)await batch.getByRole('checkbox',{name:new RegExp(company.name)}).check();
 for(const company of selected){const group=batch.getByRole('group',{name:company.name+'：明确选择两份报告',exact:true});for(const box of await group.getByRole('checkbox').all())await box.check()}
 await batch.getByRole('button',{name:'准备 2×2 计划',exact:true}).click();await batch.getByRole('heading',{name:'确认计划',exact:true}).waitFor();
 const startedAt=Date.now();const [response]=await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/cplus/batches')&&r.request().method()==='POST'),batch.getByRole('button',{name:'批准并开始',exact:true}).click()]);const ack=await response.json();proof.ack=ack;proof.ack_ms=Date.now()-startedAt;await save();
 check(ack.state==='completed'&&ack.result.dispatch_acknowledged===true&&ack.result.state==='running','start acknowledges live matrix before research finishes');
 const id=ack.result.batch_id;let running;for(let n=0;n<120;n++){running=await api('GET',`/cplus/batches/${id}`);if(running.cells.some(c=>c.state==='dispatching'))break;await page.waitForTimeout(100)}
 await batch.getByText('正在执行 · 报告年度',{exact:false}).first().waitFor();check(running.cells.filter(c=>c.state==='queued').length===3,'real first tool is active while three cells wait');
 await batch.getByRole('button',{name:'取消未开始项',exact:true}).click();let cancelled;for(let n=0;n<480;n++){cancelled=await api('GET',`/cplus/batches/${id}`);if(cancelled.state!=='running')break;await page.waitForTimeout(250)}proof.cancel_matrix=cancelled;await save();
 check(cancelled.cells.filter(c=>c.state==='cancelled').length===3&&cancelled.cells.filter(c=>c.state==='completed').length===1,'native cancellation stops only three queued tasks and preserves active result');await batch.getByRole('heading',{name:'执行状态 · 部分完成',exact:true}).waitFor();await page.screenshot({path:new URL('cancelled-matrix-1440.png',out).pathname,fullPage:true});
 const cells=selected.flatMap(c=>{const refs=sources.filter(s=>s.company_id===c.company_id).sort((a,b)=>a.report_year-b.report_year);return[{cell_key:c.company_id+':risk',company_id:c.company_id,template:'risk_excerpt',sources:[refs.find(r=>r.report_year===2025)]},{cell_key:c.company_id+':annual',company_id:c.company_id,template:'annual_changes',sources:refs}]});
 const planned=await api('POST','/cplus/batch-plans',{operation_id:randomUUID(),preparation_confirmed:true,cells,generate_explanations:aiFault});const plan=planned.result;
 const began=await api('POST','/cplus/batches',{operation_id:randomUUID(),batch_plan_id:plan.batch_plan_id,batch_plan_revision:plan.revision,batch_plan_sha256:plan.batch_plan_sha256,confirmed:true});const faultId=began.result.batch_id;
 const faultSource=sources.find(s=>s.company_id===gree.company_id&&s.report_year===2024);
 const control=process.env.CPLUS_CONTROL_RELATIVE||'data/showcase-local-controller-v1';if(!/^data\/[a-z0-9/-]+showcase-local-controller-v1$/.test(control)&&control!=='data/showcase-local-controller-v1')throw Error('owned_control_root_required');original=new URL(`${control}/active/${session.lease_generation}/objects/documents/${faultSource.document_id}.pdf`,root);held=new URL(original.href+'.owned-fault-hold');
 const before=await readFile(original);check(createHash('sha256').update(before).digest('hex')===faultSource.content_sha256,'fault targets exactly this new generation public PDF, not immutable seed');
 await rename(original,held);proof.fault={document_id:faultSource.document_id,generation:session.lease_generation,batch_id:faultId,source_sha256:faultSource.content_sha256};await save();
 let matrix;for(let n=0;n<720;n++){matrix=await api('GET',`/cplus/batches/${faultId}`);if(matrix.state!=='running')break;await page.waitForTimeout(250)}proof.fault_matrix=matrix;await save();
 check(matrix.cells.filter(c=>c.state==='unknown').length===1&&matrix.cells.filter(c=>c.state==='completed').length===3,'one missing source affects only its annual task; three real tool cells finish');
 if(!aiFault)check(matrix.cells.every(c=>c.cost_observed_or_reserved.mode==='pure_tools'&&c.cost_observed_or_reserved.provider_calls===0),'per-cell cost explicitly records pure tools, no paid model claim');else{check(matrix.cells.every(c=>c.cost_observed_or_reserved.mode==='ai_review'),'AI cells retain explicit per-call upper bound and do not invent observed cost');proof.returned_ai_cells=matrix.cells.filter(c=>c.result?.result?.payload?.interpretation||c.result?.result?.payload?.provider_outcome==='returned').length;check(proof.returned_ai_cells===3,'three unaffected cells contain real returned AI explanations');}
 await rename(held,original);held=null;check(createHash('sha256').update(await readFile(original)).digest('hex')===faultSource.content_sha256,'owned PDF restored byte-for-byte');
 const again=await api('GET',`/cplus/batches/${faultId}`);check(JSON.stringify(again)===JSON.stringify(matrix),'readonly saved matrix does not redispatch unknown or completed cells');
 await batch.getByText('已保存批次',{exact:true}).click();await batch.getByRole('button',{name:'读取批次历史',exact:true}).click();const history=await api('GET','/cplus/batches');check(history.items.some(x=>x.batch_id===faultId)&&history.items.some(x=>x.batch_id===id),'saved batches are discoverable without mutation');
 await batch.getByRole('button',{name:/4 项 · 部分完成/}).first().click();await batch.getByText('本格未完成：',{exact:false}).waitFor();await page.screenshot({path:new URL('one-fault-three-results-1440.png',out).pathname,fullPage:true});
 proof.result='PASS';await save();
}catch(error){proof.result='FAIL';proof.error=String(error);proof.visible_text=(await page.locator('body').innerText()).slice(0,6000);await page.screenshot({path:new URL('failure.png',out).pathname,fullPage:true});await save();console.error(String(error));process.exitCode=1}
finally{if(held&&original){await rename(held,original);proof.held_file_restored_in_cleanup=true}try{await api('POST','/demo/logout',{operation_id:randomUUID()})}catch{}await browser.close();await save()}
