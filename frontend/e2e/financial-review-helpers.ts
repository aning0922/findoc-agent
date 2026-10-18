import { expect, type Page } from '@playwright/test'

export const metricNames: Record<string, string> = {
  revenue: '营业收入', net_profit_parent: '归母净利润', operating_cash_flow: '经营活动现金流量净额',
}
export async function returnToReview(page: Page) {
  if (await page.locator('.candidate-panel').getAttribute('inert') !== null)
    await page.locator('.evidence-viewer').getByRole('button', { name: '返回核对', exact: true }).click()
}
export async function openCandidate(page: Page, candidate: { period: number; metric_key: string }) {
  await returnToReview(page)
  const summary = page.locator('.candidate-item > summary').filter({ hasText: new RegExp(`^${metricNames[candidate.metric_key]} · ${candidate.period} 年 ·`) })
  await expect(summary).toHaveCount(1)
  const card = summary.locator('..').getByTestId('review-candidate')
  if (!await card.isVisible()) await summary.click()
  await returnToReview(page)
  await expect(card).toBeVisible()
  return card
}
export async function generateReview(page: Page) {
  const newReview = page.getByRole('button', { name: '开始新核对', exact: true })
  if (await newReview.isVisible()) await newReview.click()
  await returnToReview(page)
  const start = page.getByRole('button', { name: '开始本组核对', exact: true })
  if (!await start.count()) {
    // An explicit scope edit clears an existing review; never invoke this for
    // an unknown acceptance/persistence operation (those use original-ID GET).
    const selected = page.locator('.review-selection input[type="checkbox"]:checked').first()
    const label = await selected.evaluate(e => e.closest('label')!.textContent!.trim())
    const sameMetric = page.getByLabel(label, { exact: true })
    await sameMetric.uncheck()
    await sameMetric.check()
  }
  const response = page.waitForResponse(r => r.url().endsWith('/financial-facts/reviews') && r.request().method() === 'POST')
  await start.click()
  const r = await response
  expect(r.status()).toBe(200)
  const review = await r.json()
  await expect(page.getByRole('button', { name: '确认本组数据', exact: true })).toBeAttached()
  if (review.review_status === 'ready_for_acceptance') {
    await expect(page.getByTestId('review-candidate').locator('input[type="checkbox"]')).toHaveCount(review.candidates.length)
    for (const candidate of review.candidates) {
      const card = await openCandidate(page, candidate)
      await card.getByRole('checkbox', { name: `已核对 ${candidate.period} ${metricNames[candidate.metric_key]}`, exact: true }).check()
    }
  }
  return review
}
