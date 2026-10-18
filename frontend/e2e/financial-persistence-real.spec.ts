// Only the isolated server labeled simulated_test is used. No human consent is asserted.
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { generateReview, returnToReview } from './financial-review-helpers.ts'
import { readFileSync, writeFileSync } from 'node:fs'
const root = readFileSync('../data/30d-foundation/d10-runtime-path.txt', 'utf8').trim()
const reports: { report_id: string; source: any }[] = JSON.parse(readFileSync(`${root}/manifest.json`, 'utf8')).reports
const gold = JSON.parse(readFileSync('../product/validation/manual-benchmark.json', 'utf8')).facts
const observations: any[] = []
test.afterAll(() => writeFileSync(process.env.FINDOC_D10_MEASUREMENTS_FILE || '../product/validation/d10-facts-browser-measurements.json', JSON.stringify({ runtime: root, observations, human_acceptance: 'pending', automated_acceptance: 'simulated_test' }, null, 2)))
async function ready(page: Page, report = reports.find(r => r.report_id === 'midea-2025')!, periods?: number[]) {
  const s = report.source
  await page.goto(`/evidence?record=new&company=${s.company_id}&document=${s.document_id}&revision=${s.source_revision}`)
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
  if (periods) await page.getByLabel('财务年度', { exact: true }).fill(periods.join(','))
  const review = await generateReview(page)
  await page.getByRole('button', { name: '确认本组数据' }).click()
  const d = page.getByRole('dialog', { name: '人工核对确认' })
  await d.getByLabel('我已逐项核对原 PDF，并明确接受本次审阅内容').check()
  const received = page.waitForResponse(r => r.url().endsWith('/financial-facts/confirmations') && r.request().method() === 'POST')
  await d.getByRole('button', { name: '我已核对并接受' }).click()
  const receipt = await (await received).json()
  await page.getByTestId('acceptance-result').locator(':scope > summary').click()
  await expect(page.getByTestId('acceptance-result')).toContainText('自动化模拟接受凭证', { timeout: 30_000 })
  await expect(page.getByTestId('fact-result')).toContainText('本组数据待保存，保存后可用于研究')
  await expect(page.getByText('已确认财务事实', { exact: true })).toHaveCount(0)
  return { review, receipt }
}
for (const report of reports) {
  test(`D10 ${report.report_id} 原PDF→模拟接受→整组事实→GET一致与证据联动`, async ({ page }) => {
    const rows = gold.filter((r: any) => r.document_id === report.report_id)
    const { receipt } = await ready(page, report, [...new Set<number>(rows.map((r: any) => r.period))])
    const created = page.waitForResponse(r => r.url().endsWith('/financial-facts/persisted') && r.request().method() === 'POST')
    const read = page.waitForResponse(r => r.url().includes(`/financial-facts/persisted/${receipt.receipt_id}`) && r.request().method() === 'GET')
    await page.getByRole('button', { name: '保存已接受数据' }).click()
    const post = await created, get = await read
    expect(post.status()).toBe(200); expect(get.status()).toBe(200)
    const facts = await post.json(); expect(await get.json()).toEqual(facts)
    expect(facts.facts).toHaveLength(rows.length)
    expect(facts.confirmation_kind).toBe('simulated_test'); expect(facts.production_calculable).toBe(false)
    for (const expected of rows) {
      const f = facts.facts.find((f: any) => f.metric_key === expected.metric && f.period === expected.period)
      expect(f.value_cny_yuan).toBe(expected.value_cny_yuan); expect(f.raw_value).toBe(expected.raw_value)
      expect(f.raw_unit).toBe(expected.raw_unit); expect(f.confirmation_status).toBe('confirmed')
      expect(f.evidence.length).toBeGreaterThan(0); expect(f.basis_evidence.length).toBeGreaterThan(0)
    }
    await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实 · 保存成功并已重新查询')
    const f = facts.facts[0], ref = f.evidence[0]
    if (!await page.getByLabel('切换引用', { exact: true }).isVisible()) await page.getByRole('button', { name: '查看原PDF', exact: true }).click()
    await page.getByLabel('切换引用', { exact: true }).selectOption(`${f.candidate_id}:0`)
    await expect(page.getByLabel('物理页码')).toHaveValue(String(ref.physical_page))
    await expect(page.locator('.pdf-location')).toContainText('金额区域已核验')
    for (const width of [1440, 1280, 1024]) {
      await page.setViewportSize({ width, height: 900 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
    await page.setViewportSize({ width: 1440, height: 900 })
    if (!await page.getByLabel('切换引用', { exact: true }).isVisible()) {
      await returnToReview(page)
      await page.getByRole('button', { name: '查看原PDF', exact: true }).click()
    }
    await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
    await expect(page.locator('canvas')).toHaveAttribute('aria-label', `PDF 物理第 ${ref.physical_page} 页`)
    await page.screenshot({ path: `../product/validation/d10-screenshots/${report.report_id}-facts.png`, fullPage: true })
    observations.push({ report: report.report_id, receipt_id: receipt.receipt_id, fact_set_id: facts.fact_set_id, disclosure_version: facts.disclosure_version, count: facts.facts.length, values: facts.facts.map((f: any) => ({metric: f.metric_key, period: f.period, value: f.value_cny_yuan})), evidence_id: ref.evidence_id, physical_page: ref.physical_page })
  })
}
test('事实响应丢失：刷新仅恢复已知ID的GET，不自动重复保存', async ({ page }) => {
  const { receipt } = await ready(page)
  let posts = 0, gets = 0
  page.on('request', r => { if (r.method() === 'GET' && r.url().includes('/financial-facts/persisted/')) gets++ })
  await page.route('**/financial-facts/persisted', async route => { posts++; await route.fetch(); await route.abort('failed') })
  await page.getByRole('button', { name: '保存已接受数据' }).click()
  await expect(page.getByTestId('fact-result')).toContainText('事实操作结果未知')
  await expect(page.getByRole('button', { name: '保存已接受数据' })).toHaveCount(0)
  await page.screenshot({ path: '../product/validation/d10-screenshots/facts-unknown.png' })
  let reviewPosts = 0
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/financial-facts/reviews')) reviewPosts++ })
  await page.reload()
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实', { timeout: 30_000 })
  expect(posts).toBe(1); expect(gets).toBe(1); expect(reviewPosts).toBe(0)
  observations.push({ recovery: receipt.receipt_id, posts, gets, known_id_only: true })
})
test('事实POST成功但GET部分损坏：不显示成功，恢复仅GET', async ({ page }) => {
  await ready(page)
  await page.route('**/financial-facts/persisted/*', async route => {
    const response = await route.fetch(), data = await response.json()
    data.facts.pop(); await route.fulfill({ response, json: data })
  })
  await page.getByRole('button', { name: '保存已接受数据' }).click()
  await expect(page.getByTestId('fact-result')).toContainText('事实操作结果未知')
  await expect(page.getByTestId('fact-result')).not.toContainText('已确认财务事实')
  await page.unroute('**/financial-facts/persisted/*')
  await page.getByRole('button', { name: '查证数据保存结果（只读）' }).click()
  await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实')
})
test('确定保存失败和取消，不能把接受凭证显示为事实', async ({ page }) => {
  await ready(page)
  await page.route('**/financial-facts/persisted', route => route.fulfill({ status: 409, json: { detail: { code: 'confirmation_required' } } }))
  await page.getByRole('button', { name: '保存已接受数据' }).click()
  await expect(page.getByTestId('fact-result')).toContainText('财务事实保存失败')
  await expect(page.getByTestId('fact-result')).not.toContainText('已确认财务事实')
  await page.screenshot({ path: '../product/validation/d10-screenshots/facts-failed.png' })
})

test('双击只保存一次；切企业后迟到事实响应不显示旧成功', async ({ page }) => {
  await ready(page)
  let posts = 0, release!: () => void, seen!: () => void
  const gate = new Promise<void>(resolve => { release = resolve }), started = new Promise<void>(resolve => { seen = resolve })
  await page.route('**/financial-facts/persisted', async route => { posts++; const response = await route.fetch(); seen(); await gate; try { await route.fulfill({ response }) } catch {} })
  await page.getByRole('button', { name: '保存已接受数据' }).dblclick({ force: true }); await started
  expect(posts).toBe(1)
  await page.getByRole('button', { name: '停止等待事实保存' }).click()
  const other = reports.find(r => r.report_id === 'gree-2025')!
  await page.getByLabel('企业', { exact: true }).selectOption(other.source.company_id)
  release()
  await expect(page.getByTestId('fact-result')).toHaveCount(0)
  await expect(page.getByTestId('acceptance-result')).toHaveCount(0)
})
