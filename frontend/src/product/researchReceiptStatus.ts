import { sourceKey } from '../evidence/contracts.ts';
import type { Source } from '../evidence/contracts.ts';
import { recoverAcceptance } from '../evidence/receiptRecovery.ts';
import type { AcceptanceRequest } from '../evidence/reviewApi.ts';
import { discoverRecords, recordSelection } from '../evidence/recordApi.ts';
import { readFacts } from '../evidence/factsApi.ts';

export type ReceiptState = { status: 'accepted-unpersisted' | 'unknown'; message: string };

// Only local query identities are inspected; a successful server GET establishes receipt state.
export async function receiptStates(source: Source, signal: AbortSignal, simulated: boolean, groups: { year: number; metrics: string[] }[] = []): Promise<Record<string, ReceiptState>> {
  const states: Record<string, ReceiptState> = {};
  const prefix = `financial-acceptance-pending-v1:${sourceKey(source)}`;
  const hints: AcceptanceRequest[] = [];
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)!;
      if (key === prefix || key.startsWith(`${prefix}:`)) {
        const q = JSON.parse(sessionStorage.getItem(key)!);
        if (q.company_id === source.company_id && q.document_id === source.document_id && q.source_revision === source.source_revision && Array.isArray(q.periods) && Array.isArray(q.metric_keys)) hints.push(q);
      }
    }
  } catch { /* server discovery does not depend on storage */ }
  for (const q of hints) {
    try {
      const { receipt: r } = await recoverAcceptance(source, q, signal);
      if (r.confirmation_kind === 'simulated_test' && !simulated) continue;
      for (const y of q.periods) for (const k of q.metric_keys) states[`${y}:${k}`] = { status: 'accepted-unpersisted', message: '已确认 · 待保存数据' };
    } catch {
      signal.throwIfAborted();
      for (const y of q.periods) for (const k of q.metric_keys) states[`${y}:${k}`] ||= { status: 'unknown', message: '确认结果待查询' };
    }
  }
  for (const group of groups) {
    try {
      const records = await discoverRecords(source, recordSelection(source, [group.year], group.metrics), signal);
      for (const r of records) {
        if (r.confirmation_kind === 'simulated_test' && !simulated) continue;
        try { await readFacts(source, r, signal); }
        catch (e) {
          signal.throwIfAborted();
          for (const metric of group.metrics) states[`${group.year}:${metric}`] = (e as { code?: string }).code === 'facts_not_found'
            ? { status: 'accepted-unpersisted', message: '已接受 · 待独立保存；请明确选择接受记录' }
            : { status: 'unknown', message: '原接受记录的保存结果待查证' };
        }
      }
    } catch {
      signal.throwIfAborted();
      for (const metric of group.metrics) states[`${group.year}:${metric}`] ||= { status: 'unknown', message: '接受记录暂不可核验' };
    }
  }
  return states;
}
