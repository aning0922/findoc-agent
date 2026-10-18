import { manageQASources, finishQASources, openQAHistory } from './qa-helpers.ts';
import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const out=process.env.UX_ARTIFACT_DIR!;
const sources=JSON.parse(readFileSync(`${out}/sources.json`,'utf8'));
let companies:any[], docs:any[]=[];
test.describe.configure({mode:'serial'});
async function counts(page:any) { return (await page.request.get('/api/__test__/d26-counts')).json(); }
async function qa(page:any) {
  await page.goto(`/research?company=${companies.find(c=>c.security_code==='000651').company_id}&mode=qa`);
  const panel=page.getByRole('region',{name:'研究资料选择'});
  await manageQASources(page);
  await panel.getByLabel('显示全部企业，允许共同选择',{exact:true}).check();
  for(const doc of docs){const name=companies.find(c=>c.company_id===doc.company_id).name;
    await panel.getByLabel(`${name} · ${doc.report_year} 年报`,{exact:true}).check();}
  await finishQASources(page);
  await panel.getByLabel('研究问题',{exact:true}).fill('请列四份年报主要会计数据和财务指标原文');
  return panel;
}
test('D26 upload response is lost after actual server commit; refresh remains read only',async({page})=>{
  companies=await (await page.request.get('/api/companies')).json();
  const company=companies.find(c=>c.security_code==='000333');
  const writes:string[]=[];let actual:any;
  page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  await page.request.post('/api/__test__/d26-drop-upload');
  await page.goto(`/research?company=${company.company_id}&mode=operating&new=1`);
  await page.getByLabel('first 期间',{exact:true}).selectOption('2025');
  await page.getByLabel('second 期间',{exact:true}).selectOption('2024');
  await page.getByRole('button',{name:'下一步：准备财报',exact:true}).click();
  await page.getByRole('button',{name:'上传财报',exact:true}).first().click();
  await page.getByLabel('报告年度',{exact:true}).fill('2025');
  await page.getByLabel('PDF 文件',{exact:true}).setInputFiles(sources.find((s:any)=>s.id==='midea-2025').absolute_path);
  await page.getByLabel('核对上传绑定',{exact:true}).check();
  await page.getByRole('button',{name:'提交 PDF 并绑定',exact:true}).click();
  await expect.poll(async()=> (await counts(page)).last_upload.document_id,{timeout:30000}).toBeTruthy();
  await page.getByRole('button',{name:'停止本页等待，转为只读查证',exact:true}).click();
  const alert=page.getByRole('alert').filter({hasText:'上传结果未知'});await expect(alert).toBeVisible();
  await expect(page.getByRole('button',{name:'提交 PDF 并绑定',exact:true})).toBeDisabled();
  const prompt=await alert.innerText();actual=(await counts(page)).last_upload;expect(actual.document_id).toBeTruthy();
  await expect.poll(async()=> (await (await page.request.get(`/api/documents/${actual.document_id}`)).json()).status,{timeout:120000}).toBe('ready');
  await page.getByRole('button',{name:'刷新资料与绑定（只读）',exact:true}).click();
  await page.reload();
  expect(writes).toHaveLength(1);
  const server=await counts(page);expect(server.tables.documents).toBe(1);expect(server.tables.document_sources).toBe(1);
  writeFileSync(`${out}/upload-lost-response-proof.json`,JSON.stringify({actual,prompt,writes,server,automatic_resubmits:0},null,2));
});
test('D26 four original PDF tables retain physical year columns through HTTP saved QA and React tables',async({page})=>{
  companies=await (await page.request.get('/api/companies')).json();
  for(const s of sources){
    const company=companies.find(c=>c.security_code===(s.id.startsWith('gree')?'000651':'000333'));
    const y=Number(s.id.slice(-4));
    const r=await page.request.post('/api/report-documents',{multipart:{file:{name:`${s.id}.pdf`,mimeType:'application/pdf',buffer:readFileSync(s.absolute_path)},metadata:JSON.stringify({company_id:company.company_id,report_year:y,report_type:'annual',basis:'PRC_GAAP',period_start:`${y}-01-01`,period_end:`${y}-12-31`})}});
    expect(r.status()).toBe(202); const id=(await r.json()).document_id;
    await expect.poll(async()=> (await (await page.request.get(`/api/documents/${id}`)).json()).status,{timeout:120000}).toBe('ready');
    const source=await (await page.request.get(`/api/documents/${id}/source`)).json();
    expect(source.content_sha256).toBe(s.sha256); docs.push(source);
  }
  const panel=await qa(page); await panel.getByRole('button',{name:'查找原文',exact:true}).click();
  const answer=panel.getByRole('region',{name:'有证据的回答'}); await expect(answer).toBeVisible();
  const checks:any[]=[];
  for(const [report,y,amount] of [['gree-2024','2024年','189,163,654,064.64'],['gree-2025','2025年','170,447,058,533.57'],['midea-2024','2024年','407,149,600'],['midea-2025','2025年','456,451,731']]){
    const doc=docs.find(d=>d.report_year===Number(String(report).slice(-4)) && d.company_id===companies.find(c=>c.security_code===(String(report).startsWith('gree')?'000651':'000333')).company_id);
    const owner=answer.locator(`[data-document-id="${doc.document_id}"][data-source-revision="${doc.source_revision}"]`);
    const table=owner.getByRole('table').filter({hasText:amount as string}).first();
    const headers=await table.locator('th').allTextContents(); const row=table.locator('tr').filter({hasText:'营业收入'}).first();
    const cells=await row.locator('td').allTextContents();
    expect(headers.indexOf(y as string)).toBe(cells.indexOf(amount as string));
    checks.push({report,headers,cells,aligned:true,source_identity:doc});
  }
  const before=await counts(page); await page.reload(); await expect(panel.getByRole('region',{name:'研究历史详情'})).toBeVisible();
  const history=await (await page.request.get('/api/research/runs?limit=20')).json();
  expect(history.items).toHaveLength(1);
  await openQAHistory(page);
  await panel.getByRole('button',{name:history.items[0].query,exact:true}).click();
  await expect(panel.getByRole('table').first()).toBeVisible();
  expect(await counts(page)).toEqual(before);
  await page.screenshot({path:`${out}/four-tables.png`,fullPage:true});
  writeFileSync(`${out}/four-table-proof.json`,JSON.stringify({checks,docs,before,after:await counts(page),actual_model:false,actual_retrieval:false,actual_pdf_http_sqlite:true,human_review:'pending'},null,2));
});

test('D26 QA response unknown recovers by original operation with zero automatic model calls',async({page})=>{
  const panel=await qa(page);const before=await counts(page);let actual:any;let writes=0;
  await page.route('**/api/research/runs',async route=>{if(route.request().method()!=='POST')return route.continue();writes++;const response=await route.fetch();expect(response.status()).toBe(200);actual=await response.json();await route.abort('failed');});
  await panel.getByRole('button',{name:'查找原文',exact:true}).click();
  const alert=panel.locator('[data-user-state="unknown"]').filter({hasText:'执行状态未知'});await expect(alert).toBeVisible({timeout:30000});
  const prompt=await alert.innerText();await page.reload();
  await page.getByRole('button',{name:'查看这次操作的结果',exact:true}).click();
  await expect(page.getByRole('region',{name:'有证据的回答'})).toBeVisible();
  const after=await counts(page);expect(writes).toBe(1);expect(after.calls.model).toBe(before.calls.model+1);expect(after.tables.research_runs).toBe(before.tables.research_runs+1);
  writeFileSync(`${out}/qa-unknown-proof.json`,JSON.stringify({actual,prompt,writes,before,after,automatic_resubmits:0},null,2));
});

test('D26 saved model connection failure explains recovery and preserves original business error identity',async({page})=>{
  await page.request.post('/api/__test__/d26-model/true');
  const panel=await qa(page);const before=await counts(page);let writes=0;let actual:any;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/research/runs'))writes++;});
  page.on('response',async r=>{if(r.request().method()==='POST'&&r.url().endsWith('/research/runs'))actual=await r.json();});
  await panel.getByRole('button',{name:'查找原文',exact:true}).click();
  const alert=panel.getByRole('alert').filter({hasText:'模型连接失败'});await expect(alert).toBeVisible({timeout:30000});
  expect(await alert.innerText()).toContain('只读');expect(await alert.innerText()).toContain('重新开始研究');
  await panel.getByText('高级诊断：已保存的错误身份',{exact:true}).click();await expect(panel).toContainText('llm_error');
  await expect(panel.getByRole('region',{name:'有证据的回答'})).toHaveCount(0);
  await openQAHistory(page);
  await panel.getByRole('button',{name:'刷新研究历史',exact:true}).click();
  const after=await counts(page);expect(writes).toBe(1);expect(after.calls.model).toBe(before.calls.model+1);
  await page.screenshot({path:`${out}/model-failure.png`,fullPage:true});
  writeFileSync(`${out}/model-failure-proof.json`,JSON.stringify({actual,alert:await alert.innerText(),writes,before,after,automatic_retries:0,actual_vendor:false},null,2));
});

test('D27 QA context budget is distinct from refusal and provider failure; history is GET-only',async({page})=>{
  await page.request.post('/api/__test__/d26-model/false');
  await page.request.post('/api/__test__/d27-budget/true');
  const panel=await qa(page);await panel.getByRole('textbox',{name:'研究问题',exact:true}).fill('请列经营介绍原文');
  const before=await counts(page);let writes=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/research/runs'))writes++;});
  await panel.getByRole('button',{name:'查找原文',exact:true}).click();
  await expect(panel.getByRole('alert').filter({hasText:'上下文预算不足'})).toBeVisible();
  const text=await panel.getByRole('alert').filter({hasText:'上下文预算不足'}).innerText();
  expect(text).toContain('缩小');expect(text).toContain('只读');
  await expect(panel.getByRole('region',{name:'有证据的回答'})).toHaveCount(0);
  const after=await counts(page);expect(after.calls.model).toBe(before.calls.model);expect(after.calls.retrieval).toBe(before.calls.retrieval+1);expect(writes).toBe(1);
  await page.reload();await openQAHistory(page);await panel.getByRole('button',{name:'请列经营介绍原文',exact:true}).first().click();
  await expect(panel.getByRole('alert').filter({hasText:'上下文预算不足'})).toBeVisible();
  expect(await counts(page)).toEqual(after);expect(writes).toBe(1);
  writeFileSync(`${out}/qa-budget-proof.json`,JSON.stringify({text,before,after,writes,model_calls:0,
    normal_refusal:false,actual_http_sqlite:true,actual_model:false,controlled_oversized_retrieval:true},null,2));
});
