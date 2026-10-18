import { expect, type Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'

// This extends the actual UI journey. The QA run remains an independent object;
// return_task is navigation only, and no QA answer becomes a report fact.
export async function verifyIntegratedQA(page: Page, task: any, out: string) {
  const reportURL = page.url()
  const before = await (await page.request.get('/api/__test__/d26-counts')).json()
  const writes: { url: string; body: any }[] = []
  const listener = (r: any) => { if (r.method() === 'POST') writes.push({ url: r.url(), body: r.postDataJSON() }) }
  page.on('request', listener)
  await page.goto(`/research?mode=qa&return_task=${task.task_id}`)
  await page.getByRole('button', { name: '管理来源', exact: true }).click()
  const chooser = page.getByRole('dialog', { name: '选择问答资料', exact: true })
  await expect(chooser.locator('[data-document-id]').getByRole('checkbox')).toHaveCount(4)
  for (const box of await chooser.locator('[data-document-id]').getByRole('checkbox').all()) await box.check()
  await chooser.getByRole('button', { name: '完成资料选择', exact: true }).click()
  const query = '请列四份年报主要会计数据和财务指标原文，不计算同比。'
  await page.getByLabel('研究问题', { exact: true }).fill(query)
  const response = page.waitForResponse(r => r.url().endsWith('/api/research/runs') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '查找原文', exact: true }).dblclick()
  const r = await response
  expect(r.status()).toBe(200)
  const run = await r.json()
  expect(run.status).toBe('answered')
  expect(run.query).toBe(query)
  expect(run.document_ids).toHaveLength(4)
  await expect(page).toHaveURL(new RegExp(`run=${run.run_id}`))
  await expect(page.getByLabel('原问题', { exact: true })).toHaveText(query)
  const answer = page.getByRole('region', { name: '有证据的回答', exact: true })
  await expect(answer).toBeVisible()
  await expect(answer.locator('[data-citation-number]')).toHaveCount(run.result.citations.length)
  for (const cite of run.result.citations) {
    const section = answer.locator(`[data-citation-number="${cite.number}"]`)
    await expect(section).toHaveAttribute('data-document-id', cite.document_id)
    await expect(section).toHaveAttribute('data-source-revision', cite.source_revision)
    await expect(section.locator('[data-saved-excerpt]')).toHaveText(cite.text)
  }
  await page.screenshot({ path: `${out}/s6-integrated-qa.png`, fullPage: true })
  await answer.getByRole('button', { name: /查看原 PDF/ }).first().click()
  const pdf = page.getByRole('dialog', { name: /原 PDF/ })
  await expect(pdf.locator('canvas')).toBeVisible({ timeout: 30000 })
  await page.screenshot({ path: `${out}/s6-integrated-qa-pdf.png` })
  await page.keyboard.press('Escape')
  await page.reload()
  await expect(page.getByLabel('原问题', { exact: true })).toHaveText(query)
  expect(writes).toHaveLength(1)
  expect(writes[0].url).toMatch(/\/research\/runs$/)
  expect(writes[0].body.document_ids).toEqual(run.document_ids)
  await page.goto(reportURL)
  await expect(page.getByLabel('选择已完成研究')).toHaveValue(task.task_id)
  expect(writes).toHaveLength(1)
  const after = await (await page.request.get('/api/__test__/d26-counts')).json()
  expect(after.calls.model - before.calls.model).toBe(1)
  expect(after.calls.retrieval - before.calls.retrieval).toBe(1)
  expect(after.tables.research_runs - before.tables.research_runs).toBe(1)
  expect(after.tables.template_tasks).toBe(before.tables.template_tasks)
  writeFileSync(`${out}/s6-integrated-qa-proof.json`, JSON.stringify({ before, after, task_id: task.task_id, run, writes, independent_run: true, refresh_zero_writes: true, human_acceptances: 0, simulated_test: true }, null, 2))
  page.off('request', listener)
}
