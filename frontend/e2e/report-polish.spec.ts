import { test, expect } from '@playwright/test';
import { randomUUID, createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { before, out, widths, setupPolish, withinPage } from './polish-helpers.ts';
const sha = (v: string | Buffer) => createHash('sha256').update(v).digest('hex');
test('Report P1 original excerpt, annual table, frozen revisions and exact Markdown remain identical', async ({ page }) => {
  const task = await setupPolish(page);
  const saved = await page.request.post('/api/reports', { data: { operation_id: randomUUID(), task_id: task.task_id, expected_task_revision: task.revision, edits: { title: '经营原文阅读补丁 · v1', conclusions: [] } } });
  expect(saved.ok(), await saved.text()).toBe(true); const v1 = await saved.json();
  const append = await page.request.post(`/api/reports/${v1.report.report_id}/revisions`, { data: { operation_id: randomUUID(), task_id: task.task_id, expected_task_revision: task.revision, expected_report_revision: 1, edits: { title: '经营原文阅读补丁 · v2', conclusions: ['用户新增断言仍待人工语义审阅。'] } } });
  expect(append.ok(), await append.text()).toBe(true);
  const detail = `/api/reports/${v1.report.report_id}/revisions/1`, exportUrl = `${detail}/markdown`;
  const snapshotBefore = await (await page.request.get(detail)).json(); const markdownBefore = await (await page.request.get(exportUrl)).body();
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.goto(`/reports?report=${v1.report.report_id}&revision=1`);
  const report = page.getByRole('article', { name: '已保存报告版本', exact: true }); await expect(report).toBeVisible();
  const section = report.locator('section').filter({ has: page.getByRole('heading', { name: /04.*经营原文与来源/ }) }).first();
  const raw = v1.report.trusted_snapshot.operating_information[0].text;
  await expect(section).toContainText('物理');
  if (!before) {
    await expect(section.getByRole('table', { name: '来源原文表格', exact: true })).toHaveCount(1);
    await expect(section.getByRole('table')).toContainText('2025年'); await expect(section.getByRole('table')).toContainText('2024年');
    await expect(section).toContainText('表格导航视图');
    await expect(section.locator('[data-saved-excerpt]')).toHaveCount(1);
    await expect(section.locator('[data-saved-excerpt]')).toBeHidden();
  }
  const measures = [];
  for (const width of widths) {
    await page.setViewportSize({ width, height: width === 390 ? 450 : 900 });
    await page.getByRole('navigation', { name: '报告正文目录' }).getByRole('button', { name: /04.*经营原文与来源/ }).click();
    await withinPage(page); measures.push({ width, height: await section.evaluate(el => el.getBoundingClientRect().height) });
    await page.screenshot({ path: `${out}/report-original-${width}.png` });
    if (width === 1440 || width === 390) await section.screenshot({ path: `${out}/report-section04-${width}.png` });
  }
  if (!before) {
    await section.getByText('完整已保存原文 [1] · 含口径、周边文字与重复内容', { exact: true }).click();
    expect(await section.locator('[data-saved-excerpt="1"]').textContent()).toBe(raw);
    await expect(section).toContainText('境内会计师事务所名称');
    await section.getByText('完整已保存原文 [1] · 含口径、周边文字与重复内容', { exact: true }).click();
  }
  const pdfButton = section.getByRole('button', { name: '打开经营原文 PDF', exact: true }).first();
  await pdfButton.click(); const pdf = page.getByRole('dialog', { name: /原 PDF/ }); await expect(pdf.locator('canvas')).toBeVisible({ timeout: 30000 });
  await page.keyboard.press('Escape'); await expect(pdfButton).toBeFocused();
  const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: '下载 v1 · Markdown', exact: true }).click();
  const download = await downloadEvent; await download.saveAs(`${out}/frozen-v1.md`);
  const markdownAfter = await (await page.request.get(exportUrl)).body(); expect(markdownAfter).toEqual(markdownBefore);
  expect(await (await page.request.get(detail)).json()).toEqual(snapshotBefore);
  expect(writes).toEqual([]);
  writeFileSync(`${out}/report-reading-proof.json`, JSON.stringify({ before, measures, reportId: v1.report.report_id, payloadSHA: v1.payload_sha256, originalTextSHA: sha(raw), markdownSHA: sha(markdownAfter), frozenRevisionUnchanged: true, writes, simulated_test: true }, null, 2));
});
test('Report P1 ambiguous, legacy and prose excerpts keep complete text and never guess table cells', async ({ page }) => {
  const task = await setupPolish(page);
  const response = await page.request.post('/api/reports', { data: { operation_id: randomUUID(), task_id: task.task_id, expected_task_revision: task.revision, edits: { title: '完整原文回退检查', conclusions: [] } } });
  expect(response.ok()).toBe(true); const saved = await response.json();
  const endpoint = `**/api/reports/${saved.report.report_id}/revisions/1`;
  const raw = saved.report.trusted_snapshot.operating_information[0].text;
  const cases = [
    { name: 'legacy', text: raw, parser: 'fast-pdf-v3;table-geometry-v1;', literal: true },
    { name: 'malformed', text: '单位：千元\n|项目|2025年|2024年|\n|---|---|---|\n|营业收入|100|90|\n|缺失列|10|\n<script>shouldNotRun()</script>', parser: 'fast-pdf-v4;table-geometry-v2;test=1', literal: true },
    { name: 'prose', text: '真实经营段落一。\n\n真实经营段落二，完整保留限定语。', parser: 'fast-pdf-v4;table-geometry-v2;test=1', literal: false },
  ];
  const writes: string[] = []; page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  for (const item of cases) {
    // Explicit HTTP presentation fixture only; the saved report/bytes in SQLite are never edited.
    await page.route(endpoint, async route => {
      const r = await route.fetch(), data = await r.json();
      const d = data.report.trusted_snapshot.operating_information[0]; d.text = d.citation.text = item.text; d.citation.parser_version = item.parser;
      await route.fulfill({ response: r, json: data });
    });
    await page.goto(`/reports?report=${saved.report.report_id}&revision=1`);
    const excerpt = page.locator('.report-excerpt').first(); await expect(excerpt).toBeVisible();
    await expect(excerpt.locator('table')).toHaveCount(0);
    await excerpt.locator('.report-complete-excerpt > summary').click();
    await expect(excerpt).toContainText(item.literal ? '按原样' : '段落');
    expect(await excerpt.locator('.report-complete-excerpt > div').textContent()).toBe(item.text);
    await expect(excerpt.locator('script')).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 450 }); await withinPage(page);
    await page.screenshot({ path: `${out}/report-fallback-${item.name}-390.png` });
    await page.unroute(endpoint);
  }
  const unchanged = await (await page.request.get(`/api/reports/${saved.report.report_id}/revisions/1`)).json();
  expect(unchanged.report.trusted_snapshot).toEqual(saved.report.trusted_snapshot); expect(writes).toEqual([]);
  writeFileSync(`${out}/report-fallback-proof.json`, JSON.stringify({ cases: cases.map(c => ({ name: c.name, literal: c.literal, textSHA: sha(c.text) })), presentationFixtureOnly: true, backendSnapshotUnchanged: true, writes, simulated_test: true }, null, 2));
});
