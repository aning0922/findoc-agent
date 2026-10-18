import { manageQASources, finishQASources } from './qa-helpers.ts';
import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const out = process.env.UX_ARTIFACT_DIR!;
const seed = JSON.parse(readFileSync(`${process.env.D26_REPORT_SEED_DIR}/journey-proof.json`, 'utf8'));
const task = seed.result;
const company = task.input.first.company_id;
const taskURL = `/research?company=${company}&mode=operating&task=${task.task_id}`;
async function harness(page: Page) {
  await page.route('**/src/main.tsx*', r => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
}
function watch(page: Page) {
  const writes: any[] = [];
  page.on('request', r => { if (r.method() !== 'GET' && r.url().includes('/api/')) writes.push({ method: r.method(), url: r.url(), body: r.postData() }); });
  return writes;
}
test('three global entries, five task destinations, history/refresh and legacy identity are read-only', async ({ page }) => {
  await harness(page); const writes = watch(page);
  await page.goto('/'); await expect(page.getByRole('heading', { name: '我的研究', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: '产品导航' }).getByRole('link')).toHaveCount(3);
  await page.getByRole('link', { name: '企业与资料', exact: true }).click();
  await expect(page.locator('#main-content')).toBeFocused();
  await expect(page).toHaveURL(/\/companies$/);
  const directory = page.getByRole('region', { name: '企业目录' });
  await expect(directory.locator('li')).toHaveCount(4); // two fixture identities and two publicly named companies
  expect(new URL(page.url()).pathname).toBe('/companies');
  await page.goto(taskURL);
  const context = page.getByRole('region', { name: '研究上下文' });
  await expect(context).toHaveAttribute('data-task-id', task.task_id);
  await expect(context).toContainText('2024'); await expect(context).toContainText('2025 年报');
  await expect(page.getByLabel('当前企业', { exact: true })).toHaveCount(0);
  const nav = context.getByRole('navigation', { name: '当前研究功能' });
  await expect(nav.getByRole('link')).toHaveCount(5);
  await nav.getByRole('link', { name: '资料与核对', exact: true }).click();
  await expect(page.getByRole('region', { name: '六项事实准备状态' })).toBeVisible();
  await expect(page).toHaveURL(/section=sources/);
  await page.getByRole('navigation', { name: '当前研究功能' }).getByRole('link', { name: '财务分析', exact: true }).click();
  await expect(page.getByRole('region', { name: '确定性分析结果' })).toBeVisible();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toHaveCount(0);
  await page.goBack(); await expect(context).toHaveAttribute('data-task-id', task.task_id);
  await expect(page).toHaveURL(/section=sources/); await page.goForward(); await expect(page).toHaveURL(/section=financial/);
  await page.reload(); await expect(context).toHaveAttribute('data-task-id', task.task_id);
  await page.getByRole('navigation', { name: '当前研究功能' }).getByRole('link', { name: '原文问答', exact: true }).click();
  expect(new URL(page.url()).searchParams.has('task')).toBe(false);
  expect(new URL(page.url()).searchParams.get('return_task')).toBe(task.task_id);
  await page.getByRole('link', { name: '返回来源研究 →', exact: true }).click();
  await expect(context).toHaveAttribute('data-task-id', task.task_id);
  await page.getByRole('navigation', { name: '当前研究功能' }).getByRole('link', { name: '报告', exact: true }).click();
  await expect(page.getByLabel('选择已完成研究')).toHaveValue(task.task_id);
  await expect(page.getByRole('article', { name: '报告草稿预览' })).toHaveCount(0);
  await page.goto(`/companies/${company}/analysis?task=${task.task_id}`);
  await expect(page.getByRole('status').filter({ hasText: '本次所需来源已全部核验' })).toBeVisible();
  // Only the existing explicit financial analysis service may POST on the legacy analysis page.
  expect(writes.filter(w => !w.url.endsWith('/__test__/analyses'))).toEqual([]);
  writeFileSync(`${out}/navigation-readonly.json`, JSON.stringify({ task_id: task.task_id, writes, business_writes: 0, history_refresh_identity: true }, null, 2));
});

test('quick QA starts one independent run, restores exact URL and keeps task return separate', async ({ page }) => {
  const doc = task.input.reports[0].document_id;
  await page.goto('/research?mode=qa'); const writes = watch(page);
  await expect(page.getByRole('heading', { name: '原文问答', exact: true })).toBeVisible();
  await manageQASources(page);
  const source = page.locator('label').filter({ has: page.locator(`input[type=checkbox]`) }).filter({ hasText: '美的集团股份有限公司 · 2025 年报' });
  await source.getByRole('checkbox').check();
  await finishQASources(page);
  await page.getByLabel('研究问题', { exact: true }).fill('列出年报中的营业收入原值，不计算同比。');
  await page.getByRole('button', { name: '查找原文', exact: true }).click();
  const detail = page.getByRole('region', { name: '研究历史详情' });
  await expect(detail).toContainText('年报原文回答');
  const run = await detail.getAttribute('data-run-id'); expect(run).toBeTruthy();
  expect(new URL(page.url()).searchParams.get('run')).toBe(run);
  expect(new URL(page.url()).searchParams.has('task')).toBe(false);
  await expect(page.getByRole('complementary', { name: '本次回答来源' })).toContainText('独立 ResearchRun');
  await page.reload(); await expect(detail).toHaveAttribute('data-run-id', run!);
  await page.goto(`/research?mode=qa&company=unrelated&run=${run}`);
  await expect(detail).toHaveAttribute('data-run-id', run!); await expect(detail).toContainText('2025 年报');
  await expect(detail).not.toContainText('unrelated');
  expect(writes.filter(w => w.url.endsWith('/research/runs'))).toHaveLength(1);
  expect(writes.some(w => /\/research\/tasks/.test(w.url))).toBe(false);
  writeFileSync(`${out}/qa-route-proof.json`, JSON.stringify({ run_id: run, expected_document: doc, writes, restore_zero_posts: true, independent_run: true }, null, 2));
});

test('dual company frozen task ignores selector and switching independent company scope performs no research writes', async ({ page }) => {
  await harness(page);
  const companies = await (await page.request.get('/api/companies')).json();
  const other = companies.find((c: any) => c.security_code === '000651');
  const docs = await (await page.request.get('/api/research/sources')).json();
  const report = docs.documents.find((d: any) => d.company_id === other.company_id && d.report_year === 2025);

  // Obtain disclosure with the existing request contract, via the explicit creation form.
  await page.goto(`/research?company=${company}&mode=operating&new=1`);
  await page.getByRole('button', { name: /两企业同期间比较/ }).click();
  await page.getByLabel('second 企业', { exact: true }).selectOption(other.company_id);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await page.getByLabel('first 年报', { exact: true }).selectOption(task.input.reports[0].document_id);
  await page.getByLabel('second 年报', { exact: true }).selectOption(report.document_id);
  await page.getByRole('button', { name: '下一步：确认来源', exact: true }).click();
  for (const group of await page.locator('.operating-side').all()) await group.getByRole('button', { name: '采用这组三项来源', exact: true }).click();
  const created = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/research/tasks'));
  await page.getByRole('button', { name: '创建研究，开始核对数据', exact: true }).click();
  const dual = await (await created).json();
  const writes = watch(page);
  const context = page.getByRole('region', { name: '研究上下文' });
  await expect(context).toContainText('美的集团'); await expect(context).toContainText('珠海格力');
  await expect(page.getByLabel('当前企业', { exact: true })).toHaveCount(0);
  await page.goto(`/research?company=${other.company_id}&mode=operating&task=${dual.task_id}`);
  await expect(context).toHaveAttribute('data-task-id', dual.task_id); await expect(context).toContainText('美的集团');
  await page.reload(); await expect(context).toContainText('珠海格力');
  await page.goto(`/research?mode=qa&company=${company}`);
  await page.getByLabel('当前企业', { exact: true }).selectOption(other.company_id);
  await expect(page.getByLabel('所选资料摘要', { exact: true })).toBeEmpty();
  expect(writes).toEqual([]);
  writeFileSync(`${out}/dual-context-proof.json`, JSON.stringify({ task_id: dual.task_id, first: dual.input.first.company_id, second: dual.input.second.company_id, writes, top_selector_absent: true }, null, 2));
});

test('formal components at seven CSS widths: text/controls bounds, long names, amounts and keyboard dialogs', async ({ page, browser }) => {
  await harness(page);
  // A presentation-only long-name fixture; object IDs and all financial/source responses remain real.
  await page.route('**/api/companies', async r => {
    if (r.request().method() !== 'GET') return r.continue();
    const response = await r.fetch(), rows = await response.json();
    rows.find((c: any) => c.company_id === company).name = '美的集团股份有限公司及其合并范围内的长期企业经营研究资料';
    await r.fulfill({ response, json: rows });
  });
  const widths = [1440, 1280, 1024, 720, 640, 512, 390], observations: any[] = [];
  const reviewURL = `/evidence?${new URLSearchParams({ company, task: task.task_id, side: 'first', period: '2025', metric_key: 'revenue', disclosure: task.input.first.choices[0].disclosure_version, document: task.input.reports[0].document_id, revision: task.input.reports[0].expected_source_revision, return_to: 'operating' })}`;
  const pages = [['home', '/'], ['research', taskURL], ['qa-entry', '/research?mode=qa'], ['report-history', '/reports'], ['review', reviewURL]];
  for (const [name, path] of pages) {
    await page.goto(path);
    if (name === 'home') await expect(page.getByLabel('当前研究', { exact: true })).not.toContainText('正在读取你的研究');
    if (name === 'qa-entry') { await manageQASources(page); await expect(page.getByRole('dialog').getByRole('checkbox')).not.toHaveCount(0); await finishQASources(page); }
    if (name === 'research') await expect(page.getByRole('region', { name: '研究上下文' })).toHaveAttribute('data-task-id', task.task_id);
    if (name === 'review') {
      await expect(page.getByTestId('review-candidate')).toHaveCount(3);
    }
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      // Reader is closed for candidate/primary-action bounds; the actual drawer is checked below.
      const back = page.locator('.evidence-viewer').getByRole('button', { name: '返回核对', exact: true });
      if (name === 'review' && await back.isVisible()) await back.click();
      const measure = await page.evaluate(() => {
        const controls = [...document.querySelectorAll<HTMLElement>('main h1, main h2, main .home-create, main .operating-primary, main .approval-primary, main .candidate-heading button, main .candidate-value, main .amount-comparison dd, main .candidate-heading p, main .review-scope')].filter(e => e.getClientRects().length && !e.closest('[hidden], details:not([open]) > :not(summary), .table-scroll, .report-table-scroll'));
        return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
          bounds: controls.map(e => { const r = e.getBoundingClientRect(); const range = document.createRange(); range.selectNodeContents(e);
            return { text: e.innerText, x: r.x, right: r.right, width: r.width, height: r.height, scrollWidth: e.scrollWidth, clientWidth: e.clientWidth,
              textRects: [...range.getClientRects()].map(t => ({ x: t.x, right: t.right, width: t.width, height: t.height })) }; }) };
      });
      expect(measure.scrollWidth, `${name} ${width} page`).toBeLessThanOrEqual(width + 1);
      for (const b of measure.bounds) { expect(b.x, b.text).toBeGreaterThanOrEqual(-1); expect(b.right, b.text).toBeLessThanOrEqual(width + 1); expect(b.scrollWidth, b.text).toBeLessThanOrEqual(b.clientWidth + 1); }
      for (const b of measure.bounds) for (const r of b.textRects) { expect(r.x, b.text).toBeGreaterThanOrEqual(-1); expect(r.right, b.text).toBeLessThanOrEqual(width + 1); }
      if (name === 'review') {
        const candidates = page.getByTestId('review-candidate');
        await expect(candidates).toHaveCount(3);
        for (const c of await candidates.all()) {
          const group = c.locator('xpath=..'), summary = group.locator(':scope > summary');
          if (!await group.evaluate(e => (e as HTMLDetailsElement).open)) await summary.click();
          if (await back.isVisible()) await back.click();
          await expect(c).toContainText('2025'); await expect(c.locator('.candidate-value')).toBeVisible();
          await expect(c.locator('.candidate-value')).not.toBeEmpty();
          const normalized = c.getByText('规范金额与单位换算', { exact: true });
          if (!await normalized.evaluate(e => (e.parentElement as HTMLDetailsElement).open)) await normalized.click();
          const values = await c.locator('.candidate-value, .amount-comparison dd, .amount-link, ul button').evaluateAll(elements => elements.map(e => {
            const b = e.getBoundingClientRect(), range = document.createRange(); range.selectNodeContents(e);
            return { text: (e as HTMLElement).innerText, x: b.x, right: b.right, width: b.width, height: b.height,
              scrollWidth: e.scrollWidth, clientWidth: e.clientWidth,
              textRects: [...range.getClientRects()].map(r => ({ x: r.x, right: r.right })) };
          }));
          for (const v of values) {
            expect(v.height, v.text).toBeGreaterThan(0); expect(v.x, v.text).toBeGreaterThanOrEqual(-1);
            expect(v.right, v.text).toBeLessThanOrEqual(width + 1); expect(v.scrollWidth, v.text).toBeLessThanOrEqual(v.clientWidth + 1);
            for (const r of v.textRects) { expect(r.x, v.text).toBeGreaterThanOrEqual(-1); expect(r.right, v.text).toBeLessThanOrEqual(width + 1); }
          }
          observations.push({ page: 'review-candidate', width, candidate: await summary.innerText(), values });
        }
      }
      observations.push({ page: name, ...measure });
      await page.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true });
    }
  }
  await page.goto('/'); await page.setViewportSize({ width: 1024, height: 900 });
  const menu = page.getByRole('button', { name: '打开导航', exact: true }); await menu.focus(); await page.keyboard.press('Enter');
  const drawer = page.getByRole('dialog', { name: '产品导航菜单' }); const close = drawer.getByRole('button', { name: '关闭导航', exact: true });
  await expect(close).toBeFocused(); await page.keyboard.press('Shift+Tab'); await expect(drawer.getByRole('link', { name: '报告', exact: true })).toBeFocused();
  await page.keyboard.press('Tab'); await expect(close).toBeFocused(); await page.keyboard.press('Escape'); await expect(menu).toBeFocused(); await expect(drawer).toHaveCount(0);
  await page.goto(taskURL); await page.setViewportSize({ width: 390, height: 900 });
  const tabs = page.getByRole('navigation', { name: '当前研究功能' }).getByRole('link');
  await tabs.first().focus();
  for (let i = 1; i < 5; i++) { await page.keyboard.press('Tab'); await expect(tabs.nth(i)).toBeFocused(); }
  const last = await tabs.last().boundingBox(); expect(last!.x).toBeGreaterThanOrEqual(0); expect(last!.x + last!.width).toBeLessThanOrEqual(390);
  await page.goto(reviewURL); await page.setViewportSize({ width: 390, height: 900 });
  await expect(page.getByTestId('review-candidate')).toHaveCount(3);
  const writes = watch(page);
  await page.getByRole('button', { name: '开始本组核对', exact: true }).click();
  for (const metric of ['营业收入', '归母净利润', '经营活动现金流量净额']) {
    const check = page.getByLabel(`已核对 2025 ${metric}`, { exact: true });
    if (!await check.isVisible()) await page.locator('.candidate-item > summary').filter({ hasText: metric }).click();
    await check.check();
  }
  const confirm = page.getByRole('button', { name: '确认本组数据', exact: true }); await confirm.click();
  const dialog = page.getByRole('dialog', { name: '人工核对确认' });
  await expect(dialog).toBeVisible(); await expect(dialog.getByRole('checkbox')).not.toBeChecked();
  await expect(dialog.getByRole('button', { name: '我已核对并接受', exact: true })).toBeDisabled();
  await page.screenshot({ path: `${out}/review-dialog-390.png`, fullPage: true });
  await page.keyboard.press('Escape'); await expect(confirm).toBeFocused();
  expect(writes.filter(w => /confirmations|persisted|\/resume|\/reports/.test(w.url))).toEqual([]);
  writeFileSync(`${out}/responsive-keyboard-proof.json`, JSON.stringify({ browser: browser.version(), widths, observations, drawer_focus_trap: true, escape_returns_focus: true, consent_unchecked: true, cancel_zero_business_writes: true, native_chrome_200_percent: 'pending', simulated_test: true }, null, 2));
});

test('production build entry smoke and screenshots preserve gates without business writes', async ({ page, browser }) => {
  // No d20 entry intercept or UI source/company fixtures: compiled production React and CSS.
  const writes = watch(page), observations: any[] = [];
  const widths = [1440, 1280, 1024, 720, 640, 512, 390];
  const paths = [['home', '/'], ['research', taskURL], ['qa-entry', '/research?mode=qa'], ['report-history', '/reports']];
  for (const [name, path] of paths) {
    await page.goto(path);
    if (name === 'home') await expect(page.getByLabel('当前研究', { exact: true })).not.toContainText('正在读取你的研究');
    if (name === 'research') {
      await expect(page.getByRole('region', { name: '研究上下文' })).toHaveAttribute('data-task-id', task.task_id);
      await expect(page.getByRole('region', { name: '有限经营研究结果' })).toHaveCount(0);
      await expect(page.getByRole('alert').filter({ hasText: '旧分析及 PDF 引用已撤下' })).toBeVisible();
    }
    if (name === 'qa-entry') { await expect(page.getByRole('button', { name: '查找原文', exact: true })).toBeDisabled(); await manageQASources(page); await expect(page.getByRole('dialog')).toContainText('2025 年报'); await finishQASources(page); }
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      const bounds = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        titles: [...document.querySelectorAll<HTMLElement>('main h1, main .home-create, main .operating-primary')].filter(e => e.getClientRects().length).map(e => {
          const r = e.getBoundingClientRect(); return { text: e.innerText, left: r.left, right: r.right, height: r.height, scrollWidth: e.scrollWidth, clientWidth: e.clientWidth };
        }) }));
      expect(bounds.scrollWidth).toBeLessThanOrEqual(width + 1);
      for (const t of bounds.titles) { expect(t.left).toBeGreaterThanOrEqual(-1); expect(t.right).toBeLessThanOrEqual(width + 1); expect(t.scrollWidth).toBeLessThanOrEqual(t.clientWidth + 1); }
      observations.push({ page: name, ...bounds });
      await page.screenshot({ path: `${out}/production-${name}-${width}.png`, fullPage: true });
    }
  }
  expect(writes).toEqual([]);
  writeFileSync(`${out}/production-smoke-proof.json`, JSON.stringify({ browser: browser.version(), widths, observations, writes, production_gate_preserved: true, simulated_backend_seed: true, frontend_entry: 'compiled production', native_chrome_200_percent: 'pending' }, null, 2));
});
