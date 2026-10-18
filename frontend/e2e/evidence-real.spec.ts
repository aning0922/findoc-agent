import { expect, test } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const stage = process.env.FINDOC_EVIDENCE_STAGE || 'd8'
const root = readFileSync(`../data/30d-foundation/${stage}-runtime-path.txt`, 'utf8').trim()
const manifest = JSON.parse(readFileSync(`${root}/manifest.json`, 'utf8'))
const reports: Array<{ report_id: string; source: Record<string, any> }> = manifest.reports
const proof: any[] = []
let browserVersion = ''
test.beforeAll(({ browser }) => { browserVersion = browser.version() })
const screenshotDir = resolve(`../product/validation/${stage}-screenshots`)
test.afterAll(() => writeFileSync(`../product/validation/${stage}-browser-measurements.json`, JSON.stringify({ reports: proof, browser_version: browserVersion, runtime: root, boundaries: manifest.substitutions, actual_ai_research_e2e: false }, null, 2)))
function url(report: typeof reports[number]) {
  return `/evidence?company=${report.source.company_id}&document=${report.source.document_id}&revision=${report.source.source_revision}`
}
async function ready(page: any) {
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验', { timeout: 30_000 })
  await expect(page.locator('canvas')).toBeVisible()
  await expect(page.getByTestId('amount-highlight')).toBeVisible()
}
for (const report of reports) {
  test(`真实四报：${report.report_id}，PDF、三指标及全部引用`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    const files: string[] = [], errors: string[] = []
    page.on('request', r => { if (new URL(r.url()).pathname.endsWith('/file')) files.push(r.url()) })
    page.on('pageerror', e => errors.push(e.message))
    const start = performance.now()
    await page.goto(url(report))
    await ready(page)
    const firstReadyMs = performance.now() - start
    const selector = page.getByLabel('切换引用')
    const options = await selector.locator('option:not([disabled])').evaluateAll(nodes => nodes.map(n => ({ key: (n as HTMLOptionElement).value, text: n.textContent })))
    expect(options).toHaveLength(6)
    const values: any[] = []
    for (const option of options) {
      const begin = performance.now()
      await selector.selectOption(option.key)
      await ready(page)
      const box = await page.getByTestId('amount-highlight').boundingBox()
      const pageNo = await page.getByLabel('物理页码').inputValue()
      values.push({ text: option.text, physical_page: Number(pageNo), ready_ms: performance.now() - begin, highlight: box })
      if (option.text?.includes('合并') || option.text?.includes('报表')) {
        const metric = option.text.split(' · ')[0]
        // Scroll the workbench into the desktop viewport so lower-page amounts
        // and the excerpt are completely visible in the evidence screenshot.
        await page.locator('.evidence-layout').evaluate(element => window.scrollTo(0, element.getBoundingClientRect().top + window.scrollY - 12))
        await page.screenshot({ path: `${screenshotDir}/${report.report_id}-${metric}-statement-1440.png` })
        if (metric === '营业收入') {
          await page.getByLabel('缩放').selectOption('0.5'); await ready(page)
          await page.getByLabel('PDF 阅读区域').evaluate(element => { element.scrollTop = 0 })
          await page.screenshot({ path: `${screenshotDir}/${report.report_id}-physical-printed-page.png` })
          await page.getByLabel('缩放').selectOption('fit'); await ready(page)
        }
        await page.evaluate(() => window.scrollTo(0, 0))
      }
    }
    expect(files).toHaveLength(1)
    expect(errors).toEqual([])
    await page.screenshot({ path: `${screenshotDir}/${report.report_id}-1440.png` })
    proof.push({ report_id: report.report_id, source: report.source, first_ready_ms: firstReadyMs, file_downloads: files.length, references: values, page_errors: errors })
  })
}
test('物理页、翻页、适宽/缩放、引用返回、前进后退、刷新和桌面尺寸', async ({ page }) => {
  const report = reports.find(r => r.report_id === 'midea-2025')!
  let files = 0
  page.on('request', r => { if (new URL(r.url()).pathname.endsWith('/file')) files++ })
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.goto(url(report)); await ready(page)
  const referencePage = await page.getByLabel('物理页码').inputValue()
  await page.getByLabel('物理页码').fill('0'); await page.getByRole('button', { name: '跳转', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('请输入')
  await page.getByLabel('物理页码').fill('1'); await page.getByRole('button', { name: '跳转', exact: true }).click()
  await expect(page.locator('.pdf-location')).toContainText('自由阅读')
  await expect(page.getByTestId('amount-highlight')).toHaveCount(0)
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.getByLabel('物理页码')).toHaveValue('2')
  await page.getByRole('button', { name: '上一页', exact: true }).click()
  await expect(page.getByLabel('物理页码')).toHaveValue('1')
  await page.getByRole('button', { name: '返回引用位置' }).click(); await ready(page)
  await expect(page.getByLabel('物理页码')).toHaveValue(referencePage)
  await page.getByLabel('缩放').selectOption('1.5'); await ready(page)
  await page.screenshot({ path: `${screenshotDir}/midea-2025-zoom150-1280.png` })
  await page.getByLabel('缩放').selectOption('fit'); await ready(page)
  const options = await page.getByLabel('切换引用').locator('option:not([disabled])').evaluateAll(nodes => nodes.map(n => (n as HTMLOptionElement).value))
  await page.getByLabel('切换引用').selectOption(options[3]); await ready(page)
  await page.goBack(); await ready(page)
  await page.goForward(); await ready(page)
  await expect(page.getByLabel('切换引用')).toHaveValue(options[3])
  expect(files).toBe(1)
  await page.reload(); await ready(page)
  await expect(page.getByLabel('切换引用')).toHaveValue(options[3])
  expect(files).toBe(2)
  await page.screenshot({ path: `${screenshotDir}/midea-2025-1280.png` })
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    await ready(page)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `${screenshotDir}/responsive-${width}.png` })
  }
  await expect(page.getByRole('dialog')).toBeVisible()
  const last = page.getByLabel('PDF 阅读区域')
  await last.focus(); await page.keyboard.press('PageDown')
  await expect(page.getByLabel('物理页码')).toHaveValue('136')
  await page.keyboard.press('PageUp'); await ready(page)
  await page.keyboard.press('+'); await expect(page.getByLabel('缩放')).toHaveValue('1.25')
  await page.keyboard.press('0'); await expect(page.getByLabel('缩放')).toHaveValue('fit')
  await page.keyboard.press('Tab')
  await expect(page.locator('.evidence-excerpt summary')).toBeFocused()
  await page.getByRole('button', { name: '收起证据侧栏' }).focus()
  await page.keyboard.press('Shift+Tab'); await expect(page.locator('.evidence-footer summary')).toBeFocused()
  await page.keyboard.press('Tab'); await expect(page.getByRole('button', { name: '收起证据侧栏' })).toBeFocused()
  // The excerpt summary remains native keyboard reachable, and the drawer keeps
  // focus among its controls; Escape restores the caller.
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: '展开证据', exact: true }).click(); await ready(page)
  await page.getByRole('button', { name: '收起证据侧栏' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
test('真实无 bbox 的段落引用仍定位物理页与原文', async ({ page }) => {
  const report = reports.find(r => r.report_id === 'gree-2025')!
  const source = await (await page.request.get(`/api/documents/${report.source.document_id}/source?company_id=${report.source.company_id}&source_revision=${report.source.source_revision}`)).json()
  const id = source.evidence_ids[0]
  const e = await (await page.request.get(`/api/documents/${report.source.document_id}/evidence/${id}?company_id=${source.company_id}&source_revision=${source.source_revision}`)).json()
  await page.goto(`${url(report)}&evidence=${id}&page=${e.physical_page}`)
  await expect(page.locator('.pdf-location')).toContainText('仅物理页与片段定位', { timeout: 30_000 })
  await expect(page.getByTestId('amount-highlight')).toHaveCount(0)
  await expect(page.locator('.evidence-excerpt')).toContainText(e.text.slice(0, 50))
  await page.screenshot({ path: `${screenshotDir}/gree-2025-no-bbox.png` })
})
test('错企业、错文档、失效版本和错引用拒绝展示文件', async ({ page }) => {
  const report = reports[0]
  const other = reports.find(r => r.source.company_id !== report.source.company_id)!
  const cases = [
    url(report).replace(report.source.company_id, other.source.company_id),
    url(report).replace(report.source.document_id, 'nonexistent'),
    url(report).replace(report.source.source_revision, '0'.repeat(64)),
    `${url(report)}&evidence=forged`,
  ]
  for (const path of cases) {
    await page.goto(path)
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('canvas')).toHaveCount(0)
    await expect(page.getByTestId('amount-highlight')).toHaveCount(0)
  }
  await page.screenshot({ path: `${screenshotDir}/source-rejected.png` })
})
test('企业切换隔离迟到的真实候选响应', async ({ page }) => {
  const first = reports[0], next = reports.find(r => r.source.company_id !== first.source.company_id)!
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let seen!: () => void
  const intercepted = new Promise<void>(resolve => { seen = resolve })
  await page.route(`**/documents/${first.source.document_id}/financial-candidates?**`, async route => {
    const response = await route.fetch(); seen(); await gate
    try { await route.fulfill({ response }) } catch { /* request was correctly aborted */ }
  })
  await page.goto(url(first)); await intercepted
  await page.getByLabel('企业', { exact: true }).selectOption(next.source.company_id)
  await expect(page.locator('canvas')).toHaveCount(0)
  await page.getByLabel('年报文档').selectOption(next.source.document_id)
  await ready(page); release()
  await expect(page.locator('.candidate-panel')).toContainText(`${next.source.report_year} 年`)
  await expect(page.getByLabel('年报文档')).toHaveValue(next.source.document_id)
  await ready(page)
})
test('PDF 文件失败、篡改字节与损坏候选 bbox 失败闭合', async ({ page }) => {
  const report = reports.find(r => r.report_id === 'midea-2025')!
  await page.route('**/file?**', route => route.fulfill({ status: 503, body: 'unavailable' }))
  await page.goto(url(report)); await expect(page.getByRole('alert')).toContainText('PDF 加载失败')
  await expect(page.locator('canvas')).toHaveCount(0)
  await page.unroute('**/file?**')
  await page.route('**/file?**', route => route.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-forged-wrong-sha' }))
  await page.reload(); await expect(page.getByRole('alert')).toContainText('PDF 校验失败')
  await expect(page.locator('canvas')).toHaveCount(0)
  await page.unroute('**/file?**')
  await page.route('**/financial-candidates?**', async route => {
    const response = await route.fetch(), body = await response.json()
    // Fault injection only: unchanged real PDF + real API evidence; corrupt geometry
    // must never create a highlight. This is not a real extraction success claim.
    for (const c of body.candidates) for (const e of c.evidence) e.bbox = [10, 10, 100, 30]
    await route.fulfill({ response, json: body })
  })
  await page.reload()
  await expect(page.locator('.pdf-location')).toContainText('仅物理页与片段定位', { timeout: 30_000 })
  await expect(page.getByTestId('amount-highlight')).toHaveCount(0)
  await page.screenshot({ path: `${screenshotDir}/invalid-bbox-fallback.png` })
})

test('真实来源纠错使旧版本与旧证据拒绝；已开文件在复核时撤下', async ({ page }) => {
  const report = reports.find(r => r.report_id === 'gree-2024')!
  await page.goto(url(report)); await ready(page)
  const oldUrl = page.url()
  const response = await page.request.post(`/api/documents/${report.source.document_id}/binding-corrections`, {
    data: { expected_attempt: report.source.attempt, reason: 'D8 isolated browser source invalidation acceptance', metadata: {
      company_id: report.source.company_id, report_year: 2024, report_type: 'annual', basis: 'unknown', period_start: '2024-01-01', period_end: '2024-12-31',
    } },
  })
  expect(response.status()).toBe(200)
  const evidence = new URL(oldUrl).searchParams.get('evidence')!
  expect((await page.request.get(`/api/documents/${report.source.document_id}/evidence/${evidence}?company_id=${report.source.company_id}&source_revision=${report.source.source_revision}`)).status()).toBe(409)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('alert')).toContainText('来源', { timeout: 30_000 })
  await expect(page.locator('canvas')).toHaveCount(0)
  await page.reload(); await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('canvas')).toHaveCount(0)
  await page.screenshot({ path: `${screenshotDir}/source-changed-old-evidence.png` })
})
