import { validateResearchAnswer } from "./researchAnswer.ts";
import type { ResearchAnswer } from "./researchAnswer.ts";
export type ResearchRun = {
  schema_version: "research-run-v1"; run_id: string; operation_id: string;
  query: string; created_at: string; ended_at: string | null; document_ids: string[];
  documents: { document_id: string; company_id: string; report_year: number; source_revision: string }[];
  status: "running" | "answered" | "refused" | "system_error";
  result: ResearchAnswer | null; historical_snapshot: true; integrity_sha256: string;
  source_states: { document_id: string; source_revision: string; status: "current_at_read" | "expired" }[];
};
export type HistoryItem = Pick<ResearchRun, "run_id" | "operation_id" | "query" | "created_at" | "status" | "document_ids" | "documents">;
export type HistoryPage = { schema_version: "research-history-v1"; items: HistoryItem[]; next_cursor: string | null };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function validateRun(v: ResearchRun, identity: string, byOperation = false): ResearchRun {
  if (v.schema_version !== "research-run-v1" || !uuid.test(v.run_id) || !uuid.test(v.operation_id)
    || v[byOperation ? "operation_id" : "run_id"] !== identity || v.historical_snapshot !== true
    || !/^[a-f0-9]{64}$/.test(v.integrity_sha256) || !Array.isArray(v.documents)
    || !Array.isArray(v.document_ids) || !Array.isArray(v.source_states)
    || !["running", "answered", "refused", "system_error"].includes(v.status)) throw new Error("历史合同不完整");
  if (v.status === "running") {
    if (v.result !== null || v.ended_at !== null) throw new Error("运行状态冲突");
  } else {
    if (!v.result || !v.ended_at || v.result.outcome !== v.status) throw new Error("结果状态冲突");
    validateResearchAnswer(v.result, v.document_ids);
    if (v.result.outcome === "answered") {
      const r = v.result;
      const content = r.citations.map(c => `${c.report_year}年报《${c.source_file}》原文：\n${c.text}\n[${c.number}]`).join("\n\n");
      if (r.answer_mode !== "verified_excerpts" || r.human_review !== "pending" || content !== r.content
        || new Set(r.citations.map(c => c.number)).size !== r.citations.length) throw new Error("保存正文不是已验证摘录");
    }
  }
  if (JSON.stringify([...v.document_ids].sort()) !== JSON.stringify(v.documents.map(d => d.document_id).sort())
    || v.source_states.length !== v.documents.length || new Set(v.source_states.map(s => s.document_id)).size !== v.documents.length
    || v.source_states.some(s => !["current_at_read", "expired"].includes(s.status)
      || !v.documents.some(d => d.document_id === s.document_id && d.source_revision === s.source_revision))) throw new Error("历史来源状态不完整");
  return v;
}
export function validateHistory(v: HistoryPage): HistoryPage {
  if (v.schema_version !== "research-history-v1" || !Array.isArray(v.items)
    || !(v.next_cursor === null || typeof v.next_cursor === "string")
    || new Set(v.items.map(i => i.run_id)).size !== v.items.length
    || v.items.some(i => !uuid.test(i.run_id) || typeof i.query !== "string" || !Array.isArray(i.documents)
      || !["running", "answered", "refused", "system_error"].includes(i.status))) throw new Error("历史列表不完整");
  return v;
}
