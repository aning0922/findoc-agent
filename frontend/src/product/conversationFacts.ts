import { eligible, productionAccess } from './api.ts';
import type { Fact } from './api.ts';
import type { ConversationSummary, FactSelection, Metric } from './conversationTypes.ts';
export function conversationFactEligible(f: Fact, conversation: ConversationSummary): boolean {
  return eligible(f) && conversation.sources.some(s => s.company_id === f.company_id && s.document_id === f.document_id
    && s.source_revision === f.source_revision && s.content_sha256 === f.content_sha256
    && s.attempt === f.attempt && s.parser_version === f.parser_version);
}
export function conversationFactSelection(f: Fact): FactSelection {
  return { company_id: f.company_id, metric_key: f.metric_key as Metric, period: f.period,
    fact_set_id: f.fact_set_id, fact_id: f.fact_id, disclosure_version: f.disclosure_version };
}
export async function readConversationFacts(conversation: ConversationSummary, signal: AbortSignal): Promise<Fact[]> {
  const results = await Promise.all([...new Set(conversation.sources.map(s => s.company_id))].map(id => productionAccess.query(id, signal)));
  return results.flatMap(r => r.facts).filter(f => conversationFactEligible(f, conversation));
}
