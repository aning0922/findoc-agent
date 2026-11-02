import { checkSource, getJson, pinned } from '../evidence/api.ts';
import { sameSource, sourceKey, validateSource } from '../evidence/contracts.ts';
import type { Candidate, Source } from '../evidence/contracts.ts';
import type { Task } from './operatingResearch.ts';

// Read-only display hints. They never grant acceptance or qualify as facts.
export async function readResearchCandidates(task: Task, signal: AbortSignal): Promise<Record<string, Candidate>> {
  const entries = await Promise.all((['first', 'second'] as const).flatMap(side => {
    const input = task.active_input[side];
    const groups = new Map<string, typeof input.choices>();
    for (const choice of input.choices) {
      const key = `${choice.document_id}:${choice.disclosure_version}`;
      groups.set(key, [...(groups.get(key) || []), choice]);
    }
    return [...groups.values()].map(async choices => {
      const document = choices[0].document_id;
      const revision = task.input.reports.find(r => r.document_id === document)?.expected_source_revision;
      if (!revision) throw new Error('冻结来源不完整');
      const params = new URLSearchParams({ company_id: input.company_id, source_revision: revision });
      const source = validateSource(await getJson<Source>(`/documents/${encodeURIComponent(document)}/source?${params}`, signal), input.company_id, document, revision);
      const disclosure = await getJson<{ schema_version: string; source: Source; disclosure_versions: string[]; automatic_selection: boolean }>(`/research/disclosures/${encodeURIComponent(document)}?${params}`, signal);
      // A candidate endpoint is source-bound, not version-selectable. Do not
      // attribute candidates to a frozen choice when disclosure is ambiguous.
      if (disclosure.schema_version !== 'research-disclosure-options-v1' || disclosure.automatic_selection !== false || !sameSource(source, disclosure.source) || disclosure.source.report_year !== source.report_year || !Array.isArray(disclosure.disclosure_versions) || disclosure.disclosure_versions.length !== 1 || disclosure.disclosure_versions[0] !== choices[0].disclosure_version) throw new Error('披露来源需手动核对');
      const query = new URLSearchParams(pinned(source));
      choices.forEach(c => query.append('metric_keys', c.metric_key));
      query.append('periods', String(input.period.year));
      const result = await getJson<{ source: Source; candidates: Candidate[] }>(`/documents/${encodeURIComponent(document)}/financial-candidates?${query}`, signal);
      if (!sameSource(source, result.source) || result.source.report_year !== source.report_year || !Array.isArray(result.candidates) || result.candidates.length !== choices.length) throw new Error('候选来源或数量不匹配');
      const values: [string, Candidate][] = [];
      for (const choice of choices) {
        const found = result.candidates.filter(c => c.metric_key === choice.metric_key && c.period === input.period.year);
        if (found.length !== 1) throw new Error('候选指标或年度不匹配');
        const c = found[0];
        if (sourceKey(c) !== sourceKey(source) || c.content_sha256 !== source.content_sha256 || c.attempt !== source.attempt || c.parser_version !== source.parser_version || !Array.isArray(c.evidence)) throw new Error('候选身份不匹配');
        values.push([`${side}:${choice.metric_key}`, c]);
      }
      await checkSource(source, signal);
      return values;
    });
  }));
  return Object.fromEntries(entries.flat());
}
