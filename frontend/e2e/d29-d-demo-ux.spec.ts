import { test, expect, type Page, type Locator } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const out = process.env.C2_OUT!, before = process.env.C2_BEFORE === '1';
const manifest = JSON.parse(readFileSync(`${out}/manifest.json`, 'utf8'));
const sha = (v: Buffer) => createHash('sha256').update(v).digest('hex');
test.beforeEach(async({page})=>{await page.route('**/src/main.tsx*',r=>r.fulfill({contentType:'text/javascript',body:'import "/test-results/d29-d-archive-entry.tsx";'}));});
const reportId = 'e37bb803-1245-46f0-a31c-da250311d12d';
const reportPath = (v: number) => `/reports?report=${reportId}&revision=${v}`;
async function state(page: Page) { return (await page.request.get('/api/__test__/c1-readonly-state')).json(); }
async function finish(page: Page, start: unknown, methods: string[], name: string) {
  const end = await state(page); expect(end).toEqual(start); expect(methods.every(m => m === 'GET')).toBeTruthy();
  writeFileSync(`${out}/${name}-audit.json`, JSON.stringify({start,end,methods,dom:await page.locator('main').first().evaluate(n=>n.outerHTML)},null,2));
}
async function screenshot(page: Page, name: string) {
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path:`${out}/${name}.png`});
}
async function metric(locator: Locator) {
  return locator.evaluate(n => { const r=n.getBoundingClientRect(),s=getComputedStyle(n);return {top:r.top+scrollY,height:r.height,fontSize:s.fontSize,lineHeight:s.lineHeight,viewportHeight:innerHeight}; });
}
async function pdfReturn(page: Page, opener: Locator, name: string, context: string) {
  await opener.click(); const dialog=page.getByRole('dialog',{name:/原 PDF/});
  await expect(dialog.locator('canvas')).toBeVisible({timeout:30000});
  await screenshot(page,`pdf-${name}`);
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(opener).toBeFocused();
  await opener.press('Enter');await expect(dialog.locator('canvas')).toBeVisible({timeout:30000});
  await dialog.getByRole('button',{name:`返回${context}阅读位置`,exact:true}).click();await expect(opener).toBeFocused();
}
for(const width of [1440,1024,390]) {
  test(`${before?'before':'after'} home value and historical entry ${width}`,async({page})=>{
    await page.setViewportSize({width,height:width===390?844:1000});
    const start=await state(page),methods:string[]=[];page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
    await page.goto('/');await expect(page.getByRole('heading',{name:/美的集团.*2025/}).first()).toBeVisible().catch(async()=>{await expect(page.getByRole('link').filter({hasText:'美的集团股份有限公司 · 2025 / 2024'}).first()).toBeVisible();});
    const entry=before?page.getByRole('link').filter({hasText:'美的集团股份有限公司 · 2025 / 2024'}).first():page.getByRole('link',{name:'阅读历史研究 →',exact:true});
    if(!before){await expect(page.locator('main')).toContainText('上传企业年报，获得可信财务变化、可追溯原文证据和版本研究报告');await expect(entry).toBeInViewport();await expect(page.locator('header[aria-label="当前研究"]')).toContainText('历史结果读取 · 不会重新运行模型');}
    writeFileSync(`${out}/home-${width}-metrics.json`,JSON.stringify(await metric(entry),null,2));
    await screenshot(page,`home-${width}`);await entry.click();await expect(page.locator('.result-change')).toHaveCount(3);
    await finish(page,start,methods,`home-${width}`);
  });
  for(const name of ['midea','comparison'])test(`${before?'before':'after'} result ${name} ${width}`,async({page})=>{
    await page.setViewportSize({width,height:width===390?844:1000});
    const item=manifest.archive_tasks.find((t:any)=>t.name===name),start=await state(page),methods:string[]=[];
    page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
    await page.goto(`/research?mode=operating&task=${item.task_id}`);await expect(page.locator('.result-change')).toHaveCount(3);
    if(!before){await expect(page.getByRole('heading',{name:'业务原文与待审线索',exact:true})).toBeVisible();await expect(page.locator('main')).toContainText('未执行逐指标经营变化原因检索');}
    const measurement=await metric(page.locator('.result-change').first());
    writeFileSync(`${out}/${name}-${width}-metrics.json`,JSON.stringify(measurement,null,2));
    if(!before)expect(measurement.top).toBeLessThan(width===390?2*844:1000);
    await screenshot(page,`${name}-${width}`);
    if(!before){
      await page.getByText(/经营原文与完整引用 ·/).click();
      const source=page.locator('article.operating-result').filter({has:page.getByRole('heading',{name:/原文 \[\d+\].*美的集团.*2025 年报/})}).first();
      await expect(source).toContainText('美的集团股份有限公司');await expect(source).toContainText('2025 年报');await expect(source).toContainText('文件：midea-2025.pdf');await expect(source).toContainText('物理第');
      await screenshot(page,`citation-${name}-${width}`);
      await pdfReturn(page,source.getByRole('button',{name:/查看原 PDF \[\d+\]/}),`${name}-${width}`,'经营原文');
      const link=source.getByRole('link',{name:'新标签打开原 PDF ↗',exact:true});await expect(link).toHaveAttribute('target','_blank');
      const file=await page.request.get((await link.getAttribute('href'))!.split('#')[0]);expect(sha(await file.body())).toBe(manifest.sources.find((s:any)=>s.report_id==='midea-2025').pdf_sha256);
      if(name==='comparison'){
        const headings=await page.locator('article.operating-result h3').allTextContents();expect(headings.some(s=>s.includes('珠海格力电器股份有限公司')&&s.includes('2025 年报'))).toBeTruthy();
        const gree=page.locator('article.operating-result').filter({has:page.getByRole('heading',{name:/原文.*珠海格力/})}).first();
        await expect(gree).toContainText('文件：gree-2025.pdf');
        const button=gree.getByRole('button',{name:/查看原 PDF/});await pdfReturn(page,button,`gree-comparison-${width}`,'经营原文');
      }
    }
    await finish(page,start,methods,`${name}-${width}`);
  });
  for(const revision of [1,2])test(`${before?'before':'after'} report v${revision} ${width}`,async({page})=>{
    await page.setViewportSize({width,height:width===390?844:1000});
    const start=await state(page),methods:string[]=[];page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
    await page.goto(reportPath(revision));await expect(page.getByLabel('已保存报告版本')).toBeVisible();
    const summary=page.locator('.report-paper section').first().locator('li').first();
    await expect(summary).toBeVisible();const measurement=await metric(summary);
    writeFileSync(`${out}/report-v${revision}-${width}-metrics.json`,JSON.stringify(measurement,null,2));
    if(!before){expect(measurement.top).toBeLessThan(width===390?2*844:1000);expect(measurement.fontSize).toBe('16px');await expect(page.locator('.report-cover')).toContainText('人工语义审阅待完成');await expect(page.locator('.report-cover')).toContainText('历史报告读取');}
    await screenshot(page,`report-v${revision}-${width}`);
    if(!before){
      const version=page.getByLabel('报告版本',{exact:true}),compare=page.getByRole('button',{name:'比较版本',exact:true}),download=page.getByRole('button',{name:`下载 v${revision} · Markdown`,exact:true});
      await download.scrollIntoViewIfNeeded();const positions=await Promise.all([version,compare,download].map(x=>x.boundingBox()));
      for(let n=0;n<2;n++){const pending=page.waitForEvent('download');await download.click();const d=await pending;const path=await d.path();expect(sha(readFileSync(path!))).toBe(manifest.archive_reports.find((r:any)=>r.revision===revision).markdown_sha256);await expect(download).toBeEnabled();}
      const afterPositions=await Promise.all([version,compare,download].map(x=>x.boundingBox()));expect(afterPositions).toEqual(positions);
      await compare.click();const dialog=page.getByRole('dialog',{name:'报告版本对照',exact:true});await expect(dialog).toContainText('冻结研究正文与证据相同');await screenshot(page,`compare-v${revision}-${width}`);await dialog.getByRole('button',{name:'返回报告',exact:true}).click();await expect(compare).toBeFocused();
      if(width===390)await page.getByRole('button',{name:/报告目录 ·/}).click();
      await page.getByRole('button',{name:'已确认财务事实',exact:false}).click();const destination=page.getByRole('heading',{name:/03.*已确认财务事实/});await expect(destination).toBeFocused();await expect(destination).toBeInViewport();
      const table=page.getByRole('region',{name:'已确认财务事实表，可横向滚动'});await expect(table).toHaveCSS('overflow-x','auto');if(width===390)expect(await table.evaluate(n=>n.scrollWidth>n.clientWidth)).toBeTruthy();await expect(table).toHaveAttribute('tabindex','0');
      await pdfReturn(page,table.getByRole('button',{name:/原 PDF · 物理/}).first(),`report-${revision}-${width}`,'报告');
      await expect(page.locator('.report-user-conclusions')).toContainText('用户新增断言尚未核准');await expect(page.locator('[data-model-statement]')).toHaveCount(4);
      await expect(page.locator('[data-external-review]')).toHaveCount(4);
      await page.getByLabel('报告版本',{exact:true}).selectOption(String(revision===1?2:1));await expect(page.getByLabel('已保存报告版本')).toHaveAttribute('data-revision',String(revision===1?2:1));
    }
    await finish(page,start,methods,`report-v${revision}-${width}`);
  });
  if(!before)test(`readonly demo from home through focused QA and saved report ${width}`,async({page})=>{
    await page.setViewportSize({width,height:width===390?844:1000});
    const start=await state(page),methods:string[]=[];page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});
    const began=Date.now();await page.goto('/');await page.getByRole('link',{name:'阅读历史研究 →',exact:true}).click();
    await expect(page.locator('.result-change')).toHaveText(['增加 12.11%','增加 14.03%','减少 11.84%']);
    await expect(page.getByLabel('解释 1 外部审阅')).toContainText('外部人工审阅改写');
    await expect(page.getByLabel('解释 1 外部审阅')).toContainText('原生语义状态：待审（pending）');
    await page.getByRole('navigation',{name:'当前研究功能'}).getByRole('link',{name:'原文问答',exact:true}).click();
    const qa=manifest.runs.find((r:any)=>r.case==='A10');await page.getByRole('button',{name:'历史问答',exact:true}).click();for(let n=0;n<4&&!await page.getByRole('button',{name:qa.run.query,exact:true}).count();n++){const more=page.waitForResponse(r=>r.url().includes('/api/research/runs?')&&r.status()===200);await page.getByRole('button',{name:'加载更多研究',exact:true}).click();await more;}await page.getByRole('button',{name:qa.run.query,exact:true}).click();
    const focus=page.getByRole('region',{name:'本题可信焦点',exact:true});await expect(focus).toContainText('456,451,731');await expect(focus).toContainText('千元');
    await expect(page.getByLabel('问答审阅状态')).toContainText('外部人工审阅：本题通过');await pdfReturn(page,focus.getByRole('button',{name:'查看原 PDF [1]',exact:true}),`qa-demo-${width}`,'回答');
    const menu=page.getByRole('button',{name:'打开导航',exact:true});if(await menu.count())await menu.click();await page.getByRole('navigation',{name:'产品导航',exact:true}).getByRole('link',{name:'报告',exact:true}).click();await page.getByRole('button',{name:'阅读报告',exact:true}).click();await expect(page.getByLabel('已保存报告版本')).toHaveAttribute('data-revision','2');
    await page.getByLabel('报告版本',{exact:true}).selectOption('1');await expect(page.getByLabel('已保存报告版本')).toHaveAttribute('data-revision','1');
    const pending=page.waitForEvent('download');await page.getByRole('button',{name:'下载 v1 · Markdown',exact:true}).click();const download=await pending;expect(sha(readFileSync((await download.path())!))).toBe('28ddda7dc495e3396a387ff966d9c56a99679084de8841d9eb57d940fd61b9d0');
    writeFileSync(`${out}/demo-${width}-duration.json`,JSON.stringify({automation_ms:Date.now()-began,not_human_timing:true},null,2));
    await finish(page,start,methods,`demo-${width}`);
  });
}
if(!before){
  test('empty company guides explicit establishment without writes',async({page})=>{
    await page.route('**/api/companies',r=>r.fulfill({json:[]}));await page.route('**/api/research/tasks?*',r=>r.fulfill({json:{schema_version:'template-task-history-v1',items:[],next_before:null}}));
    const methods:string[]=[];page.on('request',r=>{if(r.url().includes('/api/'))methods.push(r.method());});await page.goto('/');
    await page.getByRole('link',{name:'建立企业 →',exact:true}).click();await expect(page.getByLabel('企业正式名称')).toBeFocused();expect(methods.every(m=>m==='GET')).toBeTruthy();await screenshot(page,'empty-company');
  });
  test('completed history remains featured alongside unfinished work',async({page})=>{
    await page.route('**/api/research/tasks?*',async r=>{const response=await r.fetch(),v=await response.json(),waiting=structuredClone(v.items[0]);waiting.status='awaiting_human_confirmation';waiting.waiting_checkpoint=true;waiting.snapshot=null;waiting.final_research_content=null;waiting.task_id='00000000-0000-4000-8000-000000000001';waiting.operation_id='00000000-0000-4000-8000-000000000011';v.items.unshift(waiting);await r.fulfill({response,json:v});});
    await page.goto('/');await expect(page.getByRole('link',{name:'阅读历史研究 →',exact:true})).toBeInViewport();await expect(page.getByRole('heading',{name:/未完成研究/})).toBeVisible();
  });
}
if(!before)test('home finds completed history on the next page after unfinished work',async({page})=>{
  const cursors:string[]=[];
  await page.route('**/api/research/tasks?*',async r=>{const response=await r.fetch(),v=await response.json();cursors.push(new URL(r.request().url()).searchParams.get('before')||'first');if(!new URL(r.request().url()).searchParams.has('before')){const waiting=structuredClone(v.items[0]);waiting.status='awaiting_human_confirmation';waiting.waiting_checkpoint=true;waiting.snapshot=null;waiting.final_research_content=null;waiting.task_id='00000000-0000-4000-8000-000000000002';waiting.operation_id='00000000-0000-4000-8000-000000000012';v.items=[waiting];v.next_before=1;}await r.fulfill({response,json:v});});
  await page.goto('/');await expect(page.getByRole('link',{name:'阅读历史研究 →',exact:true})).toBeInViewport();expect(new Set(cursors)).toEqual(new Set(['first','1']));writeFileSync(`${out}/home-pagination-proof.json`,JSON.stringify({cursors,only_get:true},null,2));
});
