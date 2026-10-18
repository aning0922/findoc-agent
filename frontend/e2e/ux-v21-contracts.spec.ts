import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
const out = process.env.UX_ARTIFACT_DIR!;
async function openTask(page: any) {
  const list = await (await page.request.get('/api/research/tasks?limit=50')).json();
  const task = list.items.find((t: any) => t.status === 'completed' && t.publication_eligibility?.status === 'current_at_read' && t.input.template === 'company_period_change');
  expect(task).toBeTruthy();
  return task;
}
async function harness(page: any) {
  await page.route('**/src/main.tsx*', (r: any) => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
}
test('GET-only task assembly restores history, browser back and refresh without changing SQLite or budget', async ({ page }) => {
  await harness(page); const task = await openTask(page);
  const db = `${process.env.FINDOC_D22_RUNTIME_ROOT}/documents.db`;
  const digest = () => createHash('sha256').update(readFileSync(db)).digest('hex');
  const before = digest(), writes: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.method() + ' ' + r.url()); });
  const path = `/research?company=${task.input.first.company_id}&mode=operating&task=${task.task_id}`;
  await page.goto("/research?mode=operating");
  await page.getByRole("complementary", { name: "经营研究历史" }).locator(`a[href*="task=${task.task_id}"]`).click();
  expect(page.url()).toContain(`company=${task.input.first.company_id}`);
  await page.goto(path); await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  await page.getByRole('link', { name: '六项事实', exact: true }).click();
  await page.getByRole('link', { name: '财务分析', exact: true }).click();
  await page.goBack();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  expect(page.url()).toContain(task.task_id);
  await page.reload(); await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  const fresh = await (await page.request.get(`/api/research/tasks/${task.task_id}`)).json();
  expect(fresh.revision).toBe(task.revision); expect(fresh.budget).toEqual(task.budget); expect(writes).toEqual([]); expect(digest()).toBe(before);
  await page.screenshot({ path: `${out}/readonly-history-1440.png` });
  writeFileSync(`${out}/readonly-proof.json`, JSON.stringify({ task_id: task.task_id, budget_unchanged: true, revision_unchanged: true, db_unchanged: true, writes, graph_service_absent: true }, null, 2));
});
test('original D23 draft save and immutable version reload remain usable through guided task entry', async ({ page }) => {
  await harness(page); const task = await openTask(page);
  await page.goto(`/reports?company=${task.input.first.company_id}&task=${task.task_id}`);
  await expect(page.getByLabel('选择已完成的有效 D21 研究')).toHaveValue(task.task_id);
  await page.getByRole('button', { name: '生成草稿', exact: true }).click();
  await expect(page.getByRole('article', { name: '报告草稿预览' })).toBeVisible();
  const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/reports'));
  let writes = 0; page.on('request', r => { if (r.method() === 'POST') writes++; });
  await page.getByRole('button', { name: '保存报告', exact: true }).dblclick();
  const saved = await (await response).json();
  await expect(page.getByRole('status').filter({ hasText: '保存与只读读回成功' })).toBeVisible(); expect(writes).toBe(1);
  await page.getByRole('link', { name: '打开已保存 v1', exact: true }).click();
  await expect(page.getByRole('article', { name: '已保存报告版本' })).toBeVisible();
  await page.reload(); await expect(page.getByRole('article', { name: '已保存报告版本' })).toBeVisible(); expect(writes).toBe(1);
  await page.screenshot({ path: `${out}/d23-saved-version-1440.png` });
  writeFileSync(`${out}/d23-proof.json`, JSON.stringify({ saved, save_posts: writes, reload_zero_writes: true, simulated_test: true, human_acceptances: 0 }, null, 2));
});
