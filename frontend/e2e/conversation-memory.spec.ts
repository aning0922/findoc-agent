import { test, expect } from '@playwright/test'
import { counts, createConversation, operation, seedSources, send } from './conversation-helpers.ts'

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
  const proposed = await send(request, c.conversation_id, '记住：我更关注现金流。')
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
