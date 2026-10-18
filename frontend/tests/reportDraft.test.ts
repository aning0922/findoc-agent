import test from "node:test";
import assert from "node:assert/strict";
import { validateDraft } from "../src/product/reportDraft.ts";
import type { Draft } from "../src/product/reportDraft.ts";
import type { Task } from "../src/product/operatingResearch.ts";
const task = { task_id: "saved-task", revision: 4 } as Task;
function body(): Draft { return { schema_version: "report-draft-v1", task_id: task.task_id, task_revision: 4, persisted: false, status: "simulated_draft", test_mode: "simulated_test", watermark: "simulated_test", financial_facts: Array(6).fill({}), financial_analysis: Array(3).fill({}), model_interpretations: [{ text: "待审", citations: [1], validation_status: "pending_semantic_review", verified_operating_attribution: false }] } as Draft; }
test("D22 simulation is visible only in the isolated UI", () => { assert.equal(validateDraft(body(), task, true).status, "simulated_draft"); assert.throws(() => validateDraft(body(), task, false)); });
test("D22 rejects task/revision/schema mismatch and incomplete facts", () => { for (const change of [{ task_id: "other" }, { task_revision: 5 }, { schema_version: "wrong" }, { persisted: true }, { financial_facts: [] }, { financial_analysis: [] }])
    assert.throws(() => validateDraft({ ...body(), ...change } as Draft, task, true)); });
test("D22 cannot remove watermarks or promote semantic review", () => { assert.throws(() => validateDraft({ ...body(), watermark: null }, task, true)); assert.throws(() => validateDraft({ ...body(), status: "qualified_draft" }, task, true)); const d = body(); d.model_interpretations[0].verified_operating_attribution = true as false; assert.throws(() => validateDraft(d, task, true)); });
