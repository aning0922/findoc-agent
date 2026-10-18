import { checkSource } from './api.ts'
import { sameSource } from './contracts.ts'
import { canonical, request, ReviewError } from './reviewApi.ts'
import type { Receipt } from './reviewApi.ts'
import type { Candidate, Source } from './contracts.ts'

export interface FactSet {
  schema: 'financial-fact-set-v1'; fact_set_id: string; receipt_id: string; snapshot_id: string
  confirmation_kind: Receipt['confirmation_kind']; accepted_at: string; saved_at: string
  company_id: string; document_id: string; source_revision: string; disclosure_version: string
  status: 'facts_saved'; integrity: 'verified'; current_valid: boolean; invalid_reason: string | null
  calculable: boolean; production_calculable: boolean; review: Receipt['review']
  facts: (Candidate & { fact_id: string; fact_set_id: string; unit: 'CNY_YUAN' })[]
}
export function validateFactSet(value: FactSet, receipt: Receipt): FactSet {
  if (value.schema !== 'financial-fact-set-v1' || value.receipt_id !== receipt.receipt_id
    || value.fact_set_id !== receipt.receipt_id || value.snapshot_id !== receipt.snapshot_id
    || value.confirmation_kind !== receipt.confirmation_kind || value.accepted_at !== receipt.accepted_at
    || value.company_id !== receipt.company_id || value.document_id !== receipt.document_id
    || value.source_revision !== receipt.source_revision || value.status !== 'facts_saved' || value.integrity !== 'verified'
    || !/^disclosure-v1:[a-f0-9]{64}$/.test(value.disclosure_version) || !Number.isFinite(Date.parse(value.saved_at))
    || canonical(value.review) !== canonical(receipt.review)
    || !Array.isArray(value.facts) || value.facts.length !== receipt.review.candidates.length) {
    throw new ReviewError('unknown', '财务事实返回内容不完整或与接受凭证不一致。请只读查询保存结果。')
  }
  if (value.current_valid !== true || value.calculable !== true || value.invalid_reason !== null
    || value.production_calculable !== (receipt.confirmation_kind === 'local_operator')) {
    throw new ReviewError('source', '财务事实的来源已过期或失效，请重新审阅。')
  }
  const remaining = new Map(receipt.review.candidates.map(c => [c.candidate_id, c]))
  const ids = new Set<string>()
  for (const f of value.facts) {
    const candidate = remaining.get(f.candidate_id)
    const { fact_id, fact_set_id, unit, ...stored } = f
    if (!candidate || typeof fact_id !== 'string' || !fact_id || ids.has(fact_id) || fact_set_id !== value.fact_set_id || unit !== 'CNY_YUAN'
      || f.confirmation_status !== 'confirmed' || canonical({ ...stored, confirmation_status: 'pending' }) !== canonical(candidate)) {
      throw new ReviewError('unknown', '财务事实金额、单位、期间或证据未通过核验，请只读查询保存结果。')
    }
    remaining.delete(f.candidate_id); ids.add(fact_id)
  }
  return value
}
export async function readFacts(source: Source, receipt: Receipt, signal: AbortSignal): Promise<FactSet> {
  if (!sameSource(source, receipt.review.source)) throw new ReviewError('source', '凭证与当前来源不匹配，请重新审阅。')
  // This GET already verifies current binding, evidence, parser and original byte SHA on the server.
  return validateFactSet(await request(`/financial-facts/persisted/${encodeURIComponent(receipt.receipt_id)}`, { signal }) as FactSet, receipt)
}
export async function persistFacts(source: Source, receipt: Receipt, signal: AbortSignal): Promise<FactSet> {
  try { await checkSource(source, signal) } catch { throw new ReviewError('source', '来源核验失败，请重新审阅。') }
  const result = validateFactSet(await request('/financial-facts/persisted', { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ receipt_id: receipt.receipt_id }) }, true) as FactSet, receipt)
  try {
    const restored = await readFacts(source, receipt, signal)
    if (canonical(restored) !== canonical(result)) throw new Error('readback mismatch')
    return restored
  } catch (e) {
    if (e instanceof ReviewError && e.state === 'source') throw e
    throw new ReviewError('unknown', '提交后未取得一致的读回结果，事实操作结果未知。请按凭证 ID 只读查询，勿重复保存。')
  }
}
