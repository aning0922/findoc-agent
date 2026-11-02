import { test, expect } from '@playwright/test';
import { writeFileSync } from 'node:fs';
const out = process.env.UX_ARTIFACT_DIR!;

test('首页只有开始、待办和最近完成，任务列表与导航在小屏可用且读取不执行', async ({ page }) => {
  const writes: string[] = [];
  page.on('request', r => { if (r.url().includes('/api/') && r.method() !== 'GET') writes.push(r.url()); });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('每一份研究，从可靠的依据开始');
  await expect(page.getByRole('region', { name: '需要继续的研究' })).toBeVisible();
  await expect(page.getByRole('region', { name: '最近完成' })).toBeVisible();
  await expect(page.getByRole('link', { name: '开始新研究', exact: false })).toHaveCount(1);
  await expect(page.locator('.topbar select')).toHaveCount(0);
  await expect(page.locator('.dashboard-list li').first()).toBeVisible();
  for (const width of [1440, 360]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: `${out}/dashboard-${width}.png`, fullPage: true });
  }
  await page.getByRole('button', { name: '打开导航', exact: true }).click();
  const menu = page.getByRole('dialog', { name: '产品导航菜单' });
  await expect(menu).toBeVisible(); await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '打开导航', exact: true })).toBeFocused();
  await page.getByRole('link', { name: '查看全部任务' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('研究任务');
  await page.getByRole('combobox', { name: '任务状态', exact: true }).selectOption('completed');
  await expect(page.locator('.dashboard-list li').first()).toContainText('已完成');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(writes).toEqual([]);
  writeFileSync(`${out}/dashboard-proof.json`, JSON.stringify({ widths: [1440, 360], writes, page_sections: 3, mobile_menu_focus_restored: true }, null, 2));
});
