import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const out = process.env.UX_ARTIFACT_DIR!;
const sources = JSON.parse(readFileSync(`${out}/sources.json`, 'utf8'));
let companies: any[], docs: any[] = [], saved: any;
const widths = [1440, 1280, 1024, 720, 640, 512, 390];
async function counts(page: Page) { return (await page.request.get('/api/__test__/d26-counts')).json(); }
async function chooser(page: Page) {
  const button = page.getByRole('button', { name: '管理来源', exact: true });
  await button.click();
}
async function finishChooser(page: Page) {
  const button = page.getByRole('button', { name: '完成资料选择', exact: true });
  await button.click();
}
async function begin(page: Page) {
  await page.goto('/research?mode=qa');
  await chooser(page);
  for (const d of docs) {
    const name = `${companies.find(c => c.company_id === d.company_id).name} · ${d.report_year} 年报`;
    await page.getByRole('checkbox', { name: new RegExp(name) }).check();
  }
  await finishChooser(page);
  await page.getByLabel('研究问题', { exact: true }).fill('请列四份年报主要会计数据和财务指标原文，不计算同比。');
}
test.beforeAll(async ({ request }) => {
  companies = await (await request.get('/api/companies')).json();
  for (const s of sources) {
    const company = companies.find(c => c.security_code === (s.id.startsWith('gree') ? '000651' : '000333'));
    const y = Number(s.id.slice(-4));
    const r = await request.post('/api/report-documents', { multipart: { file: { name: `${s.id}.pdf`, mimeType: 'application/pdf', buffer: readFileSync(s.absolute_path) }, metadata: JSON.stringify({ company_id: company.company_id, report_year: y, report_type: 'annual', basis: 'PRC_GAAP', period_start: `${y}-01-01`, period_end: `${y}-12-31` }) } });
    expect(r.status()).toBe(202); const id = (await r.json()).document_id;
    await expect.poll(async () => (await (await request.get(`/api/documents/${id}`)).json()).status, { timeout: 120000 }).toBe('ready');
    const source = await (await request.get(`/api/documents/${id}/source`)).json();
    expect(source.content_sha256).toBe(s.sha256); docs.push(source);
  }
  const r = await request.post('/api/research/runs', { data: { operation_id: crypto.randomUUID(), document_ids: docs.map(d => d.document_id), query: '请列四份年报主要会计数据和财务指标原文，不计算同比。' } });
  expect(r.status()).toBe(200); saved = await r.json(); expect(saved.status).toBe('answered');
  writeFileSync(`${out}/saved-run.json`, JSON.stringify(saved, null, 2));
});
test('saved answer uses page reading flow, nearby citations and collapsed history at seven widths', async ({ page }) => {
  await page.goto(`/research?mode=qa&run=${saved.run_id}`);
  const answer = page.getByRole('region', { name: '有证据的回答' }); await expect(answer).toBeVisible();
  const observations: any[] = [];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await page.screenshot({ path: `${out}/qa-${width}.png`, fullPage: true });
    await page.screenshot({ path: `${out}/qa-${width}-viewport.png` });
    observations.push(await answer.evaluate(e => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      innerScroll: [...e.querySelectorAll<HTMLElement>('*')].filter(n => /auto|scroll/.test(getComputedStyle(n).overflowY) && n.scrollHeight > n.clientHeight + 1).map(n => ({ tag: n.tagName, height: n.clientHeight, maxHeight: getComputedStyle(n).maxHeight })) })));
  }
  writeFileSync(`${out}/reading-layout.json`, JSON.stringify(observations, null, 2));
  // This contract fails on S0/S1: the answer has a 420px inner scroller.
  expect(observations.flatMap(o => o.innerScroll).filter(s => s.maxHeight === '420px')).toEqual([]);
  for (const o of observations) expect(o.scrollWidth).toBeLessThanOrEqual(o.width + 1);
  const history = page.getByRole('region', { name: '研究历史列表', includeHidden: true });
  expect(await history.evaluate(e => !!e.closest('details:not([open])'))).toBe(true);
  for (const c of saved.result.citations) {
    const excerpt = answer.locator(`[data-citation-number="${c.number}"]`);
    await expect(excerpt).toHaveAttribute('data-document-id', c.document_id);
    await expect(excerpt).toHaveAttribute('data-source-revision', c.source_revision);
    await expect(excerpt.getByRole('link', { name: /打开原 PDF/ })).toHaveAttribute('href', new RegExp(`#page=${c.physical_page}$`));
    await expect(excerpt.locator('pre')).toBeHidden();
    await expect(excerpt.locator('[data-saved-excerpt]')).toHaveText(c.text);
  }
  const first = answer.locator('table').first();
  await expect(first).toBeVisible();
  await expect(page.getByLabel('原问题', { exact: true })).toHaveText(saved.query);
});
test('saved question takes priority and source chooser supports keyboard without writes', async ({ page }) => {
  const before = await counts(page); const writes: string[] = [];
  page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()); });
  await page.goto(`/research?mode=qa&company=unrelated&run=${saved.run_id}`);
  await expect(page.getByLabel('原问题', { exact: true })).toHaveText(saved.query);
  await expect(page.getByLabel('研究问题', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('complementary', { name: '本次回答来源' }).locator('[data-source-document]')).toHaveCount(4);
  const manage = page.getByRole('button', { name: '管理来源', exact: true });
  await manage.click(); const dialog = page.getByRole('dialog', { name: '选择问答资料' });
  await expect(dialog.getByRole('button', { name: '关闭选择问答资料' })).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(dialog.getByRole('button', { name: '完成资料选择' })).toBeFocused();
  await page.keyboard.press('Tab'); await expect(dialog.getByRole('button', { name: '关闭选择问答资料' })).toBeFocused();
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(manage).toBeFocused();
  await page.setViewportSize({ width: 390, height: 900 }); await page.getByRole('button', { name: '修改问题或资料' }).click();
  await expect(page.getByLabel('研究问题', { exact: true })).toHaveValue(saved.query);
  await expect(page.getByRole('region', { name: '有证据的回答' })).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has('run')).toBe(false);
  expect(writes).toEqual([]); expect(await counts(page)).toEqual(before);
  await page.screenshot({ path: `${out}/composer-390.png`, fullPage: true });
});

test('one to four explicit sources and question enable a new lookup without auto submission', async ({ page }) => {
  const before = await counts(page); await begin(page);
  await expect(page.getByLabel('所选资料摘要').locator('span')).toHaveCount(4);
  await expect(page.getByRole('button', { name: '查找原文', exact: true })).toBeEnabled();
  expect(await counts(page)).toEqual(before);
});
test('all twelve original values retain their actual annual column, unit, full rows and immutable citations', async ({ page }) => {
  const before = await counts(page);
  await page.goto(`/research?mode=qa&run=${saved.run_id}`);
  const answer = page.getByRole('region', { name: '有证据的回答' }); await expect(answer).toBeVisible();
  const amounts: Record<string, string[]> = {
    'gree-2024': ['189,163,654,064.64', '32,184,570,372.28', '29,369,250,570.66'],
    'gree-2025': ['170,447,058,533.57', '29,003,103,411.66', '46,383,114,754.02'],
    'midea-2024': ['407,149,600', '38,537,237', '60,511,572'],
    'midea-2025': ['456,451,731', '43,945,411', '53,345,930'],
  };
  const proof: any[] = [];
  for (const c of saved.result.citations) {
    const excerpt = answer.locator(`[data-citation-number="${c.number}"]`);
    const table = excerpt.getByRole('table').filter({ hasText: amounts[c.source_file.replace('.pdf', '')][0] }).first();
    const headers = await table.locator('th').allTextContents();
    for (const amount of amounts[c.source_file.replace('.pdf', '')]) {
      const row = table.locator('tr').filter({ hasText: amount }).first(); const cells = await row.locator('td').allTextContents();
      expect(cells.indexOf(amount)).toBe(headers.indexOf(`${c.report_year}年`));
      expect(cells.some(s => s.includes(c.source_file.startsWith('midea') ? '千元' : '（元）'))).toBe(true);
      proof.push({ document: c.document_id, revision: c.source_revision, citation: c.number, page: c.physical_page, amount, headers, cells });
    }
    await excerpt.locator('summary').click();
    expect(await excerpt.locator('[data-saved-excerpt]').textContent()).toBe(c.text);
    await excerpt.locator('summary').click();
  }
  expect(proof).toHaveLength(12);
  const reread = await (await page.request.get(`/api/research/runs/${saved.run_id}`)).json();
  expect(reread.result).toEqual(saved.result); expect(reread.integrity_sha256).toBe(saved.integrity_sha256);
  expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/twelve-value-and-integrity-proof.json`, JSON.stringify({ proof, run_id: saved.run_id, integrity_sha256: saved.integrity_sha256, result_unchanged: true, before, after: await counts(page), human_review: 'pending' }, null, 2));
});
test('real PDF loads in place with verified source, page and keyboard return at 1440 and 390', async ({ page }) => {
  await page.goto(`/research?mode=qa&run=${saved.run_id}`);
  const c = saved.result.citations[0]; const before = await counts(page);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const trigger = page.locator(`[data-citation-number="${c.number}"]`).getByRole('button', { name: `查看原 PDF [${c.number}]`, exact: true });
    await trigger.scrollIntoViewIfNeeded(); const position = await page.evaluate(() => scrollY);
    await trigger.click(); const dialog = page.getByRole('dialog', { name: `原 PDF · 引用 [${c.number}]` });
    await expect(dialog.getByRole('button', { name: `关闭原 PDF · 引用 [${c.number}]` })).toBeFocused();
    await expect(dialog.locator('canvas')).toHaveAttribute('aria-label', `PDF 物理第 ${c.physical_page} 页`, { timeout: 30000 });
    await expect(dialog.getByLabel('PDF 阅读工具')).toBeVisible();
    await dialog.getByRole('button', { name: '下一页', exact: true }).click();
    await expect(dialog.locator('canvas')).toHaveAttribute('aria-label', `PDF 物理第 ${c.physical_page + 1} 页`);
    await dialog.getByRole('button', { name: '返回引用页' }).click();
    await expect(dialog.locator('canvas')).toHaveAttribute('aria-label', `PDF 物理第 ${c.physical_page} 页`);
    await page.screenshot({ path: `${out}/pdf-${width}.png` });
    await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
    expect(Math.abs((await page.evaluate(() => scrollY)) - position)).toBeLessThanOrEqual(1);
  }
  const href = await page.locator(`[data-citation-number="${c.number}"]`).getByRole('link', { name: /打开原 PDF/ }).getAttribute('href');
  const file = await page.request.get(href!.split('#')[0]); expect(file.ok()).toBe(true);
  const bytes = await file.body(); const source = docs.find(d => d.document_id === c.document_id);
  const { createHash } = await import('node:crypto'); expect(createHash('sha256').update(bytes).digest('hex')).toBe(source.content_sha256);
  expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/pdf-identity-proof.json`, JSON.stringify({ citation: c.number, document: c.document_id, revision: c.source_revision, physical_page: c.physical_page, pdf_sha256: source.content_sha256, before, after: await counts(page), source_and_byte_validation: true, escape_returns_focus_and_scroll: true }, null, 2));
});
test('Run A to draft B then history and exact A URL keep original ownership with GET only', async ({ page }) => {
  const before = await counts(page); const writes: any[] = [];
  page.on('request', r => { if (r.method() !== 'GET' && r.url().includes('/api/')) writes.push(r.url()); });
  await page.goto(`/research?mode=qa&run=${saved.run_id}`); await expect(page.getByLabel('原问题')).toHaveText(saved.query);
  await page.getByRole('button', { name: '修改问题或资料' }).click();
  await chooser(page);
  for (const d of docs) await page.locator(`[data-document-id="${d.document_id}"]`).getByRole('checkbox').uncheck();
  const b = docs[1]; await page.locator(`[data-document-id="${b.document_id}"]`).getByRole('checkbox').check(); await finishChooser(page);
  await page.getByLabel('研究问题').fill('资料 B 的新问题');
  await expect(page.getByRole('region', { name: '有证据的回答' })).toHaveCount(0);
  await page.getByRole('button', { name: '历史问答', exact: true }).click();
  await page.getByRole('region', { name: '研究历史列表' }).getByRole('button', { name: saved.query, exact: true }).click();
  await expect(page.getByLabel('原问题')).toHaveText(saved.query);
  await expect(page.getByRole('complementary', { name: '本次回答来源' }).locator('[data-source-document]')).toHaveCount(4);
  await page.reload(); await expect(page.getByLabel('原问题')).toHaveText(saved.query);
  await page.goBack(); await expect(page.getByLabel('研究问题')).toHaveValue('');
  await page.goForward(); await expect(page.getByLabel('原问题')).toHaveText(saved.query);
  expect(writes).toEqual([]); expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/a-b-history-proof.json`, JSON.stringify({ run: saved.run_id, b_document: b.document_id, original_sources: saved.documents, writes, before, after: await counts(page), immutable_original_question: true }, null, 2));
});
test('unknown POST A stops local waiting and recovers original operation after scope B with zero model replay', async ({ page }) => {
  await begin(page); const before = await counts(page); let actual: any; let writes = 0; let release!: () => void;
  const gate = new Promise<void>(r => { release = r; });
  await page.route('**/api/research/runs', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    writes++; const response = await route.fetch(); expect(response.status()).toBe(200); actual = await response.json(); await gate; await route.abort('failed').catch(() => {});
  });
  await page.getByRole('button', { name: '查找原文', exact: true }).click();
  await expect.poll(() => actual?.run_id, { timeout: 30000 }).toBeTruthy();
  await page.getByRole('button', { name: '停止本页等待', exact: true }).click(); release();
  await expect(page.locator('[data-user-state="unknown"]')).toContainText('服务端任务可能仍在执行');
  await chooser(page); for (const d of docs.slice(1)) await page.locator(`[data-document-id="${d.document_id}"]`).getByRole('checkbox').uncheck(); await finishChooser(page);
  await page.getByLabel('研究问题').fill('已切换为资料 B 的草稿');
  await expect(page.getByRole('button', { name: '查找原文', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '查看这次操作的结果', exact: true }).click();
  await expect(page.getByRole('region', { name: '研究历史详情' })).toHaveAttribute('data-run-id', actual.run_id);
  await expect(page.getByLabel('原问题')).toHaveText(actual.query);
  await expect(page.getByRole('complementary', { name: '本次回答来源' }).locator('[data-source-document]')).toHaveCount(4);
  await page.reload(); await expect(page.getByLabel('原问题')).toHaveText(actual.query);
  const after = await counts(page); expect(writes).toBe(1); expect(after.calls.model).toBe(before.calls.model + 1); expect(after.tables.research_runs).toBe(before.tables.research_runs + 1);
  writeFileSync(`${out}/unknown-a-b-proof.json`, JSON.stringify({ original_operation: actual.operation_id, run: actual.run_id, query: actual.query, documents: actual.documents, writes, before, after, recovery_model_calls: 0, automatic_retries: 0 }, null, 2));
});
test('refusals, failure, budget and running records stay distinct and never invent an answer', async ({ page }) => {
  const before = await counts(page); const results: any[] = [];
  const variants = [
    ['refused', 'insufficient_evidence', '所选资料证据不足'],
    ['refused', 'requires_confirmed_financial_analysis', '当前问题需要已确认财务事实'],
    ['refused', 'unsupported_table_structure', '表格列关系暂未通过核验'],
    ['system_error', 'llm_error', '模型连接失败'],
    ['system_error', 'context_budget_error', '本次问答的处理预算不足'],
    ['running', '', '研究结果暂时无法确认'],
  ];
  for (const [status, code, title] of variants) {
    const value = { ...saved, status, ended_at: status === 'running' ? null : saved.ended_at, result: status === 'running' ? null : { ...saved.result, outcome: status, content: '', citations: [], ...(status === 'refused' ? { reason: code } : { error_code: code }) } };
    await page.route(`**/api/research/runs/${saved.run_id}`, r => r.fulfill({ json: value }));
    await page.goto(`/research?mode=qa&run=${saved.run_id}`);
    await expect(page.getByRole('region', { name: '研究历史详情' }).getByText(title, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('region', { name: '有证据的回答' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: /打开原 PDF/ })).toHaveCount(0);
    if (status === 'running') {
      await page.getByRole('button', { name: '修改问题或资料' }).click();
      await expect(page.getByRole('button', { name: '查找原文', exact: true })).toBeDisabled();
    }
    results.push({ status, code, title, answer_absent: true });
    await page.unroute(`**/api/research/runs/${saved.run_id}`);
  }
  expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/six-boundaries-proof.json`, JSON.stringify({ results, presentation_response_fixtures: true, originals_unchanged: true, before, after: await counts(page) }, null, 2));
});
test('long saved-text presentation keeps all source text and local table scrolling without shrinking body', async ({ page }) => {
  const before = await counts(page);
  const citations = Array.from({ length: 8 }, (_, i) => saved.result.citations.map((c: any) => ({ ...c, number: i * 4 + c.number }))).flat();
  const content = citations.map((c: any) => `${c.report_year}年报《${c.source_file}》原文：\n${c.text}\n[${c.number}]`).join('\n\n');
  const value = { ...saved, result: { ...saved.result, content, citations } };
  await page.route(`**/api/research/runs/${saved.run_id}`, r => r.fulfill({ json: value }));
  await page.goto(`/research?mode=qa&run=${saved.run_id}`); await page.setViewportSize({ width: 390, height: 900 });
  const answer = page.getByRole('region', { name: '有证据的回答' }); await expect(answer.locator('[data-citation-number]')).toHaveCount(32);
  const table = answer.locator('.report-table-scroll').first();
  const measurement = await table.evaluate(e => ({ clientWidth: e.clientWidth, scrollWidth: e.scrollWidth, fontSize: getComputedStyle(e.querySelector('td')!).fontSize, pageScrollWidth: document.documentElement.scrollWidth, pageHeight: document.documentElement.scrollHeight, width: innerWidth }));
  expect(measurement.scrollWidth).toBeGreaterThan(measurement.clientWidth); expect(Number.parseFloat(measurement.fontSize)).toBeGreaterThanOrEqual(16); expect(measurement.pageScrollWidth).toBeLessThanOrEqual(391); expect(measurement.pageHeight).toBeGreaterThan(10000);
  await table.focus(); await page.keyboard.press('ArrowRight'); await expect.poll(() => table.evaluate(e => e.scrollLeft)).toBeGreaterThan(0);
  for (const c of citations) {
    const raw = answer.locator(`[data-saved-excerpt="${c.number}"]`); expect(await raw.textContent()).toBe(c.text);
  }
  expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/long-reading-proof.json`, JSON.stringify({ measurement, citations: 32, repeated_real_text_presentation_fixture: true, server_content_modified: false, before, after: await counts(page) }, null, 2));
});
test('composer, long company names and source dialog remain usable at all seven CSS widths', async ({ page }) => {
  const longName = '美的集团股份有限公司及其合并范围内的长期企业经营研究资料与原文阅读工作区';
  await page.route('**/api/companies', async r => { const response = await r.fetch(); const values = await response.json(); values.find((c: any) => c.security_code === '000333').name = longName; await r.fulfill({ response, json: values }); });
  const before = await counts(page), observations: any[] = [];
  await page.goto('/research?mode=qa'); await chooser(page);
  for (const d of docs) await page.locator(`[data-document-id="${d.document_id}"]`).getByRole('checkbox').check(); await finishChooser(page);
  await page.getByLabel('研究问题').fill('列出年报中的原值原单位，不计算同比。');
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    const measure = await page.evaluate(() => {
      const controls = [...document.querySelectorAll<HTMLElement>('[aria-label="原文问答"] button, #qa-question, [aria-label="所选资料摘要"] span')].filter(e => e.getClientRects().length);
      return { width: innerWidth, scrollWidth: document.documentElement.scrollWidth, controls: controls.map(e => { const r = e.getBoundingClientRect(); return { text: e.innerText, left: r.left, right: r.right, clientWidth: e.clientWidth, scrollWidth: e.scrollWidth, height: r.height }; }) };
    });
    expect(measure.scrollWidth).toBeLessThanOrEqual(width + 1); for (const c of measure.controls) { expect(c.left).toBeGreaterThanOrEqual(-1); expect(c.right).toBeLessThanOrEqual(width + 1); expect(c.scrollWidth).toBeLessThanOrEqual(c.clientWidth + 1); }
    await page.screenshot({ path: `${out}/composer-${width}.png` });
    await chooser(page); const dialog = page.getByRole('dialog');
    const bounds = await dialog.evaluate(e => { const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, height: r.height, scrollWidth: e.scrollWidth, clientWidth: e.clientWidth }; });
    expect(bounds.left).toBeGreaterThanOrEqual(0); expect(bounds.right).toBeLessThanOrEqual(width); expect(bounds.scrollWidth).toBeLessThanOrEqual(bounds.clientWidth + 1); expect(bounds.height).toBeLessThanOrEqual(900);
    await page.screenshot({ path: `${out}/source-dialog-${width}.png` }); await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: '管理来源', exact: true })).toBeFocused();
    observations.push({ ...measure, sourceDialog: bounds });
  }
  expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/responsive-controls-proof.json`, JSON.stringify({ widths, observations, company_display_only_fixture: true, business_sources_unchanged: true, before, after: await counts(page), native_chrome_200_percent: 'pending' }, null, 2));
});
test('legacy parser and rejected PDF bytes cannot acquire verified table or PDF presentation', async ({ page }) => {
  const before = await counts(page);
  const citations = saved.result.citations.map((c: any) => ({ ...c, parser_version: 'fast-pdf-v3;table-geometry-v1;fixture=1' }));
  await page.route(`**/api/research/runs/${saved.run_id}`, r => r.fulfill({ json: { ...saved, result: { ...saved.result, citations } } }));
  await page.goto(`/research?mode=qa&run=${saved.run_id}`);
  const answer = page.getByRole('region', { name: '有证据的回答' }); await expect(answer).toBeVisible();
  await expect(answer.getByRole('table')).toHaveCount(0); await expect(answer.getByText('表格列关系暂未通过核验', { exact: true })).toHaveCount(4);
  await page.unroute(`**/api/research/runs/${saved.run_id}`);
  await page.goto(`/research?mode=qa&run=${saved.run_id}`);
  const c = saved.result.citations[3];
  await page.route(`**/api/documents/${c.document_id}/file?*`, r => r.fulfill({ contentType: 'application/pdf', body: Buffer.from('%PDF-1.7 mismatched bytes') }));
  await page.locator(`[data-citation-number="${c.number}"]`).getByRole('button', { name: `查看原 PDF [${c.number}]`, exact: true }).click();
  const dialog = page.getByRole('dialog'); await expect(dialog.getByText('原 PDF 暂不可查看', { exact: true })).toBeVisible(); await expect(dialog.locator('canvas')).toHaveCount(0);
  expect(await counts(page)).toEqual(before);
  writeFileSync(`${out}/legacy-and-byte-denial-proof.json`, JSON.stringify({ legacy_parser_response_fixture: true, byte_response_fixture: true, structured_tables: 0, mismatched_pdf_pixels: 0, before, after: await counts(page) }, null, 2));
});
test('actual source correction withdraws open PDF pixels and historical entry without changing saved answer', async ({ page }) => {
  const c = saved.result.citations[0], d = docs.find(d => d.document_id === c.document_id);
  await page.goto(`/research?mode=qa&run=${saved.run_id}`);
  await page.locator(`[data-citation-number="${c.number}"]`).getByRole('button', { name: `查看原 PDF [${c.number}]`, exact: true }).click();
  const dialog = page.getByRole('dialog'); await expect(dialog.locator('canvas')).toBeVisible({ timeout: 30000 });
  const response = await page.request.post(`/api/documents/${c.document_id}/binding-corrections`, { data: { expected_attempt: d.attempt, metadata: { company_id: d.company_id, report_year: d.report_year, report_type: 'annual', basis: 'unknown', period_start: `${d.report_year}-01-01`, period_end: `${d.report_year}-12-31` }, reason: 'S4 isolated source invalidation test' } });
  expect(response.status()).toBe(200); await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(dialog.locator('canvas')).toHaveCount(0); await expect(dialog.getByText('原 PDF 暂不可查看', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator(`[data-citation-number="${c.number}"]`).getByRole('link')).toHaveCount(0);
  await page.reload(); await expect(page.getByText('来源已过期或绑定已纠错', { exact: true })).toBeVisible();
  await expect(page.locator(`[data-citation-number="${c.number}"]`).getByRole('button')).toHaveCount(0);
  const read = await (await page.request.get(`/api/research/runs/${saved.run_id}`)).json();
  expect(read.result).toEqual(saved.result); expect(read.integrity_sha256).toBe(saved.integrity_sha256);
  const denied = await page.request.get(`/api/documents/${c.document_id}/file?${new URLSearchParams({ company_id: c.company_id, source_revision: c.source_revision })}`);
  expect(denied.status()).toBe(409);
  writeFileSync(`${out}/source-expired-proof.json`, JSON.stringify({ actual_correction: true, cited_document: c.document_id, old_revision: c.source_revision, source_states: read.source_states, saved_result_unchanged: true, old_pdf_http_status: denied.status(), cached_pixels_removed: true }, null, 2));
});
