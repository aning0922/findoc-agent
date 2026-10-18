import { checkSource } from './api.ts';
import type { Source } from './contracts.ts';
import { request, validateReview, validateReceipt, ReviewError } from './reviewApi.ts';
import type { Receipt, AcceptanceRequest, ReviewSelection } from './reviewApi.ts';

export function recordSelection(s: Source, periods: number[], metric_keys: string[]): ReviewSelection {
  return { review_schema: 'financial-review-v1', company_id: s.company_id, document_id: s.document_id,
    source_revision: s.source_revision, periods, metric_keys };
}
export function validateRecord(raw: Receipt, source: Source, scope: ReviewSelection) {
  const q: AcceptanceRequest = { ...recordSelection(source, raw.review.selection.periods, raw.review.selection.metric_keys),
    request_id: raw.request_id, snapshot_id: raw.snapshot_id, accepted: true };
  if (!scope.periods.every(y => q.periods.includes(y)) || !scope.metric_keys.every(k => q.metric_keys.includes(k)))
    throw new ReviewError('unknown', '记录与当前核对范围不一致。');
  const review = validateReview({ ...raw.review, snapshot_id: raw.snapshot_id, review_status: 'ready_for_acceptance', facts_status: 'unconfirmed' }, source, q);
  return { review, receipt: validateReceipt(raw, q, review), selection: q };
}
export async function readRecord(source: Source, receiptId: string, scope: ReviewSelection, signal: AbortSignal) {
  await checkSource(source, signal);
  const raw = await request(`/financial-facts/acceptances/${encodeURIComponent(receiptId)}`, { signal }) as Receipt;
  if (raw.receipt_id !== receiptId) throw new ReviewError('unknown', '接受记录身份不一致。');
  const result = validateRecord(raw, source, scope);
  await checkSource(source, signal);
  return result;
}
export async function discoverRecords(source: Source, scope: ReviewSelection, signal: AbortSignal) {
  const q = new URLSearchParams({ review_schema: scope.review_schema, company_id: scope.company_id,
    document_id: scope.document_id, source_revision: scope.source_revision });
  scope.periods.forEach(y => q.append('periods', String(y)));
  scope.metric_keys.forEach(k => q.append('metric_keys', k));
  await checkSource(source, signal);
  const result = await request(`/financial-facts/acceptances?${q}`, { signal }) as { schema: string; automatic_selection: boolean; items: Receipt[] };
  if (result.schema !== 'financial-acceptance-discovery-v1' || result.automatic_selection !== false || !Array.isArray(result.items)
    || new Set(result.items.map(r => r.receipt_id)).size !== result.items.length) throw new Error('接受记录索引无法核验。');
  for (const raw of result.items) {
    const record = validateRecord(raw, source, scope);
    if (record.selection.periods.slice().sort().join('|') !== scope.periods.slice().sort().join('|')
      || record.selection.metric_keys.slice().sort().join('|') !== scope.metric_keys.slice().sort().join('|')) throw new Error('记录发现范围不一致。');
  }
  await checkSource(source, signal);
  return result.items;
}
