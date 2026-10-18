import { test, expect } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { before, out, widths, setupPolish, pendingTask, withinPage } from './polish-helpers.ts';
test('S2 annual group entry, zero-write cancel and seven widths including short 390', async ({ page }) => {
  const task = await pendingTask(page, await setupPolish(page));
  // Presentation fixture only: withdraw already saved seed facts so this NEW task shows its preparation path.
  await page.route('**/api/financial-facts?**', async route => {
    const response = await route.fetch(), data = await response.json();
    await route.fulfill({ response, json: { ...data, facts: [] } });
  });
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.goto(`/research?task=${task.task_id}&mode=operating&section=sources`);
  const checklist = page.getByRole('region', { name: '六项事实准备状态', exact: true });
  await expect(checklist).toBeVisible();
  await expect(checklist.getByTestId('slot-first:revenue')).toContainText('待核对');
  if (!before) {
    await expect(checklist.locator('.fact-group[data-current="true"]')).toHaveCount(1);
    await expect(checklist.locator('.fact-checklist a')).toHaveCount(0);
    await expect(checklist.locator('.fact-group-actions a')).toHaveCount(2);
    await expect(checklist).toContainText('当前核对组');
  }
  for (const width of widths) {
    await page.setViewportSize({ width, height: width === 390 ? 450 : 900 });
    await checklist.scrollIntoViewIfNeeded(); await withinPage(page);
    await page.screenshot({ path: `${out}/s2-groups-${width}.png` });
  }
  expect(writes).toEqual([]);
  const entry = before ? checklist.getByTestId('slot-first:revenue').getByRole('link') : checklist.locator('.fact-group[data-side="first"] .fact-group-actions a');
  await entry.click();
  await expect(page.getByRole('heading', { name: '核对 2025 年财务 · 共 3 项', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '开始本组核对', exact: true }).click();
  for (const width of widths) {
    await page.setViewportSize({ width, height: width === 390 ? 450 : 900 });
    const pdf = page.getByRole('dialog', { name: 'PDF 原文证据', exact: true });
    if (await pdf.isVisible()) await page.keyboard.press('Escape');
    await withinPage(page);
    const action = page.getByRole('button', { name: '确认本组数据', exact: true });
    await action.scrollIntoViewIfNeeded();
    const box = await action.boundingBox(); expect(box!.x).toBeGreaterThanOrEqual(0); expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    const uncovered = await action.evaluate(el => { const r = el.getBoundingClientRect(); return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)); });
    expect(uncovered).toBe(true);
    await page.screenshot({ path: `${out}/s2-review-${width}.png` });
  }
  for (const name of ['营业收入', '归母净利润', '经营活动现金流量净额']) {
    const check = page.getByLabel(`已核对 2025 ${name}`, { exact: true });
    if (!(await check.isVisible())) await page.locator('.candidate-item > summary').filter({ hasText: name }).click();
    await check.check();
  }
  await page.getByRole('button', { name: '确认本组数据', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '人工核对确认', exact: true });
  await expect(dialog.getByRole('checkbox')).not.toBeChecked();
  await expect(dialog.getByRole('button', { name: before ? '明确接受并保存凭证' : '我已核对并接受', exact: true })).toBeDisabled();
  await expect(dialog.locator('li')).toHaveCount(3); await withinPage(page);
  await page.screenshot({ path: `${out}/s2-confirm-390x450.png` });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '确认本组数据', exact: true })).toBeFocused();
  expect(writes.filter(u => /confirmations|persisted|resume|reports/.test(u))).toEqual([]);
  writeFileSync(`${out}/s2-proof.json`, JSON.stringify({ before, widths, shortViewport: '390x450', writes, cancelled_business_writes: 0, simulated_test: true }, null, 2));
});
test('S2 processed inline upload returns to explicit source selection without accepting or creating', async ({ page }) => {
  const task = await setupPolish(page);
  const { readFileSync } = await import('node:fs');
  const sources = JSON.parse(readFileSync(process.env.UX_SOURCE_FILE!, 'utf8'));
  await page.goto(`/research?company=${task.input.first.company_id}&mode=operating&new=1`);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await page.getByRole('button', { name: '上传另一份财报', exact: true }).first().click();
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.getByLabel('报告年度', { exact: true }).fill('2025');
  await page.getByLabel('PDF 文件', { exact: true }).setInputFiles(sources.find((s: any) => s.id === 'midea-2025').absolute_path);
  await page.getByLabel('核对上传绑定', { exact: true }).check();
  await page.getByRole('button', { name: '提交 PDF 并绑定', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '上传与绑定已读回' })).toBeVisible({ timeout: 120000 });
  await page.getByRole('button', { name: '继续选择财报', exact: true }).click();
  await expect(page.getByLabel('first 年报', { exact: true })).toBeFocused();
  await expect(page.getByLabel('first 年报', { exact: true })).toHaveValue('');
  await expect(page.getByRole('button', { name: '下一步：确认来源', exact: true })).toBeDisabled();
  expect(writes).toEqual([expect.stringContaining('/report-documents')]);
  writeFileSync(`${out}/s2-inline-proof.json`, JSON.stringify({ explicitSelectionRequired: true, writes, accepted: 0, factsSaved: 0, taskCreated: 0, simulated_test: true }, null, 2));
});
test('S2 one saved slot does not narrow the displayed scope of the same-source review group', async ({ page }) => {
  const seed = await setupPolish(page), task = await pendingTask(page, seed);
  await page.route('**/api/financial-facts?**', async route => {
    const response = await route.fetch(), data = await response.json();
    await route.fulfill({ response, json: { ...data, facts: data.facts.filter((f: any) => f.period === 2025 && f.metric_key === 'revenue' && f.current_valid) } });
  });
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.goto(`/research?task=${task.task_id}&mode=operating&section=sources`);
  const group = page.locator('.fact-group[data-side="first"]');
  await expect(group.getByTestId('slot-first:revenue')).toContainText('已入库');
  await expect(group.locator('.fact-group-actions')).toContainText('3 项数据');
  await group.locator('.fact-group-actions a').click();
  await expect(page.getByRole('heading', { name: '核对 2025 年财务 · 共 3 项', exact: true })).toBeVisible();
  await expect(page.locator('.review-scope')).toContainText('3 项数据'); expect(writes).toEqual([]);
  writeFileSync(`${out}/s2-partial-group-proof.json`, JSON.stringify({ savedSlots: 1, taskGroupSize: 3, actualReviewSize: 3, writes, presentationFixtureOnly: true, simulated_test: true }, null, 2));
});
