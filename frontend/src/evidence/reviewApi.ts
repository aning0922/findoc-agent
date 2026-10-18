import { checkSource } from './api.ts'
import { sameSource, sourceKey } from './contracts.ts'
import type { Candidate, Source } from './contracts.ts'

export interface ReviewSelection {
  review_schema: 'financial-review-v1'; company_id: string; document_id: string; source_revision: string
  metric_keys: string[]; periods: number[]
}
export interface Review {
  schema: 'financial-review-v1'; source: Source; company: { company_id: string; name: string }
  document: { document_id: string; source_file: string }; selection: { metric_keys: string[]; periods: number[] }
  candidates: Candidate[]; source_evidence: { evidence_id: string; physical_page: number; text: string }[]
  snapshot_id: string; review_status: 'ready_for_acceptance' | 'blocked'; facts_status: 'unconfirmed'
}
export interface AcceptanceRequest extends ReviewSelection { snapshot_id: string; accepted: true; request_id: string }
export interface Receipt {
  schema: 'financial-acceptance-v1'; receipt_id: string; request_id: string; snapshot_id: string
  accepted_at: string; confirmation_kind: 'local_operator' | 'simulated_test'
  company_id: string; document_id: string; source_revision: string; review: Omit<Review, 'snapshot_id' | 'review_status' | 'facts_status'>
  status: 'acceptance_saved'; facts_status: 'pending_d10'; analysis_started: false
}
export class ReviewError extends Error {
  state: 'source' | 'rejected' | 'failed' | 'unknown'
  code: string
  constructor(state: ReviewError['state'], message: string, code = '') { super(message); this.state = state; this.code = code }
}
function ordered(values: (string | number)[]) { return [...values].sort().join('|') }
function body(review: Review | Receipt['review']) {
  const { schema, source, company, document, selection, candidates, source_evidence } = review
  return { schema, source, company, document, selection, candidates, source_evidence }
}
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical((value as Record<string, unknown>)[k])}`).join(',')}}`
  return JSON.stringify(value)
}
export function validateReview(r: Review, s: Source, q: ReviewSelection): Review {
  const expected = new Set(q.metric_keys.flatMap(k => q.periods.map(y => `${k}/${y}`)))
  if (r.schema !== 'financial-review-v1' || !/^financial-review-v1:[a-f0-9]{64}$/.test(r.snapshot_id)
    || !sameSource(r.source, s) || r.company.company_id !== s.company_id || r.document.document_id !== s.document_id
    || ordered(r.selection.metric_keys) !== ordered(q.metric_keys) || ordered(r.selection.periods) !== ordered(q.periods)
    || !Array.isArray(r.candidates) || r.candidates.length !== expected.size || !Array.isArray(r.source_evidence)
    || r.facts_status !== 'unconfirmed' || !['ready_for_acceptance', 'blocked'].includes(r.review_status)) throw new Error('审阅快照身份或选择不匹配。')
  for (const c of r.candidates) {
    if (!expected.delete(`${c.metric_key}/${c.period}`) || sourceKey(c) !== sourceKey(s)
      || c.content_sha256 !== s.content_sha256 || c.attempt !== s.attempt || c.parser_version !== s.parser_version
      || !Array.isArray(c.evidence) || !Array.isArray(c.basis_evidence)
      || c.confirmation_status !== 'pending' || !['candidate', 'needs_manual_review', 'conflict', 'unsupported'].includes(c.status)) throw new Error('候选身份或状态不匹配。')
    if (r.review_status === 'ready_for_acceptance' && (c.status !== 'candidate' || c.failure_reason !== null
      || typeof c.value_cny_yuan !== 'string' || !/^-?\d+(\.\d+)?$/.test(c.value_cny_yuan)
      || c.currency !== 'CNY' || c.scope !== 'consolidated' || c.accounting_basis !== 'PRC_GAAP'
      || !c.evidence.length || !c.basis_evidence.length)) throw new Error('候选证据不完整，不能接受。')
    for (const ref of [...c.evidence, ...c.basis_evidence]) {
      if (!r.source_evidence.some(e => e.evidence_id === ref.evidence_id && e.physical_page === ref.physical_page && e.text)
        || !Number.isSafeInteger(ref.physical_page) || ref.physical_page < 1 || ref.physical_page > s.physical_pages) throw new Error('审阅缺少原文证据。')
    }
  }
  return r
}
export function validateReceipt(r: Receipt, q: AcceptanceRequest, review: Review): Receipt {
  if (r.schema !== 'financial-acceptance-v1' || !r.receipt_id || r.request_id !== q.request_id
    || r.snapshot_id !== q.snapshot_id || r.company_id !== q.company_id || r.document_id !== q.document_id
    || r.source_revision !== q.source_revision || r.status !== 'acceptance_saved' || r.facts_status !== 'pending_d10'
    || r.analysis_started !== false || !['local_operator', 'simulated_test'].includes(r.confirmation_kind)
    || !Number.isFinite(Date.parse(r.accepted_at)) || canonical(body(r.review)) !== canonical(body(review))) {
    throw new ReviewError('unknown', '返回凭证未通过核验，接受结果未知。请只读查询保存结果。')
  }
  return r
}
export async function request(path: string, init: RequestInit, sending = false): Promise<unknown> {
  let response: Response
  try { response = await fetch(`/api${path}`, { ...init, cache: 'no-store' }) }
  catch { throw new ReviewError(sending ? 'unknown' : 'failed', sending ? '连接中断，接受结果未知。请查询凭证，勿重复接受。' : '读取失败，请重试读取。') }
  if (!response.ok) {
    const code = await response.json().then(v => v.detail?.code || '').catch(() => '')
    const source = /source_|resource_not_found|report_identity|pdf_|review_changed/.test(code)
    if (source) throw new ReviewError('source', '来源或审阅内容已变化，请重新审阅。', code)
    throw new ReviewError(sending && response.status >= 500 ? 'unknown' : response.status < 500 ? 'rejected' : 'failed',
      response.status === 404 && ['acceptance_not_found', 'facts_not_found'].includes(code) ? '未查到接受凭证。当前不能显示接受成功。' : `操作未获得有效凭证（${response.status} · ${code}）。`, code)
  }
  try { return await response.json() }
  catch { throw new ReviewError(sending ? 'unknown' : 'failed', '响应无法读取，请查询当前状态。') }
}
export async function loadReview(s: Source, q: ReviewSelection, signal: AbortSignal): Promise<Review> {
  await checkSource(s, signal)
  const r = validateReview(await request('/financial-facts/reviews', { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q) }) as Review, s, q)
  await checkSource(s, signal)
  return r
}
export async function acceptReview(s: Source, q: AcceptanceRequest, review: Review, signal: AbortSignal): Promise<Receipt> {
  try { await checkSource(s, signal) } catch { throw new ReviewError('source', '来源核验失败，请重新审阅。') }
  const value = await request('/financial-facts/confirmations', { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q) }, true)
  let r: Receipt
  try { r = validateReceipt(value as Receipt, q, review) }
  catch { throw new ReviewError('unknown', '返回凭证未通过核验，接受结果未知。请只读查询保存结果。') }
  try { await checkSource(s, signal) } catch { throw new ReviewError('source', '接受后来源核验失败，凭证当前不可用。') }
  return r
}
export async function recoverReceipt(s: Source, q: AcceptanceRequest, review: Review, signal: AbortSignal): Promise<Receipt> {
  const params = new URLSearchParams({ review_schema: q.review_schema, company_id: q.company_id,
    document_id: q.document_id, source_revision: q.source_revision, snapshot_id: q.snapshot_id })
  q.metric_keys.forEach(k => params.append('metric_keys', k)); q.periods.forEach(y => params.append('periods', String(y)))
  const receipt = validateReceipt(await request(`/financial-facts/confirmations/${encodeURIComponent(q.request_id)}?${params}`, { signal }) as Receipt, q, review)
  await checkSource(s, signal)
  return receipt
}

export async function recoverReceiptById(s: Source, receiptId: string, q: AcceptanceRequest, signal: AbortSignal): Promise<{ receipt: Receipt; review: Review }> {
  const r = await request(`/financial-facts/acceptances/${encodeURIComponent(receiptId)}`, { signal }) as Receipt
  const review = validateReview({ ...r.review, snapshot_id: r.snapshot_id, review_status: 'ready_for_acceptance', facts_status: 'unconfirmed' }, s, q)
  if (r.receipt_id !== receiptId) throw new ReviewError('unknown', '接受凭证 ID 不匹配。')
  return { receipt: validateReceipt(r, q, review), review }
}
