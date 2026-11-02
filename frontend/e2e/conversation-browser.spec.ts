import { test, expect } from '@playwright/test'
import { createHash } from 'node:crypto'
import { writeFileSync } from 'node:fs'
import { counts, createConversation, out, seedSources, send } from './conversation-helpers.ts'

let documents: Record<string, string>
test.beforeAll(async ({ request }) => {
  test.setTimeout(300_000)
  ;({ documents } = await seedSources(request))
})

for (const width of [390, 1440]) {
  test(`C18 ${width}px real saved turn/PDF, drawer focus and zero-write history`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 })
    const c = await createConversation(request, [documents['midea-2025']])
    const turn = await send(request, c.conversation_id, '请引用美的集团2025年的主要业务原文。')
    expect(turn.status).toBe('completed')
    expect(turn.result.kind).toBe('source_quote')
    expect(turn.result.evidence_refs.length).toBeGreaterThan(0)
    const before = await counts(request)
    const writes: string[] = [], errors: string[] = []
    page.on('request', req => {
      if (req.url().includes('/api/') && !['GET', 'HEAD'].includes(req.method())) writes.push(req.method() + ' ' + req.url())
    })
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`/conversations?conversation=${c.conversation_id}`)
    await expect(page.getByRole('heading', { name: '财报研究助手', exact: true })).toBeVisible()
    await expect(page.getByLabel('消息记录')).toContainText(turn.user_text)
    await expect(page.getByLabel('消息记录')).toContainText(turn.result.answer_text)
    const input = page.getByRole('textbox', { name: '研究问题', exact: true })
    await expect(input).toBeVisible()
    await input.focus()
    expect(await input.evaluate(el => document.activeElement === el)).toBeTruthy()
    const sourceButton = page.getByRole('button', { name: '查看冻结来源', exact: true })
    await sourceButton.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Tab')
    expect(await dialog.evaluate(el => el.contains(document.activeElement))).toBeTruthy()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(sourceButton).toBeFocused()
    const ref = turn.result.evidence_refs[0]
    const pdf = await request.get(`/api/documents/${ref.document_id}/source/file?source_revision=${ref.source_revision}`)
    expect(pdf.status()).toBe(200)
    expect(createHash('sha256').update(await pdf.body()).digest('hex')).toBe(ref.content_sha256)
    const pdfButton = page.getByRole('button', { name: /查看原 PDF/ }).first()
    await pdfButton.click()
    await expect(page.getByRole('dialog').locator('canvas')).toBeVisible({ timeout: 30_000 })
    await page.screenshot({ path: `${out}/conversation-${width}-pdf.png`, fullPage: true })
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(pdfButton).toBeFocused()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe('hidden')
    await page.reload()
    await expect(page.getByLabel('消息记录')).toContainText(turn.user_text)
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    expect(writes).toEqual([])
    expect(errors).toEqual([])
    const after = await counts(request)
    expect(after.calls).toEqual(before.calls)
    expect(after.tables).toEqual(before.tables)
    await page.screenshot({ path: `${out}/conversation-${width}-history.png`, fullPage: true })
    writeFileSync(`${out}/conversation-${width}-proof.json`, JSON.stringify({ before, after, writes,
      pdf_sha256: ref.content_sha256, physical_page: ref.physical_page, human_review: 'pending' }, null, 2))
  })
}

test('C07 sent POST response lost: UNKNOWN recovery only GET, same operation and no model replay', async ({ page, request }) => {
  const c = await createConversation(request, [documents['midea-2025']])
  await page.goto(`/conversations?conversation=${c.conversation_id}`)
  const input = page.getByRole('textbox', { name: '研究问题', exact: true })
  await expect(input).toBeEnabled()
  let submitted: any = null
  let posts = 0
  await page.route(`**/api/conversations/${c.conversation_id}/turns`, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    posts++
    const response = await route.fetch() // Real server registration/execution/commit precedes loss.
    submitted = await response.json()
    await route.abort('connectionreset')
  })
  const before = await counts(request)
  await input.fill('请引用美的集团2025年的主要业务原文。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '查询本次操作状态', exact: true })).toBeVisible()
  expect(submitted?.operation_id).toBeTruthy()
  const committed = await counts(request)
  await page.getByRole('button', { name: '查询本次操作状态', exact: true }).click()
  await expect(page.getByLabel('消息记录')).toContainText(submitted.user_text)
  await page.reload()
  await expect(page.getByLabel('消息记录')).toContainText(submitted.user_text)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  const after = await counts(request)
  expect(posts).toBe(1)
  expect(after.calls).toEqual(committed.calls)
  expect(after.tables).toEqual(committed.tables)
  const reread = await (await request.get(`/api/conversations/${c.conversation_id}/turns/by-operation/${submitted.operation_id}`)).json()
  expect(reread.turn_id).toBe(submitted.turn_id)
  expect(reread.integrity_sha256).toBe(submitted.integrity_sha256)
  writeFileSync(`${out}/conversation-unknown-proof.json`, JSON.stringify({ operation: submitted.operation_id,
    before, committed, after, posts, automatic_retries: 0 }, null, 2))
})

test('C04 two real tabs: unregistered conversation_busy releases only loser operation and explicit new send works', async ({ context, request }) => {
  const c = await createConversation(request, [documents['midea-2025']])
  const firstPage = await context.newPage()
  const secondPage = await context.newPage()
  const turnPath = `/api/conversations/${c.conversation_id}/turns`
  const firstPosts: { operation_id: string; text: string }[] = []
  const secondPosts: { operation_id: string; text: string }[] = []
  const secondReads: string[] = []
  firstPage.on('request', r => {
    if (r.method() === 'POST' && r.url().endsWith(turnPath)) firstPosts.push(r.postDataJSON())
  })
  secondPage.on('request', r => {
    if (r.method() === 'POST' && r.url().endsWith(turnPath)) secondPosts.push(r.postDataJSON())
    if (r.method() === 'GET' && r.url().includes('/api/')) secondReads.push(r.url())
  })
  const before = await counts(request)
  try {
    await Promise.all([firstPage.goto(`/conversations?conversation=${c.conversation_id}`),
      secondPage.goto(`/conversations?conversation=${c.conversation_id}`)])
    const firstInput = firstPage.getByRole('textbox', { name: '研究问题', exact: true })
    const secondInput = secondPage.getByRole('textbox', { name: '研究问题', exact: true })
    const firstSend = firstPage.getByRole('button', { name: '发送', exact: true })
    const secondSend = secondPage.getByRole('button', { name: '发送', exact: true })
    const draft = '请引用美的集团2025年的主要业务原文，不推断原因。'
    await firstInput.fill('请引用美的集团2025年的主要业务原文。')
    await secondInput.fill(draft)
    await expect(firstSend).toBeEnabled()
    await expect(secondSend).toBeEnabled()
    expect((await request.post('/api/__test__/conversation-mode', {
      data: { hold_provider: true },
    })).ok()).toBeTruthy()
    const firstResponse = firstPage.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(turnPath))
    await firstSend.click()
    // Hold the real provider boundary after server registration; no fixed sleep
    // or fabricated 409 can stand in for the two competing actual HTTP writes.
    await expect.poll(async () => (await counts(request)).calls.model).toBeGreaterThan(before.calls.model)
    const active = await (await request.get(`/api/conversations/${c.conversation_id}`)).json()
    expect(active.active_turn_id).not.toBeNull()
    const busyResponse = secondPage.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(turnPath))
    await secondSend.click()
    const rejected = await busyResponse
    expect(rejected.status()).toBe(409)
    expect((await rejected.json()).detail).toBe('conversation_busy')
    expect(firstPosts).toHaveLength(1)
    expect(secondPosts).toHaveLength(1)
    const rejectedOp = secondPosts[0].operation_id
    expect(rejectedOp).not.toBe(firstPosts[0].operation_id)
    expect((await request.get(`/api/conversation-operations/${rejectedOp}`)).status()).toBe(404)
    await expect(secondInput).toHaveValue(draft)
    await expect(secondPage.getByRole('button', { name: '查询本次操作状态', exact: true })).toHaveCount(0)
    await expect.poll(() => secondPage.evaluate(() => JSON.parse(
      sessionStorage.getItem('findoc:conversation-operations:v1') || '[]'))).toEqual([])
    const firstPending = await firstPage.evaluate(() => JSON.parse(
      sessionStorage.getItem('findoc:conversation-operations:v1') || '[]'))
    expect(firstPending.some((op: { operationId: string }) => op.operationId === firstPosts[0].operation_id)).toBeTruthy()
    expect((await request.post('/api/__test__/conversation-mode', { data: { hold_provider: false } })).ok()).toBeTruthy()
    const committedResponse = await firstResponse
    expect(committedResponse.status()).toBe(200)
    const committedTurn = await committedResponse.json()
    expect(committedTurn.status).toBe('completed')
    const committed = await counts(request)
    await secondPage.getByRole('button', { name: '只读刷新会话', exact: true }).click()
    await expect(secondPage.getByLabel('消息记录')).toContainText(committedTurn.user_text)
    await expect(secondInput).toHaveValue(draft)
    await expect(secondSend).toBeEnabled()
    await secondPage.evaluate(() => window.dispatchEvent(new Event('focus')))
    expect(secondPosts).toHaveLength(1)
    expect(secondReads.filter(url => url.includes(rejectedOp))).toEqual([])
    expect((await counts(request)).calls).toEqual(committed.calls)
    const retryResponse = secondPage.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(turnPath))
    await secondSend.click() // Explicit user action is the sole new send trigger.
    const accepted = await retryResponse
    expect(accepted.status()).toBe(200)
    const secondTurn = await accepted.json()
    expect(secondPosts).toHaveLength(2)
    expect(secondPosts[1].operation_id).not.toBe(rejectedOp)
    expect(secondPosts[1].operation_id).not.toBe(firstPosts[0].operation_id)
    expect(secondTurn.status).toBe('completed')
    expect(secondTurn.seq).toBe(committedTurn.seq + 1)
    expect(secondTurn.user_text).toBe(draft)
    const after = await counts(request)
    expect(after.tables.conversation_turns).toBe(before.tables.conversation_turns + 2)
    expect(after.tables.financial_acceptance_receipts).toBe(before.tables.financial_acceptance_receipts)
    writeFileSync(`${out}/conversation-two-tabs-busy-proof.json`, JSON.stringify({
      firstPosts, secondPosts, rejected_operation: rejectedOp, firstPending,
      rejected_operation_http_status: 404, secondReads, before, committed, after,
      actual_pages: 2, actual_http_conflict: true, automatic_retries: 0,
    }, null, 2))
  } finally {
    await request.post('/api/__test__/conversation-mode', { data: { hold_provider: false } })
    await firstPage.close()
    await secondPage.close()
  }
})
