import { textSha } from './answerFocus.ts';
import type { ResearchRun } from './researchHistory.ts';
import type { Task, LimitedContent } from './operatingResearch.ts';
import type { Draft } from './reportDraft.ts';
import { externalReviewManifest, externalReviewManifestSha256 } from './d28ExternalReviews.ts';

type Evidence = { path: string; sha256: string; commit: string };
export type ExternalReview = {
  kind: 'qa' | 'operating'; record_id: string; workspace_id: string;
  target_sha256: string; sources: unknown[]; decision: 'pass' | 'approved_as_written' | 'approved_with_rewrite';
  reviewer_name: string | null; original_words: string; opinion: string; scope: string;
  recorded_at: string; evidence: Evidence[]; rewrite?: string | null;
  question_id?: string; run_id?: string; operation_id?: string; query_sha256?: string; answer_sha256?: string;
  task_id?: string; task_revision?: number; statement_index?: number; statement_sha256?: string; citations?: number[];
};
export type ReviewMatch = { status: 'matched' | 'absent' | 'mismatch'; records: ExternalReview[] };
export type OperatingReviewTarget = {
  workspace_id: unknown; task_id: string; task_revision: number; sources: unknown;
  descriptions: LimitedContent['operating_descriptions'];
  model_interpretations: LimitedContent['model_interpretations']; test_mode: LimitedContent['test_mode'];
};
const runFields = ['schema_version', 'execution_config_version', 'execution_config', 'run_id', 'operation_id',
  'workspace_id', 'query', 'document_ids', 'selection_id', 'documents', 'created_at', 'ended_at', 'status', 'result'];
/** Integer-only identity projection; keeps all source and citation fields and text bytes. */
export function canonicalReview(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalReview).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalReview((value as Record<string, unknown>)[k])}`).join(',')}}`;
  if (value === undefined) throw new Error('审阅目标身份缺失');
  return JSON.stringify(value);
}
export const reviewSha = (value: unknown) => textSha(canonicalReview(value));
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
async function manifestRecords(): Promise<ExternalReview[]> {
  const m = externalReviewManifest;
  if (m.schema_version !== 'd28-external-review-reading-v1'
    || await reviewSha(m) !== externalReviewManifestSha256
    || new Set(m.records.map(r => r.record_id)).size !== m.records.length) throw new Error('外部记录版本不可核验');
  const records = m.records as ExternalReview[];
  for (const r of records) {
    if (!hash(r.target_sha256) || !r.scope || !r.original_words || !r.opinion
      || !Number.isFinite(Date.parse(r.recorded_at)) || !/(?:Z|[+-]\d{2}:\d{2})$/.test(r.recorded_at)
      || !r.evidence.length || r.evidence.some(e => !hash(e.sha256) || e.commit !== m.source_commit
        || !e.path.startsWith('product/d28/') || e.path.includes('..'))
      || (r.kind === 'qa' ? r.decision !== 'pass' : !['approved_as_written', 'approved_with_rewrite'].includes(r.decision))
      || (r.decision === 'approved_with_rewrite' && !r.rewrite)) throw new Error('外部记录合同不完整');
  }
  return records;
}
const result = (status: ReviewMatch['status'], records: ExternalReview[] = []): ReviewMatch => ({ status, records });

export async function matchRunReview(run: ResearchRun): Promise<ReviewMatch> {
  try {
    const candidates = (await manifestRecords()).filter(r => r.kind === 'qa' && r.run_id === run.run_id);
    if (!candidates.length) return result('absent');
    const r = candidates[0], raw = run as unknown as Record<string, unknown>;
    const envelope = Object.fromEntries(runFields.map(k => [k, raw[k]]));
    if (candidates.length !== 1 || !run.result || run.historical_snapshot !== true
      || r.workspace_id !== raw.workspace_id || r.operation_id !== run.operation_id
      || r.query_sha256 !== await textSha(run.query) || r.answer_sha256 !== await textSha(run.result.content)
      || r.target_sha256 !== run.integrity_sha256 || r.target_sha256 !== await reviewSha(envelope)
      || canonicalReview(r.sources) !== canonicalReview(run.documents)
      || run.result.human_review !== (run.status === 'answered' ? 'pending' : null)) return result('mismatch');
    return result('matched', candidates);
  } catch { return result('mismatch'); }
}

export function taskReviewTarget(task: Task): OperatingReviewTarget | null {
  const c = task.final_research_content;
  if (!c) return null;
  const raw = task as unknown as Record<string, unknown>;
  const snapshot = task.snapshot as unknown as Record<string, unknown>;
  return { workspace_id: raw.workspace_id, task_id: task.task_id, task_revision: task.revision,
    sources: snapshot?.documents, descriptions: c.operating_descriptions,
    model_interpretations: c.model_interpretations, test_mode: c.test_mode };
}
export function reportReviewTarget(draft: Draft): OperatingReviewTarget {
  const sources = draft.evidence_appendix.selected_reports;
  const first = Array.isArray(sources) ? sources[0] as Record<string, unknown> : null;
  return { workspace_id: first?.workspace_id, task_id: draft.task_id, task_revision: draft.task_revision,
    sources, descriptions: draft.operating_information, model_interpretations: draft.model_interpretations,
    test_mode: draft.test_mode };
}
export async function matchOperatingReviews(target: OperatingReviewTarget | null): Promise<ReviewMatch> {
  if (!target) return result('absent');
  try {
    const candidates = (await manifestRecords()).filter(r => r.kind === 'operating' && r.task_id === target.task_id);
    if (!candidates.length) return result('absent');
    const digest = await reviewSha(target);
    for (const r of candidates) {
      const statement = target.model_interpretations[r.statement_index!];
      if (target.test_mode !== null || r.workspace_id !== target.workspace_id || r.task_revision !== target.task_revision
        || digest !== r.target_sha256 || canonicalReview(r.sources) !== canonicalReview(target.sources)
        || !statement || statement.validation_status !== 'pending_semantic_review' || statement.verified_operating_attribution !== false
        || r.statement_sha256 !== await textSha(statement.text) || canonicalReview(r.citations) !== canonicalReview(statement.citations)) return result('mismatch');
    }
    return result('matched', candidates);
  } catch { return result('mismatch'); }
}
