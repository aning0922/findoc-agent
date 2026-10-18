import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const out = process.env.C1_OUT!;
const before = process.env.C1_BEFORE === '1';
const manifest = JSON.parse(readFileSync(`${out}/manifest.json`, 'utf8'));
const sha = (s: string | Uint8Array) => createHash('sha256').update(s).digest('hex');
function canonical(v: any): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`;
  return JSON.stringify(v);
}
async function state(page: Page) { return (await page.request.get('/api/__test__/c1-readonly-state')).json(); }
async function open(page: Page, item: any, width: number) {
  await page.setViewportSize({ width, height: 1000 });
  const company = item.run.documents[0].company_id;
  await page.goto(`/research?mode=qa&company=${company}&run=${item.run.run_id}`);
  await expect(page.getByLabel('原问题', { exact: true })).toHaveText(item.run.query);
}
async function savedText(page: Page, item: any) {
  for (const c of item.run.result.citations) {
    const article = page.locator(`[data-citation-number="${c.number}"]`);
    const text = article.locator('[data-saved-excerpt]');
    if (await text.count()) {
      await article.getByText(`完整已保存原文 [${c.number}] · 含口径与上下文`, { exact: true }).click();
      expect(await text.textContent()).toBe(c.text);
      expect(sha((await text.textContent())!)).toBe(sha(c.text));
    }
  }
}
async function pdfReturn(page: Page, opener: any, path: string) {
  await opener.focus(); await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: /原 PDF · 引用/ });
  await expect(dialog.locator('canvas')).toBeVisible({ timeout: 30000 });
  await page.screenshot({ path: `${out}/${path}-pdf.png` });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0); await expect(opener).toBeFocused();
  await opener.press('Enter'); await expect(dialog.locator('canvas')).toBeVisible({ timeout: 30000 });
  await dialog.getByRole('button', { name: '返回回答阅读位置', exact: true }).click();
  await expect(opener).toBeFocused();
}
async function audit(page: Page, item: any, name: string, start: any, methods: any[]) {
  const end = await state(page);
  expect(end).toEqual(start); expect(methods.every(m => m.method === 'GET')).toBeTruthy();
  const detail = await (await page.request.get(`/api/research/runs/${item.run.run_id}`)).json();
  expect(detail.result).toEqual(item.run.result); expect(detail.integrity_sha256).toBe(item.run.integrity_sha256);
  writeFileSync(`${out}/${name}-audit.json`, JSON.stringify({ run: item.run.run_id, query: item.run.query,
    query_sha256: sha(item.run.query), integrity_sha256: detail.integrity_sha256, answer_sha256: sha(detail.result.content),
    citations_sha256: sha(canonical(detail.result.citations)), sources: detail.documents, start, end, methods,
    dom: await page.locator('[aria-label="研究历史详情"]').evaluate(n => n.outerHTML) }, null, 2));
}
for (const width of [1440, 1024, 390]) {
  for (const item of manifest.runs.filter((i: any) => i.case.startsWith('A') && (!before || ['A01','A02','A03'].includes(i.case)))) {
    test(`${before ? 'before' : 'after'} ${item.case} at ${width}`, async ({ page }) => {
      const start = await state(page); const methods: any[] = [];
      page.on('request', r => { if (r.url().includes('/api/')) methods.push({ method: r.method(), url: r.url() }); });
      await open(page, item, width);
      const answer = page.getByRole('region', { name: '有证据的回答', exact: true });
      await expect(answer).toBeVisible();
      const focus = page.getByRole('region', { name: '本题可信焦点', exact: true });
      if (before) {
        await expect(focus).toHaveCount(0);
        const tables = answer.getByRole('table', { name: '来源原文表格', exact: true });
        expect(await tables.count()).toBeGreaterThan(0); await expect(tables.first()).toContainText('营业收入');
        await expect(tables.first()).toContainText('净利润'); await expect(tables.first()).toContainText('现金');
      } else {
        await expect(focus).toBeVisible();
        await expect(focus).toContainText(item.expected_value); await expect(focus).toContainText(`${item.expected_year} 财务年度`);
        const f = item.projection.focus;
        expect(item.projection.status).toBe('located'); expect(f.raw_value).toBe(item.expected_value);
        expect(f.raw_unit).toBe(item.expected_unit); expect(f.financial_year).toBe(item.expected_year);
        expect(f.row_index).toBe(item.expected_row);
        await expect(focus.getByRole('heading')).toHaveText(f.row_label);
        await expect(focus).toHaveAttribute('data-focus-table', f.table_id);
        await focus.getByText('核对本题原始表格行与年度列', { exact: true }).click();
        const cells = await focus.locator('tbody tr td').allTextContents();
        expect(cells).toEqual(f.original_row);
        expect(await focus.locator('thead th').allTextContents()).toEqual(f.original_header);
        await focus.getByText('核对本题原始表格行与年度列', { exact: true }).click();
        await answer.getByText(`完整年度表格 [1] · 保留全部行列`, { exact: true }).click();
        const whole = answer.locator('[data-citation-number="1"]').getByRole('table', { name: '来源原文表格', exact: true });
        await expect(whole.first()).toContainText(f.raw_value);
        await expect(whole.first()).toContainText('营业收入'); await expect(whole.first()).toContainText('净利润');
        expect((await whole.first().locator('thead th').allTextContents()).filter(s => /^\d{4}年$/.test(s)).length).toBeGreaterThanOrEqual(3);
        await answer.getByText(`完整年度表格 [1] · 保留全部行列`, { exact: true }).click();
      }
      await answer.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${out}/${item.case}-${width}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await pdfReturn(page, before ? answer.getByRole('button', { name: '查看原 PDF [1]', exact: true }) : focus.getByRole('button', { name: '查看原 PDF [1]', exact: true }), `${item.case}-${width}`);
      await savedText(page,item);
      await page.reload(); await expect(page.getByLabel('原问题', { exact: true })).toHaveText(item.run.query);
      if (!before) await expect(focus).toContainText(item.expected_value);
      await audit(page,item,`${item.case}-${width}`,start,methods);
    });
  }
}
if (!before) {
  for (const item of manifest.distractors) test(`distractor ${item.case} actual captured PDF at 390`, async ({ page }) => {
    const start=await state(page), methods:any[]=[];
    page.on('request',r=>{ if(r.url().includes('/api/'))methods.push({method:r.method(),url:r.url()}); });
    await open(page,item,390);
    const focus=page.getByRole('region',{name:'本题可信焦点',exact:true});
    if (item.expected_value===null) {
      await expect(page.getByText('当前无法可靠定位本题数值',{exact:true})).toBeVisible();
      // The endpoint's exact unlocated result removes any asynchronous uncertainty.
      expect(item.projection.status).toBe('unlocated'); await expect(focus).toHaveCount(0);
      await expect(page.getByRole('table',{name:'来源原文表格',exact:true}).first()).toBeVisible();
    } else {
      await expect(focus).toContainText(item.expected_value);
      expect(item.projection.focus.raw_value).toBe(item.expected_value);
      expect(item.projection.focus.raw_unit).toBe(item.expected_unit);
      expect(item.projection.focus.financial_year).toBe(item.expected_year);
    }
    await savedText(page,item); await audit(page,item,`${item.case}-390`,start,methods);
  });
  for(const item of manifest.runs.filter((i:any)=>i.case.startsWith('R'))) test(`preserve ${item.case} refusal and zero writes`,async({page})=>{
    const start=await state(page),methods:any[]=[];page.on('request',r=>{if(r.url().includes('/api/'))methods.push({method:r.method(),url:r.url()});});
    await open(page,item,1024);await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toHaveCount(0);
    expect(item.projection.status).toBe('unlocated');expect(item.projection.reason).toBe('non_answer');
    if(item.case==='R06')await expect(page.getByText('当前不支持这类财务计算',{exact:true})).toBeVisible();
    if(item.case==='R05')await expect(page.getByText('当前问题需要已确认财务事实',{exact:true})).toBeVisible();
    await audit(page,item,item.case,start,methods);
  });
  for(const fault of ['swap_run','query_hash','wrong_value','wrong_unit','wrong_year','wrong_table','http_503','source_changed_after_run_read'])test(`reject projection ${fault}`,async({page})=>{
    const item=manifest.runs[0];const start=await state(page);const methods:any[]=[];
    page.on('request',r=>{if(r.url().includes('/api/'))methods.push({method:r.method(),url:r.url()});});
    await page.route(`**/research/runs/${item.run.run_id}/focus`,async route=>{
      if(fault==='http_503'){await route.fulfill({status:503,json:{detail:'unavailable'}});return;}
      if(fault==='source_changed_after_run_read'){await route.fulfill({status:409,json:{detail:'source_changed'}});return;}
      const v=JSON.parse(JSON.stringify(fault==='swap_run'?manifest.runs[1].projection:item.projection));
      if(fault==='query_hash')v.query_sha256='f'.repeat(64);
      if(fault==='wrong_value')v.focus.raw_value='32,184,570,372.28';
      if(fault==='wrong_unit')v.focus.raw_unit='千元';
      if(fault==='wrong_year')v.focus.financial_year=2023;
      if(fault==='wrong_table'){v.focus.table_text=v.focus.table_text.replace('189,163,654,064.64','999.00');v.focus.table_text_sha256=sha(v.focus.table_text);}
      const{projection_sha256:_projection_sha256,...payload}=v;v.projection_sha256=sha(canonical(payload));await route.fulfill({json:v});
    });
    await open(page,item,1440);await expect(page.getByText('当前无法可靠定位本题数值',{exact:true})).toBeVisible();
    await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toHaveCount(0);
    if(fault==='source_changed_after_run_read'){
      await expect(page.getByText('已保存的历史原文',{exact:true})).toBeVisible();
      await expect(page.getByRole('button',{name:'查看原 PDF [1]',exact:true})).toHaveCount(0);
    }
    await savedText(page,item);await audit(page,item,`fault-${fault}`,start,methods);
  });
  for(const width of [1440,1024,390])test(`footer citation and auxiliary PDF return at ${width}`,async({page})=>{
    const item=manifest.runs[0],start=await state(page),methods:any[]=[];
    page.on('request',r=>{if(r.url().includes('/api/'))methods.push({method:r.method(),url:r.url()});});
    await open(page,item,width);await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toBeVisible();
    const article=page.locator('[data-citation-number="1"]');
    await pdfReturn(page,article.getByRole('button',{name:'查看原 PDF [1]',exact:true}),`footer-${width}`);
    const link=article.getByRole('link',{name:'打开原 PDF [1] · 新标签',exact:true});
    await link.focus();
    // Chromium headless shell downloads PDFs; a full Chromium browser can render them.
    // Both paths must request the pinned file. Never treat about:blank as verification.
    const downloaded=new Promise<any>(resolve=>{
      page.once('download',resolve);
      page.context().once('page',tab=>tab.once('download',resolve));
    });
    const opened=page.waitForEvent('popup');await link.press('Enter');const popup=await opened;
    const result=await Promise.race([
      downloaded.then(async download=>{
        const path=await download.path();expect(path).toBeTruthy();
        const hash=sha(readFileSync(path));expect(hash).toBe(item.run.documents[0].content_sha256);
        return {mode:'headless_pdf_download',pdf_sha256:hash};
      }),
      popup.waitForURL(/#page=7$/,{timeout:15000}).then(()=>({mode:'native_pdf_tab',url:popup.url()})).catch(error=>{
        if(String(error).includes('ERR_ABORTED'))return new Promise<never>(()=>{});
        throw error;
      }),
    ]);
    writeFileSync(`${out}/auxiliary-${width}.json`,JSON.stringify(result,null,2));
    await popup.close();await expect(link).toBeFocused();
    await audit(page,item,`footer-${width}`,start,methods);
  });
  test('focus timeout keeps original reading available without resubmission',async({page})=>{
    const item=manifest.runs[0],start=await state(page),methods:any[]=[];
    page.on('request',r=>{if(r.url().includes('/api/'))methods.push({method:r.method(),url:r.url()});});
    await page.route(`**/research/runs/${item.run.run_id}/focus`,async route=>{
      await new Promise(r=>setTimeout(r,18000));await route.fulfill({json:item.projection}).catch(()=>{});
    });
    await open(page,item,390);await savedText(page,item);
    await page.waitForTimeout(16000);await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toHaveCount(0);
    await expect(page.getByText('当前无法可靠定位本题数值',{exact:true})).toBeVisible();
    await audit(page,item,'focus-timeout',start,methods);
  });
  test('late A01 projection cannot become A02 focus',async({page})=>{
    const a=manifest.runs[0],b=manifest.runs[1];let release:()=>void=()=>{};
    const gate=new Promise<void>(r=>release=r);
    await page.route(`**/research/runs/${a.run.run_id}/focus`,async route=>{await gate;await route.fulfill({json:a.projection}).catch(()=>{});});
    await open(page,a,1440);await open(page,b,1440);release();
    await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toContainText(b.expected_value);
    await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).not.toContainText(a.expected_value);
  });
  test('source invalidation blocks focus and old PDF while preserving historical bytes',async({page})=>{
    const item=manifest.runs[0];await open(page,item,390);
    await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toBeVisible();
    const d=item.run.documents[0];
    const change=await page.request.post(`/api/documents/${d.document_id}/binding-corrections`,{data:{expected_attempt:d.attempt,reason:'isolated C1 source invalidation fixture',metadata:{company_id:d.company_id,report_year:d.report_year,report_type:'annual',period_start:d.period_start,period_end:d.period_end,basis:'IFRS'}}});
    expect(change.status(),await change.text()).toBe(200);const start=await state(page),methods:any[]=[];
    page.on('request',r=>{if(r.url().includes('/api/'))methods.push({method:r.method(),url:r.url()});});
    await page.reload();await expect(page.getByText('已保存的历史原文',{exact:true})).toBeVisible();
    await expect(page.getByRole('region',{name:'本题可信焦点',exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:'查看原 PDF [1]',exact:true})).toHaveCount(0);
    await expect(page.getByText('来源已过期或不可用，不可打开原 PDF',{exact:true})).toBeVisible();
    const file=await page.request.get(`/api/documents/${d.document_id}/file?company_id=${d.company_id}&source_revision=${d.source_revision}`);expect(file.ok()).toBeFalsy();
    await savedText(page,item);await audit(page,item,'source-invalidated',start,methods);
    await page.screenshot({path:`${out}/source-invalidated-390.png`,fullPage:true});
  });
}
