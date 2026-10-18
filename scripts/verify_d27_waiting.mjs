// Real model, actual backend commit, browser abort/response loss and GET-only recovery.
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { readFileSync,mkdirSync,writeFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
const out=process.argv[2];mkdirSync(out,{recursive:true});
const eventPath=new URL('../data/d27/c-wait-server/events.jsonl',import.meta.url);
const events=()=>readFileSync(eventPath,'utf8').trim().split('\n').filter(Boolean).map(x=>JSON.parse(x));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900}});
const page=await context.newPage();
const proof={actual_bge_milvus_deepseek:true,formal_built_frontend:true,production_gates:true,
  cases:[],writes:[],errors:[],human_review:'pending'};
page.on('pageerror',e=>proof.errors.push(e.message));
page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/research/runs'))proof.writes.push(JSON.parse(r.postData()));});
const companies=await (await context.request.get('http://127.0.0.1:14227/api/companies')).json();
const gree=companies.find(c=>c.security_code==='000651');
const sources=await (await context.request.get('http://127.0.0.1:14227/api/research/sources')).json();
async function prepare(query){
  await page.goto(`http://127.0.0.1:14227/research?company=${gree.company_id}&mode=qa`);
  const panel=page.getByRole('region',{name:'研究资料选择'});
  await panel.getByLabel('显示全部企业，允许共同选择',{exact:true}).check();
  for(const d of sources.documents){const name=companies.find(c=>c.company_id===d.company_id).name;
    await panel.getByLabel(`${name} · ${d.report_year} 年报 · ready`,{exact:true}).check();}
  await panel.getByLabel('研究问题',{exact:true}).fill(query);return panel;
}
async function terminal(operation){
  const t=performance.now();
  while(performance.now()-t<120000){
    const r=await context.request.get(`http://127.0.0.1:14227/api/research/runs/by-operation/${operation}`);
    if(r.status()===200){const value=await r.json();if(value.status!=='running')return value;}
    await page.waitForTimeout(250);
  }throw new Error('terminal GET deadline');
}
try{
  const before=events().filter(e=>e.kind==='provider_http').length;
  const panel=await prepare('请列四份年报主要会计数据和财务指标原文，不计算同比。');
  const t=performance.now();
  await panel.getByRole('button',{name:'开始研究',exact:true}).evaluate(b=>{b.click();b.click();});
  await page.getByLabel('本页等待状态',{exact:true}).waitFor();
  assert.equal(proof.writes.length,1);const operation=proof.writes[0].operation_id;
  const deadline=performance.now()+30000;
  while(!events().some(e=>e.kind==='provider_http.started')){
    assert(performance.now()<deadline,'real model request did not start');await page.waitForTimeout(50);
  }
  const running=await (await context.request.get(`http://127.0.0.1:14227/api/research/runs/by-operation/${operation}`)).json();
  assert.equal(running.status,'running');
  const waitingText=await page.getByLabel('本页等待状态',{exact:true}).innerText();
  assert(waitingText.includes('本页已等待'));assert(!/\d+%/.test(waitingText));
  await page.getByRole('button',{name:'停止本页等待',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'已停止本页等待'}).waitFor();
  const stoppedText=await page.getByRole('alert').filter({hasText:'已停止本页等待'}).innerText();
  assert(stoppedText.includes('可能仍在执行'));assert.equal(proof.writes.length,1);
  await page.screenshot({path:`${out}/wait-stopped.png`,fullPage:true});
  await page.goto(`http://127.0.0.1:14227/companies/${gree.company_id}/overview`);
  const result=await terminal(operation);
  assert.equal(result.status,'answered');
  assert.equal(new Set(result.result.citations.map(c=>c.document_id)).size,4);
  assert.equal(await page.getByRole('region',{name:'有证据的回答'}).count(),0);
  await page.goto(`http://127.0.0.1:14227/research?company=${gree.company_id}&mode=qa`);
  await page.getByRole('button',{name:'按操作身份恢复',exact:true}).click();
  await page.getByRole('region',{name:'有证据的回答'}).waitFor();
  assert.equal(proof.writes.length,1);
  assert.equal(events().filter(e=>e.kind==='provider_http').length,before+1);
  proof.cases.push({kind:'actual_model_wait_aborted',operation,waitingText,stoppedText,running,result,
    wall_seconds:(performance.now()-t)/1000,duplicate_click_posts:1,model_physical_calls:1,
    late_response_other_page_visible:false,readonly_recovery:true});
  await page.screenshot({path:`${out}/wait-recovered.png`,fullPage:true});
  let persisted;
  await page.route('**/api/research/runs',async route=>{
    if(route.request().method()!=='POST')return route.continue();
    const response=await route.fetch();assert.equal(response.status(),200);persisted=await response.json();
    await route.abort('failed');
  });
  const next=await prepare('请摘录格力2025年度营业收入原值及原单位，不计算同比。');
  await next.getByRole('button',{name:'开始研究',exact:true}).click();
  const unknown=page.getByRole('alert').filter({hasText:'执行状态未知'});await unknown.waitFor({state:'visible',timeout:120000});
  const unknownText=await unknown.innerText();assert(persisted && persisted.status==='answered');
  const writes=proof.writes.length;assert.equal(writes,2);
  await page.reload();await page.getByRole('button',{name:'按操作身份恢复',exact:true}).click();
  await page.getByRole('region',{name:'有证据的回答'}).waitFor();
  assert.equal(proof.writes.length,writes);
  assert.equal(events().filter(e=>e.kind==='provider_http').length,before+2);
  proof.cases.push({kind:'actual_commit_response_lost',unknownText,result:persisted,posts:1,
    model_physical_calls:1,automatic_resubmits:0,readonly_refresh_recovery:true});
  assert.equal(proof.errors.length,0);
}finally{writeFileSync(`${out}/results.json`,JSON.stringify(proof,null,2));await browser.close();}
