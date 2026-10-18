import test from "node:test";
import assert from "node:assert/strict";
import { validateResearchAnswer, researchPdfUrl } from "../src/product/researchAnswer.ts";
import type { ResearchAnswer } from "../src/product/researchAnswer.ts";
const rev = "a".repeat(64);
const result: ResearchAnswer = { schema_version: "research-answer-v1", selection_id: rev, outcome: "answered", content: "原文[1]",
  documents: [{ document_id: "d", company_id: "c", source_revision: rev }],
  citations: [{ number: 1, document_id: "d", company_id: "c", report_year: 2025, source_revision: rev, chunk_id: "same", physical_page: 7, source_file: "x.pdf", text: "原文", kind: "paragraph" }] };
test("selected answer validates every citation identity and pinned physical PDF link", () => {
  assert.equal(validateResearchAnswer(result, ["d"]), result);
  const url = researchPdfUrl(result.citations[0]);
  assert.ok(url.includes(`source_revision=${rev}`)); assert.ok(url.endsWith("#page=7"));
});
for (const changes of [{ document_id: "foreign" }, { company_id: "other" }, { source_revision: "old" }, { physical_page: 0 }])
  test(`reject citation mismatch ${JSON.stringify(changes)}`, () => {
    assert.throws(() => validateResearchAnswer({ ...result, citations: [{ ...result.citations[0], ...changes }] }, ["d"]));
  });
test("reject answer for obsolete selection and errors carrying candidate content", () => {
  assert.throws(() => validateResearchAnswer(result, ["other"]));
  assert.throws(() => validateResearchAnswer({ ...result, outcome: "system_error" }, ["d"]));
  assert.throws(() => validateResearchAnswer({ ...result, outcome: "refused" }, ["d"]));
});
