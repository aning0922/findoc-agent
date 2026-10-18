import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const out = process.env.D30_PUBLIC_OUT!;
for (const width of [1440, 1024, 390]) {
  test(`static historical journey and exact v1 download ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    const requests: string[] = [];
    page.on('request', r => requests.push(r.method()));
    await page.goto('/');
    await expect(page.locator('header')).toContainText('真实历史快照');
    await page.screenshot({ path: `${out}/public-home-${width}.png` });
    await page.locator('main').getByRole('link', { name: '读取真实历史成果', exact: true }).first().click();
    await expect(page.locator('main')).toContainText('12.11%');
    await expect(page.locator('main')).toContainText('14.03%');
    await expect(page.locator('main')).toContainText('-11.84%');
    await expect(page.locator('main')).toContainText('外部人工审阅 · 同意改写');
    await expect(page.locator('main')).toContainText('外部人工审阅 · 接受原句');
    await page.screenshot({ path: `${out}/public-midea-${width}.png` });
    await page.getByRole('link', { name: '可信问答 A10', exact: true }).click();
    await expect(page.getByRole('region', { name: '本题可信焦点' })).toContainText('456,451,731 千元');
    await page.screenshot({ path: `${out}/public-focus-${width}.png` });
    await page.getByText('审阅原话与适用范围', { exact: true }).click();
    const evidence = await page.request.get('/review-D28-A10.json');
    const record = await evidence.json();
    expect(record.copy_kind).toBe('reviewed_projection');
    expect(record.record.run_id).toBe('d1474a54-eeee-4d1d-82c0-d8800b0daf81');
    await expect(page.getByRole('link', { name: '本地公开证据摘录', exact: true })).toBeVisible();
    await page.getByRole('link', { name: '报告 v2', exact: true }).click();
    await expect(page.locator('main')).toContainText('trusted-markdown-v1');
    await page.getByRole('link', { name: '版本对照', exact: true }).first().click();
    await expect(page.locator('main')).toContainText('原财务与冻结研究内容保持不变');
    await page.screenshot({ path: `${out}/public-compare-${width}.png` });
    await page.getByRole('link', { name: '读取 v1 和指定下载', exact: true }).click();
    for (let i = 0; i < 2; i++) {
      const pending = page.waitForEvent('download');
      await page.getByRole('link', { name: '精确下载历史 v1 Markdown', exact: true }).click();
      const download = await pending;
      expect(createHash('sha256').update(readFileSync((await download.path())!)).digest('hex'))
        .toBe('28ddda7dc495e3396a387ff966d9c56a99679084de8841d9eb57d940fd61b9d0');
    }
    await page.screenshot({ path: `${out}/public-v1-${width}.png` });
    await page.getByRole('link', { name: '未知恢复说明', exact: true }).click();
    await expect(page.locator('main')).toContainText('不得自动重发 POST');
    expect(requests.every(m => m === 'GET')).toBeTruthy();
    expect(await page.locator('script,form,input,iframe').count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}
