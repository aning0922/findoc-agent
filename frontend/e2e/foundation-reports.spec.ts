import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
const out = process.env.UX_ARTIFACT_DIR!;
const seed = JSON.parse(readFileSync(`${process.env.D26_REPORT_SEED_DIR}/journey-proof.json`, 'utf8'));
test('A unknown report save → B draft → read-only A recovery retains actual ownership', async ({ page }) => {
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const a = await (await page.request.get(`/api/research/tasks/${seed.result.task_id}`)).json();
  // New task B is explicitly created in this disposable simulated_test assembly.
  const input = structuredClone(a.input);
  for (const side of ['first', 'second']) for (const choice of input[side].choices) { choice.fact_id = null; choice.fact_set_id = null; }
  const create = await page.request.post('/api/research/tasks', { data: { operation_id: randomUUID(), input, run_version: 'd21-operating-graph-v2' } });
  expect(create.ok()).toBe(true);
  const created = await create.json();
  const facts = ['first', 'second'].flatMap(side => a.active_input[side].choices.map((c: any) => ({ side, metric_key: c.metric_key, fact_id: c.fact_id, fact_set_id: c.fact_set_id })));
  const resumed = await page.request.post(`/api/research/tasks/${created.task_id}/resume`, { data: { operation_id: randomUUID(), expected_revision: created.revision, facts } });
  expect(resumed.ok(), await resumed.text()).toBe(true); const b = await resumed.json(); expect(b.status).toBe('completed'); expect(b.task_id).not.toBe(a.task_id);
  const writes: any[] = [], gets: string[] = [];
  page.on('request', r => { if (r.method() === 'POST') writes.push({ url: r.url(), body: r.postDataJSON() }); else if (r.url().includes('/reports/')) gets.push(r.url()); });
  await page.goto(`/reports?task=${a.task_id}`);
  await page.getByRole('button', { name: '生成草稿', exact: true }).click();
  await expect(page.getByRole('article', { name: '报告草稿预览' })).toBeVisible();
  let saved: any;
  await page.route('**/api/reports', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    const response = await route.fetch(); expect(response.ok()).toBe(true); saved = await response.json(); await route.abort('failed');
  });
  await page.getByRole('button', { name: '保存第 1 版', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '保存结果未知' })).toBeVisible();
  await page.goto(`/reports?task=${b.task_id}`);
  await page.getByRole('button', { name: '生成草稿', exact: true }).click();
  await expect(page.getByRole('article', { name: '报告草稿预览' })).toBeVisible();
  await expect(page.getByRole('button', { name: '保存第 1 版', exact: true })).toBeDisabled();
  const before = await (await page.request.get('/api/__test__/d26-counts')).json();
  await page.getByRole('button', { name: '查询保存操作结果（GET）', exact: true }).click();
  const persisted = page.getByRole('article', { name: '已保存报告版本' });
  await expect(persisted).toBeVisible();
  const baseline = process.env.FOUNDATION_BASELINE === '1';
  if (baseline) {
    // Evidence of the original problem: A displayed inside the still-selected B draft.
    await expect(page.getByLabel('选择已完成研究')).toHaveValue(b.task_id);
    expect(new URL(page.url()).searchParams.get('task')).toBe(b.task_id);
  } else {
    await expect(page).toHaveURL(new RegExp(`report=${saved.report.report_id}&revision=1`));
    await expect(page.getByRole('article', { name: '报告草稿预览' })).toHaveCount(0);
    await expect(persisted).toHaveAttribute('data-task-id', a.task_id);
    await page.reload(); await expect(persisted).toBeVisible();
    const companies = await (await page.request.get('/api/companies')).json();
    const other = companies.find((c: any) => c.security_code === '000651');
    await page.goto(`/reports?company=${other.company_id}&report=${saved.report.report_id}&revision=1`);
    const context = page.getByRole('region', { name: '报告冻结上下文' });
    await expect(context).toHaveAttribute('data-task-id', a.task_id);
    await expect(context).toContainText('美的'); await expect(context).not.toContainText(other.name);
    await expect(page.getByLabel('当前企业', { exact: true })).toHaveCount(0);
    for (const width of [1440, 1280, 1024, 720, 640, 512, 390]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
      await page.screenshot({ path: `${out}/frozen-report-${width}.png`, fullPage: true });
    }
  }
  expect(writes.filter(w => w.url.endsWith('/api/reports'))).toHaveLength(1);
  expect(writes.filter(w => w.url.endsWith('/revisions'))).toHaveLength(0);
  expect(writes.some(w => w.url.endsWith('/api/reports') && w.body.task_id === b.task_id)).toBe(false);
  expect(await (await page.request.get('/api/__test__/d26-counts')).json()).toEqual(before);
  expect(gets.some(url => url.endsWith(`/reports/by-operation/${saved.report.operation_id}`))).toBe(true);
  await page.screenshot({ path: `${out}/cross-task-recovery.png`, fullPage: true });
  writeFileSync(`${out}/cross-task-proof.json`, JSON.stringify({ baseline, task_a: a.task_id, task_b: b.task_id, recovered_task: saved.report.trusted_snapshot.task_id, recovered_report: saved.report.report_id, writes, gets, before, final_url: page.url(), simulated_test: true, human_acceptances: 0 }, null, 2));
});
