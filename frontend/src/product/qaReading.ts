import { excerptBlocks, verifiedTableVersion } from './excerptBlocks.ts';
import type { ResearchCitation } from './researchAnswer.ts';

/** Navigation view only: complete server-verified annual tables, never inferred cells or selected rows. */
export function annualTables(citation: Pick<ResearchCitation, 'text' | 'parser_version'>) {
  if (!verifiedTableVersion(citation.parser_version)) return [];
  return excerptBlocks(citation.text).filter(block => block.kind === 'table' && block.rows.length > 0
    && block.header.filter(cell => /^\d{4}年(?:末)?$/.test(cell)).length >= 2);
}
export function citationGroups(citations: ResearchCitation[]) {
  const groups = new Map<string, ResearchCitation[]>();
  for (const citation of citations) {
    const key = `${citation.document_id}:${citation.source_revision}`;
    const items = groups.get(key) || []; items.push(citation); groups.set(key, items);
  }
  return [...groups.values()];
}
