import { test, expect } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { counts, createConversation, operation, out, seedSources, send } from './conversation-helpers.ts'

let documents: Record<string, string>
test.beforeAll(async ({ request }) => {
  test.setTimeout(300_000)
  ;({ documents } = await seedSources(request))
})
const ids = () => [documents['midea-2024'], documents['midea-2025']]

test('C05/C06 creation operation replay, conflict and exact read-only receipt', async ({ request }) => {
  const op = operation()
  const data = { operation_id: op, document_ids: ids(), title: '幂等创建验收' }
  const before = await counts(request)
  const first = await request.post('/api/conversations', { data })
  expect(first.status()).toBe(201)
  const value = await first.json()
  const second = await request.post('/api/conversations', { data })
  expect(second.status()).toBe(200)
  expect((await second.json()).conversation_id).toBe(value.conversation_id)
  const conflict = await request.post('/api/conversations', { data: { ...data, title: '不同载荷' } })
  expect(conflict.status()).toBe(409)
  const receipt = await (await request.get(`/api/conversation-operations/${op}`)).json()
  expect(receipt.kind).toBe('create_conversation')
  expect(receipt.conversation_id).toBe(value.conversation_id)
  expect(receipt.status).toBe('completed')
  expect((await counts(request)).calls).toEqual(before.calls)
})

test('C01/C11 three actual turns preserve frozen scope and never calculate unconfirmed facts', async ({ request }) => {
  const conversation = await createConversation(request, ids())
  const before = await counts(request)
  const turns = []
  for (const text of ['请摘录美的集团2025年的营业收入原文。', '同比变化呢？', '经营现金流也这样吗？']) {
    turns.push(await send(request, conversation.conversation_id, text))
  }
  expect(turns[0].resolved_query.metric_key).toBe('revenue')
  expect(turns[1].resolved_query.metric_key).toBe('revenue')
  expect(turns[2].resolved_query.metric_key).toBe('operating_cash_flow')
  for (const turn of turns) {
    expect(turn.resolved_query.company_id).toBe(conversation.sources[0].company_id)
    expect(turn.result.interpretation_status).toBe('not_generated')
    expect(turn.result.verified_financial_fact_refs).toEqual([])
    expect(turn.result.analysis).toBeNull()
    for (const ref of turn.result.evidence_refs) {
      expect(ids()).toContain(ref.document_id)
      expect(ref.verification).toBe('exact_original_with_context')
    }
  }
  expect(turns[1].result.kind).toBe('needs_human_review')
  const after = await counts(request)
  expect(after.tables.financial_acceptance_receipts).toBe(before.tables.financial_acceptance_receipts)
  expect(after.tables.confirmed_financial_facts).toBe(before.tables.confirmed_financial_facts)
  const read = await (await request.get(`/api/conversations/${conversation.conversation_id}`)).json()
  expect(read.source_scope_sha).toBe(conversation.source_scope_sha)
  expect(read.sources).toEqual(conversation.sources)
  writeFileSync(`${out}/c01-three-turns.json`, JSON.stringify({ turns, before, after }, null, 2))
})

test('C02/C08 ambiguous companies clarify and outside scope cannot change sources', async ({ request }) => {
  const multi = await createConversation(request, [documents['midea-2025'], documents['gree-2025']])
  const ambiguous = await send(request, multi.conversation_id, '它的营业收入是多少？')
  expect(ambiguous.result.kind).toBe('clarification')
  const single = await createConversation(request, ids())
  const outside = await send(request, single.conversation_id, '请查询格力集团2025年的营业收入。')
  expect(['clarification', 'unsupported']).toContain(outside.result.kind)
  expect(outside.result.evidence_refs).toEqual([])
  const read = await (await request.get(`/api/conversations/${single.conversation_id}`)).json()
  expect(read.sources).toEqual(single.sources)
})

test('C03/C05/C06/C19 same turn replay is immutable, all history reads have zero execution', async ({ request }) => {
  const oldResponse = await request.post('/api/research/runs', { data: {
    operation_id: operation(), document_ids: ids(), query: '请引用美的集团2025年的主要业务原文。',
  } })
  expect(oldResponse.status()).toBe(200)
  const oldRun = await oldResponse.json()
  expect(oldRun.status).toBe('answered')
  const c = await createConversation(request, ids())
  const op = operation()
  const first = await send(request, c.conversation_id, '请引用美的集团2025年的主要业务原文。', op)
  const before = await counts(request)
  const replay = await send(request, c.conversation_id, first.user_text, op)
  expect(replay.turn_id).toBe(first.turn_id)
  expect(replay.integrity_sha256).toBe(first.integrity_sha256)
  expect(replay.result).toEqual(first.result)
  const conflict = await request.post(`/api/conversations/${c.conversation_id}/turns`, {
    data: { operation_id: op, text: '不同问题' },
  })
  expect(conflict.status()).toBe(409)
  for (const path of ['/api/conversations', `/api/conversations/${c.conversation_id}`,
    `/api/conversation-operations/${op}`, `/api/conversations/${c.conversation_id}/turns/by-operation/${op}`,
    `/api/conversations/${c.conversation_id}/turns/${first.turn_id}`]) {
    expect((await request.get(path)).status()).toBe(200)
  }
  const after = await counts(request)
  expect(after.calls).toEqual(before.calls)
  expect(after.tables).toEqual(before.tables)
  const oldRead = await (await request.get(`/api/research/runs/${oldRun.run_id}`)).json()
  expect(oldRead.result).toEqual(oldRun.result)
  expect(oldRead.integrity_sha256).toBe(oldRun.integrity_sha256)
  expect(oldRead.result.content).toBe(oldRun.result.content)
})

test('C04 two concurrent HTTP sends admit only one running turn', async ({ request }) => {
  const c = await createConversation(request, ids())
  await request.post('/api/__test__/conversation-mode', { data: { delay_seconds: 2 } })
  try {
    const first = request.post(`/api/conversations/${c.conversation_id}/turns`, {
      data: { operation_id: operation(), text: '请引用美的集团2025年的主要业务原文。' },
    })
    await expect.poll(async () => {
      const detail = await (await request.get(`/api/conversations/${c.conversation_id}`)).json()
      return detail.active_turn_id
    }).not.toBeNull()
    const second = await request.post(`/api/conversations/${c.conversation_id}/turns`, {
      data: { operation_id: operation(), text: '请引用美的集团2024年的主要业务原文。' },
    })
    expect(second.status()).toBe(409)
    expect((await first).status()).toBe(200)
  } finally {
    await request.post('/api/__test__/conversation-mode', { data: { delay_seconds: 0 } })
  }
})

test('C13 provider unknown quote number cannot publish evidence', async ({ request }) => {
  const c = await createConversation(request, ids())
  await request.post('/api/__test__/conversation-mode', { data: { forged_quote: true } })
  try {
    const turn = await send(request, c.conversation_id, '请引用美的集团2025年的主要业务原文。')
    expect(['refused', 'failed']).toContain(turn.status)
    expect(turn.result.evidence_refs).toEqual([])
    expect(turn.result.verified_financial_fact_refs).toEqual([])
  } finally {
    await request.post('/api/__test__/conversation-mode', { data: { forged_quote: false } })
  }
})

test('C07 provider failure is terminal, operation reads never retry', async ({ request }) => {
  const c = await createConversation(request, ids())
  await request.post('/api/__test__/conversation-mode', { data: { provider_failure: true } })
  try {
    const turn = await send(request, c.conversation_id, '请引用美的集团2025年的主要业务原文。')
    expect(turn.status).toBe('failed')
    const before = await counts(request)
    for (let i = 0; i < 3; i++) await request.get(`/api/conversations/${c.conversation_id}/turns/by-operation/${turn.operation_id}`)
    expect((await counts(request)).calls).toEqual(before.calls)
  } finally {
    await request.post('/api/__test__/conversation-mode', { data: { provider_failure: false } })
  }
})

test('deleting conversation removes content but retains exact tombstone and never recreates on replay', async ({ request }) => {
  const createOp = operation()
  const data = { operation_id: createOp, document_ids: ids(), title: '删除正文验收' }
  const c = await (await request.post('/api/conversations', { data })).json()
  const turn = await send(request, c.conversation_id, '请引用美的集团2025年的主要业务原文。')
  const before = await counts(request)
  const delOp = operation()
  const deletion = await request.delete(`/api/conversations/${c.conversation_id}`, { data: { operation_id: delOp } })
  expect(deletion.status()).toBe(200)
  const receipt = await deletion.json()
  expect(receipt.resource_deleted).toBe(true)
  expect(receipt.kind).toBe('delete_conversation')
  expect((await request.get(`/api/conversation-operations/${delOp}`)).status()).toBe(200)
  expect((await request.get(`/api/conversations/${c.conversation_id}`)).status()).toBe(410)
  expect((await request.get(`/api/conversations/${c.conversation_id}/turns/by-operation/${turn.operation_id}`)).status()).toBe(410)
  expect((await request.post('/api/conversations', { data })).status()).toBe(410)
  expect((await counts(request)).calls).toEqual(before.calls)
})

test('strict create range and server-owned workspace reject without execution', async ({ request }) => {
  const before = await counts(request)
  for (const data of [
    { operation_id: operation(), document_ids: [] },
    { operation_id: operation(), document_ids: ids(), workspace_id: 'other' },
    { operation_id: operation(), document_ids: [...ids(), ...ids(), 'outside'] },
  ]) {
    expect((await request.post('/api/conversations', { data })).status()).toBe(422)
  }
  expect((await counts(request)).calls).toEqual(before.calls)
})

test('C09 actual isolated binding correction expires new use while historical answer is immutable', async ({ request }) => {
  const original = JSON.parse(readFileSync(`${out}/sources.json`, 'utf8')).find((s: { id: string }) => s.id === 'gree-2024')
  const originalBytes = readFileSync(original.absolute_path)
  expect(createHash('sha256').update(originalBytes).digest('hex')).toBe(original.sha256)
  const derivedBytes = Buffer.concat([originalBytes, Buffer.from(`\n% isolated C09 ${operation()}\n`)])
  const derivedSha = createHash('sha256').update(derivedBytes).digest('hex')
  expect(derivedSha).not.toBe(original.sha256)
  const seed = await createConversation(request, [documents['gree-2024']])
  const company = seed.sources[0].company_id
  const upload = await request.post('/api/report-documents', { multipart: {
    file: { name: 'gree-2024-c09-derived.pdf', mimeType: 'application/pdf', buffer: derivedBytes },
    metadata: JSON.stringify({ company_id: company, report_year: 2024, report_type: 'annual',
      basis: 'PRC_GAAP', period_start: '2024-01-01', period_end: '2024-12-31' }),
  } })
  expect(upload.status()).toBe(202)
  const derivedId = (await upload.json()).document_id
  expect(derivedId).not.toBe(documents['gree-2024'])
  await expect.poll(async () => (await (await request.get(`/api/documents/${derivedId}`)).json()).status,
    { timeout: 120_000 }).toBe('ready')
  const c = await createConversation(request, [derivedId])
  const turn = await send(request, c.conversation_id, '请引用珠海格力电器股份有限公司2024年的主要业务原文。')
  expect(turn.status).toBe('completed')
  expect(turn.result.kind).toBe('source_quote')
  expect(turn.result.evidence_refs.length).toBeGreaterThan(0)
  const source = c.sources[0]
  const before = await counts(request)
  const changed = await request.post(`/api/documents/${source.document_id}/binding-corrections`, { data: {
    expected_attempt: source.attempt, reason: 'V1.2 disposable source invalidation check',
    metadata: { company_id: source.company_id, report_year: source.report_year,
      report_type: 'annual', basis: 'unknown', period_start: source.period_start, period_end: source.period_end },
  } })
  expect(changed.status()).toBe(200)
  const read = await (await request.get(`/api/conversations/${c.conversation_id}`)).json()
  expect(read.source_states[0].status).toBe('expired')
  expect(read.turns[0].result).toEqual(turn.result)
  expect(read.turns[0].integrity_sha256).toBe(turn.integrity_sha256)
  const denied = await request.get(`/api/documents/${source.document_id}/file?source_revision=${source.source_revision}`)
  expect(denied.status()).toBe(409)
  const next = await request.post(`/api/conversations/${c.conversation_id}/turns`, { data: {
    operation_id: operation(), text: '请再说明主要业务。',
  } })
  expect(next.status()).toBe(409)
  expect((await counts(request)).calls).toEqual(before.calls)
  expect(createHash('sha256').update(readFileSync(original.absolute_path)).digest('hex')).toBe(original.sha256)
  writeFileSync(`${out}/c09-invalidation-proof.json`, JSON.stringify({ before,
    after: await counts(request), source, historical_integrity: turn.integrity_sha256,
    original_sha256: original.sha256, derived_sha256: derivedSha, isolated_derived_copy: true,
    source_states: read.source_states, old_pdf_status: denied.status() }, null, 2))
})
