import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const out = process.env.D30_LIVE_OUT!;
const evidence = process.env.D30_EVIDENCE!;
const verified = JSON.parse(readFileSync(`${evidence}/live-verification/summary.json`, 'utf8'));
test('real D30 saved QA reads C1 without inheriting D28 external acceptance', async ({ page }) => {
  const methods: string[] = [];
  page.on('request', r => { if (r.url().includes('/api/')) methods.push(r.method()); });
  const a10 = verified.qa.find((x: { case: string }) => x.case === 'A10');
  await page.goto(`/research?mode=qa&run=${a10.run_id}`);
  const focus = page.getByRole('region', { name: '本题可信焦点', exact: true });
  await expect(focus).toContainText('456,451,731');
  await expect(focus).toContainText('千元');
  await expect(page.getByLabel('问答审阅状态')).toContainText('无本项适用记录');
  await expect(page.getByLabel('问答审阅状态')).toContainText('待审（pending）');
  await page.screenshot({ path: `${out}/live-A10-pending.png` });
  await focus.getByRole('button', { name: '查看原 PDF [1]', exact: true }).click();
  await expect(page.getByRole('dialog').locator('canvas')).toBeVisible({ timeout: 30000 });
  await page.screenshot({ path: `${out}/live-A10-PDF.png` });
  await page.keyboard.press('Escape');
  expect(methods.every(m => m === 'GET')).toBeTruthy();
  writeFileSync(`${out}/live-qa-methods.json`, JSON.stringify(methods));
});
test('three real tasks remain separate human checkpoints during reading', async ({ page }) => {
  const methods: string[] = [];
  page.on('request', r => { if (r.url().includes('/api/')) methods.push(r.method()); });
  for (const name of ['midea', 'gree', 'comparison']) {
    const { task } = JSON.parse(readFileSync(`${evidence}/waiting-tasks/${name}.json`, 'utf8'));
    await page.goto(`/research?company=${task.input.first.company_id}&mode=operating&task=${task.task_id}`);
    await expect(page.locator('main')).toContainText('核对');
    const response = await page.request.get(`/api/research/tasks/${task.task_id}`);
    const current = await response.json();
    expect(current.status).toBe('awaiting_human_confirmation');
    expect(current.waiting_checkpoint).toBe(true);
    expect(current.final_research_content).toBe(null);
    await page.screenshot({ path: `${out}/live-${name}-waiting.png` });
  }
  expect(methods.every(m => m === 'GET')).toBeTruthy();
  writeFileSync(`${out}/live-task-methods.json`, JSON.stringify(methods));
});
