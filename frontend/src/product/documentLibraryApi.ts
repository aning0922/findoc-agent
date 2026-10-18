import { json } from './api.ts';
import { validateSource } from '../evidence/contracts.ts';
import type { Source } from '../evidence/contracts.ts';
export type Metadata = { company_id: string; report_year: number; report_type: 'annual'; basis: 'PRC_GAAP'; period_start: string; period_end: string };
export type DocumentRow = { document_id: string; source_file: string; status: string; safe_error_message?: string | null; metadata: Metadata | null };
export class UploadError extends Error {
  unknown: boolean;
  constructor(message: string, unknown = false) { super(message); this.unknown = unknown; }
}
export function annualMetadata(company: string, year: string): Metadata {
  if (!company || !/^[0-9]{1,4}$/.test(year) || Number(year) < 1 || Number(year) > 9999) throw new Error('请选择企业并输入有效报告年度。');
  const y = String(Number(year)).padStart(4, '0');
  return { company_id: company, report_year: Number(year), report_type: 'annual', basis: 'PRC_GAAP', period_start: `${y}-01-01`, period_end: `${y}-12-31` };
}
export async function listDocuments(signal: AbortSignal): Promise<DocumentRow[]> {
  const docs = await json<Omit<DocumentRow, 'metadata'>[]>('/documents', signal);
  if (!Array.isArray(docs)) throw new Error('资料目录读取不完整。');
  return Promise.all(docs.map(async d => {
    const r = await fetch(`/api/documents/${encodeURIComponent(d.document_id)}/metadata`, { signal, cache: 'no-store' });
    if (r.status === 404) return { ...d, metadata: null };
    if (!r.ok) throw new Error(`资料绑定读取失败（${r.status}），请刷新查询。`);
    return { ...d, metadata: await r.json() as Metadata };
  }));
}
export async function uploadReport(file: File, metadata: Metadata, signal: AbortSignal, sourceUrl = "") {
  const body = new FormData(); body.append('file', file); body.append('metadata', JSON.stringify({ ...metadata, source_url: sourceUrl || null }));
  let r: Response;
  try { r = await fetch('/api/report-documents', { method: 'POST', body, signal }); }
  catch { throw new UploadError('上传响应未知。请先刷新资料目录并核对绑定，系统不会自动重传。', true); }
  if (!r.ok) {
    const messages: Record<number, string> = { 404: '企业或资料不存在，请重新选择。', 409: '文件已有不同绑定或来源声明冲突，请核对企业、年度和原来源网址，也可直接使用已有资料。', 413: 'PDF 超出服务允许的大小。', 415: '文件不是有效的可读取 PDF。', 422: '企业、报告年度、期间或封面校验未通过，请核对后重新提交。' };
    throw new UploadError(messages[r.status] || '上传响应未知，可能留下未绑定资料。请只读刷新目录并核对。', r.status >= 500);
  }
  try {
    const v = await r.json();
    if (r.status !== 202 || typeof v.document_id !== 'string' || !v.document_id) throw new Error();
    return { document_id: v.document_id as string, duplicate: v.duplicate === true };
  } catch { throw new UploadError('上传回执不完整，结果未知。请只读刷新目录核对。', true); }
}
export async function readUploaded(id: string, expected: Metadata, signal: AbortSignal): Promise<{ status: string; source: Source | null }> {
  const [doc, meta] = await Promise.all([
    json<{ document_id: string; status: string; safe_error_message?: string }>(`/documents/${encodeURIComponent(id)}`, signal),
    json<Metadata>(`/documents/${encodeURIComponent(id)}/metadata`, signal),
  ]);
  if (doc.document_id !== id || Object.entries(expected).some(([k, v]) => meta[k as keyof Metadata] !== v)) throw new Error('上传资料的企业、年度或期间绑定不一致，尚未确认完成。');
  if (doc.status === 'failed') throw new Error(doc.safe_error_message || '资料处理失败，请核对资料后显式重试。');
  const source = doc.status === 'ready' ? validateSource(await json<Source>(`/documents/${encodeURIComponent(id)}/source?${new URLSearchParams({ company_id: expected.company_id })}`, signal), expected.company_id, id) : null;
  if (source && source.report_year !== expected.report_year) throw new Error('来源年度与绑定不一致。');
  return { status: doc.status, source };
}
