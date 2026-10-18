import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

// Invoked inside the guided journey, before source invalidation. Actual HTTP,
// SQLite, original PDF and browser downloads; consent/model remain simulated.
export async function verifyReportJourney(page: Page, task: any, out: string) {
  const posts: string[] = [];
  const listener = (r: any) => { if (r.method() === 'POST') posts.push(r.url()); };
  page.on('request', listener);
  await expect(page.getByRole('button', { name: '下载 v1 · Markdown', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '生成草稿', exact: true }).click();
  await expect(page.getByRole('article', { name: '报告草稿预览' })).toBeVisible();
  await expect(page.getByRole('button', { name: '下载 v1 · Markdown', exact: true })).toHaveCount(0);
  await page.getByLabel('用户结论 1（待人工语义审阅）').fill('集成 v1 用户断言，人工语义待审。');
  const saving = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/reports'));
  await page.getByRole('button', { name: '保存第 1 版', exact: true }).dblclick();
  const saved = await (await saving).json();
  expect(saved.report.revision).toBe(1);
  expect(saved.report.trusted_snapshot.task_id).toBe(task.task_id);
  await expect(page).toHaveURL(new RegExp(`report=${saved.report.report_id}&revision=1`));
  const article = page.getByRole('article', { name: '已保存报告版本' });
  await expect(article).toBeVisible();
  const savedV1Text = await article.innerText();
  await page.screenshot({ path: `${out}/saved-v1-status-observation.png` });
  await page.getByRole('button', { name: '编辑为新版本', exact: true }).click();
  await page.getByLabel('用户结论 1（待人工语义审阅）').fill('集成 v2 用户断言，不能出现在 v1 导出。');
  const appending = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/reports/${saved.report.report_id}/revisions`));
  await page.getByRole('button', { name: '保存为 v2', exact: true }).dblclick();
  const v2 = await (await appending).json();
  expect(v2.report.revision).toBe(2);
  await expect(article).toContainText('父版本 1');
  const savedV2Text = await article.innerText();
  writeFileSync(`${out}/saved-status-observation.json`, JSON.stringify({
    simulated_test: true, human_acceptances: 0,
    v1_saved: saved.report.revision === 1, v2_saved: v2.report.revision === 2,
    v1_still_says_unsaved: savedV1Text.includes('报告草稿尚未保存'),
    v2_still_says_unsaved: savedV2Text.includes('报告草稿尚未保存'),
    v1_text: savedV1Text, v2_text: savedV2Text,
  }, null, 2));
  await page.getByLabel('报告版本', { exact: true }).selectOption('1');
  await expect(article).toContainText('集成 v1 用户断言');
  await expect(page.getByLabel('报告标题')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '打开最新版本后编辑', exact: true })).toBeVisible();
  const before = posts.length;
  await page.reload(); await expect(article).toBeVisible();
  await expect(page.getByLabel('报告版本', { exact: true })).toHaveValue('1');
  const downloads: any[] = [];
  await page.evaluate(() => {
    (window as any).__s6ExportClicks = [];
    document.addEventListener('click', e => {
      const target = e.target as HTMLElement;
      (window as any).__s6ExportClicks.push({ text: target.closest('button, summary')?.textContent,
        x: e.clientX, y: e.clientY, width: innerWidth, dpr: devicePixelRatio });
    }, true);
  });
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    // Wait for the shell's matchMedia-driven React control as well as CSS.
    // Otherwise a breakpoint can insert the menu between dblclick's two clicks.
    if (width < 1100) await expect(page.getByRole('button', { name: '打开导航', exact: true })).toBeVisible();
    else await expect(page.getByRole('button', { name: '打开导航', exact: true })).toHaveCount(0);
    const controls = page.getByRole('region', { name: '报告 Markdown 导出' });
    await expect(controls.getByRole('button')).toContainText('下载 v1 · Markdown');
    const reading = page.waitForResponse(r => r.url().endsWith(`/reports/${saved.report.report_id}/revisions/1/markdown`));
    const downloading = page.waitForEvent('download');
    await controls.getByRole('button', { name: '下载 v1 · Markdown', exact: true }).dblclick();
    writeFileSync(`${out}/export-click-${width}.json`, JSON.stringify(await page.evaluate(() => ({ clicks: (window as any).__s6ExportClicks, url: location.href, width: innerWidth, dpr: devicePixelRatio })), null, 2));
    const response = await reading, download = await downloading;
    expect(response.status()).toBe(200);
    expect(await download.failure()).toBeNull();
    expect(download.suggestedFilename()).toContain(`-${saved.report.report_id}-v1.md`);
    const file = `${out}/guided-saved-v1-${width}.md`;
    await download.saveAs(file);
    const bytes = readFileSync(file), md = bytes.toString('utf8');
    const hash = createHash('sha256').update(bytes).digest('hex');
    expect(hash).toBe(response.headers()['x-markdown-sha256']);
    expect(response.headers()['x-report-payload-sha256']).toBe(saved.payload_sha256);
    expect(md).toContain('集成 v1 用户断言'); expect(md).not.toContain('集成 v2 用户断言');
    expect(md).toContain('simulated_test'); expect(md).toContain('pending_semantic_review');
    for (const f of saved.report.trusted_snapshot.financial_facts) {
      for (const key of ['raw_value', 'raw_unit', 'value_cny_yuan', 'receipt_id']) expect(md).toContain(f[key]);
    }
    const pdfLink = md.match(/\]\((\/api\/documents\/[^\n]+?)\)/)![1];
    const pdf = await page.request.get(pdfLink.split('#')[0]);
    expect(pdf.status()).toBe(200); expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: `${out}/guided-saved-v1-${width}.png` });
    downloads.push({ width, file, sha256: hash, payload_sha256: saved.payload_sha256, pdf_link_opened: true });
  }
  expect(posts.length).toBe(before);
  expect(posts.filter(url => url.endsWith('/api/reports'))).toHaveLength(1);
  expect(posts.filter(url => url.endsWith(`/reports/${saved.report.report_id}/revisions`))).toHaveLength(1);
  await page.getByText('已保存报告历史', { exact: true }).click();
  await expect(page.getByRole('region', { name: '已保存报告历史' })).toContainText('v2');
  writeFileSync(`${out}/guided-report-proof.json`, JSON.stringify({ task_id: task.task_id, saved, v2, posts, downloads, reload_and_exports_zero_posts: true, human_acceptance: 'pending', simulated_test: true }, null, 2));
  page.off('request', listener);
}
