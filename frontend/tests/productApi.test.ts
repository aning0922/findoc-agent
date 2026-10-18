import test from "node:test";
import assert from "node:assert/strict";
import {
  eligible,
  formatDecimal,
  productionAccess,
  reference,
  validateAnalysis,
  validateQuery,
} from "../src/product/api.ts";
import type { Fact, Analysis } from "../src/product/api.ts";
const f = {
  company_id: "c",
  document_id: "d",
  candidate_id: "candidate",
  fact_id: "f",
  fact_set_id: "s",
  period: 2025,
  metric_key: "revenue",
  source_revision: "a".repeat(64),
  disclosure_version: `disclosure-v1:${"b".repeat(64)}`,
  value_cny_yuan: "9007199254740993.005",
  unit: "CNY_YUAN",
  production_calculable: true,
  current_valid: true,
  calculable: true,
  confirmation_kind: "local_operator",
  integrity: "verified",
  confirmation_status: "confirmed",
  evidence: [{ evidence_id: "e", physical_page: 1 }],
  basis_evidence: [{ evidence_id: "basis", physical_page: 2 }],
} as Fact;
const p = { ...f, fact_id: "p", period: 2024 };
const query = {
  schema: "financial-fact-query-v1",
  facts: [f],
  automatic_selection: false as const,
  requires_version_selection: false,
  ambiguous_periods: [],
  conflicting_periods: [],
};
const a = {
  schema: "financial-analysis-v1",
  company_id: "c",
  metric_key: "revenue",
  status: "analyzed",
  selection: { current: reference(f), previous: reference(p) },
  current: f,
  previous: p,
  absolute_change: "0.00",
  percentage_change: "0.00",
  percentage_reason: null,
  sign_transition: "ordinary",
  reasons: [],
  limitations: [],
  production_calculable: true,
  confirmation_kind: "local_operator",
} as Analysis;
test("exact decimal formatting preserves values beyond JS precision and unit shift", () => {
  assert.equal(formatDecimal(f.value_cny_yuan), "9,007,199,254,740,993.005");
  assert.equal(formatDecimal(f.value_cny_yuan, 8), "90,071,992.54740993005");
  assert.equal(formatDecimal("-0.005", 8), "-0.00000000005");
  assert.equal(formatDecimal("0.00", 8), "0");
  assert.equal(formatDecimal("NaN"), "—");
});
test("production never admits simulated, invalid, pending, or damaged facts", () => {
  assert.equal(eligible(f), true);
  for (const change of [
    { confirmation_kind: "simulated_test" },
    { production_calculable: false },
    { current_valid: false },
    { integrity: "bad" },
    { confirmation_status: "pending" },
    { calculable: false },
  ])
    assert.equal(eligible({ ...f, ...change }), false);
});
test("query rejects foreign enterprise, broken provenance and duplicate IDs", () => {
  assert.equal(validateQuery(query, "c"), query);
  for (const facts of [
    [{ ...f, company_id: "other" }],
    [{ ...f, evidence: [] }],
    [{ ...f, source_revision: "" }],
    [f, f],
  ])
    assert.throws(() => validateQuery({ ...query, facts }, "c"));
});
test("analysis rejects stale versions, switched amounts, and production simulation", () => {
  assert.equal(validateAnalysis(a, "c", "revenue", f, p, productionAccess), a);
  for (const result of [
    {
      ...a,
      selection: {
        ...a.selection,
        current: { ...reference(f), disclosure_version: "other" },
      },
    },
    { ...a, current: { ...f, value_cny_yuan: "0" } },
    { ...a, production_calculable: false, confirmation_kind: "simulated_test" },
  ])
    assert.throws(() =>
      validateAnalysis(
        result as Analysis,
        "c",
        "revenue",
        f,
        p,
        productionAccess,
      ),
    );
});
test("zero and non-adjacent partial results keep null percentages", () => {
  for (const reason of ["zero_base", "non_adjacent_annual_periods"]) {
    const partial = {
      ...a,
      status: "partial" as const,
      percentage_change: null,
      percentage_reason: reason,
    };
    assert.equal(
      validateAnalysis(partial, "c", "revenue", f, p, productionAccess)
        .percentage_change,
      null,
    );
  }
});
