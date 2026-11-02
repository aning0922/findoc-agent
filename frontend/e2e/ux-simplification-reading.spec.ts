import { test, expect, type APIRequestContext } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

// Real PDF/API/SQLite path in the isolated UX harness. The harness owns model substitutions.
const out = process.env.UX_ARTIFACT_DIR!;
const sources = JSON.parse(readFileSync(`${out}/sources.json`, 'utf8'));
const seed = JSON.parse(readFileSync(`${process.env.D26_REPORT_SEED_DIR}/journey-proof.json`, 'utf8'));
async function createVersions(request: APIRequestContext) {
  const task = await (await request.get(`/api/research/tasks/${seed.result.task_id}`)).json();
  async function save(path: string, revision?: number) {
    const response = await request.post(path, { data: { operation_id: randomUUID(), task_id: task.task_id,
      expected_task_revision: task.revision, ...(revision ? { expected_report_revision: revision } : {}),
      edits: { title: `阅读体验验收 v${revision ? 2 : 1}`, conclusions: ['用户结论仍待人工语义审阅。'] } } });
    expect(response.ok(), await response.text()).toBe(true); return response.json();
  }
  const v1 = await save('/api/reports');
  const v2 = await save(`/api/reports/${v1.report.report_id}/revisions`, 1);
  return { v1, v2 };
}

test('P1 问答原 PDF 侧栏保持实际来源、物理页与原阅读位置', async ({ page, request }) => {
  const fixture = sources.find((s: { id: string }) => s.id === 'midea-2025');
  const companies = await (await request.get('/api/companies')).json();
  const company = companies.find((c: { security_code: string }) => c.security_code === '000333');
  const response = await request.post('/api/report-documents', { multipart: {
    file: { name: `${fixture.id}.pdf`, mimeType: 'application/pdf', buffer: readFileSync(fixture.absolute_path) },
    metadata: JSON.stringify({ company_id: company.company_id, report_year: 2025, report_type: 'annual', basis: 'PRC_GAAP', period_start: '2025-01-01', period_end: '2025-12-31' }),
  } });
  expect(response.status()).toBe(202); const documentId = (await response.json()).document_id;
  await expect.poll(async () => (await (await request.get(`/api/documents/${documentId}`)).json()).status, { timeout: 120000 }).toBe('ready');
  const created = await request.post('/api/research/runs', { data: { operation_id: randomUUID(), document_ids: [documentId], query: '2025年营业收入是多少？请给出原文出处。' } });
  expect(created.status()).toBe(200); const run = await created.json(); expect(run.status).toBe('answered');
  const citation = run.result.citations[0];
  const writes: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET' && r.url().includes('/api/')) writes.push(r.url()); });
  await page.goto(`/research?mode=qa&run=${run.run_id}`);
  await expect(page.getByRole('heading', { name: '回答与证据', exact: true })).toBeVisible();
  const review = page.getByText('人工语义审阅与历史附注', { exact: true });
  expect(await review.evaluate(e => e.parentElement!.hasAttribute('open'))).toBe(false);
  const trigger = page.locator(`[data-citation-number="${citation.number}"]`).getByRole('button', { name: `查看原 PDF [${citation.number}]`, exact: true });
  const layouts = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 }); await trigger.scrollIntoViewIfNeeded();
    const scrollBefore = await page.evaluate(() => scrollY); await trigger.click();
    const dialog = page.getByRole('dialog', { name: `原 PDF · 引用 [${citation.number}]`, exact: true });
    await expect(dialog.locator('canvas')).toHaveAttribute('aria-label', `PDF 物理第 ${citation.physical_page} 页`, { timeout: 30000 });
    const box = await dialog.boundingBox(); expect(box).not.toBeNull();
    expect(Math.abs(box!.x + box!.width - width)).toBeLessThanOrEqual(1);
    expect(box!.width).toBeLessThanOrEqual(width); expect(box!.height).toBe(900);
    await page.screenshot({ path: `${out}/p1-qa-drawer-${width}.png` }); layouts.push({ width, box });
    await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
    expect(Math.abs(await page.evaluate(() => scrollY) - scrollBefore)).toBeLessThanOrEqual(1);
  }
  const href = await page.locator(`[data-citation-number="${citation.number}"]`).getByRole('link', { name: /打开原 PDF/ }).getAttribute('href');
  const pdf = await request.get(href!.split('#')[0]); expect(pdf.ok()).toBe(true);
  const sha = createHash('sha256').update(await pdf.body()).digest('hex'); expect(sha).toBe(fixture.sha256);
  const reread = await (await request.get(`/api/research/runs/${run.run_id}`)).json();
  expect(reread.result).toEqual(run.result); expect(reread.integrity_sha256).toBe(run.integrity_sha256); expect(writes).toEqual([]);
  writeFileSync(`${out}/p1-qa-reading-proof.json`, JSON.stringify({ run_id: run.run_id, layouts, sha256: sha, writes, immutable_result_unchanged: true, model_execution: 'harness substitution; not live model validation' }, null, 2));
});

test('P1 报告库直出，版本阅读分离，返回库保留未保存编辑保护', async ({ page, request }) => {
  // Isolated simulated consent stays confined to the existing test entry.
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const { v1, v2 } = await createVersions(request);
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET' && r.url().includes('/api/')) writes.push(r.url()); });
  await page.goto('/reports');
  const library = page.getByRole('region', { name: '已保存报告历史', exact: true });
  await expect(library).toBeVisible(); expect(await library.evaluate(e => !!e.closest('details'))).toBe(false);
  const row = library.locator(`[data-report-id="${v1.report.report_id}"]`);
  await expect(row).toContainText('阅读体验验收 v2'); await row.getByRole('button', { name: '阅读报告', exact: true }).click();
  const article = page.getByRole('article', { name: '已保存报告版本', exact: true });
  await expect(article).toHaveAttribute('data-revision', '2'); await expect(library).toHaveCount(0);
  await expect(page.getByText('从已完成研究整理报告草稿', { exact: true })).toHaveCount(0);
  await page.getByLabel('报告版本', { exact: true }).selectOption('1');
  await expect(article).toHaveAttribute('data-revision', '1'); expect(new URL(page.url()).searchParams.get('revision')).toBe('1');
  await expect(page.getByRole('button', { name: '编辑为新版本', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('报告标题', { exact: true })).toHaveCount(0);
  await page.reload(); await expect(article).toHaveAttribute('data-revision', '1');
  await page.getByRole('button', { name: '打开最新版本后编辑', exact: true }).click();
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  const title = page.getByLabel('报告标题', { exact: true }); await title.fill('尚未保存，不能悄悄丢失');
  await page.getByRole('button', { name: '返回报告库', exact: true }).click();
  const guard = page.getByRole('dialog', { name: '修改尚未保存', exact: true }); await expect(guard).toBeVisible();
  await guard.getByRole('button', { name: '继续编辑', exact: true }).click(); await expect(title).toHaveValue('尚未保存，不能悄悄丢失');
  await page.getByRole('button', { name: '返回报告库', exact: true }).click();
  await guard.getByRole('button', { name: '放弃修改并离开', exact: true }).click();
  await expect(library).toBeVisible(); expect(new URL(page.url()).search).toBe('');
  expect((await (await request.get(`/api/reports/${v1.report.report_id}/revisions/2`)).json()).report).toEqual(v2.report);
  expect(writes).toEqual([]); await page.screenshot({ path: `${out}/p1-report-library.png`, fullPage: true });
});

test('P1 未确认的版本保存返回报告库后仍以原操作身份查证', async ({ page, request }) => {
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const { v1 } = await createVersions(request);
  await page.goto(`/reports?report=${v1.report.report_id}&revision=2`);
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  await page.getByLabel('报告标题', { exact: true }).fill('提交已完成但响应丢失的第三版');
  let committed: any;
  const writes: string[] = [];
  page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()); });
  await page.route(`**/api/reports/${v1.report.report_id}/revisions`, async route => {
    const response = await route.fetch(); expect(response.ok(), await response.text()).toBe(true);
    committed = await response.json(); await route.abort('failed');
  });
  await page.getByRole('button', { name: '保存为 v3', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '保存结果未知' })).toBeVisible();
  await page.getByRole('button', { name: '返回报告库', exact: true }).click();
  await expect(page.getByLabel('保存操作身份')).toHaveValue(committed.report.operation_id);
  await page.getByRole('button', { name: '查看这次保存的结果', exact: true }).click();
  await expect(page.getByRole('article', { name: '已保存报告版本', exact: true })).toHaveAttribute('data-revision', '3');
  expect(new URL(page.url()).searchParams.get('revision')).toBe('3'); expect(writes).toHaveLength(1);
  const reread = await (await request.get(`/api/reports/${v1.report.report_id}/revisions/3`)).json();
  expect(reread.report).toEqual(committed.report);
});

test('P1 保存前的资格读取在离开编辑器后不能继续 POST', async ({ page, request }) => {
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const { v1, v2 } = await createVersions(request);
  await page.goto(`/reports?report=${v1.report.report_id}&revision=2`);
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  await page.getByLabel('报告标题', { exact: true }).fill('离开编辑器后不可提交的新标题');
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let markStarted!: () => void; const started = new Promise<void>(resolve => { markStarted = resolve; });
  let finish!: () => void; const finished = new Promise<void>(resolve => { finish = resolve; });
  const writes: string[] = [];
  page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()); });
  await page.route(`**/api/reports/${v1.report.report_id}/revisions/2`, async route => {
    const response = await route.fetch(); expect(response.ok()).toBe(true); markStarted(); await gate;
    await route.fulfill({ response }).catch(() => {}); finish();
  });
  await page.getByRole('button', { name: '保存为 v3', exact: true }).click(); await started;
  await page.getByRole('button', { name: '返回报告库', exact: true }).click();
  await expect(page.getByRole('region', { name: '已保存报告历史', exact: true })).toBeVisible();
  release(); await finished;
  // The subsequent HTTP read acts as a barrier after the delayed preflight was released.
  const current = await (await request.get(`/api/reports/${v1.report.report_id}/revisions/2`)).json();
  expect(current.current_revision).toBe(2); expect(current.report).toEqual(v2.report); expect(writes).toEqual([]);
  expect(await page.evaluate(() => sessionStorage.getItem('findoc-report-unknown-operation-v1'))).toBeNull();
  await expect(page.getByRole('heading', { name: '报告库', exact: true })).toBeFocused();
});
