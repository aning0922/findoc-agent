import { json } from "./api.ts";
import type { Draft } from "./reportDraft.ts";
import { validateDraft } from "./reportDraft.ts";
import type { Task } from "./operatingResearch.ts";
export type Eligibility = { status: "current_at_read" | "invalidated"; reason: string | null; production_qualified?: boolean };
export type ReportDetail = {
  schema_version: "report-detail-v1";
  payload_sha256: string;
  current_revision: number;
  current_eligibility: Eligibility;
  report: {
    schema_version: "report-revision-v1";
    report_id: string; revision: number; parent_revision: number | null;
    operation_id: string; created_at: string; persisted: true;
    trusted_snapshot: Draft;
    editor_revision: { title: string | null; conclusions: string[]; origin: "user_edit";
      validation_status: "pending_semantic_review"; verified_operating_attribution: false;
      qualification_limit: "user_assertions_unverified" };
  };
};
export type HistoryItem = { report_id: string; current_revision: number; title: string; watermark: string | null; created_at?: string; task_id?: string; task_revision?: number; current_eligibility: Eligibility };
export function validateReport(value: ReportDetail, simulated: boolean): ReportDetail {
  const r = value.report, e = r.editor_revision;
  if (value.schema_version !== "report-detail-v1" || r.schema_version !== "report-revision-v1" || r.persisted !== true || !Number.isInteger(r.revision) || r.revision < 1 || r.parent_revision !== (r.revision > 1 ? r.revision - 1 : null) || value.current_revision < r.revision || !/^[a-f0-9]{64}$/.test(value.payload_sha256) || e.origin !== "user_edit" || e.validation_status !== "pending_semantic_review" || e.verified_operating_attribution !== false || e.qualification_limit !== "user_assertions_unverified")
    throw new Error("报告版本或编辑来源身份不一致");
  if (!Number.isSafeInteger(value.current_revision) || !['current_at_read', 'invalidated'].includes(value.current_eligibility.status)
      || (e.title !== null && (typeof e.title !== 'string' || !e.title || e.title.length > 200))
      || !Array.isArray(e.conclusions) || e.conclusions.length > 4 || e.conclusions.some(t => typeof t !== 'string' || !t || t.length > 2000))
    throw new Error('报告资格或用户编辑字段不完整');
  validateDraft(r.trusted_snapshot, { task_id: r.trusted_snapshot.task_id, revision: r.trusted_snapshot.task_revision } as Task, simulated);
  return value;
}
export class SaveRejected extends Error {}
// 5xx may follow a successful commit/readback failure. Only a definitive 4xx unlocks POST.
export async function saveReport(path: string, body: unknown, signal: AbortSignal): Promise<ReportDetail> {
  const response = await fetch(`/api${path}`, { method: "POST", signal, cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const value = await response.json();
  if (!response.ok) {
    if (response.status >= 400 && response.status < 500) throw new SaveRejected(value.error_code || `保存被拒绝（${response.status}）`);
    throw new Error("保存响应未知");
  }
  return value;
}

export async function readExactReport(id: string, revision: number, simulated: boolean, signal: AbortSignal, expectedSha?: string): Promise<ReportDetail> {
  if (!id || !Number.isSafeInteger(revision) || revision < 1) throw new Error('报告读取身份不完整');
  const value = validateReport(await json<ReportDetail>(`/reports/${encodeURIComponent(id)}/revisions/${revision}`, signal), simulated);
  signal.throwIfAborted();
  if (value.report.report_id !== id || value.report.revision !== revision || (expectedSha && value.payload_sha256 !== expectedSha)) throw new Error('报告版本身份或不可变内容不一致');
  return value;
}
