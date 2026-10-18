import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { generateReview, returnToReview, openCandidate } from './financial-review-helpers.ts';
const out = process.env.D29_ARTIFACT_DIR!;
const before = process.env.D29_BEFORE === '1';
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

test('D29 baseline natural template then company must keep dual', async ({ page }) => {
  const writes = watch(page);
  await page.goto('/research?mode=operating&new=1');
  await page.getByRole('button', { name: /两企业同期间比较/ }).click();
  await page.getByLabel('first 企业', { exact: true }).selectOption(company('000333'));
  await expect(page.getByLabel('first 企业', { exact: true })).toHaveValue(company('000333'));
  await shot(page, 'template-company');
  expect(writes).toEqual([]);
  await expect(page.getByRole('button', { name: /两企业同期间比较/ })).toHaveAttribute('aria-pressed', 'true');
});

for (const entry of ['empty', 'company', 'old-single', 'old-dual']) for (const order of ['template-first', 'company-first']) {
  test(`D29 draft matrix ${entry} ${order}`, async ({ page }) => {
    const writes = watch(page);
    await page.goto('/');
    if (entry.startsWith('old-')) await page.evaluate(({ id, template }) => {
      const c = (company: string) => ({ company, year: '2023', document: '', versions: {}, facts: {} });
      sessionStorage.setItem(`findoc:research-draft:${id}`, JSON.stringify({ template, config: { first: c(id), second: c(id) } }));
    }, { id: company('000333'), template: entry === 'old-single' ? 'company_period_change' : 'company_same_period_comparison' });
    await page.goto(`/research?mode=operating&new=1&company=${entry === 'empty' ? '' : company('000333')}`);
    if (order === 'company-first') await page.getByLabel('first 企业', { exact: true }).selectOption(company('000333'));
    await page.getByRole('button', { name: /两企业同期间比较/ }).click();
    if (order === 'template-first') await page.getByLabel('first 企业', { exact: true }).selectOption(company('000333'));
    await expect(page.getByRole('button', { name: /两企业同期间比较/ })).toHaveAttribute('aria-pressed', 'true');
    await page.getByLabel('second 企业', { exact: true }).selectOption(company('000651'));
    await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
    const url = page.url();
    await page.reload();
    await expect(page.getByLabel('second 企业', { exact: true })).toHaveValue(company('000651'));
    await expect(page.getByLabel('first 期间', { exact: true })).toHaveValue('2025');
    expect(page.url()).toBe(url);
    expect(writes).toEqual([]);
  });
}

test('D29 stage 2/3 A B year source edits revoke only affected selections; refresh and history keep draft', async ({ page }) => {
  const writes = watch(page);
  await dual(page); await sourceStage(page);
  const original = page.url();
  await page.reload();
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '修改研究范围', exact: true }).click();
  await page.getByLabel('first 企业', { exact: true }).selectOption('');
  await expect(page.getByLabel('second 企业', { exact: true })).toHaveValue(company('000651'));
  await expect(page.getByLabel('first 期间', { exact: true })).toHaveValue('2025');
  await expect(page.locator('.scope-change')).toContainText('来源选择需重新确认');
  await page.getByLabel('first 企业', { exact: true }).selectOption(company('000333'));
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await expect(page.getByLabel('first 年报', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('second 年报', { exact: true })).toHaveValue(report('gree-2025').document_id);
  await page.getByLabel('first 年报', { exact: true }).selectOption(report('midea-2025').document_id);
  await page.getByRole('button', { name: '修改研究范围', exact: true }).click();
  await page.getByLabel('second 企业', { exact: true }).selectOption('');
  await page.getByLabel('second 企业', { exact: true }).selectOption(company('000651'));
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await expect(page.getByLabel('first 年报', { exact: true })).toHaveValue(report('midea-2025').document_id);
  await expect(page.getByLabel('second 年报', { exact: true })).toHaveValue('');
  await page.getByLabel('second 年报', { exact: true }).selectOption(report('gree-2025').document_id);
  await page.getByRole('button', { name: '修改研究范围', exact: true }).click();
  await page.getByLabel('first 期间', { exact: true }).selectOption('2024');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  for (const side of ['first', 'second']) await expect(page.getByLabel(`${side} 年报`, { exact: true })).toHaveValue('');
  await page.getByLabel('first 年报', { exact: true }).selectOption(report('midea-2024').document_id);
  await page.getByLabel('second 年报', { exact: true }).selectOption(report('gree-2024').document_id);
  await page.getByRole('button', { name: '下一步：确认来源', exact: true }).click();
  for (let i = 0; i < 2; i++) await page.locator('.operating-side').nth(i).getByRole('button', { name: '采用这组三项来源', exact: true }).click();
  await page.getByRole('button', { name: '修改财报', exact: true }).click();
  await page.getByLabel('first 年报', { exact: true }).selectOption(report('midea-2025').document_id);
  await page.getByRole('button', { name: '下一步：确认来源', exact: true }).click();
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeDisabled();
  await expect(page.locator('.operating-side').nth(1).getByRole('button', { name: '采用这组三项来源', exact: true })).toHaveCount(0);
  await page.goto('/'); await page.goBack();
  expect(page.url()).toBe(original);
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
});

test('D29 single company switch preserves both years; final task payload equals visible scope', async ({ page }) => {
  const writes = watch(page);
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await sourceStage(page, 'midea-2025', 'midea-2024');
  await page.getByRole('button', { name: '修改研究范围', exact: true }).click();
  await page.getByLabel('first 企业', { exact: true }).selectOption(company('000651'));
  await expect(page.getByLabel('first 期间', { exact: true })).toHaveValue('2025');
  await expect(page.getByLabel('second 期间', { exact: true })).toHaveValue('2024');
  await sourceStage(page, 'gree-2025', 'gree-2024');
  expect(writes).toEqual([]);
  const response = page.waitForResponse(r => r.url().endsWith('/research/tasks') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '创建研究，开始核对数据', exact: true }).dblclick();
  const t = await (await response).json();
  expect(t.input.template).toBe('company_period_change');
  for (const [side, year] of [['first', 2025], ['second', 2024]] as const) {
    expect(t.input[side].company_id).toBe(company('000651')); expect(t.input[side].period.year).toBe(year);
    expect(t.input[side].choices.map((c: any) => c.document_id)).toEqual(metrics.map(() => report(`gree-${year}`).document_id));
  }
  expect(writes).toEqual(['/api/research/tasks']);
  writeFileSync(`${out}/single-task-payload.json`, JSON.stringify(t, null, 2));
});

test('D29 dual final payload equals A B shared year and documents', async ({ page }) => {
  const writes = watch(page); await dual(page); await sourceStage(page);
  expect(writes).toEqual([]);
  const response = page.waitForResponse(r => r.url().endsWith('/research/tasks') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '创建研究，开始核对数据', exact: true }).click();
  const t = await (await response).json(); expect(t.input.template).toBe('company_same_period_comparison');
  for (const [side, code, id] of [['first', '000333', 'midea-2025'], ['second', '000651', 'gree-2025']]) {
    expect(t.input[side].company_id).toBe(company(code)); expect(t.input[side].period.year).toBe(2025);
    expect(t.input[side].choices.map((c: any) => c.document_id)).toEqual(metrics.map(() => report(id).document_id));
  }
  expect(writes).toEqual(['/api/research/tasks']); writeFileSync(`${out}/dual-task-payload.json`, JSON.stringify(t, null, 2));
});

test('D29 baseline saved record without sessionStorage restores facts and receipt read-only', async ({ page, browser }) => {
  const writes = watch(page), s = report('midea-2024'), id = manifest.saved.receipt_id;
  await page.goto(evidence(s, 'read', id));
  if (before) { await expect(page.getByRole('button', { name: '开始本组核对', exact: true })).toBeVisible(); await shot(page, 'saved-record'); }
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实', { timeout: 10000 });
  await returnToReview(page);
  await expect(page.getByRole('button', { name: '确认本组数据', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '保存已接受数据', exact: true })).toHaveCount(0);
  await expect(page.locator('.candidate-item > summary')).toHaveCount(3);
  await expect(page.locator('.candidate-panel')).toContainText(id);
  await shot(page, 'saved-record');
  await page.reload(); await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  for (const candidate of manifest.saved.facts) {
    const card = await openCandidate(page, candidate); await expect(card).toContainText(candidate.raw_value);
  }
  const fresh = await browser.newContext(); const tab = await fresh.newPage(); const newWrites = watch(tab);
  await tab.route('**/src/main.tsx*', r => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  await tab.goto(page.url()); await expect(tab.getByTestId('fact-result')).toContainText('已确认财务事实');
  expect(await tab.evaluate(() => sessionStorage.length)).toBe(0);
  await fresh.close(); expect(writes).toEqual([]); expect(newWrites).toEqual([]);
  const result = await (await page.request.get(`/api/financial-facts/persisted/${id}`)).json();
  expect(result.facts.map((f: any) => f.fact_id)).toEqual(manifest.saved.facts.map((f: any) => f.fact_id));
});

test('D29 task history link carries saved fact_set/receipt; library separates PDF and facts', async ({ page }) => {
  const t = await singleTask(page); const writes = watch(page);
  const group = page.locator('.fact-group[data-side="second"]');
  await page.getByRole('button', { name: '查看全部六项', exact: true }).click();
  await group.getByText('已入库事实与证据', { exact: true }).first().click();
  const link = group.getByRole('link', { name: '查看已保存核对记录（只读） →', exact: true }).first();
  await expect(link).toHaveAttribute('href', new RegExp(`receipt=${manifest.saved.receipt_id}`));
  await link.click(); await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  await page.goto(`/companies/${company('000333')}/documents`);
  const row = page.locator('article').filter({ has: page.getByRole('heading', { name: 'midea-2024.pdf', exact: true }) });
  await expect(row).toContainText('PDF 处理就绪'); await expect(row).toContainText('已保存财务事实 3 项');
  await page.goBack(); await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  expect(writes).toEqual([]); expect(t.waiting_checkpoint).toBe(true);
});

test('D29 unsubmitted checks reset on refresh; cancel/navigate never accept save resume', async ({ page }) => {
  const { dialog } = await reviewDialog(page, 'gree-2024'); const writes = watch(page);
  await dialog.getByRole('button', { name: '取消审阅', exact: true }).click();
  await page.reload();
  await returnToReview(page);
  await expect(page.getByRole('checkbox', { name: /已核对 2024/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '保存已接受数据', exact: true })).toHaveCount(0);
  await page.goto('/'); await page.goBack(); expect(writes).toEqual([]);
});

test('D29 accepted unsaved after local identity loss discovers all exact records and requires selection', async ({ page }) => {
  const a = await accept(page, 'gree-2024');
  const b = await accept(page, 'gree-2024');
  const writes = watch(page);
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(evidence(report('gree-2024')));
  await expect(page.getByRole('button', { name: '查看这条核对记录（只读）', exact: true })).toHaveCount(2);
  await expect(page.getByRole('button', { name: '确认本组数据', exact: true })).toHaveCount(0);
  await page.locator('article').filter({ hasText: a.receipt_id }).getByRole('button').click();
  await expect(page.getByTestId('acceptance-result')).toContainText('自动化模拟接受凭证');
  await expect(page.locator('.candidate-panel')).toContainText('本凭证尚无已保存事实');
  await expect(page.getByRole('button', { name: '保存已接受数据', exact: true })).toHaveCount(0);
  await page.reload(); await expect(page.locator('.candidate-panel')).toContainText(a.receipt_id);
  expect(writes).toEqual([]);
  writeFileSync(`${out}/accepted-unsaved-identities.json`, JSON.stringify({ a: a.receipt_id, b: b.receipt_id, reads_only: true }));
});

test('D29 accept unknown uses request snapshot scope GET; save unknown uses receipt GET without local storage', async ({ page }) => {
  const { dialog } = await reviewDialog(page); const writes = watch(page); let receipt: any, saved: any;
  await page.route('**/api/financial-facts/confirmations', async r => { const response = await r.fetch(); receipt = await response.json(); await r.abort('failed'); });
  await dialog.getByLabel('我已逐项核对原 PDF，并明确接受本次审阅内容').check();
  await dialog.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  await expect(page.getByRole('button', { name: '查证接受结果（只读）', exact: true })).toBeVisible();
  await shot(page, 'accept-unknown');
  let recoveryUrl = '';
  page.on('request', r => { if (r.method() === 'GET' && r.url().includes('/financial-facts/confirmations/')) recoveryUrl = r.url(); });
  await page.reload(); await expect(page.getByTestId('acceptance-result')).toContainText('自动化模拟接受凭证');
  expect(recoveryUrl).toContain(receipt.request_id); expect(recoveryUrl).toContain(encodeURIComponent(receipt.snapshot_id));
  await returnToReview(page);
  await page.route('**/api/financial-facts/persisted', async r => { const response = await r.fetch(); saved = await response.json(); await r.abort('failed'); });
  await page.getByRole('button', { name: '保存已接受数据', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('事实操作结果未知');
  await shot(page, 'save-unknown');
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(evidence(report('midea-2025'), 'read', receipt.receipt_id));
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  await shot(page, 'unknown-recovered');
  const restored = await (await page.request.get(`/api/financial-facts/persisted/${receipt.receipt_id}`)).json();
  expect(restored.facts.map((f: any) => f.fact_id)).toEqual(saved.facts.map((f: any) => f.fact_id));
  expect(restored.production_calculable).toBe(false);
  expect(writes).toEqual(['/api/financial-facts/confirmations', '/api/financial-facts/persisted']);
  writeFileSync(`${out}/unknown-proof.json`, JSON.stringify({ request: receipt.request_id, snapshot: receipt.snapshot_id, receipt: receipt.receipt_id, fact_ids: restored.facts.map((f: any) => f.fact_id), writes, recoveryUrl }, null, 2));
});


test('D29 top company filter opens separate workspace and back restores owned draft', async ({ page }) => {
  const writes = watch(page); await dual(page); const draft = page.url();
  await page.getByLabel('当前企业', { exact: true }).selectOption(company('000651'));
  await expect(page.getByLabel('first 企业', { exact: true })).toHaveValue(company('000651'));
  expect(page.url()).not.toBe(draft);
  await page.goBack(); expect(page.url()).toBe(draft);
  await expect(page.getByRole('button', { name: /两企业同期间比较/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('first 企业', { exact: true })).toHaveValue(company('000333'));
  await expect(page.getByLabel('second 企业', { exact: true })).toHaveValue(company('000651'));
  expect(writes).toEqual([]);
});

test('D29 accepted response unknown and all local IDs lost recovers only an explicitly chosen server record', async ({ page }) => {
  const { dialog } = await reviewDialog(page, 'gree-2025'); let receipt: any;
  const writes = watch(page);
  await page.route('**/api/financial-facts/confirmations', async route => { const response = await route.fetch(); receipt = await response.json(); await route.abort('failed'); });
  await dialog.getByLabel('我已逐项核对原 PDF，并明确接受本次审阅内容').check();
  await dialog.getByRole('button', { name: '我已核对并接受', exact: true }).click();
  await expect(page.getByRole('button', { name: '查证接受结果（只读）', exact: true })).toBeVisible();
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(evidence(report('gree-2025')));
  await page.locator('article').filter({ hasText: receipt.receipt_id }).getByRole('button').click();
  await expect(page.getByTestId('acceptance-result')).toContainText('自动化模拟接受凭证');
  await expect(page.locator('.candidate-panel')).toContainText('本凭证尚无已保存事实');
  expect(writes).toEqual(['/api/financial-facts/confirmations']);
});

test('D29 saved read failure never becomes unconfirmed; forged receipt scope is rejected', async ({ page }) => {
  const writes = watch(page), saved = manifest.saved;
  await page.route(`**/api/financial-facts/persisted/${saved.receipt_id}`, route => route.fulfill({ status: 503, json: { detail: { code: 'test_read_unavailable' } } }));
  await page.goto(evidence(report('midea-2024'), 'read', saved.receipt_id));
  await expect(page.getByTestId('fact-result')).toContainText('事实操作结果未知');
  await expect(page.getByRole('button', { name: '保存已接受数据', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认本组数据', exact: true })).toHaveCount(0);
  await page.unroute(`**/api/financial-facts/persisted/${saved.receipt_id}`);
  await page.getByRole('button', { name: '查证数据保存结果（只读）', exact: true }).click();
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  await page.goto(evidence(report('gree-2024'), 'read', saved.receipt_id));
  await expect(page.locator('.candidate-panel')).toContainText('记录暂不可核验');
  await expect(page.getByTestId('fact-result')).toHaveCount(0);
  await expect(page.locator('canvas')).toHaveCount(0);
  expect(writes).toEqual([]);
});

test('D29 accepted record saves separately; six saved facts still wait for explicit resume', async ({ page }) => {
  const receipt = await accept(page, 'midea-2025'); const writes = watch(page);
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(evidence(report('midea-2025'), 'read', receipt.receipt_id).replace(`&fact_set=${receipt.receipt_id}`, ''));
  await expect(page.locator('.candidate-panel')).toContainText('本凭证尚无已保存事实');
  await page.getByRole('button', { name: '继续独立保存这条接受记录', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存已接受数据', exact: true })).toBeVisible();
  expect(writes).toEqual([]);
  const response = page.waitForResponse(r => r.url().endsWith('/financial-facts/persisted') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '保存已接受数据', exact: true }).click();
  const saved = await (await response).json(); expect(saved.production_calculable).toBe(false);
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  // Both current Midea 2025 receipts are now valid. Task creation still submits
  // no facts and no resume; explicitly select one exact fact per ambiguous slot.
  const t = await singleTask(page);
  await page.getByRole('button', { name: '查看全部六项', exact: true }).click();
  await expect(page.locator('.fact-group[data-side="first"] li').first()).toContainText(/多个有效事实|已入库/, { timeout: 20000 });
  for (const metric of metrics) {
    const picker = page.getByLabel(`first:${metric} 恢复事实`, { exact: true });
    if (await picker.count()) await picker.selectOption(saved.facts.find((f: any) => f.metric_key === metric).fact_id);
  }
  const resume = page.getByRole('button', { name: '复核并继续研究', exact: true });
  await expect(resume).toBeEnabled();
  expect(writes).toEqual(['/api/financial-facts/persisted', '/api/research/tasks']);
  const result = page.waitForResponse(r => r.url().endsWith(`/research/tasks/${t.task_id}/resume`) && r.request().method() === 'POST');
  await resume.click(); const completed = await (await result).json();
  expect(completed.status).toBe('completed'); expect(completed.final_research_content.financial_facts.every((f: any) => f.production_calculable === false)).toBe(true);
  expect(writes.filter(w => w.endsWith('/resume'))).toHaveLength(1);
  writeFileSync(`${out}/separate-authorization-proof.json`, JSON.stringify({ receipt: receipt.receipt_id, fact_set: saved.fact_set_id, task: completed.task_id, status: completed.status, writes }, null, 2));
});

test('D29 saved history vs new review retains persistent card; actual source change revokes old facts PDF', async ({ page }) => {
  const s = report('midea-2024'), writes = watch(page);
  await page.goto(evidence(s, 'read', manifest.saved.receipt_id));
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实');
  await page.getByRole('button', { name: '开始新核对', exact: true }).click();
  await expect(page.getByRole('heading', { name: '新核对流程', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '财务核对记录', exact: true })).toContainText('本来源已有 3 项已保存财务事实');
  expect(writes).toEqual([]);
  const correction = await page.request.post(`/api/documents/${s.document_id}/binding-corrections`, { data: { expected_attempt: s.attempt,
    metadata: { company_id: s.company_id, report_year: 2024, report_type: 'annual', basis: 'unknown', period_start: '2024-01-01', period_end: '2024-12-31' }, reason: 'D29 isolated source-change regression' } });
  expect(correction.status()).toBe(200);
  const invalid = await page.request.get(`/api/financial-facts/persisted/${manifest.saved.receipt_id}`); expect(invalid.status()).toBe(409);
  await page.reload(); await expect(page.getByRole('heading', { name: '原文来源不可用', exact: true })).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0); await expect(page.getByTestId('fact-result')).toHaveCount(0);
  expect(writes).toEqual([]);
});
