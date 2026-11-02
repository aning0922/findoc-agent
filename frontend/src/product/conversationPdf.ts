import { getJson, checkSource } from '../evidence/api.ts';
import { validateSource } from '../evidence/contracts.ts';
import type { Source } from '../evidence/contracts.ts';
import type { Action, ConversationSummary, SourceSnapshot } from './conversationTypes.ts';
import { safeConversationAction } from './conversationApi.ts';
export type ConversationPdfLocation = SourceSnapshot & { physical_page: number };
export type ConversationPdfCitation = Pick<SourceSnapshot, 'document_id' | 'company_id' | 'report_year' | 'source_revision' | 'parser_version'>
  & { physical_page: number; source_file: string; number?: number };
// A financial action is a location within the frozen scope, not an original-text
// EvidenceRef. Never manufacture a citation number, chunk, or excerpt for it.
export function conversationActionPdfLocation(action: Action, conversation: ConversationSummary): ConversationPdfLocation {
  if (action.kind !== 'open_source' || !safeConversationAction(action)) throw new Error('原 PDF 动作身份不完整。');
  const sources = conversation.sources.filter(s => s.document_id === action.document_id && s.source_revision === action.source_revision);
  if (sources.length !== 1) throw new Error('原 PDF 动作不属于会话冻结来源。');
  return { ...sources[0], physical_page: action.physical_page! };
}
// The shared PDF dialog then independently rechecks source and actual bytes.
export async function verifyConversationPdf(location: ConversationPdfLocation, signal: AbortSignal): Promise<Source> {
  if (!Number.isSafeInteger(location.physical_page) || location.physical_page < 1) throw new Error('物理页无效。');
  const q = new URLSearchParams({ company_id: location.company_id, source_revision: location.source_revision });
  const source = validateSource(await getJson<Source>(`/documents/${encodeURIComponent(location.document_id)}/source?${q}`, signal), location.company_id, location.document_id, location.source_revision);
  const metadata = source as Source & Pick<SourceSnapshot, 'report_type' | 'period_start' | 'period_end' | 'basis'>;
  if (source.content_sha256 !== location.content_sha256 || source.attempt !== location.attempt
    || source.parser_version !== location.parser_version || source.report_year !== location.report_year
    || metadata.report_type !== location.report_type || metadata.period_start !== location.period_start
    || metadata.period_end !== location.period_end || metadata.basis !== location.basis
    || location.physical_page > source.physical_pages) throw new Error('引用与冻结 PDF 来源不匹配。');
  await checkSource(source, signal, location.physical_page);
  return source;
}
export async function readConversationActionPdf(action: Action, conversation: ConversationSummary, signal: AbortSignal): Promise<ConversationPdfCitation> {
  const location = conversationActionPdfLocation(action, conversation);
  const source = await verifyConversationPdf(location, signal);
  // Source snapshots contain no filename. The existing document metadata GET is
  // display-only; no current fact, receipt or recalculation is needed for history.
  const document = await getJson<{ document_id: string; source_file: string; status: string }>(`/documents/${encodeURIComponent(location.document_id)}`, signal);
  if (document.document_id !== location.document_id || typeof document.source_file !== 'string' || !document.source_file.trim()
    || document.status !== 'ready') throw new Error('PDF 文件名或文档身份无法核验。');
  await checkSource(source, signal, location.physical_page);
  return { document_id: location.document_id, company_id: location.company_id, report_year: location.report_year,
    source_revision: location.source_revision, physical_page: location.physical_page,
    parser_version: location.parser_version, source_file: document.source_file };
}
