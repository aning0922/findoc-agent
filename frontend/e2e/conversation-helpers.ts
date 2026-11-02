import { expect, type APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'

export const operation = () => randomUUID()
export const out = process.env.FINDOC_CONVERSATION_OUT!

export async function seedSources(api: APIRequestContext) {
  const pinned = JSON.parse(readFileSync(`${out}/sources.json`, 'utf8'))
  const catalog = await (await api.get('/api/companies')).json()
  const companies: Record<string, string> = {}
  for (const [prefix, name, security_code] of [
    ['midea', '美的集团股份有限公司', '000333'],
    ['gree', '珠海格力电器股份有限公司', '000651'],
  ]) {
    const existing = catalog.find((c: { security_code: string }) => c.security_code === security_code)
    if (existing) companies[prefix] = existing.company_id
    else {
      const response = await api.post('/api/companies', { data: { name, security_code, exchange: 'SZSE' } })
      expect(response.ok()).toBeTruthy()
      companies[prefix] = (await response.json()).company_id
    }
  }
  const existing = await (await api.get('/api/research/sources')).json()
  const documents: Record<string, string> = {}
  for (const source of pinned) {
    const company = companies[source.id.split('-')[0]]
    const year = Number(source.id.slice(-4))
    const known = existing.documents.find((d: { company_id: string; report_year: number }) =>
      d.company_id === company && d.report_year === year)
    if (known) documents[source.id] = known.document_id
    else {
      const response = await api.post('/api/report-documents', { multipart: {
        file: { name: `${source.id}.pdf`, mimeType: 'application/pdf', buffer: readFileSync(source.absolute_path) },
        metadata: JSON.stringify({ company_id: company, report_year: year, report_type: 'annual',
          basis: 'PRC_GAAP', period_start: `${year}-01-01`, period_end: `${year}-12-31` }),
      } })
      expect(response.status()).toBe(202)
      documents[source.id] = (await response.json()).document_id
    }
    const id = documents[source.id]
    await expect.poll(async () => (await (await api.get(`/api/documents/${id}`)).json()).status,
      { timeout: 120_000 }).toBe('ready')
    const verified = await (await api.get(`/api/documents/${id}/source?company_id=${company}`)).json()
    expect(verified.content_sha256).toBe(source.sha256)
    expect(verified.report_year).toBe(year)
  }
  return { documents, companies }
}

export async function createConversation(api: APIRequestContext, ids: string[], title?: string) {
  const response = await api.post('/api/conversations', {
    data: { operation_id: operation(), document_ids: ids, ...(title ? { title } : {}) },
  })
  expect(response.status()).toBe(201)
  return response.json()
}

export async function send(api: APIRequestContext, cid: string, text: string, op = operation()) {
  const response = await api.post(`/api/conversations/${cid}/turns`, { data: { operation_id: op, text } })
  expect(response.status()).toBe(200)
  const turn = await response.json()
  expect(turn.schema_version).toBe('conversation-turn-v1')
  expect(turn.conversation_id).toBe(cid)
  expect(turn.operation_id).toBe(op)
  expect(turn.status).not.toBe('running')
  expect(turn.integrity_sha256).toMatch(/^[a-f0-9]{64}$/)
  return turn
}

export async function counts(api: APIRequestContext) {
  const response = await api.get('/api/__test__/conversation-counts')
  expect(response.ok()).toBeTruthy()
  return response.json()
}
