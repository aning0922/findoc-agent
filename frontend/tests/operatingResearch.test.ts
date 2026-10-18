import { test } from "node:test";
import assert from "node:assert/strict";
import {
  acceptRevision,
  resumeFacts,
  taskRequest,
  validateInput,
  validateTask,
  TaskError,
} from "../src/product/operatingResearch.ts";
import type { Task, TemplateInput } from "../src/product/operatingResearch.ts";
import type { Fact } from "../src/product/api.ts";
const uuid = "12345678-1234-1234-1234-123456789012",
  hash = "a".repeat(64),
  version = `disclosure-v1:${hash}`;
function input(): TemplateInput {
  const side = (year: number) => ({
    company_id: "actual-company",
    period: {
      year,
      start: `${year}-01-01`,
      end: `${year}-12-31`,
      period_type: "annual" as const,
    },
    choices: ["revenue", "net_profit_parent", "operating_cash_flow"].map(
      (metric_key) => ({
        metric_key,
        document_id: "document",
        disclosure_version: version,
        fact_id: null,
        fact_set_id: null,
      }),
    ),
  });
  return {
    schema_version: "operating-research-input-v1",
    template: "company_period_change",
    reports: [{ document_id: "document", expected_source_revision: hash }],
    first: side(2025),
    second: side(2024),
    direction: "business_overview",
  };
}
function task(): Task {
  return {
    schema_version: "persistent-template-task-v1",
    graph_version: "d19-operating-graph-v1",
    task_id: uuid,
    operation_id: uuid,
    revision: 20,
    created_at: "2026-10-10T12:00:00Z",
    status: "awaiting_human_confirmation",
    execution_status: "idle",
    input: input(),
    active_input: input(),
    budget: {
      schema_version: "template-budget-v1",
      limits: {
        steps: 32,
        tool_calls: 24,
        retrieval_total: 24,
        model_calls: 4,
      },
      used: { steps: 16, tool_calls: 13, retrieval_total: 0, model_calls: 0 },
      elapsed_seconds: 1,
      error_code: null,
    },
    trace: [],
    snapshot: null,
    waiting_checkpoint: true,
    error_code: null,
    persistence: "persisted",
    checkpointer: true,
    final_research_content: null,
  };
}
test("frozen inputs reject invented disclosure, invalid annual relationship and unpaired IDs", () => {
  assert.equal(validateInput(input()).template, "company_period_change");
  const v = input();
  v.first.choices[0].disclosure_version = "2025-report";
  assert.throws(() => validateInput(v));
  const x = input();
  x.first.choices[0].fact_id = "invented";
  assert.throws(() => validateInput(x));
  const y = input();
  y.second.period.year = 2025;
  assert.throws(() => validateInput(y));
});
test("D19 collecting_explanation never completed; failed or unqualified snapshots cannot publish", () => {
  assert.equal(validateTask(task()).status, "awaiting_human_confirmation");
  const t = task();
  t.status = "completed";
  assert.throws(() => validateTask(t));
  const t2 = task();
  t2.budget.used.tool_calls = 25;
  assert.throws(() => validateTask(t2));
  const t3 = task();
  t3.snapshot = {
    schema_version: "operating-research-plan-v1",
    status: t3.status,
    steps: [],
    facts: [],
    analysis_results: [{ amount: "10" }],
    operating_evidence: null,
    verified_operating_attribution: false,
    final_research_content: null,
    test_mode: null,
  };
  assert.throws(() => validateTask(t3));
});
test("revision ownership refuses other tasks and earlier snapshots", () => {
  const t = task();
  assert.equal(acceptRevision(t, { ...t, revision: 19 }), false);
  assert.equal(acceptRevision(t, { ...t, task_id: "different" }), false);
  assert.equal(acceptRevision(t, { ...t, revision: 21 }), true);
});
test("resume requires six qualified frozen-version IDs; amounts, invalid facts and ambiguous facts are insufficient", () => {
  const i = input();
  const fs = (["first", "second"] as const).flatMap((side) =>
    i[side].choices.map(
      (c) =>
        ({
          company_id: i[side].company_id,
          period: i[side].period.year,
          metric_key: c.metric_key,
          document_id: c.document_id,
          source_revision: hash,
          disclosure_version: version,
          fact_id: `${side}-${c.metric_key}`,
          fact_set_id: "set",
        }) as Fact,
    ),
  );
  assert.equal(resumeFacts(i, fs, {}, () => true).length, 6);
  assert.throws(() => resumeFacts(i, fs.slice(1), {}, () => true));
  assert.throws(() => resumeFacts(i, fs, {}, () => false));
  assert.throws(() =>
    resumeFacts(
      i,
      fs.map((f) => ({
        ...f,
        disclosure_version: `disclosure-v1:${"b".repeat(64)}`,
      })),
      {},
      () => true,
    ),
  );
  const duplicate = { ...fs[0], fact_id: "another" };
  assert.throws(() => resumeFacts(i, [...fs, duplicate], {}, () => true));
  assert.equal(
    resumeFacts(
      i,
      [...fs, duplicate],
      { "first:revenue": "another" },
      () => true,
    )[0].fact_id,
    "another",
  );
});
test("HTTP 202/409/503 business records decode; plain errors preserve unknown and never replay writes", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  try {
    for (const code of [202, 409, 503]) {
      const t = task();
      if (code === 202) {
        t.execution_status = "running";
        t.waiting_checkpoint = false;
      } else {
        t.status = code === 409 ? "refused" : "failed";
        t.waiting_checkpoint = false;
      }
      globalThis.fetch = async () => {
        calls++;
        return new Response(JSON.stringify(t), { status: code });
      };
      assert.equal(
        (
          await taskRequest("", new AbortController().signal, {
            operation_id: uuid,
            input: input(),
          })
        ).status,
        t.status,
      );
    }
    globalThis.fetch = async () => {
      calls++;
      return new Response(
        JSON.stringify({ error_code: "operation_request_conflict" }),
        { status: 409 },
      );
    };
    await assert.rejects(
      () => taskRequest("/by-operation/" + uuid, new AbortController().signal),
      TaskError,
    );
    assert.equal(calls, 4);
    globalThis.fetch = async () => {
      calls++;
      throw new TypeError("network lost");
    };
    await assert.rejects(() =>
      taskRequest("", new AbortController().signal, {
        operation_id: uuid,
        input: input(),
      }),
    );
    assert.equal(calls, 5);
  } finally {
    globalThis.fetch = original;
  }
});

function completedV2(): Task {
  const t = task();
  t.schema_version = "persistent-template-task-v2";
  t.graph_version = "d21-operating-graph-v2";
  t.status = "completed";
  t.waiting_checkpoint = false;
  t.budget.schema_version = "template-budget-v2";
  t.budget.limits = {steps:40, tool_calls:28, retrieval_total:24, model_calls:2};
  const content = {
    schema_version: "limited-operating-research-v2" as const,
    task_id: t.task_id, template:t.input.template, run_version: "d21-operating-graph-v2" as const,
    operating_descriptions:[{text:"公司主营家电业务。", verification:"exact_original_with_context", citation:{
      number:1, text:"公司主营家电业务。", physical_page:1, document_id:"document", source_revision:hash, company_id:"actual-company"}}],
    model_interpretations:[{text:"业务结构可能影响经营表现，需人工核验。",citations:[1],validation_status:"pending_semantic_review" as const,verified_operating_attribution:false as const}],
    unresolved_questions:["业务与经营变化之间的联系是否充分？"], limitations:["有限检索与待审语义"],
    human_review_status:"pending" as const,outcome:"completed" as const, verified_operating_attribution:false as const,test_mode:null,
  };
  t.final_research_content=content;
  t.snapshot={schema_version:"operating-research-plan-v2",status:t.status,steps:[],facts:[],analysis_results:[],
    operating_evidence:{status:"pending_review",citations:[content.operating_descriptions[0].citation]},
    verified_operating_attribution:false,final_research_content:content,test_mode:null};
  return t;
}
test("D21 v2 completed needs persisted provenance, pending semantics and version matching", () => {
  assert.equal(validateTask(completedV2()).status,"completed");
  for (const corrupt of [
    (t:Task) => {t.final_research_content=null;},
    (t:Task) => {t.budget.schema_version="template-budget-v1";},
    (t:Task) => {t.final_research_content!.operating_descriptions[0].text="模型自写的事实";},
    (t:Task) => {t.final_research_content!.operating_descriptions[0].citation.source_revision="foreign";},
    (t:Task) => {t.final_research_content!.model_interpretations[0].text="利润增加123亿元";},
    (t:Task) => {t.final_research_content!.model_interpretations[0].citations=[99];},
  ]) {
    const t=completedV2(); corrupt(t); assert.throws(() => validateTask(t));
  }
});
test("D21 failed, running unknown and v1 history never inherit another result", () => {
  assert.equal(validateTask(task()).graph_version,"d19-operating-graph-v1");
  const t=completedV2(); t.status="failed"; t.snapshot!.status="failed";
  assert.throws(() => validateTask(t));
  const unknown=completedV2(); unknown.status="collecting_explanation";unknown.snapshot!.status="collecting_explanation";
  unknown.execution_status="running";unknown.final_research_content=unknown.snapshot!.final_research_content=null;
  unknown.snapshot!.analysis_results=[]; unknown.snapshot!.operating_evidence=null;
  assert.equal(validateTask(unknown).execution_status,"running");
});

test("D21 HTTP v2 records decode without treating HTTP200 as unknown", async () => {
  const original=globalThis.fetch;
  globalThis.fetch=async () => new Response(JSON.stringify(completedV2()),{status:200});
  try { assert.equal((await taskRequest("",new AbortController().signal)).status,"completed"); }
  finally { globalThis.fetch=original; }
});

test("D21 rejects generated Chinese percentages, implicit doubling and Unicode amounts", () => {
  for (const text of ["营业收入增长七个百分点","归母利润增长百分之三","营收翻番","营收增加⑦亿元"]) {
    const t=completedV2();t.final_research_content!.model_interpretations[0].text=text;
    assert.throws(() => validateTask(t));
  }
});

test("D21 budget-only v2 task safely reads old NULL plan without completion", () => {
  const t=task();t.schema_version="persistent-template-task-v2";t.graph_version="d21-operating-graph-v2";
  t.budget.schema_version="template-budget-v2";t.budget.limits={steps:40,tool_calls:28,model_calls:2,retrieval_total:24};
  t.snapshot={schema_version:"operating-research-plan-v1",status:t.status,steps:[],facts:[],analysis_results:[],operating_evidence:null,
    verified_operating_attribution:false,final_research_content:null,test_mode:null};
  assert.equal(validateTask(t).snapshot!.schema_version,"operating-research-plan-v1");
  t.status="completed";t.snapshot.status="completed";assert.throws(() => validateTask(t));
});
