import { test, expect } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { counts, createConversation, operation, out, seedSources } from './conversation-helpers.ts'

let documents: Record<string, string>
test.beforeAll(async ({ request }) => {
  test.setTimeout(300_000)
  ;({ documents } = await seedSources(request))
})

test('G02 stale catalog create409 is unregistered, retains draft, and permits explicit valid creation', async ({ page, request }) => {
  test.setTimeout(150_000)
  const pinned = JSON.parse(readFileSync(`${out}/sources.json`, 'utf8')).find((s: { id: string }) => s.id === 'midea-2024')
  const raw = readFileSync(pinned.absolute_path)
  expect(createHash('sha256').update(raw).digest('hex')).toBe(pinned.sha256)
  const bytes = Buffer.concat([raw, Buffer.from(`\n% isolated G02 ${operation()}\n`)])
  const original = await (await request.get(`/api/documents/${documents['midea-2024']}/source`)).json()
  const metadata = { company_id: original.company_id, report_year: 2024, report_type: 'annual',
    basis: 'PRC_GAAP', period_start: '2024-01-01', period_end: '2024-12-31' }
  const filename = 'midea-2024-g02-derived.pdf'
  const upload = await request.post('/api/report-documents', { multipart: {
    file: { name: filename, mimeType: 'application/pdf', buffer: bytes }, metadata: JSON.stringify(metadata),
  } })
  expect(upload.status()).toBe(202)
  const id = (await upload.json()).document_id
  await expect.poll(async () => (await (await request.get(`/api/documents/${id}`)).json()).status,
    { timeout: 120_000 }).toBe('ready')
  const source = await (await request.get(`/api/documents/${id}/source`)).json()
  await page.goto('/conversations')
  const draft = '我需要保留的问题草稿'
  await page.getByRole('textbox', { name: '研究问题', exact: true }).fill(draft)
  await page.getByRole('button', { name: '选择年报', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('checkbox', { name: new RegExp(filename) }).check()
  const changed = await request.post(`/api/documents/${id}/binding-corrections`, { data: {
    expected_attempt: source.attempt, metadata: { ...metadata, report_year: 2023,
      period_start: '2023-01-01', period_end: '2023-12-31' }, reason: 'G02 isolated stale source',
  } })
  expect(changed.status()).toBe(200)
  const ops: string[] = []
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/api/conversations')) ops.push(r.postDataJSON().operation_id) })
  const rejection = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/conversations'))
  await dialog.getByRole('button', { name: '创建会话', exact: true }).click()
  const rejected = await rejection
  expect(rejected.status()).toBe(409)
  expect(['source_changed', 'source_not_ready', 'report_identity_unverified']).toContain((await rejected.json()).detail)
  expect((await request.get(`/api/conversation-operations/${ops[0]}`)).status()).toBe(404)
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem('findoc:conversation-operations:v1') || '[]'))).toEqual([])
  if (await dialog.count()) await page.keyboard.press('Escape')
  await expect(page.getByRole('textbox', { name: '研究问题', exact: true })).toHaveValue(draft)
  await expect(page.getByRole('button', { name: '查询本次操作状态', exact: true })).toHaveCount(0)
  expect(ops).toHaveLength(1)
  await page.getByRole('button', { name: '选择年报', exact: true }).click()
  await dialog.getByRole('button', { name: '重新读取年报状态', exact: true }).click()
  const stale = dialog.getByRole('checkbox', { name: new RegExp(filename) })
  if (await stale.isChecked()) await stale.uncheck()
  await dialog.getByRole('checkbox', { name: /midea-2025.pdf/ }).check()
  const creation = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/conversations'))
  await dialog.getByRole('button', { name: '创建会话', exact: true }).click()
  expect((await creation).status()).toBe(201)
  expect(ops).toHaveLength(2)
  expect(ops[1]).not.toBe(ops[0])
  expect(createHash('sha256').update(readFileSync(pinned.absolute_path)).digest('hex')).toBe(pinned.sha256)
  writeFileSync(`${out}/g02-stale-create-proof.json`, JSON.stringify({ operations: ops,
    rejected_operation_http_status: 404, original_sha256: pinned.sha256,
    derived_sha256: createHash('sha256').update(bytes).digest('hex'), automated_fixture: true }, null, 2))
})

test('G02 two real tabs busy DELETE409 clears only rejected delete and permits explicit retry', async ({ context, request }) => {
  const c = await createConversation(request, [documents['midea-2025']])
  const writer = await context.newPage(), deleter = await context.newPage()
  const path = `/api/conversations/${c.conversation_id}`
  const deletes: string[] = []
  deleter.on('request', r => { if (r.method() === 'DELETE' && r.url().endsWith(path)) deletes.push(r.postDataJSON().operation_id) })
  try {
    await Promise.all([writer.goto(`/conversations?conversation=${c.conversation_id}`), deleter.goto(`/conversations?conversation=${c.conversation_id}`)])
    await deleter.getByRole('textbox', { name: '研究问题', exact: true }).fill('删除拒绝后保留草稿')
    await deleter.getByRole('button', { name: '删除此会话', exact: true }).click()
    await request.post('/api/__test__/conversation-mode', { data: { hold_provider: true } })
    await writer.getByRole('textbox', { name: '研究问题', exact: true }).fill('请引用美的集团股份有限公司2025年的主要业务原文。')
    await writer.getByRole('button', { name: '发送', exact: true }).click()
    await expect.poll(async () => (await (await request.get(path)).json()).active_turn_id).not.toBeNull()
    const rejection = deleter.waitForResponse(r => r.request().method() === 'DELETE' && r.url().endsWith(path))
    await deleter.getByRole('dialog').getByRole('button', { name: '确认删除会话', exact: true }).click()
    const rejected = await rejection
    expect(rejected.status()).toBe(409)
    expect((await rejected.json()).detail).toBe('conversation_busy')
    expect((await request.get(`/api/conversation-operations/${deletes[0]}`)).status()).toBe(404)
    await expect.poll(() => deleter.evaluate(() => JSON.parse(sessionStorage.getItem('findoc:conversation-operations:v1') || '[]'))).toEqual([])
    await expect(deleter.getByRole('button', { name: '查询本次操作状态', exact: true })).toHaveCount(0)
    await expect(deleter.getByRole('textbox', { name: '研究问题', exact: true })).toHaveValue('删除拒绝后保留草稿')
    await request.post('/api/__test__/conversation-mode', { data: { hold_provider: false } })
    await expect.poll(async () => (await (await request.get(path)).json()).active_turn_id).toBeNull()
    const beforeRefresh = await counts(request)
    await deleter.getByRole('button', { name: '只读刷新会话', exact: true }).click()
    await expect(deleter.getByRole('button', { name: '删除此会话', exact: true })).toBeEnabled()
    expect(deletes).toHaveLength(1)
    expect((await counts(request)).calls).toEqual(beforeRefresh.calls)
    await deleter.getByRole('button', { name: '删除此会话', exact: true }).click()
    const deletion = deleter.waitForResponse(r => r.request().method() === 'DELETE' && r.url().endsWith(path))
    await deleter.getByRole('dialog').getByRole('button', { name: '确认删除会话', exact: true }).click()
    expect((await deletion).status()).toBe(200)
    expect(deletes).toHaveLength(2)
    expect(deletes[1]).not.toBe(deletes[0])
    writeFileSync(`${out}/g02-busy-delete-proof.json`, JSON.stringify({ operations: deletes, real_pages: 2, automatic_retries: 0 }, null, 2))
  } finally {
    await request.post('/api/__test__/conversation-mode', { data: { hold_provider: false } })
    await writer.close(); await deleter.close()
  }
})

for (const kind of ['create_memory', 'update_memory'] as const) {
  test(`G03 ${kind} response lost, another real tab deletes, original tombstone resolves without replay`, async ({ context, request }) => {
    const a = await context.newPage(), b = await context.newPage()
    const key = kind === 'create_memory' ? 'display_unit' : 'analysis_focus'
    const label = key === 'display_unit' ? '展示单位' : '分析侧重'
    if (kind === 'update_memory') {
      const setup = await request.post('/api/memories', { data: { operation_id: operation(),
        type: 'research_preference', key, value: 'cash_flow', confirmed: true } })
      expect(setup.status()).toBe(201)
    }
    let committed: any = null, originalOp = '', writes = 0
    try {
      for (const page of [a, b]) {
        await page.goto('/conversations')
        await page.getByRole('button', { name: '我的研究偏好', exact: true }).click()
        await expect(page.getByRole('dialog').getByLabel('偏好类型')).toBeVisible()
      }
      const dialog = a.getByRole('dialog')
      if (kind === 'update_memory') await dialog.getByRole('button', { name: `编辑${label}`, exact: true }).click()
      else await dialog.getByLabel('偏好类型').selectOption(key)
      await dialog.getByLabel('偏好内容').selectOption(kind === 'create_memory' ? 'CNY_TEN_THOUSAND' : 'balanced')
      await a.route('**/api/memories{,/*}', async route => {
        const req = route.request()
        if (req.method() !== (kind === 'create_memory' ? 'POST' : 'PATCH')) return route.continue()
        writes++; originalOp = req.postDataJSON().operation_id
        const response = await route.fetch()
        expect(response.ok()).toBeTruthy()
        committed = await response.json()
        await route.abort('connectionreset')
      })
      await dialog.getByRole('button', { name: kind === 'create_memory' ? '保存偏好' : '确认修改偏好', exact: true }).click()
      await expect.poll(() => committed?.memory_id, { timeout: 60_000 }).toBeTruthy()
      await expect(dialog.getByRole('button', { name: '查询偏好操作状态', exact: true })).toBeVisible()
      const other = b.getByRole('dialog')
      await other.getByRole('button', { name: '重新读取偏好', exact: true }).click()
      await other.getByRole('button', { name: `删除${label}`, exact: true }).click()
      await other.getByRole('button', { name: '确认删除偏好', exact: true }).click()
      await expect(other.getByText('暂无已确认研究偏好。', { exact: true })).toBeVisible()
      const tombstone = await (await request.get(`/api/memory-operations/${originalOp}`)).json()
      expect(tombstone.kind).toBe(kind)
      expect(tombstone.memory_id).toBe(committed.memory_id)
      expect(tombstone.resource_deleted).toBe(true)
      expect(JSON.stringify(tombstone)).not.toContain(committed.value)
      const before = await counts(request)
      await dialog.getByRole('button', { name: '查询偏好操作状态', exact: true }).click()
      await expect(dialog.getByRole('button', { name: '查询偏好操作状态', exact: true })).toHaveCount(0)
      await expect(dialog.getByText('暂无已确认研究偏好。', { exact: true })).toBeVisible()
      await expect(dialog.getByRole('button', { name: '保存偏好', exact: true })).toBeEnabled()
      expect(await a.evaluate(() => sessionStorage.getItem('findoc:memory-operation:v1'))).toBeNull()
      expect(writes).toBe(1)
      const after = await counts(request)
      expect(after.tables).toEqual(before.tables)
      expect(after.calls).toEqual(before.calls)
      writeFileSync(`${out}/g03-${kind}-deleted-proof.json`, JSON.stringify({ original_operation: originalOp,
        tombstone, before, after, writes, real_pages: 2, restored_deleted_value: false }, null, 2))
    } finally {
      await a.unrouteAll({ behavior: 'wait' })
      await a.close(); await b.close()
    }
  })
}
