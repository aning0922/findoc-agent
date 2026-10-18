import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { verifyReportJourney } from '../tests/support/d24-ux-report-journey.ts';
import { generateReview, returnToReview } from './financial-review-helpers.ts';
const out = process.env.D29_ARTIFACT_DIR!;
process.env.UX_ARTIFACT_DIR = out;
const manifest = JSON.parse(readFileSync(`${out}/manifest.json`, 'utf8'));
const metrics = ['revenue', 'net_profit_parent', 'operating_cash_flow'];
const company = (code: string) => manifest.companies.find((c: any) => c.security_code === code).company_id;
const report = (id: string) => manifest.reports.find((r: any) => r.report_id === id).source;
const evidence = (s: any, mode = '', receipt = '') => `/evidence?${new URLSearchParams({ company: s.company_id, document: s.document_id, revision: s.source_revision, ...(mode ? { record: mode } : {}), ...(receipt ? { receipt, fact_set: mode === 'read' ? receipt : '' } : {}) })}`;
function watch(page: Page) { const writes: string[] = []; page.on('request', r => { if (['POST', 'PUT', 'DELETE'].includes(r.method()) && r.url().includes('/api/')) writes.push(new URL(r.url()).pathname); }); return writes; }
async function shot(page: Page, label: string) {
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await expect(page.locator('main')).toBeVisible();
    if (label === 'saved-record' || label === 'unknown-recovered') await returnToReview(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: `${out}/${label}-${width}.png` });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
async function dual(page: Page, initial = '') {
  await page.goto(`/research?mode=operating&new=1&company=${initial}`);
  await page.getByRole('button', { name: /两企业同期间比较/ }).click();
  await page.getByLabel('first 企业', { exact: true }).selectOption(company('000333'));
  await expect(page.getByRole('button', { name: /两企业同期间比较/ })).toHaveAttribute('aria-pressed', 'true');
  await page.getByLabel('second 企业', { exact: true }).selectOption(company('000651'));
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
}
async function sourceStage(page: Page, a = 'midea-2025', b = 'gree-2025') {
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await page.getByLabel('first 年报', { exact: true }).selectOption(report(a).document_id);
  await page.getByLabel('second 年报', { exact: true }).selectOption(report(b).document_id);
  await page.getByRole('button', { name: '下一步：确认来源', exact: true }).click();
  for (let i = 0; i < 2; i++) await page.locator('.operating-side').nth(i).getByRole('button', { name: '采用这组三项来源', exact: true }).click();
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeEnabled();
}
async function singleTask(page: Page) {
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await sourceStage(page, 'midea-2025', 'midea-2024');
  const response = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/research/tasks');
  await page.getByRole('button', { name: '创建研究，开始核对数据', exact: true }).click();
  const t = await (await response).json();
  await expect(page.getByRole('region', { name: '六项事实准备状态' })).toBeVisible();
  return t;
}
async function reviewDialog(page: Page, id = 'midea-2025') {
  await page.goto(evidence(report(id), 'new'));
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30000 });
  const review = await generateReview(page);
  await returnToReview(page);
  await page.getByRole('button', { name: '确认本组数据', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '人工核对确认', exact: true });
  await expect(dialog.getByLabel('我已逐项核对原 PDF，并明确接受本次审阅内容')).not.toBeChecked();
  return { dialog, review };
}
async function accept(page: Page, id = 'midea-2025') {
  const { dialog } = await reviewDialog(page, id);
  await dialog.getByLabel('我已逐项核对原 PDF，并明确接受本次审阅内容').check();
  const response = page.waitForResponse(r => r.url().endsWith('/financial-facts/confirmations') && r.request().method() === 'POST');
  await dialog.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  const receipt = await (await response).json();
  await expect(page.getByTestId('acceptance-result')).toContainText('自动化模拟接受凭证');
  expect(receipt.confirmation_kind).toBe('simulated_test');
  return receipt;
}

test.beforeEach(async ({ page }) => {
  await page.route('**/src/main.tsx*', r => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
});

test('D29-D native single and dual explicit consent through v1 v2 and S6 repeat-download',async({page})=>{
  test.setTimeout(240000);
  const writes=watch(page),proof:any[]=[],recoveryReads:string[]=[];page.on('request',r=>{if(r.method()==='GET'&&r.url().includes('/research/tasks/by-operation/'))recoveryReads.push(r.url());});
  for(const comparison of [false,true]){
    let task:any;
    if(!comparison)task=await singleTask(page);
    else{await dual(page);await sourceStage(page);const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/research/tasks');await page.getByRole('button',{name:'创建研究，开始核对数据',exact:true}).click();task=await(await response).json();}
    const groups:any[]=[];
    for(const id of (comparison?['gree-2025']:['midea-2024','midea-2025'])){
      let receipt:any;
      if(!comparison&&id==='midea-2024'){
        const {dialog}=await reviewDialog(page,id),count=writes.length,start=await(await page.request.get('/api/__test__/d29-readonly-state')).json();
        await dialog.getByRole('button',{name:'取消审阅',exact:true}).click();expect(writes.length).toBe(count);expect(await(await page.request.get('/api/__test__/d29-readonly-state')).json()).toEqual(start);
        await page.getByRole('button',{name:'确认本组数据',exact:true}).click();const again=page.getByRole('dialog',{name:'人工核对确认',exact:true});await expect(again.getByRole('checkbox')).not.toBeChecked();await again.getByRole('checkbox').check();
        const response=page.waitForResponse(r=>r.url().endsWith('/financial-facts/confirmations')&&r.request().method()==='POST');await again.getByRole('button',{name:'我已核对并接受',exact:true}).click();receipt=await(await response).json();
      }else receipt=await accept(page,id);
      expect(receipt.confirmation_kind).toBe('simulated_test');expect(receipt.facts_status).toBe('pending_d10');expect(receipt.analysis_started).toBe(false);
      const acceptedCount=writes.length;await expect(page.getByRole('button',{name:'保存已接受数据',exact:true})).toBeEnabled();
      const beforePersist=await(await page.request.get(`/api/financial-facts/persisted/${receipt.receipt_id}`)).json();expect(beforePersist.fact_set_id).toBeUndefined();expect(writes.length).toBe(acceptedCount);
      const persisted=page.waitForResponse(r=>r.url().endsWith('/financial-facts/persisted')&&r.request().method()==='POST');await page.getByRole('button',{name:'保存已接受数据',exact:true}).click();const group=await(await persisted).json();expect(group.confirmation_kind).toBe('simulated_test');expect(group.production_calculable).toBe(false);groups.push({id,...group});await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
    }
    await page.goto(`/research?mode=operating&company=${task.input.first.company_id}&task=${task.task_id}`);await page.getByRole('button',{name:'查看全部六项',exact:true}).click();
    await expect(page.locator('.fact-group[data-side="first"] li').first()).toContainText(/多个有效事实|已入库/,{timeout:20000});
    for(const side of ['first','second'])for(const metric of metrics){const picker=page.getByLabel(`${side}:${metric} 恢复事实`,{exact:true});if(await picker.count()){const group=groups.find(g=>g.company_id===task.input[side].company_id&&g.facts.some((f:any)=>f.period===task.input[side].period.year));if(group)await picker.selectOption(group.facts.find((f:any)=>f.metric_key===metric).fact_id);}}
    const previous=writes.filter(w=>w.endsWith(`/tasks/${task.task_id}/resume`)).length;expect(previous).toBe(0);
    let result:any,resumeOperation='';
    if(comparison){
      let finishLost!:()=>void;const lost=new Promise<void>(resolve=>{finishLost=resolve;});
      await page.route(`**/api/research/tasks/${task.task_id}/resume`,async route=>{resumeOperation=route.request().postDataJSON().operation_id;const response=await route.fetch({timeout:120000});expect(response.status()).toBe(200);result=await response.json();await route.abort('failed');finishLost();});
      await page.getByRole('button',{name:'复核并继续研究',exact:true}).click();await lost;await expect(page.getByRole('alert').filter({hasText:'网络响应未知'})).toBeVisible();const writeCount=writes.length;
      await page.reload();const recovery=page.waitForResponse(r=>r.url().endsWith(`/research/tasks/by-operation/${resumeOperation}`)&&r.request().method()==='GET');await page.getByRole('button',{name:'查证刚才的结果（只读）',exact:true}).click();expect((await(await recovery).json()).task_id).toBe(task.task_id);await expect(page.locator('.result-change')).toHaveCount(3);expect(writes.length).toBe(writeCount);
      const recovered=await(await page.request.get(`/api/research/tasks/${task.task_id}`)).json();expect(recovered).toEqual(result);
    }else{const response=page.waitForResponse(r=>r.url().endsWith(`/tasks/${task.task_id}/resume`)&&r.request().method()==='POST');await page.getByRole('button',{name:'复核并继续研究',exact:true}).click();result=await(await response).json();}
    expect(result.status).toBe('completed');expect(result.final_research_content.financial_facts.every((f:any)=>!f.production_calculable)).toBe(true);expect(writes.filter(w=>w.endsWith(`/tasks/${task.task_id}/resume`))).toHaveLength(1);
    await expect(page.locator('.result-change')).toHaveCount(3);await shot(page,comparison?'native-dual':'native-single');
    const unchanged=await(await page.request.get(`/api/research/tasks/${task.task_id}`)).json();
    await page.getByRole('link',{name:'整理报告 →',exact:true}).click();const reportOut=`${out}/${comparison?"dual":"single"}-reports`;mkdirSync(reportOut,{recursive:true});await verifyReportJourney(page,result,reportOut);
    expect(await(await page.request.get(`/api/research/tasks/${task.task_id}`)).json()).toEqual(unchanged);
    proof.push({comparison,recovery_operation:resumeOperation||null,task:result.task_id,revision:result.revision,groups:groups.map(g=>({receipt:g.fact_set_id,facts:g.facts.map((f:any)=>f.fact_id)})),simulated_test:true,human_acceptances:0});
  }
  expect(writes.filter(w=>w.endsWith('/api/research/tasks'))).toHaveLength(2);expect(writes.filter(w=>w.endsWith('/financial-facts/confirmations'))).toHaveLength(3);expect(writes.filter(w=>w.endsWith('/financial-facts/persisted'))).toHaveLength(3);
  writeFileSync(`${out}/native-integration-proof.json`,JSON.stringify({proof,writes,recoveryReads,model:'controlled dependency; no provider calls'},null,2));
});
