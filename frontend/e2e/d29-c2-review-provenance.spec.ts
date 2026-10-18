import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const out = process.env.C2_OUT!, before = process.env.C2_BEFORE === '1';
const manifest = JSON.parse(readFileSync(`${out}/manifest.json`, 'utf8'));
const sha = (v: string | Buffer) => createHash('sha256').update(v).digest('hex');
async function state(page: Page) { return (await page.request.get('/api/__test__/c1-readonly-state')).json(); }
async function audit(page: Page, start: unknown, methods: string[], name: string) {
  const end = await state(page); expect(end).toEqual(start); expect(methods.every(m => m === 'GET')).toBeTruthy();
  writeFileSync(`${out}/${name}-audit.json`, JSON.stringify({start,end,methods,dom:await page.locator('main').first().evaluate(n=>n.outerHTML)},null,2));
}
async function qa(page: Page, item: any, width: number) {
  await page.setViewportSize({width,height:1000});
  await page.goto(`/research?mode=qa&company=${item.run.documents[0].company_id}&run=${item.run.run_id}`);
  await expect(page.getByLabel('原问题',{exact:true})).toHaveText(item.run.query);
}
const cases = before ? ['A01','A02','R06'] : manifest.runs.map((r:any)=>r.case);
for(const id of cases) test(`${before?'before':'after'} exact question ${id}`,async({page})=>{
  const item=manifest.runs.find((r:any)=>r.case===id), start=await state(page), methods:string[]=[];
  page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
  await qa(page,item,1024);
  const marker=page.locator(`[data-external-review="D28-${id}"]`);
  if(before) await expect(marker).toHaveCount(0);
  else {
    await expect(marker).toContainText('外部人工审阅：本题通过');
    const reading=page.getByLabel('问答审阅状态');
    await expect(reading).toContainText(id.startsWith('A')?'待审（pending）':'无原生审阅结论（null）');
    await reading.getByText('审阅来源、时间与适用范围',{exact:true}).click();
    await expect(reading).toContainText(`${id}通过`); await expect(reading).toContainText('不等于产品原生签核');
    await page.reload();await expect(marker).toBeVisible();
  }
  const response=await page.request.get(`/api/research/runs/${item.run.run_id}`);
  expect(sha(await response.body())).toBe(sha(JSON.stringify(item.run)));
  expect((await response.json()).result).toEqual(item.run.result);
  await audit(page,start,methods,`qa-${id}`);
});
for(const width of [1440,1024,390])test(`${before?'before':'after'} QA screenshot at ${width}`,async({page})=>{
  const item=manifest.runs[0];await qa(page,item,width);
  await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toBeVisible();
  if(!before)await expect(page.locator('[data-external-review="D28-A01"]')).toBeVisible();
  await page.screenshot({path:`${out}/qa-${width}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
for(const width of [1440,1024,390])for(const name of (before?['midea']:['midea','gree','comparison']))test(`${before?'before':'after'} ${name} four statements at ${width}`,async({page})=>{
  const item=manifest.archive_tasks.find((t:any)=>t.name===name),start=await state(page),methods:string[]=[];
  page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
  await page.setViewportSize({width,height:1000});await page.goto(`/test-results/c2-reader/reading.html?task=${item.task_id}`);
  const originals=page.locator('[data-model-statement]');
  if(before)await expect(page.locator('article.operating-result > strong').filter({hasText:/^待审解释 [1-4]$/})).toHaveCount(4);
  else {
    await expect(originals).toHaveCount(4);
    if(name==='midea'){
      await expect(page.locator('[data-external-review]')).toHaveCount(4);
      await expect(page.locator('.external-review-rewrite')).toHaveCount(2);
      const task=await (await page.request.get(`/api/__test__/archive/tasks/${item.task_id}`)).json();
      expect(await originals.allTextContents()).toEqual(task.final_research_content.model_interpretations.map((i:any)=>i.text));
      for(const index of [1,2,3,4])await expect(page.getByLabel(`解释 ${index} 外部审阅`)).toContainText(index%2?'同意改写':'接受原句');
    }else {
      await expect(page.locator('[data-external-review]')).toHaveCount(0);
      for(const index of [1,2,3,4])await expect(page.getByLabel(`解释 ${index} 外部审阅`)).toContainText('无本项适用记录 · 待审');
    }
    await expect(page.getByLabel('解释 1 外部审阅')).toContainText('经营因果：未验证（false）');
  }
  await page.screenshot({path:`${out}/${name}-${width}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.reload(); if(!before&&name==='midea')await expect(page.locator('[data-external-review]')).toHaveCount(4);
  await audit(page,start,methods,`${name}-${width}`);
});
for(const revision of [1,2])for(const width of [1440,1024,390])test(`${before?'before':'after'} report v${revision} at ${width}`,async({page})=>{
  const start=await state(page),methods:string[]=[];
  page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
  await page.setViewportSize({width,height:1000});await page.goto(`/test-results/c2-reader/reading.html?revision=${revision}`);
  await expect(page.getByLabel('已保存报告版本')).toBeVisible();
  if(before)await expect(page.locator('[data-external-review]')).toHaveCount(0);
  else{
    await expect(page.locator('[data-external-review]')).toHaveCount(4);
    await expect(page.getByLabel('已保存报告版本')).toContainText('历史报告正文未被修改');
    await expect(page.getByRole('heading',{name:'用户结论 · 待人工语义审阅',exact:true})).toBeVisible();
    await expect(page.locator('.report-user-conclusions')).toContainText('用户新增断言尚未核准');
    await expect(page.locator('[data-model-statement]')).toHaveCount(4);
  }
  await page.screenshot({path:`${out}/report-v${revision}-${width}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const response=await page.request.get(`/api/__test__/archive/reports/${revision}`);
  expect(sha(await response.body())).toBe(manifest.archive_reports.find((r:any)=>r.revision===revision).sha256);
  const markdown=await page.request.get(`/api/__test__/archive/reports/${revision}/markdown`);
  expect(sha(await markdown.body())).toBe(manifest.archive_reports.find((r:any)=>r.revision===revision).markdown_sha256);
  if(revision===1)expect(sha(await markdown.body())).toBe('28ddda7dc495e3396a387ff966d9c56a99679084de8841d9eb57d940fd61b9d0');
  await audit(page,start,methods,`report-v${revision}-${width}`);
});
if(!before){
  for(const change of ['query','source','answer-hash','run','workspace'])test(`reject QA ${change} identity`,async({page})=>{
    const item=manifest.runs[0];
    await page.route(`**/api/research/runs/${item.run.run_id}`,async route=>{
      const response=await route.fetch(),v=await response.json();
      if(change==='query')v.query=manifest.runs[1].run.query;
      if(change==='source')v.documents[0].content_sha256='0'.repeat(64);
      if(change==='answer-hash')v.integrity_sha256='0'.repeat(64);
      if(change==='run')v.run_id=manifest.runs[1].run.run_id;
      if(change==='workspace')v.workspace_id='foreign';
      await route.fulfill({response,json:v});
    });
    await page.goto(`/research?mode=qa&company=${item.run.documents[0].company_id}&run=${item.run.run_id}`);
    if(change==='run')await expect(page.getByText('问答记录暂时无法读取',{exact:true})).toBeVisible();
    else await expect(page.getByLabel('问答审阅状态')).toContainText('记录不适用');
    await expect(page.locator('[data-external-review]')).toHaveCount(0);
  });
  for(const change of ['revision','statement','source','citation'])test(`reject operating ${change} identity`,async({page})=>{
    const item=manifest.archive_tasks[0];
    await page.route('**/api/__test__/archive/tasks/*',async route=>{
      const response=await route.fetch(),v=await response.json();
      if(change==='revision')v.revision++;
      if(change==='statement'){v.final_research_content.model_interpretations[0].text+='额外断言。';v.snapshot.final_research_content=v.final_research_content;}
      if(change==='source')v.snapshot.documents[0].source_revision='0'.repeat(64);
      if(change==='citation'){v.final_research_content.operating_descriptions[0].citation.chunk_id+='changed';v.snapshot.final_research_content=v.final_research_content;}
      await route.fulfill({response,json:v});
    });
    await page.goto(`/test-results/c2-reader/reading.html?task=${item.task_id}`);
    await expect(page.getByLabel('解释 1 外部审阅')).toContainText('记录不适用');
    await expect(page.locator('[data-external-review]')).toHaveCount(0);
  });
  test('exact historical review after source expiration grants no current PDF or focus',async({page})=>{
    const item=manifest.runs[0];
    await page.route(`**/api/research/runs/${item.run.run_id}`,async route=>{const response=await route.fetch(),v=await response.json();v.source_states[0].status='expired';await route.fulfill({response,json:v});});
    await qa(page,item,390);await expect(page.getByLabel('问答审阅状态')).toContainText('当前来源已变化，不授予当前资格');
    await expect(page.locator('[data-external-review="D28-A01"]')).toBeVisible();
    await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:'查看原 PDF [1]',exact:true})).toHaveCount(0);
  });
}
