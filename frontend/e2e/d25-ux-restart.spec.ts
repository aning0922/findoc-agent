import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const proof = JSON.parse(readFileSync(process.env.INTEGRATION_REPORT_PROOF!, 'utf8'));
test('new process restores immutable v1/v2 using GET only', async ({ page }) => {
  // Production rejects simulated receipts. Use the existing isolated UI entry,
  // exactly as the D23 history suite; all page components remain unchanged.
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const mutations: string[] = [];
  page.on('request', r => { if (['POST','PUT','PATCH','DELETE'].includes(r.method())) mutations.push(r.url()); });
  const rid = proof.saved.report.report_id;
  await page.goto(`/reports?report=${rid}&revision=2`);
  const article = page.getByRole('article', { name: '已保存报告版本' });
  await expect(article).toContainText('集成 v2 用户断言');
  await expect(page.getByLabel('读取指定版本')).toHaveValue('2');
  await page.getByLabel('读取指定版本').selectOption('1');
  await expect(article).toContainText('集成 v1 用户断言');
  await expect(article).not.toContainText('集成 v2 用户断言');
  await page.reload();
  await expect(article).toContainText('集成 v1 用户断言');
  for (const width of [1440,1280,1024,512]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({path:`${process.env.INTEGRATION_RESTART_OUT}/restart-v1-${width}.png`});
  }
  expect(mutations).toEqual([]);
  writeFileSync(`${process.env.INTEGRATION_RESTART_OUT}/browser-proof.json`,JSON.stringify({simulated_test:true,human_acceptances:0,mutations,v1_restored:true,v2_restored:true,selected_v1_reload:true},null,2));
});

test('four-source QA selection and saved model connection error remain explicit', async ({ page }) => {
  const out = process.env.INTEGRATION_RESTART_OUT!;
  const upload = JSON.parse(readFileSync(`${process.env.INTEGRATION_REPORT_PROOF!.replace('guided-report-proof.json','upload-proof.json')}`, 'utf8'));
  const docs = upload.receipts.map((r: any) => ({...r.meta, status:'ready',selectable:true,reason:null}));
  let payload: any;
  await page.route('**/api/research/sources', r => r.fulfill({json:{schema_version:'research-source-options-v1',max_selected_documents:4,documents:docs}}));
  await page.route('**/api/research/runs?**',r=>r.fulfill({json:{schema_version:'research-history-v1',items:[],next_cursor:null}}));
  await page.route('**/api/research/runs',r=>{
    payload=r.request().postDataJSON();
    const sources=upload.receipts.map((v:any)=>v.source);
    return r.fulfill({json:{schema_version:'research-run-v1',run_id:'11111111-1111-4111-8111-111111111111',operation_id:payload.operation_id,query:payload.query,document_ids:payload.document_ids,documents:sources,status:'system_error',created_at:'2026-10-12T00:00:00Z',ended_at:'2026-10-12T00:00:01Z',result:{schema_version:'research-answer-v1',selection_id:'a'.repeat(64),outcome:'system_error',error_code:'llm_error',content:'',citations:[],documents:sources},historical_snapshot:true,integrity_sha256:'b'.repeat(64),source_states:sources.map((s:any)=>({document_id:s.document_id,source_revision:s.source_revision,status:'current_at_read'}))}});
  });
  await page.goto(`/research?company=${docs[0].company_id}&mode=qa`);
  const panel=page.getByRole('region',{name:'研究资料选择'});
  await panel.getByLabel('显示全部企业，允许共同选择',{exact:true}).check();
  const companies=await (await page.request.get('/api/companies')).json();
  for(const doc of docs) {
    const name=companies.find((c:any)=>c.company_id===doc.company_id).name;
    await panel.getByLabel(`${name} · ${doc.report_year} 年报 · ready`,{exact:true}).check();
  }
  await expect(panel).toContainText('已选择 4 / 4 份');
  await panel.getByLabel('研究问题',{exact:true}).fill('请列四份年报营业收入原文');
  await panel.getByRole('button',{name:'开始研究',exact:true}).click();
  const error=panel.getByRole('alert');
  await expect(error).toContainText('系统错误（已保存）：llm_error');
  await expect(panel.getByRole('region',{name:'有证据的回答'})).toHaveCount(0);
  expect(payload.document_ids.sort()).toEqual(docs.map((d:any)=>d.document_id).sort());
  await page.screenshot({path:`${out}/qa-connection-error.png`});
  writeFileSync(`${out}/qa-error-observation.json`,JSON.stringify({controlled_protocol:true,actual_model:false,simulated_test:true,human_acceptances:0,selected_documents:payload.document_ids,visible_alert:await error.innerText(),business_recovery_hint_complete:false},null,2));
});
