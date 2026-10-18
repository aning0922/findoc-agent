import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const stage = process.env.FINDOC_EVIDENCE_STAGE || 'd8'
const root = readFileSync(`../data/30d-foundation/${stage}-runtime-path.txt`, 'utf8').trim()
const report = JSON.parse(readFileSync(`${root}/manifest.json`, 'utf8')).reports.find((r: any) => r.report_id === 'midea-2025')
const source = report.source
const url = `/evidence?company=${source.company_id}&document=${source.document_id}&revision=${source.source_revision}`
test('并发复现：更换同表指标时，迟到证据不能覆盖新引用或保留旧高亮', async ({ page }) => {
  await page.goto(url)
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
  const options = await page.getByLabel('切换引用').locator('option:not([disabled])').evaluateAll(nodes => nodes.map(n => (n as HTMLOptionElement).value))
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let seen!: () => void
  const started = new Promise<void>(resolve => { seen = resolve })
  let first = true
  await page.route('**/evidence/**', async route => {
    if (!first) { await route.continue(); return }
    first = false
    const response = await route.fetch(); seen(); await gate
    try { await route.fulfill({ response }) } catch { /* aborted stale response */ }
  })
  await page.getByLabel('切换引用').selectOption(options[2]); await started
  await expect(page.getByTestId('amount-highlight')).toHaveCount(0)
  await page.getByLabel('切换引用').selectOption(options[5])
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验')
  release()
  await expect(page.getByLabel('切换引用')).toHaveValue(options[5])
  await expect(page.getByLabel('物理页码')).toHaveValue('137')
  await expect(page.getByTestId('amount-highlight')).toHaveAttribute('aria-label', '原文金额 53,345,930')
})
test('并发复现：缩放/翻页后立即撤掉上一个页面的画布', async ({ page }) => {
  await page.goto(url)
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
  await page.getByLabel('物理页码').fill('135'); await page.getByRole('button', { name: '跳转', exact: true }).click()
  await expect(page.locator('canvas')).toHaveAttribute('aria-label', 'PDF 物理第 135 页')
  for (const p of ['136', '137', '1', '135']) {
    await page.getByLabel('物理页码').fill(p); await page.getByRole('button', { name: '跳转', exact: true }).click()
    await expect(page.locator('canvas[aria-label]:visible')).not.toHaveAttribute('aria-label', 'PDF 物理第 9 页')
  }
})
test('定位复现：同一物理页滚离金额后，返回引用位置必须再次定位', async ({ page }) => {
  await page.goto(url)
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
  const reader = page.getByLabel('PDF 阅读区域')
  const original = await reader.evaluate(element => element.scrollTop)
  await reader.evaluate(element => { element.scrollTop = 0 })
  await page.getByRole('button', { name: '返回引用位置' }).click()
  await expect.poll(() => reader.evaluate(element => element.scrollTop)).toBeCloseTo(original, 0)
})
