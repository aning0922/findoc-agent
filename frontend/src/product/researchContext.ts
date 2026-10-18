import type { Company } from './api.ts';
import type { Task } from './operatingResearch.ts';
import type { Draft } from './reportDraft.ts';
export type ContextSource = { document_id: string; company_id: string; source_revision: string; report_year: number };
export type ContextScope = { company_id: string; name: string; year: number; side: string };
function sources(raw: unknown): ContextSource[] {
  return Array.isArray(raw) ? raw.filter((r): r is ContextSource => !!r && typeof r.document_id === 'string' && typeof r.company_id === 'string' && typeof r.source_revision === 'string' && Number.isSafeInteger(r.report_year) && r.report_year > 0) : [];
}
export function taskContext(task: Task, companies: Company[]) {
  const frozenSources = sources((task.snapshot as unknown as { documents?: unknown } | null)?.documents);
  return {
    scopes: (['first', 'second'] as const).map(side => ({ side, company_id: task.input[side].company_id,
      name: companies.find(c => c.company_id === task.input[side].company_id)?.name || task.input[side].company_id,
      year: task.input[side].period.year })),
    sources: frozenSources.filter(r => task.input.reports.some(p => p.document_id === r.document_id && p.expected_source_revision === r.source_revision) &&
      (['first', 'second'] as const).some(s => task.input[s].company_id === r.company_id && task.input[s].choices.some(c => c.document_id === r.document_id))),
  };
}
export function reportContext(draft: Draft) {
  const scopes: ContextScope[] = [];
  for (const f of draft.financial_facts) if (!scopes.some(s => s.side === f.side))
    scopes.push({ side: f.side, company_id: f.company_id, name: f.company_name, year: f.period });
  return { scopes, sources: sources(draft.evidence_appendix.selected_reports).filter(r => draft.financial_facts.some(f =>
    f.document_id === r.document_id && f.source_revision === r.source_revision && f.company_id === r.company_id)) };
}
