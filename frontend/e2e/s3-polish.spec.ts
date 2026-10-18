import { test, expect } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { before, out, widths, setupPolish, pendingTask, withinPage } from './polish-helpers.ts';
import { formatDecimal } from '../src/product/api.ts';
test('S3 waiting, stop, original operation GET and exact result reading', async ({ page }) => {
  const task = await pendingTask(page, await setupPolish(page));
  await page.goto(`/research?task=${task.task_id}&mode=operating`);
  await expect(page.getByRole('button', { name: '复核并继续研究', exact: true })).toBeEnabled();
  let release!: () => void, arrived!: () => void;
  const gate = new Promise<void>(r => release = r), committed = new Promise<void>(r => arrived = r);
  let completed: any, operation = '';
  const endpoint = `**/api/research/tasks/${task.task_id}/resume`;
  await page.route(endpoint, async route => {
    operation = route.request().postDataJSON().operation_id;
    const response = await route.fetch(); completed = await response.json(); arrived();
    await gate; await route.fulfill({ response }).catch(() => {});
  });
  const writes: string[] = [], gets: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); else gets.push(r.url()); });
  await page.getByRole('button', { name: '复核并继续研究', exact: true }).click(); await committed;
  await expect(page.getByRole('button', { name: '停止本页等待', exact: true })).toBeVisible();
  if (!before) { await expect(page.locator('#research-recovery')).toHaveCount(0); await expect(page.getByRole('region', { name: '研究上下文' })).toContainText('正在执行经营研究'); await expect(page.getByRole('button', { name: '复核并继续研究', exact: true })).toHaveCount(0); }
  await page.screenshot({ path: `${out}/s3-waiting-1440.png` });
  await page.getByRole('button', { name: '停止本页等待', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '服务端任务可能仍在执行' })).toBeVisible();
  release(); await page.unroute(endpoint);
  await page.screenshot({ path: `${out}/s3-stopped-1440.png` });
  await page.getByRole('button', { name: before ? '查询最新执行结果（只读）' : '查证刚才的结果（只读）', exact: true }).click();
  const results = page.getByRole('region', { name: '确定性分析结果', exact: true }); await expect(results).toBeVisible();
  expect(gets.some(u => u.endsWith(`/research/tasks/by-operation/${operation}`))).toBe(true);
  await expect(results.locator('.operating-result')).toHaveCount(3);
  if (!before) for (const r of completed.snapshot.analysis_results) {
    await expect(results).toContainText(formatDecimal(r.absolute_change));
  }
  const model = page.getByRole('region', { name: '有限经营研究结果', exact: true });
  await expect(model).toContainText('待人工语义复核');
  if (!before) await expect(results.getByRole('link', { name: '整理报告 →', exact: true })).toBeVisible();
  for (const width of widths) {
    await page.setViewportSize({ width, height: width === 390 ? 450 : 900 }); await withinPage(page);
    await results.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${out}/s3-results-${width}.png` });
  }
  await model.getByRole('button', { name: /^原文 \[/ }).first().click(); await expect(page.locator('[id*="-cite-"]:focus')).toHaveCount(1);
  if (!before) { await model.getByText(/经营原文与完整引用/).click(); await model.getByRole('button', { name: /^原文 \[/ }).first().click(); await expect(page.locator('[id*="-cite-"]:focus')).toHaveCount(1); }
  await model.getByRole('button', { name: '返回待审解释', exact: true }).first().click(); await expect(page.locator('[id*="-interpretation-"]:focus')).toHaveCount(1);
  expect(writes).toEqual([expect.stringContaining(`/tasks/${task.task_id}/resume`)]);
  writeFileSync(`${out}/s3-proof.json`, JSON.stringify({ before, operation, writes, gets, status: completed.status, sevenWidths: widths, simulated_test: true }, null, 2));
});
