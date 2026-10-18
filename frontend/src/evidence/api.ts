import { ProductError } from '../product/api.ts';
import { VerificationInvalidated } from '../product/researchVerification.ts';
import { sameSource, sourceKey, validateSource, validateEvidence } from './contracts.ts'
import type { Candidate, Evidence, Source } from './contracts.ts'

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, { signal, cache: 'no-store' })
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    const code = typeof value?.detail === 'string' ? value.detail : value?.detail?.code || '';
    throw new ProductError(value?.detail?.message || (code === 'source_changed' ? '来源已变化，旧引用不可用于当前文件。' : '') || `来源读取失败（${response.status}），请稍后重试。`,
      false, code, response.status);
  }
  return response.json() as Promise<T>
}
export function pinned(s: Source, page?: number): string {
  const q = new URLSearchParams({ company_id: s.company_id, source_revision: s.source_revision })
  if (page !== undefined) q.set('page', String(page))
  return q.toString()
}
export async function checkSource(s: Source, signal: AbortSignal, page?: number): Promise<void> {
  const latest = await getJson<Source>(`/documents/${encodeURIComponent(s.document_id)}/source?${pinned(s, page)}`, signal)
  if (!sameSource(s, latest)) throw new VerificationInvalidated('来源版本已变化，旧文件已撤下。')
}
// Only settled bytes are cached. Callers MUST validate source before every reuse.
// Bounded to two revisions / 24 MiB; copies protect cache from PDF.js transfer detachment.
const pdfCache = new Map<string, Uint8Array>()
export function forgetPdf(s: Source): void { pdfCache.delete(sourceKey(s)) }
export async function loadPdf(s: Source, signal: AbortSignal): Promise<Uint8Array> {
  const key = sourceKey(s)
  const hit = pdfCache.get(key)
  if (hit) { pdfCache.delete(key); pdfCache.set(key, hit); return hit.slice() }
  const response = await fetch(`/api/documents/${encodeURIComponent(s.document_id)}/file?${pinned(s)}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(response.status === 409 ? '来源已变化，PDF 已拒绝。' : `PDF 加载失败（${response.status}）。`)
  if (!response.headers.get('content-type')?.startsWith('application/pdf')) throw new Error('来源未返回 PDF 文件。')
  const bytes = new Uint8Array(await response.arrayBuffer())
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const sha = Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('')
  if (sha !== s.content_sha256) throw new Error('PDF 校验失败，未展示不匹配的文件。')
  signal.throwIfAborted()
  if (bytes.byteLength <= 24 * 1024 * 1024) {
    pdfCache.set(key, bytes)
    while (pdfCache.size > 2 || [...pdfCache.values()].reduce((n, b) => n + b.byteLength, 0) > 24 * 1024 * 1024) {
      pdfCache.delete(pdfCache.keys().next().value!)
    }
  }
  return bytes.slice()
}
export async function loadDocument(company: string, document: string, revision: string, signal: AbortSignal, period?: number, recordOnly = false) {
  const q = new URLSearchParams({ company_id: company })
  if (revision) q.set('source_revision', revision)
  const source = validateSource(await getJson<Source>(`/documents/${encodeURIComponent(document)}/source?${q}`, signal), company, document, revision)
  if (recordOnly) {
    const bytes = await loadPdf(source, signal);
    await checkSource(source, signal);
    return { source, candidates: [] as Candidate[], bytes };
  }
  const query = new URLSearchParams(pinned(source))
  for (const metric of ['revenue', 'net_profit_parent', 'operating_cash_flow']) query.append('metric_keys', metric)
  query.append('periods', String(period ?? source.report_year))
  // Both requests settle before returning; a failed peer cannot leave an unhandled response.
  const results = await Promise.allSettled([
    getJson<{ source: Source; candidates: Candidate[] }>(`/documents/${encodeURIComponent(document)}/financial-candidates?${query}`, signal),
    loadPdf(source, signal),
  ])
  for (const result of results) if (result.status === 'rejected') { forgetPdf(source); throw result.reason }
  const result = (results[0] as PromiseFulfilledResult<{ source: Source; candidates: Candidate[] }>).value
  const bytes = (results[1] as PromiseFulfilledResult<Uint8Array>).value
  if (!sameSource(source, result.source) || !Array.isArray(result.candidates)
    || result.candidates.some(c => c.period !== (period ?? source.report_year) || sourceKey(c) !== sourceKey(source) || c.content_sha256 !== source.content_sha256
      || c.attempt !== source.attempt || c.parser_version !== source.parser_version || !Array.isArray(c.evidence))) {
    forgetPdf(source); throw new Error('候选与 PDF 来源版本不匹配。')
  }
  try { await checkSource(source, signal) } catch (e) { forgetPdf(source); throw e }
  return { source, candidates: result.candidates, bytes }
}
export async function loadEvidence(s: Source, id: string, page: number | undefined, signal: AbortSignal) {
  await checkSource(s, signal, page)
  const e = validateEvidence(await getJson<Evidence>(`/documents/${encodeURIComponent(s.document_id)}/evidence/${encodeURIComponent(id)}?${pinned(s)}`, signal), s, id, page)
  await checkSource(s, signal)
  return e
}
