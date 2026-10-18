import { validateSource } from '../evidence/contracts.ts';
import type { Source } from '../evidence/contracts.ts';
import type { Task } from './operatingResearch.ts';

export type VerificationState = 'checking' | 'current' | 'unavailable' | 'invalidated';
export const verificationText: Record<VerificationState, string> = {
  checking: '正在核验当前来源与事实',
  current: '当前来源与事实有效',
  unavailable: '暂时无法核验当前来源与事实',
  invalidated: '来源或事实资格已失效',
};
export class VerificationInvalidated extends Error {}
const invalidationCodes = new Set(['source_changed', 'acceptance_revoked', 'selection_mismatch',
  'confirmation_integrity_error', 'report_identity_mismatch']);

// A broad "source error" or failed GET is not evidence of invalidation.
export function verificationFailure(error: unknown): 'unavailable' | 'invalidated' {
  if (error instanceof VerificationInvalidated) return 'invalidated';
  const e = error as { code?: string; status?: number } | null;
  return e && typeof e.status === 'number' && e.status >= 400 && e.status < 500
    && invalidationCodes.has(e.code || '') ? 'invalidated' : 'unavailable';
}
export function taskInvalidated(task: Task): boolean {
  return task.publication_eligibility?.status === 'invalidated'
    || invalidationCodes.has(task.error_code || '');
}
export function currentSource(value: Source, company: string, document: string, revision: string): Source {
  // Validate the entire response before treating a different version as reliable evidence.
  const source = validateSource(value, company, document);
  if (source.source_revision !== revision) throw new VerificationInvalidated('来源版本与冻结版本不一致。');
  return source;
}
export function invalidFactReason(reason: string | null | undefined): boolean {
  return invalidationCodes.has(reason || '');
}

// source_not_ready can be temporary. Only an immutable correction of this exact
// frozen attempt/metadata proves that its old qualification was invalidated.
export function correctionInvalidates(history: unknown, task: Task, company: string, document: string, revision: string): boolean {
  const documents = (task.snapshot as unknown as { documents?: Record<string, unknown>[] } | null)?.documents;
  if (!Array.isArray(history) || !Array.isArray(documents)) return false;
  const frozen = documents.find(d => d.document_id === document && d.company_id === company && d.source_revision === revision);
  const keys = ['company_id', 'report_year', 'report_type', 'basis', 'period_start', 'period_end'];
  if (!frozen || !/^[a-f0-9]{64}$/.test(String(frozen.content_sha256))
    || !/^[a-f0-9]{64}$/.test(revision) || typeof frozen.attempt !== 'number' || !Number.isSafeInteger(frozen.attempt) || frozen.attempt < 1
    || keys.some(key => frozen[key] === undefined)) return false;
  const oldAttempt = frozen.attempt;
  return history.some(row => row && row.document_id === document && row.action_kind === 'explicit_user_request'
    && /^[a-f0-9-]{36}$/.test(row.correction_id) && Number.isFinite(Date.parse(row.created_at))
    && row.old_attempt === oldAttempt && row.new_attempt === oldAttempt + 1
    && row.old_metadata_json?.document_id === document
    && keys.every(key => row.old_metadata_json?.[key] === frozen[key]));
}
