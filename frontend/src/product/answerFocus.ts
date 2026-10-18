import type { ResearchRun } from './researchHistory.ts';
import { tableCells } from './excerptBlocks.ts';

export type AnswerFocus = {
  workspace_id: string; document_id: string; company_id: string; company_name: string;
  source_revision: string; parser_version: string; content_sha256: string; attempt: number;
  chunk_id: string; source_file: string; physical_page: number; report_year: number;
  financial_year: number; metric_key: string; citation_number: number; citation_sha256: string;
  table_id: string; table_sha256: string; table_text: string; table_text_sha256: string;
  row_index: number; column_index: number; header_row_index: number; metric_column_index: number;
  row_label: string; year_header: string; raw_value: string; raw_unit: string;
  original_row: string[]; original_header: string[];
  raw_cells: number[][]; unit_raw_cells: number[][]; year_raw_cells: number[][]; bbox: string[];
};
export type FocusProjection = {
  projection_version: 'trusted-answer-focus-v1'; run_id: string; query_sha256: string;
  run_integrity_sha256: string; answer_sha256: string; projection_sha256: string;
  status: 'located' | 'unlocated'; reason: string | null; focus: AnswerFocus | null;
};
export async function textSha(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}
function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical((v as Record<string, unknown>)[k])}`).join(',')}}`;
  return JSON.stringify(v);
}
const compact = (s: string) => s.replace(/\s+/g, '');
const hash = (v: string) => /^[a-f0-9]{64}$/.test(v);
/** Validate a server projection against this exact historical question and full citation.
 * Never find a value locally, repair a projection or accept one from another Run. */
export async function validateAnswerFocus(value: FocusProjection, run: ResearchRun): Promise<FocusProjection> {
  const { projection_sha256, ...payload } = value;
  if (value.projection_version !== 'trusted-answer-focus-v1' || value.run_id !== run.run_id
    || value.query_sha256 !== await textSha(run.query) || value.run_integrity_sha256 !== run.integrity_sha256
    || value.answer_sha256 !== await textSha(run.result?.content || '')
    || !hash(projection_sha256) || projection_sha256 !== await textSha(canonical(payload))) throw new Error('焦点身份不一致');
  if (value.status === 'unlocated') {
    if (value.focus !== null || !value.reason) throw new Error('焦点响应不完整');
    return value;
  }
  const f = value.focus;
  const c = run.result?.citations.find(c => c.number === f?.citation_number);
  if (run.status !== 'answered' || value.status !== 'located' || value.reason !== null || !f || !c) throw new Error('焦点响应不完整');
  for (const key of ['document_id', 'company_id', 'source_revision', 'parser_version', 'chunk_id', 'physical_page', 'report_year', 'source_file'] as const) {
    if (f[key] !== c[key]) throw new Error('焦点来源不一致');
  }
  // Retain the stricter server-only identity fields in the reading layer as well.
  const identity = c as unknown as Record<string, unknown>;
  for (const key of ['workspace_id', 'content_sha256', 'attempt']) {
    if (identity[key] !== (f as unknown as Record<string, unknown>)[key]) throw new Error('焦点解析身份不一致');
  }
  if (!f.parser_version.startsWith('fast-pdf-v4;table-geometry-v2;') || !hash(f.table_id) || !hash(f.table_sha256)
    || f.citation_sha256 !== await textSha(c.text) || f.table_text_sha256 !== await textSha(f.table_text)
    || !c.text.split('\n').join('\n').includes(f.table_text) || !f.company_name || !f.metric_key
    || !Number.isSafeInteger(f.financial_year) || f.financial_year < 1 || f.financial_year > 9999
    || !['元', '千元', '万元', '亿元'].includes(f.raw_unit) || typeof f.raw_value !== 'string' || !f.raw_value.trim()) throw new Error('焦点证据不完整');
  const rows = f.table_text.split('\n').map(tableCells).filter((r): r is string[] => Boolean(r && !r.every(c => /^:?-{3,}:?$/.test(c))));
  if ([f.row_index, f.column_index, f.header_row_index, f.metric_column_index].some(n => !Number.isSafeInteger(n) || n < 0)
    || f.header_row_index >= f.row_index || !Array.isArray(f.original_row) || !Array.isArray(f.original_header)
    || JSON.stringify(rows[f.row_index]) !== JSON.stringify(f.original_row)
    || JSON.stringify(rows[f.header_row_index]) !== JSON.stringify(f.original_header)
    || f.original_row[f.metric_column_index] !== f.row_label || f.original_header[f.column_index] !== f.year_header
    || compact(f.original_row[f.column_index] || '') !== compact(f.raw_value)
    || !new RegExp(`^${f.financial_year}年(?:度)?$`).test(compact(f.year_header))
    || !compact(f.row_label).endsWith(`（${f.raw_unit}）`) && !compact(f.row_label).endsWith(`(${f.raw_unit})`)
    || ![f.raw_cells, f.unit_raw_cells, f.year_raw_cells].every(refs => Array.isArray(refs) && refs.length > 0 && refs.every(r => r.length === 2 && r.every(n => Number.isSafeInteger(n) && n >= 0)))
    || !Array.isArray(f.bbox) || f.bbox.length !== 4 || !f.bbox.every(n => typeof n === 'string' && n.trim() && Number.isFinite(Number(n)))) throw new Error('焦点行列不一致');
  return value;
}
