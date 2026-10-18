import { test, expect, type Page } from '@playwright/test';
import { randomUUID, createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
const out = process.env.UX_ARTIFACT_DIR!;
const seed = JSON.parse(readFileSync(`${process.env.D26_REPORT_SEED_DIR}/journey-proof.json`, 'utf8'));
async function setup(page: Page) {
  await page.route('**/src/main.tsx*', r => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const task = await (await page.request.get(`/api/research/tasks/${seed.result.task_id}`)).json();
  const post = async (path: string, revision?: number) => {
    const response = await page.request.post(path, { data: { operation_id: randomUUID(), task_id: task.task_id, expected_task_revision: task.revision, ...(revision ? { expected_report_revision: revision } : {}), edits: { title: `S5 v${revision ? 2 : 1} 阅读报告`, conclusions: [revision ? 'S5 v2 新增用户结论，待人工语义审阅。' : 'S5 v1 初始用户结论。'] } } });
    expect(response.ok(), await response.text()).toBe(true); return response.json();
  };
  const v1 = await post('/api/reports'); const v2 = await post(`/api/reports/${v1.report.report_id}/revisions`, 1);
  return { task, v1, v2, url: `/reports?report=${v1.report.report_id}&revision=1` };
}
test('S5 historical v1 is entirely read-only while latest v2 is explicitly editable', async ({ page }) => {
  const { v1, v2, url } = await setup(page); await page.goto(url);
  const article = page.getByRole('article', { name: '已保存报告版本' }); await expect(article).toContainText('S5 v1');
  await page.screenshot({ path: `${out}/historical-v1.png`, fullPage: true });
  // This deliberately fails on S4: history mounts editable inputs despite disabled save.
  await expect(page.getByLabel('用户编辑标题（可选）')).toHaveCount(0);
  await expect(page.getByLabel('报告标题', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '打开最新版本后编辑', exact: true }).click();
  await expect(article).toContainText('S5 v2');
  await expect(page.getByRole('region', { name: '编辑报告', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  await expect(page.getByLabel('报告标题', { exact: true })).toHaveValue(v2.report.editor_revision.title);
  await page.screenshot({ path: `${out}/editing-1440.png` });
  await page.setViewportSize({ width: 390, height: 900 }); await page.getByLabel('报告标题', { exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${out}/editing-390.png` });
  const { generated_at: generation1, ...frozen1 } = v1.report.trusted_snapshot;
  const { generated_at: generation2, ...frozen2 } = v2.report.trusted_snapshot;
  expect(frozen1).toEqual(frozen2); expect(generation1).toBeTruthy(); expect(generation2).toBeTruthy();
});
test('S5 comparison performs two exact GETs and does not write or use a cached failed side', async ({ page }) => {
  const { v1, v2, url } = await setup(page); await page.goto(url);
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toBeVisible();
  const writes: string[] = [], gets: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); else if (r.url().includes('/revisions/')) gets.push(r.url()); });
  const before = await (await page.request.get('/api/__test__/d26-counts')).json();
  await page.getByRole('button', { name: '比较版本', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '报告版本对照', exact: true });
  await expect(dialog).toContainText('S5 v1'); await expect(dialog).toContainText('S5 v2');
  await expect(dialog).toContainText('固定财务事实与公式快照相同');
  await expect(dialog).toContainText('来源快照相同');
  await expect(dialog).toContainText('待人工语义审阅');
  expect(gets.filter(u => u.endsWith('/revisions/1')).length).toBeGreaterThanOrEqual(1);
  expect(gets.filter(u => u.endsWith('/revisions/2')).length).toBeGreaterThanOrEqual(1);
  await page.screenshot({ path: `${out}/comparison-1440.png` });
  await page.route(`**/api/reports/${v1.report.report_id}/revisions/2`, r => r.fulfill({ status: 503, json: { error_code: 'test_read_failure' } }));
  await dialog.getByRole('button', { name: '重新读取两个版本' }).click();
  await expect(dialog.getByRole('alert')).toBeVisible();
  await expect(dialog.getByText(v2.report.editor_revision.conclusions[0], { exact: true })).toHaveCount(0);
  expect(writes).toEqual([]); expect(await (await page.request.get('/api/__test__/d26-counts')).json()).toEqual(before);
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: '比较版本', exact: true })).toBeFocused();
  writeFileSync(`${out}/comparison-proof.json`, JSON.stringify({ report_id: v1.report.report_id, gets, writes, before, failed_side_removed: true }, null, 2));
});
test('S5 exact v1 download has the selected identity, frozen payload and byte SHA', async ({ page }) => {
  const { v1, url } = await setup(page); await page.goto(url);
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toBeVisible();
  const endpoint = `/reports/${v1.report.report_id}/revisions/1/markdown`;
  const responseEvent = page.waitForResponse(r => r.url().endsWith(endpoint)); const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载 v1 · Markdown', exact: true }).click();
  const response = await responseEvent, download = await downloadEvent;
  await download.saveAs(`${out}/exact-v1.md`); expect(await download.failure()).toBeNull();
  const bytes = readFileSync(`${out}/exact-v1.md`), sha256 = createHash('sha256').update(bytes).digest('hex');
  expect(bytes).toEqual(await response.body()); expect(sha256).toBe(response.headers()['x-markdown-sha256']);
  expect(response.headers()['x-report-id']).toBe(v1.report.report_id); expect(response.headers()['x-report-revision']).toBe('1');
  expect(response.headers()['x-report-payload-sha256']).toBe(v1.payload_sha256);
  expect(download.suggestedFilename()).toContain(`-${v1.report.report_id}-v1.md`);
  expect(bytes.toString()).toContain('S5 v1 初始用户结论'); expect(bytes.toString()).not.toContain('S5 v2 新增用户结论');
  await expect(page.getByRole('status').filter({ hasText: '已交给浏览器下载' })).toBeVisible();
  writeFileSync(`${out}/exact-export-proof.json`, JSON.stringify({ report_id: v1.report.report_id, revision: 1, payload_sha256: v1.payload_sha256, headers: response.headers(), sha256, filename: download.suggestedFilename(), playwright_saveAs_verified: true, browser_receipt_alone_is_disk_proof: false }, null, 2));
});
test('S5 saved library and linked outline preserve frozen scope and readable document', async ({ page }) => {
  const { v1, url } = await setup(page); await page.goto('/reports');
  const row = page.locator(`.report-library-list li[data-report-id="${v1.report.report_id}"]`);
  await expect(row).toContainText('美的'); await expect(row).toContainText('2025'); await expect(row).toContainText('保存于');
  await page.screenshot({ path: `${out}/library-1440.png`, fullPage: true });
  await page.goto(url); const article = page.getByRole('article', { name: '已保存报告版本' }); await expect(article).toBeVisible();
  const outline = page.getByRole('navigation', { name: '报告正文目录' });
  await outline.getByRole('button', { name: /06.*未解决问题/ }).click();
  await expect(outline.getByRole('button', { name: /06.*未解决问题/ })).toHaveAttribute('aria-current', 'location');
  await expect(article.getByRole('heading', { name: /06.*未解决问题/ })).toBeFocused();
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(outline.getByRole('button', { name: /01.*执行摘要/ })).toHaveAttribute('aria-current', 'location');
  await expect(article.locator('input,textarea')).toHaveCount(0);
  await page.screenshot({ path: `${out}/reading-1440.png`, fullPage: true });
});
test('S5 dirty editing protects navigation, cancellation and versions without autosave', async ({ page }) => {
  const { v1, v2 } = await setup(page);
  await page.goto(`/reports?report=${v1.report.report_id}&revision=2`);
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  const title = page.getByLabel('报告标题', { exact: true }); await expect(title).toBeFocused();
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await title.fill('尚未保存的新标题'); await expect(page.getByRole('status').filter({ hasText: '当前编辑尚未保存' })).toBeVisible();
  await page.getByRole('navigation', { name: '产品导航' }).getByRole('link', { name: '我的研究', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '修改尚未保存' }); await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(title).toHaveValue('尚未保存的新标题');
  await page.getByLabel('报告版本', { exact: true }).selectOption('1'); await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: '继续编辑', exact: true }).click(); await expect(page.getByLabel('报告版本', { exact: true })).toHaveValue('2');
  await page.getByRole('button', { name: '取消编辑', exact: true }).click(); await expect(dialog).toBeVisible();
  await page.screenshot({ path: `${out}/discard-dialog.png` });
  await dialog.getByRole('button', { name: '放弃修改并离开', exact: true }).click();
  await expect(page.getByRole('region', { name: '编辑报告', exact: true })).toHaveCount(0);
  const again = await (await page.request.get(`/api/reports/${v1.report.report_id}/revisions/2`)).json(); expect(again.report).toEqual(v2.report); expect(writes).toEqual([]);
  writeFileSync(`${out}/dirty-navigation-proof.json`, JSON.stringify({ report_id: v1.report.report_id, writes, persisted_revision_unchanged: true, escape_and_continue_keep_text: true }, null, 2));
});
test('S5 seven widths retain operations, exact amounts, keyboard dialogs and local table scrolling', async ({ page }) => {
  const { v1, url } = await setup(page); const observations: any[] = [];
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.goto(url); const article = page.getByRole('article', { name: '已保存报告版本' }); await expect(article).toBeVisible();
  for (const width of [1440, 1280, 1024, 720, 640, 512, 390]) {
    await page.setViewportSize({ width, height: 900 }); await page.evaluate(() => scrollTo(0, 0));
    const layout = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, controls: [...document.querySelectorAll<HTMLElement>('.report-version-bar button,.report-version-bar select,.report-paper h1,.report-detail .task-context-header h2')].map(n => ({ text: n.textContent, left: n.getBoundingClientRect().left, right: n.getBoundingClientRect().right, scroll: n.scrollWidth, client: n.clientWidth })), paperFont: getComputedStyle(document.querySelector('.report-paper')!).fontSize }));
    expect(layout.scrollWidth).toBeLessThanOrEqual(width + 1); expect(parseFloat(layout.paperFont)).toBeGreaterThanOrEqual(16);
    for (const c of layout.controls) { expect(c.left).toBeGreaterThanOrEqual(-1); expect(c.right).toBeLessThanOrEqual(width + 1); expect(c.scroll).toBeLessThanOrEqual(c.client + 1); }
    for (const f of v1.report.trusted_snapshot.financial_facts) {
      const row = article.locator(`[data-fact-id="${f.fact_id}"]`); await expect(row).toContainText(`${f.raw_value} ${f.raw_unit}`); await expect(row.locator('data')).toHaveAttribute('value', f.value_cny_yuan); await expect(row.locator('data')).toHaveText(f.value_cny_yuan.replace(/\B(?=(\d{3})+(?!\d))/g, ','));
    }
    await page.screenshot({ path: `${out}/reading-${width}.png`, fullPage: true });
    await page.screenshot({ path: `${out}/reading-top-${width}.png` });
    await page.getByRole('button', { name: '比较版本', exact: true }).click(); const dialog = page.getByRole('dialog', { name: '报告版本对照' });
    await expect(dialog).toContainText('固定财务事实与公式快照相同');
    expect(await dialog.evaluate(e => e.scrollWidth <= e.clientWidth + 1)).toBe(true);
    await expect(dialog.getByRole('button', { name: '关闭报告版本对照' })).toBeFocused();
    await page.keyboard.press('Shift+Tab'); await expect(dialog.getByRole('button', { name: '返回报告', exact: true })).toBeFocused();
    await page.keyboard.press('Tab'); await expect(dialog.getByRole('button', { name: '关闭报告版本对照' })).toBeFocused();
    await page.screenshot({ path: `${out}/comparison-${width}.png` });
    await page.keyboard.press('Escape'); await expect(page.getByRole('button', { name: '比较版本', exact: true })).toBeFocused();
    observations.push(layout);
  }
  const table = page.getByRole('region', { name: '已确认财务事实表，可横向滚动' });
  await table.focus(); const before = await table.evaluate(e => e.scrollLeft); await page.keyboard.press('ArrowRight');
  await expect.poll(() => table.evaluate(e => e.scrollLeft)).toBeGreaterThan(before);
  expect(writes).toEqual([]);
  writeFileSync(`${out}/responsive-proof.json`, JSON.stringify({ observations, exact_amounts_all_widths: true, table_keyboard_scroll: true, writes, native_chrome_200_percent: 'pending' }, null, 2));
});
test('S5 multi-field edits explicitly append v3 and protect browser Back', async ({ page }) => {
  const { v1, v2, url } = await setup(page); await page.goto(url);
  await page.getByLabel('报告版本', { exact: true }).selectOption('2');
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  await page.getByLabel('用户结论 1（待人工语义审阅）').fill('v3 第一项用户断言。');
  await page.getByRole('button', { name: '添加用户结论' }).click(); await page.getByLabel('用户结论 2（待人工语义审阅）').fill('v3 第二项用户断言。');
  await page.goBack(); const dialog = page.getByRole('dialog', { name: '修改尚未保存' }); await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: '继续编辑', exact: true }).click();
  await expect(page.getByLabel('用户结论 2（待人工语义审阅）')).toHaveValue('v3 第二项用户断言。');
  const posts: any[] = []; page.on('request', r => { if (r.method() === 'POST') posts.push({ url: r.url(), body: r.postDataJSON() }); });
  await page.getByRole('button', { name: '保存为 v3', exact: true }).dblclick();
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toContainText('v3 第二项用户断言');
  expect(posts).toHaveLength(1); expect(posts[0].body.edits.conclusions).toEqual(['v3 第一项用户断言。', 'v3 第二项用户断言。']);
  const original = await (await page.request.get(`/api/reports/${v1.report.report_id}/revisions/2`)).json(); expect(original.report).toEqual(v2.report);
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存为 v4', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '取消编辑', exact: true }).click();
  writeFileSync(`${out}/multifield-save-proof.json`, JSON.stringify({ posts, immutable_v2_exact: true, browser_back_retains_two_unsaved_fields: true }, null, 2));
});
test('S5 long title, four user conclusions and frozen company text wrap at seven widths', async ({ page }) => {
  const { v1, v2, task } = await setup(page);
  const title = '经营变化与长期现金流风险的用户研究标题'.repeat(10).slice(0, 200);
  const conclusions = Array.from({ length: 4 }, (_, i) => `第${i + 1}项用户断言，尚待人工审阅。` + '需核对经营原文与来源。'.repeat(60));
  const response = await page.request.post(`/api/reports/${v1.report.report_id}/revisions`, { data: { operation_id: randomUUID(), task_id: task.task_id, expected_task_revision: task.revision, expected_report_revision: 2, edits: { title, conclusions } } });
  expect(response.ok()).toBe(true); const saved = await response.json();
  // Bounded renderer fixture: only frozen display names change; IDs, years, money,
  // formulas, source revisions and database remain real and unchanged.
  const presented = structuredClone(saved), longCompany = '大型跨国企业集团股份有限公司及其合并财务报告研究范围'.repeat(4);
  for (const f of presented.report.trusted_snapshot.financial_facts) f.company_name = longCompany;
  await page.route(`**/api/reports/${v1.report.report_id}/revisions/3`, r => r.fulfill({ json: presented }));
  await page.goto(`/reports?report=${v1.report.report_id}&revision=3`);
  const article = page.getByRole('article', { name: '已保存报告版本' }); await expect(article).toContainText(title); await expect(page.getByRole('region', { name: '报告冻结上下文' })).toContainText(longCompany);
  const observations: any[] = [];
  for (const width of [1440, 1280, 1024, 720, 640, 512, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const bounds = await page.evaluate(() => ({ width: innerWidth, page: document.documentElement.scrollWidth, titles: [...document.querySelectorAll<HTMLElement>('.report-paper h1,.report-detail .task-context-header h2')].map(n => ({ scroll: n.scrollWidth, client: n.clientWidth, left: n.getBoundingClientRect().left, right: n.getBoundingClientRect().right })) }));
    expect(bounds.page).toBeLessThanOrEqual(width + 1); for (const b of bounds.titles) { expect(b.scroll).toBeLessThanOrEqual(b.client + 1); expect(b.left).toBeGreaterThanOrEqual(-1); expect(b.right).toBeLessThanOrEqual(width + 1); }
    observations.push(bounds); await page.screenshot({ path: `${out}/long-title-${width}.png` });
  }
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  for (let i = 0; i < 4; i++) await expect(page.getByLabel(`用户结论 ${i + 1}（待人工语义审阅）`)).toHaveValue(conclusions[i]);
  await expect(page.getByRole('button', { name: '添加用户结论' })).toHaveCount(0); await expect(page.getByRole('button', { name: '保存为 v4', exact: true })).toBeDisabled();
  await page.screenshot({ path: `${out}/editor-390.png`, fullPage: true });
  const read = await (await page.request.get(`/api/reports/${v1.report.report_id}/revisions/2`)).json(); expect(read.report).toEqual(v2.report);
  writeFileSync(`${out}/long-reading-proof.json`, JSON.stringify({ presentation_fixture_only: true, modified_display_field: 'financial_facts.company_name', actual_saved_title_length: title.length, actual_four_saved_conclusions: true, observations, v2_immutable: true }, null, 2));
});
test('S5 wrong revision identity and refresh failure remove cached details while library remains readable', async ({ page }) => {
  const { v1, v2, url } = await setup(page);
  await page.route(`**/api/reports/${v1.report.report_id}/revisions/1`, r => r.fulfill({ json: v2 }));
  await page.goto(url);
  const alert = page.getByRole('alert').filter({ hasText: '报告版本身份或不可变内容不一致' }); await expect(alert).toBeVisible();
  await expect(page.getByRole('button', { name: '刷新报告历史', exact: true })).toBeEnabled();
  await expect(alert).toBeVisible(); await expect(page.getByRole('article', { name: '已保存报告版本' })).toHaveCount(0);
  await page.unroute(`**/api/reports/${v1.report.report_id}/revisions/1`); await page.goto(url);
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toBeVisible();
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.route(`**/api/reports/${v1.report.report_id}/revisions/1`, r => r.fulfill({ status: 503, json: { error_code: 'test_unavailable' } }));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '下载 v1 · Markdown', exact: true })).toHaveCount(0);
  await expect(page.getByRole('alert').filter({ hasText: '历史完整性或资格无法读回' })).toBeVisible(); expect(writes).toEqual([]);
  writeFileSync(`${out}/identity-failure-proof.json`, JSON.stringify({ wrong_revision_rejected: true, detail_error_survives_successful_list: true, failed_refresh_removes_cached_report: true, writes }, null, 2));
});
for (const fault of ['wrong-report', 'wrong-revision', 'wrong-payload', 'bad-sha', 'truncated', 'unsafe-filename', 'wrong-eligibility', 'dispatch']) {
  test(`S5 export fails closed for ${fault}`, async ({ page }) => {
    const { url } = await setup(page); await page.goto(url); await expect(page.getByRole('article', { name: '已保存报告版本' })).toBeVisible();
    let downloads = 0; page.on('download', () => downloads++);
    if (fault === 'dispatch') await page.evaluate(() => { HTMLAnchorElement.prototype.click = () => { throw new Error('test_dispatch_failed'); }; });
    else await page.route('**/revisions/1/markdown', async route => {
      const response = await route.fetch(), headers = { ...response.headers() };
      if (fault === 'wrong-report') headers['x-report-id'] = 'another-report';
      if (fault === 'wrong-revision') headers['x-report-revision'] = '2';
      if (fault === 'wrong-payload') headers['x-report-payload-sha256'] = 'f'.repeat(64);
      if (fault === 'bad-sha') headers['x-markdown-sha256'] = 'f'.repeat(64);
      if (fault === 'unsafe-filename') headers['content-disposition'] = "attachment; filename*=UTF-8''..%2Fbad.md";
      if (fault === 'wrong-eligibility') headers['x-report-eligibility'] = 'qualified_at_export';
      await route.fulfill({ response, headers, ...(fault === 'truncated' ? { body: '截断' } : {}) });
    });
    await page.getByRole('button', { name: '下载 v1 · Markdown', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: '导出或下载失败' })).toBeVisible();
    expect(downloads).toBe(0); await expect(page.getByRole('status').filter({ hasText: '已交给浏览器下载' })).toHaveCount(0);
  });
}
if (process.env.S5_COMPILED_REPORT_TEST === '1') test('S5 compiled production entry refuses simulated revisions and draft qualification', async ({ page }) => {
  const { v1, url, task } = await setup(page);
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.goto(url);
  await expect(page.getByRole('alert').filter({ hasText: '报告结构或研究身份不一致' })).toBeVisible();
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '编辑为新版本' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '下载 v1 · Markdown' })).toHaveCount(0);
  await page.goto(`/reports?task=${task.task_id}`);
  await page.getByRole('button', { name: '生成草稿', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '报告结构或研究身份不一致' })).toBeVisible();
  await expect(page.getByRole('article', { name: '报告草稿预览' })).toHaveCount(0);
  expect(writes).toHaveLength(1); expect(writes[0]).toContain('/reports/drafts');
  writeFileSync(`${out}/compiled-production-proof.json`, JSON.stringify({ report_id: v1.report.report_id, simulated_history_rejected: true, simulated_draft_rejected: true, writes, fixture_report_saves: 2, human_acceptances: 0 }, null, 2));
});
test('S5 source correction withdraws PDF, edit and export while preserving exact audit revisions', async ({ page }) => {
  const { v1, url } = await setup(page); await page.goto(url); const article = page.getByRole('article', { name: '已保存报告版本' }); await expect(article).toBeVisible();
  const trigger = article.getByRole('button', { name: /原 PDF · 物理/ }).first(); await trigger.scrollIntoViewIfNeeded(); const y = await page.evaluate(() => scrollY);
  await trigger.click(); const dialog = page.getByRole('dialog', { name: '原 PDF · 财务事实' }); await expect(dialog.locator('canvas')).toBeVisible({ timeout: 30_000 });
  const f = v1.report.trusted_snapshot.financial_facts[0];
  const source = await (await page.request.get(`/api/documents/${f.document_id}/source?${new URLSearchParams({ company_id: f.company_id, source_revision: f.source_revision })}`)).json();
  const pdf = await page.request.get(`/api/documents/${f.document_id}/file?${new URLSearchParams({ company_id: f.company_id, source_revision: f.source_revision })}`);
  const pdfSha = createHash('sha256').update(await pdf.body()).digest('hex'); expect(pdfSha).toBe(source.content_sha256);
  await page.screenshot({ path: `${out}/report-pdf-1440.png` }); await page.keyboard.press('Escape'); await expect(trigger).toBeFocused(); expect(Math.abs((await page.evaluate(() => scrollY)) - y)).toBeLessThan(3);
  await page.setViewportSize({ width: 390, height: 900 }); await trigger.click(); await expect(dialog.locator('canvas')).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: `${out}/report-pdf-390.png` });
  const d = source;
  const response = await page.request.post(`/api/documents/${f.document_id}/binding-corrections`, { data: { expected_attempt: d.attempt, metadata: { company_id: d.company_id, report_year: d.report_year, report_type: 'annual', basis: 'unknown', period_start: `${d.report_year}-01-01`, period_end: `${d.report_year}-12-31` }, reason: 'S5 isolated source invalidation test' } });
  expect(response.status()).toBe(200); await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(dialog.locator('canvas')).toHaveCount(0); await page.keyboard.press('Escape');
  await expect(article).toContainText('来源已失效'); await expect(page.getByRole('button', { name: '打开最新版本后编辑' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '下载 v1 · Markdown', exact: true })).toBeDisabled();
  const read = await (await page.request.get(`/api/reports/${v1.report.report_id}/revisions/1`)).json(); expect(read.report).toEqual(v1.report); expect(read.payload_sha256).toBe(v1.payload_sha256);
  const denied = await page.request.get(`/api/reports/${v1.report.report_id}/revisions/1/markdown`); expect(denied.status()).toBe(409);
  const before = await (await page.request.get('/api/__test__/d26-counts')).json();
  await page.getByRole('button', { name: '比较版本', exact: true }).click(); const comparison = page.getByRole('dialog', { name: '报告版本对照' }); await expect(comparison).toContainText('仅供历史审计对照');
  await page.keyboard.press('Escape'); await page.reload(); await expect(article).toContainText('来源已失效');
  expect(await (await page.request.get('/api/__test__/d26-counts')).json()).toEqual(before);
  await page.screenshot({ path: `${out}/invalidated-390.png`, fullPage: true });
  writeFileSync(`${out}/source-invalidation-proof.json`, JSON.stringify({ report_id: v1.report.report_id, immutable_payload_sha256: v1.payload_sha256, pdfSha, actual_binding_correction: true, export_status: denied.status(), before, human_acceptances: 0 }, null, 2));
});
