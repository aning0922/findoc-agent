import { test, expect } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const out = process.env.UX_ARTIFACT_DIR!;
const sources = JSON.parse(readFileSync(process.env.UX_SOURCE_FILE!, 'utf8'));

test('真实绑定纠错撤下原位 PDF 与候选，保留原研究来源', async ({ page }) => {
  test.setTimeout(300_000);
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const seed = JSON.parse(readFileSync(`${out}/journey-proof.json`, 'utf8')).task;
  const original = sources.find((s: any) => s.id.startsWith('midea') && s.id.endsWith('2025'));
  const originalBytes = readFileSync(original.absolute_path);
  expect(createHash('sha256').update(originalBytes).digest('hex')).toBe(original.sha256);
  // Document identity is content based; a different filename alone aliases the
  // seed. A trailing PDF comment creates an isolated derivative without changing pages.
  const bytes = Buffer.concat([originalBytes, Buffer.from(`\n% isolated-source-invalidation ${randomUUID()}\n`)]);
  const derivativeSha = createHash('sha256').update(bytes).digest('hex');
  expect(derivativeSha).not.toBe(original.sha256);
  const company = seed.input.first.company_id;
  const originalReport = seed.input.reports[0];
  const originalQuery = new URLSearchParams({ company_id: company, source_revision: originalReport.expected_source_revision });
  const originalBefore = await (await page.request.get(`/api/documents/${originalReport.document_id}/source?${originalQuery}`)).json();
  await page.goto(`/companies/${company}/documents`);
  await page.getByRole('button', { name: '上传并绑定年报', exact: true }).click();
  await page.getByLabel('报告年度', { exact: true }).fill('2025');
  await page.getByLabel('PDF 文件', { exact: true }).setInputFiles({ name: `isolated-${randomUUID()}.pdf`, mimeType: 'application/pdf', buffer: bytes });
  await page.getByLabel('核对上传绑定', { exact: true }).check();
  const uploadResponse = page.waitForResponse(r => r.url().endsWith('/api/report-documents') && r.request().method() === 'POST', { timeout: 180_000 });
  await page.getByRole('button', { name: '提交 PDF 并绑定', exact: true }).click();
  const upload = await (await uploadResponse).json();
  await expect(page.getByRole('status').filter({ hasText: '上传与绑定已读回' })).toBeVisible({ timeout: 120_000 });
  expect(upload.document_id).not.toBe(originalReport.document_id);
  const source = await (await page.request.get(`/api/documents/${upload.document_id}/source?company_id=${company}`)).json();
  expect(source.content_sha256).toBe(derivativeSha);
  const q = new URLSearchParams({ company_id: company, source_revision: source.source_revision });
  const disclosure = await (await page.request.get(`/api/research/disclosures/${upload.document_id}?${q}`)).json();
  expect(disclosure.disclosure_versions).toHaveLength(1);
  const input = structuredClone(seed.input);
  input.reports = [{ document_id: upload.document_id, expected_source_revision: source.source_revision }];
  for (const side of ['first', 'second']) for (const choice of input[side].choices) {
    choice.document_id = upload.document_id;
    choice.disclosure_version = disclosure.disclosure_versions[0];
    choice.fact_id = null;
    choice.fact_set_id = null;
  }
  const created = await page.request.post('/api/research/tasks', { data: { operation_id: randomUUID(), input, run_version: 'd21-operating-graph-v2' }, timeout: 180_000 });
  expect(created.ok()).toBeTruthy();
  const task = await created.json();
  expect(task.status).toBe('awaiting_human_confirmation');
  const writes: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(`${r.method()} ${r.url()}`); });
  await page.goto(`/research?company=${company}&mode=operating&task=${task.task_id}`);
  const cell = page.getByTestId('slot-second:revenue');
  await expect(cell).toContainText('候选待核对', { timeout: 60_000 });
  await cell.getByRole('button', { name: '核对原文' }).click();
  const panel = page.getByRole('region', { name: '原位核对财报' });
  await panel.getByRole('button', { name: '开始新核对' }).click();
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 60_000 });
  await panel.getByRole('button', { name: '开始本组核对' }).click();
  const check = panel.getByLabel('已核对 2024 营业收入', { exact: true });
  await check.focus();
  await page.keyboard.press('Space');
  await expect(check).toBeChecked();
  await page.setViewportSize({ width: 360, height: 900 });
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden');
  const beforeCorrection = [...writes];
  const corrected = await page.request.post(`/api/documents/${upload.document_id}/binding-corrections`, { data: {
    expected_attempt: source.attempt,
    metadata: { company_id: company, report_year: 2025, report_type: 'annual', basis: 'unknown', period_start: '2025-01-01', period_end: '2025-12-31' },
    reason: 'isolated embedded review invalidation test',
  } });
  expect(corrected.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.locator('[data-verification-state="invalidated"]')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('.evidence-viewer:visible')).toHaveCount(0);
  await expect(page.locator('canvas:visible')).toHaveCount(0);
  await expect(cell).not.toContainText('候选待核对');
  await expect(cell.getByRole('button', { name: '核对原文' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '复核并继续研究' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '确认本组数据' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '保存已接受数据' })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).not.toBe('hidden');
  expect(writes).toEqual(beforeCorrection);
  const fresh = await (await page.request.get(`/api/research/tasks/${task.task_id}`)).json();
  expect(fresh.budget).toEqual(task.budget);
  const oldSource = await page.request.get(`/api/documents/${originalReport.document_id}/source?${originalQuery}`);
  expect(oldSource.status()).toBe(200);
  expect(await oldSource.json()).toEqual(originalBefore);
  const oldPdf = await page.request.get(`/api/documents/${upload.document_id}/file?${q}`);
  expect(oldPdf.status()).toBe(409);
  await page.screenshot({ path: `${out}/embedded-source-invalidated-360.png` });
  writeFileSync(`${out}/embedded-invalidation-proof.json`, JSON.stringify({ real_binding_correction: true, original_sha256: original.sha256, derivative_sha256: derivativeSha, derivative_kind: 'real PDF with trailing isolated test comment', seed_document_unchanged: true, old_derivative_pdf_status: oldPdf.status(), task_id: task.task_id, zero_additional_writes_after_correction: true, model_budget_unchanged: true, keyboard_space_checkbox: true, simulated_test: true, fake_model_and_index: true, human_acceptances: 0 }, null, 2));
});
