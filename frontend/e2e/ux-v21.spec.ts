import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { verifyReportJourney } from '../tests/support/d24-ux-report-journey.ts';
const sources = JSON.parse(readFileSync(process.env.UX_SOURCE_FILE!, 'utf8'));
const out = process.env.UX_ARTIFACT_DIR!;
const live = process.env.FINDOC_UX_LIVE === '1';
const metrics = ['revenue', 'net_profit_parent', 'operating_cash_flow'];
const names = ['营业收入', '归母净利润', '经营活动现金流量净额'];
let companies: any[], documents: any[];
test.describe.configure({ mode: 'serial' });
async function catalog(page: Page) {
  companies = await (await page.request.get('/api/companies')).json();
  const rows = await (await page.request.get('/api/research/sources')).json();
  documents = rows.documents;
}
function company(code: string) { return companies.find(c => c.security_code === code || c.security_code === (code === '000333' ? 'MIDEA' : 'GREE')).company_id; }
function docId(code: string, year: number) { return documents.find(d => d.company_id === company(code) && d.report_year === year).document_id; }
async function harness(page: Page) {
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
}
async function screenshots(page: Page, name: string) {
  const audits: any[] = [];
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const audit = await page.evaluate(() => {
      const rgb = (s: string) => { const n = s.match(/[\d.]+/g)?.map(Number) || []; return [n[0] || 0, n[1] || 0, n[2] || 0, n.length > 3 ? n[3] : 1]; };
      const blend = (a: number[], b: number[]) => [0, 1, 2].map(i => a[i] * a[3] + b[i] * (1 - a[3]));
      const lum = (c: number[]) => c.slice(0, 3).map(x => x / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4).reduce((a, x, i) => a + x * [.2126, .7152, .0722][i], 0);
      const root = window.document.querySelector('main')!;
      const walker = window.document.createTreeWalker(root, NodeFilter.SHOW_TEXT), rows: any[] = [];
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.textContent?.trim(), el = node.parentElement;
        if (!text || !el || el.closest('script, style, option, button:disabled, input:disabled, select:disabled')) continue;
        const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
        if (!rect.width || !rect.height || rect.bottom <= 0 || rect.top >= innerHeight || rect.right <= 0 || rect.left >= innerWidth || style.visibility !== 'visible') continue;
        let opacity = 1, bg = [255, 255, 255], chain: HTMLElement[] = [];
        for (let p: HTMLElement | null = el; p; p = p.parentElement) chain.unshift(p);
        for (const p of chain) { const s = getComputedStyle(p); opacity *= Number(s.opacity); bg = blend(rgb(s.backgroundColor), bg); }
        const fg = rgb(style.color); fg[3] *= opacity;
        const a = lum(blend(fg, bg)), b = lum(bg), contrast = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        rows.push({ text: text.slice(0, 90), color: style.color, background: bg, font: style.fontSize, line_height: style.lineHeight, contrast });
      }
      return { nodes: rows.length, minimum: rows.length ? Math.min(...rows.map(r => r.contrast)) : null, failures: rows.filter(r => r.contrast < 4.5), rows };
    });
    audits.push({ name, width, ...audit });
    await page.screenshot({ path: `${out}/${name}-${width}.png` });
  }
  writeFileSync(`${out}/${name}-readability.json`, JSON.stringify(audits, null, 2));
  expect(audits.flatMap(a => a.failures)).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 900 });
}
async function configure(page: Page, comparison = false) {
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await page.getByRole('button', { name: comparison ? /两企业同期间比较/ : /单企业两期间变化/ }).click();
  if (comparison) await page.getByLabel('second 企业', { exact: true }).selectOption(company('000651'));
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  if (!comparison) await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await page.getByLabel('first 年报', { exact: true }).selectOption(docId('000333', 2025));
  // Deliberately choose the prior-year column of the SAME 2025 PDF.
  await page.getByLabel('second 年报', { exact: true }).selectOption(docId(comparison ? '000651' : '000333', 2025));
  for (const side of ['first', 'second']) for (const metric of metrics) {
    const select = page.getByLabel(`${side} ${metric} 披露`, { exact: true });
    await expect(select.locator('option')).toHaveCount(2);
    await select.selectOption({ index: 1 });
  }
  await expect(page.getByRole('button', { name: '建立研究并检查六项事实' })).toBeEnabled();
  await expect(page.getByRole('button', { name: '开始经营研究', exact: true })).toHaveCount(0);
}
async function start(page: Page) {
  const response = page.waitForResponse(r => r.url().endsWith('/api/research/tasks') && r.request().method() === 'POST', { timeout: 180000 });
  await page.getByRole('button', { name: '建立研究并检查六项事实' }).dblclick();
  const task = await (await response).json();
  expect(task.status).toBe('awaiting_human_confirmation');
  for (const side of ['first', 'second']) expect(task.input[side].choices.every((c: any) => c.fact_id === null && c.fact_set_id === null)).toBe(true);
  await expect(page.getByRole('region', { name: '六项事实准备状态' })).toBeVisible();
  return task;
}
async function review(page: Page, side: string, year: number) {
  await page.locator(`.fact-group[data-side="${side}"] .fact-group-actions`).getByRole('link').click();
  await expect(page.getByLabel('财务年度', { exact: true })).toHaveValue(String(year));
  await expect(page.getByTestId('review-candidate')).toHaveCount(3);
  await expect(page.getByTestId('review-candidate').first()).toContainText(`${year} 年`);
  await expect(page.locator('canvas').first()).toBeVisible();
  await page.getByRole('button', { name: '生成审阅快照', exact: true }).click();
  for (const name of names) await page.getByLabel(`已核对 ${year} ${name}`, { exact: true }).check();
  await page.getByRole('button', { name: '人工核对并确认', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '人工核对确认', exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}
test('正式首页、缺少资料、真实四 PDF 上传绑定与三种桌面布局', async ({ page }) => {
  await catalog(page);
  let posts = 0; page.on('request', r => { if (r.method() === 'POST') posts++; });
  await page.goto('/');
  await expect(page.getByRole('link', { name: '新建企业经营研究 →' })).toBeVisible();
  await screenshots(page, 'home');
  await page.getByRole('link', { name: '新建企业经营研究 →' }).click();
  await page.getByLabel('first 企业', { exact: true }).selectOption(company('000333'));
  expect(posts).toBe(0);
  if (!live) {
    await expect(page.getByText(/所选期间暂无可用财报/).first()).toBeVisible();
    await page.getByRole('button', { name: '准备或上传这家企业的财报' }).first().click();
    await page.getByRole('button', { name: '上传并绑定年报', exact: true }).click();
    await page.getByRole('button', { name: '取消上传', exact: true }).click();
    expect(posts).toBe(0);
  }
  const receipts: any[] = [];
  for (const source of sources) {
    const [code, year] = [source.id.startsWith('midea') ? '000333' : '000651', Number(source.id.slice(-4))];
    await page.goto(`/companies/${company(code)}/documents`);
    await page.getByRole('button', { name: '上传并绑定年报', exact: true }).click();
    await page.getByLabel('报告年度', { exact: true }).fill(String(year));
    await page.getByLabel('PDF 文件', { exact: true }).setInputFiles(source.absolute_path);
    if (live) { await page.getByText('来源网址（可选）', { exact: true }).click(); await page.getByLabel('来源网址', { exact: true }).fill(source.url); }
    await page.getByLabel('核对上传绑定', { exact: true }).check();
    const response = page.waitForResponse(r => r.url().endsWith('/api/report-documents') && r.request().method() === 'POST', { timeout: 180000 });
    await page.getByRole('button', { name: '提交 PDF 并绑定', exact: true }).dblclick();
    const upload = await (await response).json();
    await expect(page.getByRole('status').filter({ hasText: '上传与绑定已读回' })).toBeVisible({ timeout: 120000 });
    const meta = await (await page.request.get(`/api/documents/${upload.document_id}/metadata`)).json();
    const src = await (await page.request.get(`/api/documents/${upload.document_id}/source?company_id=${company(code)}`)).json();
    expect(meta.company_id).toBe(company(code)); expect(meta.report_year).toBe(year); expect(meta.period_start).toBe(`${year}-01-01`); expect(src.content_sha256).toBe(source.sha256);
    receipts.push({ original: source.id, sha: src.content_sha256, upload, meta, source: src });
  }
  expect(posts).toBe(4);
  await screenshots(page, 'upload-ready');
  writeFileSync(`${out}/upload-proof.json`, JSON.stringify({ receipts, posts, actual_api: true, facts_confirmed: false }, null, 2));
});
test('任务缺项、逐项核对取消零写入、接受未入库、入库只读返回和显式恢复', async ({ page }) => {
  await catalog(page); await harness(page);
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
  const writes: string[] = []; page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()); });
  await configure(page); await screenshots(page, 'configure');
  const task = await start(page);
  await expect(page.getByRole('button', { name: '复核并继续研究', exact: true })).toBeDisabled();
  const beforeContinue = writes.length;
  await page.goto('/');
  await page.getByRole('region', { name: '继续尚未完成的研究' }).locator(`a[href*="task=${task.task_id}"]`).click();
  await expect(page.getByRole('region', { name: '六项事实准备状态' })).toBeVisible();
  expect(page.url()).toContain(task.task_id);
  expect(writes.length).toBe(beforeContinue);
  await screenshots(page, 'waiting');
  let dialog = await review(page, 'second', 2024);
  const beforeCancel = writes.length;
  await dialog.getByRole('button', { name: '取消审阅', exact: true }).click();
  expect(writes.length).toBe(beforeCancel);
  await page.getByRole('button', { name: '人工核对并确认', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '人工核对确认', exact: true });
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  await expect(page.getByTestId('acceptance-result')).toContainText('财务事实入库待完成');
  const beforeReturn = writes.length;
  await page.getByRole('link', { name: '返回原研究任务（只读） →' }).click();
  await expect(page.getByTestId('slot-second:revenue')).toContainText('接受凭证已经保存但尚未入库');
  expect(writes.length).toBe(beforeReturn);
  await page.locator('.fact-group[data-side="second"] .fact-group-actions').getByRole('link').click();
  await page.getByRole('button', { name: '生成审阅快照', exact: true }).click();
  await expect(page.getByRole('button', { name: '查证接受结果（只读）', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '查证接受结果（只读）', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存已接受财务事实', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '保存已接受财务事实', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('保存成功并已重新查询');
  await screenshots(page, 'review-2024');
  let before = writes.length;
  await page.getByRole('link', { name: '返回原研究任务（只读） →' }).click();
  await expect(page.getByTestId('slot-second:revenue')).toContainText('已经具备有效核准事实');
  expect(writes.length).toBe(before);
  dialog = await review(page, 'first', 2025);
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  await page.getByRole('button', { name: '保存已接受财务事实', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('保存成功并已重新查询');
  before = writes.length;
  await page.getByRole('link', { name: '返回原研究任务（只读） →' }).click();
  const resume = page.getByRole('button', { name: '复核并继续研究', exact: true });
  await expect(resume).toBeEnabled(); expect(writes.length).toBe(before);
  await screenshots(page, 'six-ready');
  const response = page.waitForResponse(r => r.url().endsWith(`/api/research/tasks/${task.task_id}/resume`) && r.request().method() === 'POST', { timeout: 180000 });
  await resume.dblclick();
  const result = await (await response).json();
  expect(result.status).toBe('completed');
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  await screenshots(page, 'result');
  expect(writes.filter(x => x.endsWith(`/tasks/${task.task_id}/resume`))).toHaveLength(1);
  before = writes.length; await page.reload();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible(); expect(writes.length).toBe(before);
  await page.getByRole('link', { name: '企业概览', exact: true }).click();
  await page.getByRole('link', { name: 'AI 研究', exact: true }).click();
  await page.getByRole('tab', { name: '经营研究', exact: true }).click();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible(); expect(writes.length).toBe(before);
  await page.getByRole('link', { name: '进入报告草稿与保存版本 →' }).click();
  await expect(page.getByLabel('选择已完成的有效 D21 研究')).toHaveValue(task.task_id);
  expect(writes.length).toBe(before);
  if (process.env.FINDOC_UX_INTEGRATION === '1') await verifyReportJourney(page, result, out);
  writeFileSync(`${out}/journey-proof.json`, JSON.stringify({ task, result, writes, cancel_zero_writes: true, return_zero_writes: true, reload_zero_writes: true, errors, live }, null, 2));
  expect(errors).toHaveLength(0);
});
test('原文问答以多文档问答为主，旧工作台通过明确兼容入口访问', async ({ page }) => {
  await page.goto('/research?mode=qa');
  await expect(page.getByRole('region', { name: '研究资料选择' })).toBeVisible();
  await expect(page.locator('.legacy-workbench')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '开始研究', exact: true })).toHaveCount(1);
  await page.getByText('兼容工具：原有单文档工作台', { exact: true }).click();
  await page.getByRole('link', { name: '打开原有单文档 RAG / Agent / 上传工作台' }).click();
  expect(new URL(page.url()).pathname).toBe('/legacy');
  await expect(page.getByRole('button', { name: 'Agent 有限任务', exact: true })).toBeVisible();
});
test('双企业研究、resume 响应丢失、按操作只读恢复和历史刷新', async ({ page }) => {
  await catalog(page); await harness(page); await configure(page, true);
  const task = await start(page);
  const dialog = await review(page, 'second', 2025);
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  await page.getByRole('button', { name: '保存已接受财务事实', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('保存成功并已重新查询');
  await page.getByRole('link', { name: '返回原研究任务（只读） →' }).click();
  let posts = 0; page.on('request', r => { if (r.method() === 'POST') posts++; });
  await page.route(`**/api/research/tasks/${task.task_id}/resume`, async route => { const r = await route.fetch({ timeout: 120000 }); expect(r.status()).toBe(200); await route.abort('failed'); });
  await page.getByRole('button', { name: '复核并继续研究', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '网络响应未知' })).toBeVisible({ timeout: 120000 });
  expect(posts).toBe(1);
  await page.reload();
  await page.getByRole('button', { name: '查证刚才的结果（只读）', exact: true }).click();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  expect(posts).toBe(1);
  await screenshots(page, 'comparison-recovered');
  writeFileSync(`${out}/unknown-proof.json`, JSON.stringify({ task_id: task.task_id, resume_posts: posts, no_automatic_retry: true }));
});
test('上下文篡改、企业切换和迟到 GET 不展示另一任务 PDF', async ({ page }) => {
  await catalog(page); await harness(page);
  const proof = JSON.parse(readFileSync(`${out}/journey-proof.json`, 'utf8'));
  await page.goto(`/research?company=${company('000333')}&mode=operating&task=${proof.task.task_id}`);
  const link = page.locator('.fact-group[data-side="second"] .fact-group-actions').getByRole('link');
  await expect(link).toBeVisible(); const href = await link.getAttribute('href');
  let files = 0; page.on('request', r => { if (r.url().includes('/file?')) files++; });
  await page.goto(href!.replace('period=2024', 'period=2025'));
  await expect(page.getByRole('alert')).toContainText('不一致'); expect(files).toBe(0); expect(await page.locator('canvas').count()).toBe(0);
  await page.goto(`/research?company=${company('000333')}&mode=operating&task=${proof.task.task_id}`);
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  let release!: () => void; const gate = new Promise<void>(r => release = r);
  await page.route(`**/api/research/tasks/${proof.task.task_id}`, async route => { const r = await route.fetch(); await gate; await route.fulfill({ response: r }).catch(() => {}); });
  await page.getByRole('button', { name: '刷新状态（只读）', exact: true }).click();
  await page.getByLabel('当前企业', { exact: true }).selectOption(company('000651'));
  release();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toHaveCount(0);
  await page.unrouteAll({ behavior: 'wait' });
  await page.goto('/'); await expect(page.getByRole('region', { name: '最近完成的研究' })).toContainText('美的');
});
test('接受与事实入库丢包后刷新只读恢复，1024 PDF 抽屉可退出核对', async ({ page }) => {
  await catalog(page); await harness(page);
  await page.goto(`/evidence?company=${company('000651')}&document=${docId('000651', 2024)}`);
  await expect(page.getByTestId('review-candidate')).toHaveCount(3);
  await page.getByRole('button', { name: '生成审阅快照', exact: true }).click();
  for (const name of names) await page.getByLabel(`已核对 2024 ${name}`, { exact: true }).check();
  await page.getByRole('button', { name: '人工核对并确认', exact: true }).click();
  let acceptancePosts = 0, persistencePosts = 0;
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/financial-facts/confirmations')) acceptancePosts++; if (r.method() === 'POST' && r.url().endsWith('/financial-facts/persisted')) persistencePosts++; });
  await page.route('**/api/financial-facts/confirmations', async route => { const r = await route.fetch({ timeout: 120000 }); expect(r.status()).toBe(200); await route.abort('failed'); });
  await page.getByRole('dialog').getByRole('checkbox').check();
  await page.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '接受结果未知' }).first()).toBeVisible();
  await page.reload(); await page.getByRole('button', { name: '生成审阅快照', exact: true }).click();
  await page.getByRole('button', { name: '查证接受结果（只读）', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存已接受财务事实', exact: true })).toBeEnabled(); expect(acceptancePosts).toBe(1);
  await page.route('**/api/financial-facts/persisted', async route => { const r = await route.fetch({ timeout: 120000 }); expect(r.status()).toBe(200); await route.abort('failed'); });
  await page.getByRole('button', { name: '保存已接受财务事实', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('事实操作结果未知');
  await page.reload(); await page.getByRole('button', { name: '按已知 ID 只读恢复财务事实', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('保存成功并已重新查询'); expect(persistencePosts).toBe(1);
  await page.setViewportSize({ width: 1024, height: 900 }); await page.reload();
  await expect(page.getByRole('button', { name: '展开证据', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '展开证据', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'PDF 原文证据', exact: true })).toBeVisible();
  await page.screenshot({ path: `${out}/pdf-drawer-1024.png` });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'PDF 原文证据', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '生成审阅快照', exact: true })).toBeEnabled();
  writeFileSync(`${out}/acceptance-unknown-proof.json`, JSON.stringify({ acceptance_posts: acceptancePosts, persistence_posts: persistencePosts, recovered_by_get: true, drawer_escape: true }));
});
test('服务端真实失败、拒答与预算耗尽显示不同下一动作', async ({ page }) => {
  test.skip(live, 'provider fault injection exists only in controlled server assembly');
  await catalog(page); await harness(page);
  const cases: any[] = [];
  for (const kind of ['failed', 'refused', 'budget']) {
    expect((await page.request.post(`/api/__test__/ux-state/${kind}`)).ok()).toBe(true);
    await configure(page);
    for (const side of ['first', 'second']) for (const metric of metrics) await page.getByLabel(`${side} ${metric} 事实`, { exact: true }).selectOption({ index: 1 });
    const waiting = await start(page);
    const response = page.waitForResponse(r => r.url().endsWith(`/api/research/tasks/${waiting.task_id}/resume`) && r.request().method() === 'POST', { timeout: 180000 });
    await page.getByRole('button', { name: '复核并继续研究', exact: true }).click();
    const task = await (await response).json();
    expect(task.status).toBe(kind === 'refused' ? 'refused' : 'failed');
    const stage = page.getByRole('region', { name: '研究阶段与下一步' });
    await expect(stage).toContainText(kind === 'budget' ? '预算已耗尽' : kind === 'refused' ? '证据不足' : '研究未完成');
    await expect(page.getByRole('region', { name: '有限经营研究结果' })).toHaveCount(0);
    let posts = 0; page.on('request', r => { if (r.method() === 'POST') posts++; });
    await page.reload(); await expect(stage).toContainText(kind === 'budget' ? '预算已耗尽' : kind === 'refused' ? '证据不足' : '研究未完成'); expect(posts).toBe(0);
    await page.screenshot({ path: `${out}/task-${kind}-1440.png` }); cases.push({ kind, task });
    page.removeAllListeners('request');
  }
  await page.request.post('/api/__test__/ux-state/normal');
  writeFileSync(`${out}/terminal-proof.json`, JSON.stringify(cases, null, 2));
});
test('正式入口保留生产门禁，来源重建撤下旧研究金额与 PDF', async ({ page }) => {
  await catalog(page);
  const proof = JSON.parse(readFileSync(`${out}/journey-proof.json`, 'utf8'));
  const path = `/research?company=${company('000333')}&mode=operating&task=${proof.task.task_id}`;
  // Formal main.tsx, no harness: simulated facts can never become production facts.
  await page.goto(path);
  await expect(page.getByRole('region', { name: '六项事实准备状态' })).toContainText('资格失效');
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toHaveCount(0);
  await harness(page); await page.reload();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  const id = docId('000333', 2025), source = await (await page.request.get(`/api/documents/${id}/source?company_id=${company('000333')}`)).json();
  expect((await page.request.post(`/api/documents/${id}/reindex`, { data: { expected_attempt: source.attempt } })).status()).toBe(202);
  let posts = 0; page.on('request', r => { if (r.method() === 'POST') posts++; });
  await page.reload();
  await expect(page.getByRole('region', { name: '六项事实准备状态' })).toContainText('资格失效');
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toHaveCount(0);
  await expect(page.locator('.operating-result-values')).toHaveCount(0); expect(posts).toBe(0);
  await page.screenshot({ path: `${out}/source-invalidated-1440.png` });
});
