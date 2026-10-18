import { test } from "node:test";
import assert from "node:assert/strict";
import { validateHistory, validateRun } from "../src/product/researchHistory.ts";
import type { ResearchRun } from "../src/product/researchHistory.ts";
const id = "00000000-0000-4000-8000-000000000001";
const doc = { document_id: "d", company_id: "c", source_revision: "a".repeat(64), report_year: 2025 };
function saved(): ResearchRun {
  return { schema_version: "research-run-v1", run_id: id, operation_id: id,
    query: "q", created_at: "2026-10-10T00:00:00Z", ended_at: "2026-10-10T00:00:01Z", document_ids: ["d"], documents: [doc],
    status: "answered", historical_snapshot: true, integrity_sha256: "b".repeat(64),
    source_states: [{ document_id: "d", source_revision: doc.source_revision, status: "current_at_read" }],
    result: { schema_version: "research-answer-v1", selection_id: "c".repeat(64), documents: [doc],
      outcome: "answered", answer_mode: "verified_excerpts", human_review: "pending", content: "2025年报《report.pdf》原文：\n原文\n[1]",
      citations: [{ ...doc, number: 1, chunk_id: "chunk", physical_page: 1, source_file: "report.pdf", text: "原文", kind: "paragraph" }] } };
}
test("saved exact excerpts and expired audit snapshots are distinct from current evidence", () => {
  const value = saved(); assert.equal(validateRun(value, id), value);
  value.source_states[0].status = "expired"; assert.equal(validateRun(value, id, true), value);
});
for (const mutate of [
  (v: ResearchRun) => { v.run_id = "foreign"; },
  (v: ResearchRun) => { v.result!.content = "raw unverified model output"; },
  (v: ResearchRun) => { v.result!.answer_mode = undefined; },
  (v: ResearchRun) => { v.result!.outcome = "refused"; },
  (v: ResearchRun) => { v.source_states = []; },
  (v: ResearchRun) => { v.status = "running"; },
]) test(`history rejects corruption ${mutate.toString()}`, () => { const v = saved(); mutate(v); assert.throws(() => validateRun(v, id)); });
test("bounded page adapter rejects duplicate result identities", () => {
  const page = { schema_version: "research-history-v1" as const, items: [saved()], next_cursor: null };
  assert.equal(validateHistory(page), page); page.items.push(saved()); assert.throws(() => validateHistory(page));
});
