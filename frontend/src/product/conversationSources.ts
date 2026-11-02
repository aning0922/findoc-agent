// This is the existing research-source-options-v1 contract, not a Conversation DTO.
export interface ConversationSourceOption {
  document_id: string;
  company_id: string;
  report_year: number;
  report_type: string;
  source_file: string;
  status: string;
  selectable: boolean;
  reason: string | null;
}
export interface ConversationSourceOptions {
  schema_version: 'research-source-options-v1';
  max_selected_documents: number;
  documents: ConversationSourceOption[];
}
export function validateConversationSources(input: unknown): ConversationSourceOptions {
  if (!input || typeof input !== 'object') throw new Error('年报目录响应不完整。');
  const v = input as ConversationSourceOptions;
  if (v.schema_version !== 'research-source-options-v1' || !Number.isSafeInteger(v.max_selected_documents)
    || v.max_selected_documents < 1 || !Array.isArray(v.documents)
    || new Set(v.documents.map(d => d?.document_id)).size !== v.documents.length
    || v.documents.some(d => !d || typeof d.document_id !== 'string' || !d.document_id
      || typeof d.company_id !== 'string' || !d.company_id || !Number.isSafeInteger(d.report_year)
      || typeof d.source_file !== 'string' || typeof d.report_type !== 'string'
      || typeof d.status !== 'string' || typeof d.selectable !== 'boolean'
      || !(d.reason === null || typeof d.reason === 'string'))) throw new Error('年报目录响应不完整。');
  return v;
}
export function selectableConversationScope(options: ConversationSourceOptions | null, ids: readonly string[]): boolean {
  return !!options && ids.length >= 1 && ids.length <= Math.min(4, options.max_selected_documents)
    && new Set(ids).size === ids.length
    && ids.every(id => options.documents.some(d => d.document_id === id && d.selectable && d.report_type === 'annual'));
}
export async function readConversationSources(signal: AbortSignal): Promise<ConversationSourceOptions> {
  const response = await fetch('/api/research/sources', { signal, cache: 'no-store' });
  if (!response.ok) throw new Error('年报目录暂不可读取，请重试读取。');
  return validateConversationSources(await response.json());
}
