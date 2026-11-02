import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { counts, createConversation, operation, out, seedSources, send } from './conversation-helpers.ts'

let documents: Record<string, string>
test.beforeAll(async ({ request }) => {
  test.setTimeout(300_000)
  ;({ documents } = await seedSources(request))
})

test('C14/C15/C16 explicit memory CRUD has operation receipts and no deleted-value replay', async ({ request }) => {
  // A fresh suite runtime is required; there are no inherited preference seeds.
  const initial = await (await request.get('/api/memories')).json()
  expect(initial.items).toEqual([])
  const c = await createConversation(request, [documents['midea-2025']])
  const proposed = await send(request, c.conversation_id, '以后研究先关注现金流')
  expect(proposed.result.memory_candidates).toEqual([{
    type: 'research_preference', key: 'analysis_focus', value: 'cash_flow',
    source_turn_id: proposed.turn_id, confirmation_required: true,
  }])
  expect((await (await request.get('/api/memories')).json()).items).toEqual([])
  expect(proposed.result.verified_financial_fact_refs).toEqual([])
  const createOp = operation()
  const create = { operation_id: createOp, type: 'research_preference', key: 'analysis_focus',
    value: 'cash_flow', confirmed: true, source_turn_id: proposed.turn_id }
  const response = await request.post('/api/memories', { data: create })
  expect(response.status()).toBe(201)
  const item = await response.json()
  expect(item.value).toBe('cash_flow')
  expect(item.revision).toBe(1)
  const receipt = await (await request.get(`/api/memory-operations/${createOp}`)).json()
  expect(receipt.memory_id).toBe(item.memory_id)
  expect(receipt.kind).toBe('create_memory')
  const duplicate = await request.post('/api/memories', { data: create })
  expect(duplicate.status()).toBe(200)
  expect((await duplicate.json()).memory_id).toBe(item.memory_id)
  const updateOp = operation()
  const patch = { operation_id: updateOp, expected_revision: item.revision,
    value: 'balanced', confirmed: true }
  const updated = await request.patch(`/api/memories/${item.memory_id}`, { data: patch })
  expect(updated.status()).toBe(200)
  const current = await updated.json()
  expect(current.value).toBe('balanced')
  expect(current.revision).toBe(2)
  expect((await request.patch(`/api/memories/${item.memory_id}`, {
    data: { ...patch, operation_id: operation() },
  })).status()).toBe(409)
  const beforeRead = await counts(request)
  const updateReceipt = await (await request.get(`/api/memory-operations/${updateOp}`)).json()
  expect(updateReceipt.kind).toBe('update_memory')
  expect((await counts(request)).calls).toEqual(beforeRead.calls)
  const delOp = operation()
  const deletion = await request.delete(`/api/memories/${item.memory_id}`, {
    data: { operation_id: delOp, expected_revision: current.revision },
  })
  expect(deletion.status()).toBe(200)
  const tombstone = await deletion.json()
  expect(tombstone.resource_deleted).toBe(true)
  expect(tombstone.kind).toBe('delete_memory')
  expect(tombstone.revision).toBe(current.revision + 1)
  expect(JSON.stringify(tombstone)).not.toContain('balanced')
  expect((await (await request.get('/api/memories')).json()).items).toEqual([])
  const replay = await request.post('/api/memories', { data: create })
  expect(replay.status()).toBe(410)
  expect(JSON.stringify(await replay.json())).not.toContain('cash_flow')
  const replayPatch = await request.patch(`/api/memories/${item.memory_id}`, { data: patch })
  expect(replayPatch.status()).toBe(410)
  expect(JSON.stringify(await replayPatch.json())).not.toContain('balanced')
  expect((await request.get(`/api/memory-operations/${delOp}`)).status()).toBe(200)
  const fresh = await createConversation(request, [documents['midea-2025']])
  await send(request, fresh.conversation_id, '请引用美的集团2025年的主要业务原文。')
  expect((await (await request.get('/api/memories')).json()).items).toEqual([])
})

test('C10 invalid preference, missing consent, PDF-style fact and owner injection are rejected', async ({ request }) => {
  const before = await counts(request)
  for (const invalidFields of [
    { key: 'analysis_focus', value: '123456789元', confirmed: true },
    { key: 'analysis_focus', value: 'cash_flow', confirmed: false },
    { key: 'analysis_focus', value: 'cash_flow', confirmed: true, workspace_id: 'other' },
    { key: 'asset_value', value: 'cash_flow', confirmed: true },
  ]) {
    const response = await request.post('/api/memories', { data: {
      operation_id: operation(), type: 'research_preference', ...invalidFields,
    } })
    expect(response.status()).toBe(422)
  }
  expect((await counts(request)).tables.memory_items).toBe(before.tables.memory_items)
  expect((await counts(request)).calls).toEqual(before.calls)
})

test('S4 original user phrase: separate UI save, actual fresh context recall and explicit deletion without resurrection', async ({ page, request }) => {
  test.setTimeout(150_000)
  expect((await (await request.get('/api/memories')).json()).items).toEqual([])
  const before = await counts(request)
  const memoryWrites: { method: string; operation: string }[] = []
  page.on('request', r => {
    if (r.url().includes('/api/memories') && ['POST', 'PATCH', 'DELETE'].includes(r.method())) {
      memoryWrites.push({ method: r.method(), operation: r.postDataJSON().operation_id })
    }
  })
  async function uiSend(target: Page, cid: string, text: string) {
    await target.goto(`/conversations?conversation=${cid}`)
    await target.getByRole('textbox', { name: '研究问题', exact: true }).fill(text)
    const response = target.waitForResponse(r => r.request().method() === 'POST'
      && r.url().endsWith(`/api/conversations/${cid}/turns`))
    await target.getByRole('button', { name: '发送', exact: true }).click()
    const received = await response
    expect(received.status()).toBe(200)
    const turn = await received.json()
    expect(turn.conversation_id).toBe(cid)
    expect(turn.status).toBe('completed')
    return turn
  }
  async function contextFor(turn: { turn_id: string }) {
    const response = await request.get(`/api/__test__/conversation-context/${turn.turn_id}`)
    expect(response.status()).toBe(200)
    const observed = await response.json()
    expect(observed.actual_context_observation).toBe(true)
    expect(observed.prompt_preferences).toEqual(observed.preferences)
    return observed
  }
  const origin = await createConversation(request, [documents['midea-2025']])
  const candidate = await uiSend(page, origin.conversation_id, '以后研究先关注现金流')
  expect(candidate.result.kind).toBe('clarification')
  expect(candidate.result.memory_candidates).toEqual([{
    type: 'research_preference', key: 'analysis_focus', value: 'cash_flow',
    source_turn_id: candidate.turn_id, confirmation_required: true,
  }])
  expect(memoryWrites).toEqual([])
  expect((await (await request.get('/api/memories')).json()).items).toEqual([])
  const unconfirmed = await createConversation(request, [documents['midea-2025']])
  const query = '请引用美的集团股份有限公司2025年的主要业务原文。'
  const noRecall = await uiSend(page, unconfirmed.conversation_id, query)
  expect(noRecall.result.kind).toBe('source_quote')
  const beforeSaveContext = await contextFor(noRecall)
  expect(beforeSaveContext.preferences).toEqual([])
  await page.goto(`/conversations?conversation=${origin.conversation_id}`)
  await page.getByRole('button', { name: '查看并确认偏好', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('偏好内容')).toHaveValue('cash_flow')
  expect(memoryWrites).toEqual([])
  const saving = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/memories'))
  await dialog.getByRole('button', { name: '保存偏好', exact: true }).click()
  const savedResponse = await saving
  expect(savedResponse.status()).toBe(201)
  const saved = await savedResponse.json()
  expect(saved.source_turn_id).toBe(candidate.turn_id)
  expect(saved.value).toBe('cash_flow')
  await expect(dialog.getByText('研究偏好已明确保存。', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  const fresh = await createConversation(request, [documents['midea-2025']])
  const recalled = await uiSend(page, fresh.conversation_id, query)
  expect(recalled.result.kind).toBe('source_quote')
  const savedContext = await contextFor(recalled)
  expect(savedContext.preferences).toEqual([{ key: 'analysis_focus', value: 'cash_flow' }])
  expect(savedContext.memory_generation).toBeGreaterThan(beforeSaveContext.memory_generation)
  await page.getByRole('button', { name: '我的研究偏好', exact: true }).click()
  await dialog.getByRole('button', { name: '删除分析侧重', exact: true }).click()
  const deleting = page.waitForResponse(r => r.request().method() === 'DELETE' && r.url().endsWith(`/api/memories/${saved.memory_id}`))
  await dialog.getByRole('button', { name: '确认删除偏好', exact: true }).click()
  expect((await deleting).status()).toBe(200)
  await expect(dialog.getByText('暂无已确认研究偏好。', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  const afterDeletion = await createConversation(request, [documents['midea-2025']])
  const next = await uiSend(page, afterDeletion.conversation_id, query)
  const removedContext = await contextFor(next)
  expect(removedContext.preferences).toEqual([])
  expect(removedContext.memory_generation).toBeGreaterThan(savedContext.memory_generation)
  const historical = await uiSend(page, origin.conversation_id, query)
  const historicalContext = await contextFor(historical)
  expect(historicalContext.preferences).toEqual([])
  expect(historicalContext.prior_turn_ids).not.toContain(candidate.turn_id)
  expect(memoryWrites.map(w => w.method)).toEqual(['POST', 'DELETE'])
  expect((await (await request.get('/api/memories')).json()).items).toEqual([])
  const after = await counts(request)
  expect(after.tables.financial_acceptance_receipts).toBe(before.tables.financial_acceptance_receipts)
  expect(after.tables.confirmed_financial_facts).toBe(before.tables.confirmed_financial_facts)
  writeFileSync(`${out}/s4-original-ui-preference-proof.json`, JSON.stringify({
    phrase: '以后研究先关注现金流', candidate_turn: candidate.turn_id, memory_id: saved.memory_id,
    beforeSaveContext, savedContext, removedContext, historicalContext, memoryWrites,
    actual_context_observation: true, actual_llm: false, human_acceptances: 0,
  }, null, 2))
})
