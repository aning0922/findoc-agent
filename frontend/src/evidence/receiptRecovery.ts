import { checkSource } from './api.ts';
import type { Source } from './contracts.ts';
import { request, validateReview, validateReceipt } from './reviewApi.ts';
import type { AcceptanceRequest, Receipt } from './reviewApi.ts';

// A stored identity is only a query hint. Both the server snapshot and source must pass.
export async function recoverAcceptance(source: Source, q: AcceptanceRequest, signal: AbortSignal) {
  await checkSource(source, signal);
  const params = new URLSearchParams({ review_schema: q.review_schema, company_id: q.company_id,
    document_id: q.document_id, source_revision: q.source_revision, snapshot_id: q.snapshot_id });
  q.metric_keys.forEach(k => params.append('metric_keys', k));
  q.periods.forEach(y => params.append('periods', String(y)));
  const raw = await request(`/financial-facts/confirmations/${encodeURIComponent(q.request_id)}?${params}`, { signal }) as Receipt;
  const review = validateReview({ ...raw.review, snapshot_id: raw.snapshot_id,
    review_status: 'ready_for_acceptance', facts_status: 'unconfirmed' }, source, q);
  const receipt = validateReceipt(raw, q, review);
  await checkSource(source, signal);
  return { review, receipt };
}

export function matchesReviewScope(q: AcceptanceRequest, year: number, metrics: string[]) {
  return q.periods.length === 1 && q.periods[0] === year &&
    [...q.metric_keys].sort().join('|') === [...metrics].sort().join('|');
}
