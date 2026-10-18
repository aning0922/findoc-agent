import { expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
export const out = process.env.UX_ARTIFACT_DIR!;
export const before = process.env.POLISH_BEFORE === '1';
export const widths = [1440, 1280, 1024, 720, 640, 512, 390];
export async function setupPolish(page: Page) {
  await page.route('**/src/main.tsx*', r => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const seed = JSON.parse(readFileSync(`${process.env.D26_REPORT_SEED_DIR}/journey-proof.json`, 'utf8'));
  return (await page.request.get(`/api/research/tasks/${seed.result.task_id}`)).json();
}
export async function pendingTask(page: Page, task: any) {
  const input = structuredClone(task.input);
  for (const side of ['first', 'second']) for (const c of input[side].choices) c.fact_id = c.fact_set_id = null;
  const response = await page.request.post('/api/research/tasks', { data: { operation_id: randomUUID(), input, run_version: 'd21-operating-graph-v2' } });
  expect(response.ok(), await response.text()).toBe(true); return response.json();
}
export async function withinPage(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
}
