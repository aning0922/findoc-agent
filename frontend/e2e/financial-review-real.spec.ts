// Every accept is an explicit automated simulation in a fresh, simulated_test server.
// No test invokes human acceptance or touches a production root.
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { generateReview, openCandidate, returnToReview } from './financial-review-helpers.ts'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const stage = process.env.FINDOC_E2E_STAGE || 'd9'
const root = readFileSync(`../data/30d-foundation/${stage}-runtime-path.txt`, 'utf8').trim()
const manifest = JSON.parse(readFileSync(`${root}/manifest.json`, 'utf8'))
const reports: { report_id: string; source: any }[] = manifest.reports
const gold = JSON.parse(readFileSync('../product/validation/manual-benchmark.json', 'utf8')).facts
const screenshots = resolve(`../product/validation/${stage}-screenshots`)
const observations: any[] = []
let browserVersion = ''
test.beforeAll(({ browser }) => { browserVersion = browser.version() })
test.afterAll(() => writeFileSync(stage === 'd9' ? '../product/validation/d9-browser-measurements.json' : `../product/validation/${stage}-review-browser-measurements.json`, JSON.stringify({ runtime: root, browserVersion, observations, human_acceptance: 'pending', automated_acceptance: 'simulated_test', substitutions: manifest.substitutions }, null, 2)))
function url(report = reports.find(r => r.report_id === 'midea-2025')!) { const s = report.source; return `/evidence?record=new&company=${s.company_id}&document=${s.document_id}&revision=${s.source_revision}` }
async function initial(page: Page, report?: typeof reports[number]) {
  await page.goto(url(report)); await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
}
async function generate(page: Page) { return generateReview(page) }
async function dialog(page: Page) {
  await returnToReview(page)
  await page.getByRole('button', { name: '确认本组数据' }).click()
  return page.getByRole('dialog', { name: '人工核对确认' })
}
const consent = '我已逐项核对原 PDF，并明确接受本次审阅内容'
for (const report of reports) {
  test(`D9 真实18条：${report.report_id} 动态审阅、逐处原PDF、模拟接受与只读恢复`, async ({ page }) => {
    const errors: string[] = []; page.on('pageerror', e => errors.push(e.message))
    await page.setViewportSize({ width: 1440, height: 900 }); await initial(page, report)
    const expected = gold.filter((r: any) => r.document_id === report.report_id)
    await page.getByLabel('财务年度', { exact: true }).fill([...new Set(expected.map((r: any) => r.period))].join(','))
    const start = performance.now(); const review = await generate(page)
    expect(review.review_status).toBe('ready_for_acceptance')
    expect(review.candidates).toHaveLength(expected.length)
    const evidenceProofs: any[] = []
    for (const fact of expected) {
      const c = review.candidates.find((c: any) => c.period === fact.period && c.metric_key === fact.metric)
      expect(c.raw_value).toBe(fact.raw_value); expect(c.value_cny_yuan).toBe(fact.value_cny_yuan)
      const card = await openCandidate(page, c)
      await card.getByText('规范金额与单位换算', { exact: true }).click()
      await expect(card).toContainText(fact.value_cny_yuan)
      for (const [index, ref] of c.evidence.entries()) {
        if (!await page.getByLabel('切换引用', { exact: true }).isVisible()) await page.getByRole('button', { name: '查看原PDF', exact: true }).click()
        await page.getByLabel('切换引用', { exact: true }).selectOption(`${c.candidate_id}:${index}`)
        await expect(page.getByLabel('物理页码')).toHaveValue(String(ref.physical_page))
        await expect(page.locator('canvas')).toHaveAttribute('aria-label', `PDF 物理第 ${ref.physical_page} 页`)
        await expect(page.locator('.pdf-location')).toContainText('金额区域已核验')
        evidenceProofs.push({ candidate_id: c.candidate_id, evidence_id: ref.evidence_id, role: ref.role, physical_page: ref.physical_page })
      }
    }
    const c = review.candidates[0]
    if (!await page.getByLabel('切换引用', { exact: true }).isVisible()) await page.getByRole('button', { name: '查看原PDF', exact: true }).click()
    await page.getByLabel('切换引用', { exact: true }).selectOption(`${c.candidate_id}:basis:0`)
    await expect(page.locator('.pdf-location')).toContainText('仅物理页与片段定位')
    await expect(page.getByTestId('amount-highlight')).toHaveCount(0)
    await page.screenshot({ path: `${screenshots}/${report.report_id}-review.png`, fullPage: true })
    const d = await dialog(page)
    await expect(d.getByLabel(consent)).not.toBeChecked()
    await expect(d.getByRole('button', { name: '我已核对并接受' })).toBeDisabled()
    if (report.report_id === 'midea-2025') await page.screenshot({ path: `${screenshots}/acceptance-unchecked.png` })
    await d.getByLabel(consent).check() // Simulated acceptance, server uses simulated_test.
    await d.getByRole('button', { name: '我已核对并接受' }).click()
    await page.getByTestId('acceptance-result').locator(':scope > summary').click()
    await expect(page.getByTestId('acceptance-result')).toContainText('自动化模拟接受凭证', { timeout: 30_000 })
    await expect(page.getByTestId('acceptance-result')).toContainText('财务事实入库待完成')
    expect(errors).toEqual([])
    if (report.report_id === 'midea-2025') await page.screenshot({ path: `${screenshots}/simulated-acceptance-saved.png`, fullPage: true })
    observations.push({ report: report.report_id, snapshot_id: review.snapshot_id, candidates: review.candidates.length, evidenceProofs, review_and_accept_ms: performance.now()-start, errors })
  })
}
test('取消和返回修改零接受请求；弹窗重新打开默认未勾选；桌面和键盘', async ({ page }) => {
  let accepts = 0; page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/financial-facts/confirmations')) accepts++ })
  await initial(page); await generate(page)
  let d = await dialog(page); await d.getByLabel(consent).check(); await d.getByRole('button', { name: '取消审阅' }).click()
  expect(accepts).toBe(0); await expect(page.getByRole('button', { name: '确认本组数据' })).toBeFocused()
  d = await dialog(page); await expect(d.getByLabel(consent)).not.toBeChecked(); await page.keyboard.press('Escape')
  await dialog(page); await page.getByRole('button', { name: '返回修改', exact: true }).click()
  await expect(page.getByRole('button', { name: '确认本组数据' })).toHaveCount(0)
  expect(accepts).toBe(0)
  await generate(page)
  await page.getByRole('button', { name: '返回核对', exact: true }).first().click()
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `${screenshots}/review-${width}.png`, fullPage: true })
  }
  d = await dialog(page)
  await d.getByRole('button', { name: '取消审阅' }).focus(); await page.keyboard.press('Shift+Tab')
  await expect(d.getByLabel(consent)).toBeFocused()
  await page.keyboard.press('Escape')
})
test('未支持年度与冲突不能接受；修改年度和指标撤销旧资格', async ({ page }) => {
  await initial(page); await generate(page)
  await page.getByLabel('财务年度', { exact: true }).fill('1900')
  await expect(page.getByRole('button', { name: '确认本组数据' })).toHaveCount(0)
  const r = await generate(page); expect(r.review_status).toBe('blocked')
  await expect(page.getByRole('button', { name: '确认本组数据' })).toBeDisabled()
  await expect(page.getByTestId('review-candidate')).toHaveCount(3)
  const unsupported = await openCandidate(page, r.candidates[0])
  await unsupported.getByText('规范金额与单位换算', { exact: true }).click()
  await expect(unsupported).toContainText('无有效值')
  await page.screenshot({ path: `${screenshots}/unsupported-period.png` })
  await page.getByLabel('财务年度', { exact: true }).fill('2025')
  await page.getByLabel('营业收入', { exact: true }).uncheck()
  const selected = await generate(page); expect(selected.candidates).toHaveLength(2)
  await page.route('**/financial-facts/reviews', async route => {
    const response = await route.fetch(), data = await response.json()
    data.review_status = 'blocked'; data.candidates[0].status = 'conflict'; data.candidates[0].value_cny_yuan = null
    data.candidates[0].failure_reason = 'disclosure_value_conflict'
    await route.fulfill({ response, json: data }) // Explicit response fault injection.
  })
  await generate(page)
  await expect(page.getByRole('button', { name: '确认本组数据' })).toBeDisabled()
  await expect(await openCandidate(page, selected.candidates[0])).toContainText('冲突')
  await page.screenshot({ path: `${screenshots}/conflict-injected.png` })
})
test('迟到审阅响应在年度修改后丢弃', async ({ page }) => {
  await initial(page)
  let release!: () => void, seen!: () => void
  const gate = new Promise<void>(resolve => { release = resolve }), started = new Promise<void>(resolve => { seen = resolve })
  await page.route('**/financial-facts/reviews', async route => { const r = await route.fetch(); seen(); await gate; try { await route.fulfill({ response: r }) } catch {} })
  await page.getByRole('button', { name: '开始本组核对' }).click(); await started
  await page.getByLabel('财务年度', { exact: true }).fill('2024'); release()
  await expect(page.getByRole('button', { name: '确认本组数据' })).toHaveCount(0)
  await expect(page.locator('.pending-notice')).toContainText('旧核对资格已清除')
})
test('双击防重，切企业后迟到接受响应不能显示旧成功', async ({ page }) => {
  await initial(page); await generate(page); const d = await dialog(page); await d.getByLabel(consent).check()
  let posts = 0, release!: () => void, seen!: () => void
  const gate = new Promise<void>(resolve => { release = resolve }), started = new Promise<void>(resolve => { seen = resolve })
  await page.route('**/financial-facts/confirmations', async route => { posts++; const r = await route.fetch(); seen(); await gate; try { await route.fulfill({ response: r }) } catch {} })
  await d.getByRole('button', { name: '我已核对并接受' }).dblclick({ force: true }); await started
  expect(posts).toBe(1)
  await d.getByRole('button', { name: '停止等待' }).click()
  const other = reports.find(r => r.report_id === 'gree-2025')!
  await page.getByLabel('企业', { exact: true }).selectOption(other.source.company_id)
  release(); await expect(page.getByTestId('acceptance-result')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '确认本组数据' })).toHaveCount(0)
})
test('保存后丢失响应为结果未知；刷新只恢复GET查询，无自动接受', async ({ page }) => {
  await initial(page); await page.getByLabel('财务年度', { exact: true }).fill('2024,2025'); await generate(page); const d = await dialog(page); await d.getByLabel(consent).check()
  let posts = 0, gets = 0
  page.on('request', r => { if (r.method() === 'GET' && r.url().includes('/financial-facts/confirmations/')) gets++ })
  await page.route('**/financial-facts/confirmations', async route => { posts++; await route.fetch(); await route.abort('failed') })
  await d.getByRole('button', { name: '我已核对并接受' }).click()
  await expect(d).toContainText('接受结果未知')
  await d.getByRole('button', { name: '返回查看结果' }).click()
  await expect(page.getByTestId('acceptance-result')).toHaveCount(0)
  await page.screenshot({ path: `${screenshots}/result-unknown.png` })
  let reviewPosts = 0
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/financial-facts/reviews')) reviewPosts++ })
  await page.reload()
  await page.getByTestId('acceptance-result').locator(':scope > summary').click()
  await expect(page.getByLabel('财务年度', { exact: true })).toHaveValue('2024,2025')
  await expect(page.getByTestId('acceptance-result')).toContainText('接受已保存', { timeout: 30_000 })
  expect(posts).toBe(1); expect(gets).toBe(1); expect(reviewPosts).toBe(0)
})
test('来源纠错后审阅和已存接受资格失效', async ({ page }) => {
  const report = reports.find(r => r.report_id === 'gree-2024')!
  await initial(page, report); await generate(page)
  const d = await dialog(page); await d.getByLabel(consent).check(); await d.getByRole('button', { name: '我已核对并接受' }).click()
  await expect(page.getByTestId('acceptance-result')).toBeVisible({ timeout: 30_000 })
  if (stage === 'd10') {
    await page.getByRole('button', { name: '保存已接受数据' }).click()
    await expect(page.getByTestId('fact-result')).toContainText('已确认财务事实', { timeout: 30_000 })
  }
  const s = report.source
  const r = await page.request.post(`/api/documents/${s.document_id}/binding-corrections`, { data: { expected_attempt: s.attempt,
    metadata: { company_id: s.company_id, report_year: s.report_year, report_type: s.report_type, period_start: s.period_start, period_end: s.period_end, basis: 'unknown' }, reason: 'D9 automated simulated correction in isolated runtime' } })
  expect(r.status()).toBe(200)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.locator('.source-failure')).toContainText('来源', { timeout: 15_000 })
  await expect(page.getByTestId('acceptance-result')).toHaveCount(0)
  await expect(page.getByTestId('fact-result')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '确认本组数据' })).toHaveCount(0)
  await page.screenshot({ path: `${screenshots}/source-corrected.png` })
})
