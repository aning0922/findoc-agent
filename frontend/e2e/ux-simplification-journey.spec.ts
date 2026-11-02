import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

const sources = JSON.parse(readFileSync(process.env.UX_SOURCE_FILE!, 'utf8'));
const out = process.env.UX_ARTIFACT_DIR!;
const metrics = ['revenue', 'net_profit_parent', 'operating_cash_flow'];
const names = ['营业收入', '归母净利润', '经营活动现金流量净额'];

test('真实 PDF 与隔离模拟接受：同页核对六项后明确继续研究', async ({ page }) => {
  test.setTimeout(600_000);
  await page.route('**/src/main.tsx*', route => route.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
  const companies = await (await page.request.get('/api/companies')).json();
  const company = (code: string) => companies.find((c: any) => c.security_code === code || c.security_code === (code === '000333' ? 'MIDEA' : 'GREE')).company_id;
  const uploads: any[] = [];
  for (const source of sources) {
    const code = source.id.startsWith('midea') ? '000333' : '000651';
    const year = Number(source.id.slice(-4));
    await page.goto(`/companies/${company(code)}/documents`);
    await page.getByRole('button', { name: '上传并绑定年报', exact: true }).click();
    await page.getByLabel('报告年度', { exact: true }).fill(String(year));
    await page.getByLabel('PDF 文件', { exact: true }).setInputFiles(source.absolute_path);
    await page.getByLabel('核对上传绑定', { exact: true }).check();
    const response = page.waitForResponse(r => r.url().endsWith('/api/report-documents') && r.request().method() === 'POST', { timeout: 180_000 });
    await page.getByRole('button', { name: '提交 PDF 并绑定', exact: true }).click();
    const upload = await (await response).json();
    await expect(page.getByRole('status').filter({ hasText: '上传与绑定已读回' })).toBeVisible({ timeout: 120_000 });
    const actual = await (await page.request.get(`/api/documents/${upload.document_id}/source?company_id=${company(code)}`)).json();
    expect(actual.content_sha256).toBe(source.sha256);
    uploads.push({ id: source.id, document_id: upload.document_id, sha256: actual.content_sha256 });
  }
  const doc = uploads.find(x => x.id.startsWith('midea') && x.id.endsWith('2025')).document_id;
  const writes: string[] = [], errors: string[] = [];
  page.on('request', r => { if (r.method() === 'POST') writes.push(r.url()); });
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await page.getByLabel('first 年报', { exact: true }).selectOption(doc);
  await page.getByRole('button', { name: '也用本期年报核对 2024 年', exact: true }).click();
  await page.getByRole('button', { name: '下一步：准备核对', exact: true }).click();
  for (const index of [0, 1]) await page.locator('.operating-side').nth(index).getByRole('button', { name: '采用这组三项来源', exact: true }).click();
  const create = page.getByRole('button', { name: '创建研究，开始核对数据', exact: true });
  await expect(create).toBeEnabled();
  const created = page.waitForResponse(r => r.url().endsWith('/api/research/tasks') && r.request().method() === 'POST', { timeout: 180_000 });
  await create.click();
  const task = await (await created).json();
  expect(task.status).toBe('awaiting_human_confirmation');
  const matrix = page.getByRole('region', { name: '六项事实准备状态' });
  await expect(matrix.locator('tbody tr')).toHaveCount(3);
  await expect(matrix.locator('[data-testid^="slot-"]')).toHaveCount(6);
  await expect(page).toHaveURL(new RegExp(`task=${task.task_id}`));
  const taskUrl = page.url();
  await page.screenshot({ path: `${out}/matrix-before-review.png`, fullPage: true });
  for (const [side, year] of [['second', 2024], ['first', 2025]] as const) {
    const cell = page.getByTestId(`slot-${side}:revenue`);
    await expect(cell.getByRole('button', { name: '核对原文' })).toBeEnabled({ timeout: 60_000 });
    await cell.getByRole('button', { name: '核对原文' }).click();
    const panel = page.getByRole('region', { name: '原位核对财报' });
    await expect(panel).toBeVisible();
    expect(page.url()).toBe(taskUrl);
    await panel.getByRole('button', { name: '开始新核对' }).click();
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 60_000 });
    if (side === 'second') {
      await page.setViewportSize({ width: 360, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden');
      const beforeMobileRecheck = writes.length;
      // Fault injection affects only the qualification GET. PDF bytes and business values remain real.
      await page.route('**/api/financial-facts?**', route => route.fulfill({ status: 503, json: { detail: 'temporarily_unavailable' } }));
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await expect(page.locator('[data-verification-state="unavailable"]')).toBeVisible({ timeout: 60_000 });
      await expect.poll(() => page.evaluate(() => document.body.style.overflow)).not.toBe('hidden');
      await expect(page.locator('.evidence-viewer:visible')).toHaveCount(0);
      await expect(page.locator('dialog:modal')).toHaveCount(0);
      expect(writes).toHaveLength(beforeMobileRecheck);
      await page.unroute('**/api/financial-facts?**');
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await expect(page.locator('[data-verification-state="current"]')).toBeVisible({ timeout: 60_000 });
      await expect(page.locator('.evidence-viewer:visible')).toHaveCount(1);
      await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden');
      expect(writes).toHaveLength(beforeMobileRecheck);
      await page.setViewportSize({ width: 1440, height: 900 });
      await expect.poll(() => page.evaluate(() => document.body.style.overflow)).not.toBe('hidden');
      await expect(page.locator('.research-review-viewer canvas').first()).toBeVisible({ timeout: 60_000 });
      await matrix.evaluate(el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 20));
      await page.screenshot({ path: `${out}/inline-review-viewport-1440.png` });
      const layout = await page.evaluate(() => {
        const cells = [...document.querySelectorAll('[data-testid^="slot-"]')].map(el => el.getBoundingClientRect());
        const pdf = document.querySelector('.research-review-viewer canvas')?.getBoundingClientRect();
        return { cells: cells.map(r => ({ top: r.top, bottom: r.bottom })), pdf: pdf && { top: pdf.top, bottom: pdf.bottom, left: pdf.left }, width: innerWidth, height: innerHeight };
      });
      expect(layout.cells).toHaveLength(6);
      expect(layout.cells.every(r => r.top >= 0 && r.bottom <= layout.height)).toBe(true);
      expect(layout.pdf && layout.pdf.top < layout.height && layout.pdf.bottom > 0).toBeTruthy();
    }
    await page.screenshot({ path: `${out}/inline-review-${year}.png`, fullPage: true });
    await panel.getByRole('button', { name: '开始本组核对' }).click();
    const firstCheck = panel.getByLabel(`已核对 ${year} 营业收入`, { exact: true });
    await firstCheck.check();
    await page.getByTestId(`slot-${side}:net_profit_parent`).getByRole('button', { name: '核对原文' }).click();
    await expect(firstCheck).toBeChecked();
    await page.getByTestId(`slot-${side}:revenue`).getByRole('button', { name: '核对原文' }).click();
    await expect(firstCheck).toBeChecked();
    for (const name of names) {
      const check = panel.getByLabel(`已核对 ${year} ${name}`, { exact: true });
      if (!(await check.isVisible())) await panel.locator('.candidate-item > summary').filter({ hasText: name }).click();
      await check.check();
    }
    await panel.getByRole('button', { name: '确认本组数据' }).click();
    const dialog = page.getByRole('dialog', { name: '人工核对确认' });
    await expect(dialog.locator('li')).toHaveCount(3);
    await dialog.getByRole('checkbox').check();
    if (side === 'second') {
      const beforeRecheck = writes.length;
      await page.route('**/api/financial-facts?**', route => route.fulfill({ status: 503, json: { detail: 'temporarily_unavailable' } }));
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await expect(page.locator('[data-verification-state="unavailable"]')).toBeVisible({ timeout: 60_000 });
      await expect(page.locator('dialog:modal')).toHaveCount(0);
      expect(writes.length).toBe(beforeRecheck);
      await page.unroute('**/api/financial-facts?**');
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await expect(page.locator('[data-verification-state="current"]')).toBeVisible({ timeout: 60_000 });
      await expect(firstCheck).toBeChecked();
      await panel.getByRole('button', { name: '确认本组数据' }).click();
      await expect(dialog.getByRole('checkbox')).not.toBeChecked();
      await dialog.getByRole('checkbox').check();
    }
    await dialog.getByRole('button', { name: '我已核对并接受' }).click();
    await expect(panel.getByTestId('acceptance-result')).toContainText('数据尚未保存');
    const beforeSave = writes.filter(x => x.endsWith('/financial-facts/persisted')).length;
    if (side === 'second') await page.route('**/api/financial-facts/persisted', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      await route.abort('failed');
    });
    await panel.getByRole('button', { name: '保存已接受数据' }).click();
    if (side === 'second') {
      await expect(panel.getByTestId('fact-result')).toContainText('事实操作结果未知');
      await page.unroute('**/api/financial-facts/persisted');
      await panel.getByRole('button', { name: '查证数据保存结果（只读）' }).click();
    }
    await expect(panel.getByTestId('fact-result')).toContainText('保存成功并已重新查询');
    expect(writes.filter(x => x.endsWith('/financial-facts/persisted'))).toHaveLength(beforeSave + 1);
    await panel.getByRole('button', { name: '完成并刷新核对状态' }).click();
    await expect(cell).toContainText('已保存', { timeout: 60_000 });
    expect(page.url()).toBe(taskUrl);
  }
  const facts = await (await page.request.get(`/api/financial-facts?company_id=${company('000333')}&include_invalid=true`)).json();
  for (const side of ['first', 'second']) for (const metric of metrics) {
    const fact = facts.facts.find((f: any) => f.current_valid && f.period === task.active_input[side].period.year && f.metric_key === metric && f.document_id === doc);
    expect(fact).toBeTruthy();
    await expect(page.getByTestId(`slot-${side}:${metric}`)).toContainText(`${fact.raw_value} ${fact.raw_unit}`);
  }
  expect(writes.filter(x => x.endsWith('/resume'))).toHaveLength(0);
  const resume = page.getByRole('button', { name: '复核并继续研究', exact: true });
  await expect(resume).toBeEnabled();
  const resumed = page.waitForResponse(r => r.url().endsWith(`/api/research/tasks/${task.task_id}/resume`) && r.request().method() === 'POST', { timeout: 180_000 });
  await resume.click();
  const result = await (await resumed).json();
  expect(result.status).toBe('completed');
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible({ timeout: 60_000 });
  const countBeforeReload = writes.length;
  await page.reload();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible({ timeout: 60_000 });
  expect(writes).toHaveLength(countBeforeReload);
  const trigger_counts = { accept: writes.filter(x => x.endsWith('/financial-facts/confirmations')).length, persist: writes.filter(x => x.endsWith('/financial-facts/persisted')).length, resume: writes.filter(x => x.endsWith(`/tasks/${task.task_id}/resume`)).length };
  expect(trigger_counts).toEqual({ accept: 2, persist: 2, resume: 1 });
  expect(errors).toEqual([]);
  writeFileSync(`${out}/journey-proof.json`, JSON.stringify({ task, result, writes, trigger_counts, uploads, reload_zero_writes: true, same_page_review: true, same_group_checks_preserved: true, paused_mobile_scroll_lock_released: true, modal_pause_resets_consent: true, qualification_get_503_injected: true, lost_save_response_get_recovery: true, simulated_test: true, fake_model_and_index: true, human_acceptances: 0, errors }, null, 2));
});
