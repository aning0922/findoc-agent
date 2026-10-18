import { test } from "node:test";
import assert from "node:assert/strict";
import {
  intentOf,
  revalidateIntents,
  frozenTaskIntents,
} from "../src/product/sourceIntent.ts";
import type { Fact } from "../src/product/api.ts";
import type { Task } from "../src/product/operatingResearch.ts";
const fact = {
  company_id: "company",
  period: 2024,
  metric_key: "revenue",
  document_id: "chosen-document",
  source_revision: "frozen-source",
  disclosure_version: "explicit-disclosure",
  fact_set_id: "set",
  fact_id: "fact",
  current_valid: true,
} as Fact;
const eligible = (f: Fact) => f.current_valid;
test("restores only a complete earlier identity matched against current qualified server facts", () => {
  assert.deepEqual(revalidateIntents([intentOf(fact)], [fact], eligible), {
    "2024/revenue": "fact",
  });
  for (const field of [
    "company_id",
    "period",
    "metric_key",
    "document_id",
    "source_revision",
    "disclosure_version",
    "fact_set_id",
    "fact_id",
  ] as const) {
    assert.deepEqual(
      revalidateIntents(
        [{ ...intentOf(fact), [field]: field === "period" ? 2025 : "changed" }],
        [fact],
        eligible,
      ),
      {},
    );
  }
  assert.deepEqual(
    revalidateIntents(
      [intentOf(fact)],
      [{ ...fact, current_valid: false }],
      eligible,
    ),
    {},
  );
  assert.deepEqual(
    revalidateIntents(
      [{ company_id: "company", period: 2024 }],
      [fact],
      eligible,
    ),
    {},
  );
});
test("ambiguous identities and conflicting saved choices do not select a source", () => {
  assert.deepEqual(
    revalidateIntents([intentOf(fact)], [fact, fact], eligible),
    {},
  );
  const alternative = {
    ...fact,
    document_id: "newer-document",
    disclosure_version: "other-disclosure",
    fact_id: "other",
  };
  assert.deepEqual(
    revalidateIntents(
      [intentOf(fact), intentOf(alternative)],
      [fact, alternative],
      eligible,
    ),
    {},
  );
  assert.deepEqual(revalidateIntents([], [fact, alternative], eligible), {});
  assert.deepEqual(
    revalidateIntents([intentOf(fact)], [fact, alternative], eligible),
    { "2024/revenue": "fact" },
  );
});
function task(): Task {
  const input = {
    first: {
      company_id: "company",
      period: { year: 2024 },
      choices: [
        {
          metric_key: "revenue",
          document_id: "chosen-document",
          disclosure_version: "explicit-disclosure",
          fact_set_id: "set",
          fact_id: "fact",
        },
      ],
    },
    second: { company_id: "second", period: { year: 2024 }, choices: [] },
    reports: [
      {
        document_id: "chosen-document",
        expected_source_revision: "frozen-source",
      },
    ],
  };
  return { input, active_input: input } as unknown as Task;
}
test("server frozen intent does not follow a newer disclosure or another company", () => {
  const t = task();
  assert.deepEqual(frozenTaskIntents(t, "company", [fact], eligible), [
    intentOf(fact),
  ]);
  assert.deepEqual(frozenTaskIntents(t, "second", [fact], eligible), []);
  assert.deepEqual(
    frozenTaskIntents(
      t,
      "company",
      [{ ...fact, source_revision: "newer" }],
      eligible,
    ),
    [],
  );
  assert.deepEqual(
    frozenTaskIntents(
      { ...t, publication_eligibility: { status: "invalidated" } } as Task,
      "company",
      [fact],
      eligible,
    ),
    [],
  );
});
test("an explicit frozen document and disclosure can match a sole fact after independent persistence", () => {
  const t = structuredClone(task());
  t.active_input.first.choices[0].fact_id = null;
  t.active_input.first.choices[0].fact_set_id = null;
  assert.deepEqual(frozenTaskIntents(t, "company", [fact], eligible), [
    intentOf(fact),
  ]);
  assert.deepEqual(
    frozenTaskIntents(
      t,
      "company",
      [fact, { ...fact, fact_id: "another-receipt" }],
      eligible,
    ),
    [],
  );
});

import {
  recoverTaskSources,
  sourceCoverage,
} from "../src/product/sourceIntent.ts";
const scope = {
  company: "company",
  currentYear: 2025,
  previousYear: 2024,
  metrics: ["revenue", "net_profit_parent", "operating_cash_flow"],
};
function periodTask(): Task {
  const t = structuredClone(task());
  t.input.template = "company_period_change";
  t.active_input.first.period.year = 2025;
  t.active_input.second = {
    ...t.active_input.first,
    period: { ...t.active_input.first.period, year: 2024 },
  };
  return t;
}
test("explicit task owns its periods and leaves missing slots empty without local A", () => {
  const t = periodTask();
  const a = { ...fact, document_id: "old-A", fact_id: "A" };
  const current = { ...fact, period: 2025 };
  const r = recoverTaskSources(t, "company", [fact, current, a], eligible);
  assert.equal(r.scope.currentYear, 2025);
  assert.equal(r.scope.previousYear, 2024);
  assert.equal(r.choices["2024/revenue"], "fact");
  const partial = recoverTaskSources(
    t,
    "company",
    [current, a, { ...fact, current_valid: false }],
    eligible,
  );
  assert.deepEqual(partial.choices, { "2025/revenue": "fact" });
  const older = structuredClone(t);
  older.active_input.first.period.year = 2023;
  older.active_input.second.period.year = 2022;
  assert.deepEqual(recoverTaskSources(older, "company", [], eligible).scope, {
    company: "company",
    currentYear: 2023,
    previousYear: 2022,
    metrics: ["revenue"],
  });
  assert.throws(() => recoverTaskSources(t, "other-company", [fact], eligible));
});
test("current scope coverage ignores historical keys and requires exact current identities", () => {
  const historical = Array.from({ length: 8 }, (_, i) => ({
    ...fact,
    period: 2000 + i,
    fact_id: `old-${i}`,
  }));
  const all = [fact, ...historical];
  const intents = all.map(intentOf);
  const choices = revalidateIntents(intents, all, eligible);
  const coverage = sourceCoverage(scope, choices, intents, all, eligible);
  assert.equal(Object.keys(choices).length, 9);
  assert.equal(coverage.expected, 6);
  assert.equal(coverage.valid, 1);
  assert.equal(coverage.unresolved.length, 5);
  assert.equal(
    sourceCoverage(
      scope,
      choices,
      intents,
      [{ ...fact, source_revision: "rebuilt" }],
      eligible,
    ).valid,
    0,
  );
  assert.equal(
    sourceCoverage(
      scope,
      choices,
      intents,
      [{ ...fact, current_valid: false }],
      eligible,
    ).valid,
    0,
  );
});
test("multiple valid candidates and cleared storage never auto-select latest or equal amounts", () => {
  const b = {
    ...fact,
    fact_id: "B",
    document_id: "B",
    disclosure_version: "B",
  };
  const coverage = sourceCoverage(scope, {}, [], [fact, b], eligible);
  assert.equal(coverage.valid, 0);
  assert.equal(
    coverage.unresolved.find((s) => s.key === "2024/revenue")?.status,
    "ambiguous",
  );
  const t = periodTask();
  t.active_input.second.choices[0].fact_id = null;
  t.active_input.second.choices[0].fact_set_id = null;
  assert.deepEqual(
    recoverTaskSources(
      t,
      "company",
      [fact, { ...fact, fact_id: "other-receipt" }],
      eligible,
    ).choices,
    {},
  );
});
