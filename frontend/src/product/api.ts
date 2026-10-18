import type { Candidate } from "../evidence/contracts.ts";
import { METRICS } from "../evidence/contracts.ts";
export interface Company {
  company_id: string;
  name: string;
  security_code: string;
  exchange: string;
}
export interface Report {
  document_id: string;
  source_file: string;
  status: string;
  company_id: string;
  report_year: number;
  report_type: string;
}
export interface Fact extends Candidate {
  fact_id: string;
  fact_set_id: string;
  disclosure_version: string;
  confirmation_kind: string;
  current_valid: boolean;
  invalid_reason?: string | null;
  production_calculable: boolean;
  calculable: boolean;
  integrity: string;
  unit: string;
  value_cny_yuan: string;
  period_start: string;
  period_end: string;
}
export interface FactQuery {
  schema: string;
  facts: Fact[];
  requires_version_selection: boolean;
  ambiguous_periods: string[];
  conflicting_periods: string[];
  automatic_selection: false;
}
export interface Reason {
  code: string;
  message: string;
}
export interface Analysis {
  schema: string;
  company_id: string;
  metric_key: string;
  status: "analyzed" | "partial" | "blocked";
  selection: { current: FactReference | null; previous: FactReference | null };
  current: Fact | null;
  previous: Fact | null;
  absolute_change: string | null;
  percentage_change: string | null;
  percentage_reason: string | null;
  reasons: Reason[];
  limitations: Reason[];
  sign_transition: string | null;
  production_calculable: boolean;
  confirmation_kind: string;
}
export interface FactReference {
  fact_set_id: string;
  fact_id: string;
  period: number;
  source_revision: string;
  disclosure_version: string;
}
export class ProductError extends Error {
  source: boolean;
  code: string;
  status: number;
  constructor(message: string, source = false, code = '', status = 0) {
    super(message);
    this.source = source;
    this.code = code;
    this.status = status;
  }
}
export async function json<T>(
  path: string,
  signal: AbortSignal,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      signal,
      cache: "no-store",
      ...(body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
  } catch (e) {
    if (signal.aborted) throw e;
    throw new ProductError("网络连接失败，请重试读取。");
  }
  const value = await response.json().catch(() => {
    throw new ProductError("服务响应无法读取。");
  });
  if (!response.ok) {
    if (!value.detail && ["financial-analysis-v1", "financial-company-comparison-v1"].includes(value.schema) && value.status === "blocked")
      return value as T;
    const code = typeof value.detail === 'string' ? value.detail : value.detail?.code || "";
    throw new ProductError(
      value.detail?.message || (code === 'source_changed' ? '来源版本已变化。' : '') ||
        `服务暂不可用（${response.status}${code ? ` · ${code}` : ""}）`,
      /source_|resource_not_found|pdf_|report_identity/.test(code),
      code,
      response.status,
    );
  }
  return value as T;
}
export function eligible(f: Fact): boolean {
  return (
    f.current_valid === true &&
    f.production_calculable === true &&
    f.confirmation_kind === "local_operator" &&
    f.calculable === true &&
    f.confirmation_status === "confirmed" &&
    f.integrity === "verified"
  );
}
export function reference(f: Fact): FactReference {
  return {
    fact_set_id: f.fact_set_id,
    fact_id: f.fact_id,
    period: f.period,
    source_revision: f.source_revision,
    disclosure_version: f.disclosure_version,
  };
}
export function sameReference(
  a: FactReference | null,
  b: FactReference,
): boolean {
  return (
    !!a &&
    Object.keys(b).every(
      (k) => a[k as keyof FactReference] === b[k as keyof FactReference],
    )
  );
}
export function validateQuery(q: FactQuery, company: string): FactQuery {
  if (
    q.schema !== "financial-fact-query-v1" ||
    !Array.isArray(q.facts) ||
    typeof q.requires_version_selection !== "boolean" ||
    !Array.isArray(q.ambiguous_periods) ||
    !Array.isArray(q.conflicting_periods) ||
    q.automatic_selection !== false
  )
    throw new ProductError("事实查询合同不完整，未展示金额。");
  const ids = new Set<string>();
  for (const f of q.facts) {
    if (
      f.company_id !== company ||
      !f.fact_id ||
      ids.has(f.fact_id) ||
      !f.fact_set_id ||
      !f.candidate_id ||
      !f.document_id ||
      !/^disclosure-v1:[a-f0-9]{64}$/.test(f.disclosure_version) ||
      !/^[a-f0-9]{64}$/.test(f.source_revision) ||
      !Number.isSafeInteger(f.period) ||
      !METRICS[f.metric_key] ||
      !/^-?\d+(\.\d+)?$/.test(f.value_cny_yuan) ||
      f.unit !== "CNY_YUAN" ||
      !Array.isArray(f.evidence) ||
      !f.evidence.length ||
      !Array.isArray(f.basis_evidence) ||
      !f.basis_evidence.length
    )
      throw new ProductError("事实身份、金额、单位或引用不完整，未展示金额。");
    ids.add(f.fact_id);
  }
  return q;
}
export interface DataAccess {
  label?: string;
  eligible: (f: Fact) => boolean;
  query: (company: string, signal: AbortSignal) => Promise<FactQuery>;
  analyze: (
    company: string,
    metric: string,
    current: Fact,
    previous: Fact,
    signal: AbortSignal,
  ) => Promise<Analysis>;
  analysisEligible: (a: Analysis) => boolean;
  compare: (a: string, b: string, period: number, rows: ComparisonSelection[], signal: AbortSignal) => Promise<Comparison>;
  comparisonEligible: (c: Comparison) => boolean;
}
export const productionAccess: DataAccess = {
  compare: (a, b, period, rows, signal) => json("/analyses/company-comparison", signal, comparisonBody(a,b,period,rows)),
  comparisonEligible: c => c.production_calculable && c.confirmation_kind === "local_operator",
  eligible,
  query: async (company, signal) =>
    validateQuery(
      await json<FactQuery>(
        `/financial-facts?company_id=${encodeURIComponent(company)}&include_invalid=true`,
        signal,
      ),
      company,
    ),
  analyze: (company, metric, current, previous, signal) =>
    json<Analysis>("/analyses", signal, {
      schema_version: "financial-analysis-v1",
      company_id: company,
      metric_key: metric,
      current: reference(current),
      previous: reference(previous),
    }),
  analysisEligible: (a) =>
    a.production_calculable === true &&
    a.confirmation_kind === "local_operator",
};
export function validateAnalysis(
  a: Analysis,
  company: string,
  metric: string,
  current: Fact,
  previous: Fact,
  access: DataAccess,
): Analysis {
  if (
    a.schema !== "financial-analysis-v1" ||
    a.company_id !== company ||
    a.metric_key !== metric ||
    !["analyzed", "partial", "blocked"].includes(a.status) ||
    !Array.isArray(a.reasons) ||
    !Array.isArray(a.limitations) ||
    !sameReference(a.selection?.current, reference(current)) ||
    !sameReference(a.selection?.previous, reference(previous))
  )
    throw new ProductError("分析响应与当前选择不一致，旧结果已撤下。");
  if (a.status === "blocked") {
    if (
      a.absolute_change !== null ||
      a.percentage_change !== null ||
      a.current !== null ||
      a.previous !== null
    )
      throw new ProductError("被阻断的分析包含数值，结果已撤下。");
    return a;
  }
  if (
    (a.status === "analyzed" &&
      (a.percentage_change === null || a.percentage_reason !== null)) ||
    (a.status === "partial" &&
      (a.percentage_change !== null ||
        !["zero_base", "non_adjacent_annual_periods"].includes(
          a.percentage_reason || "",
        )))
  )
    throw new ProductError("分析状态与百分比合同不一致，结果已撤下。");
  if (
    !access.analysisEligible(a) ||
    !a.current ||
    !a.previous ||
    !a.current.current_valid ||
    !a.previous.current_valid ||
    !sameReference(reference(a.current), reference(current)) ||
    !sameReference(reference(a.previous), reference(previous)) ||
    a.current.value_cny_yuan !== current.value_cny_yuan ||
    a.previous.value_cny_yuan !== previous.value_cny_yuan ||
    !/^-?\d+(\.\d+)?$/.test(a.absolute_change || "") ||
    (a.percentage_change !== null &&
      !/^-?\d+(\.\d+)?$/.test(a.percentage_change))
  )
    throw new ProductError("分析资格、金额或来源不一致，结果已撤下。");
  return a;
}
// Decimal strings remain strings. This moves a decimal point for display only, without rounding or arithmetic.
export function formatDecimal(value: string, shift = 0): string {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return "—";
  const negative = value.startsWith("-"),
    [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const padded = whole.padStart(shift + 1, "0"),
    split = padded.length - shift;
  const left = padded.slice(0, split).replace(/^0+(?=\d)/, "");
  const right = (padded.slice(split) + fraction).replace(/0+$/, "");
  return `${negative ? "-" : ""}${left.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${right ? `.${right}` : ""}`;
}

export interface ComparisonRow {
  metric_key: string;
  selection: { a: FactReference | null; b: FactReference | null };
  a: Fact | null;
  b: Fact | null;
  status: "compared" | "partial" | "blocked" | "incomplete";
  absolute_change: string | null;
  percentage_change: string | null;
  percentage_reason: string | null;
  reasons: Reason[];
  limitations: Reason[];
}
export interface Comparison {
  schema: string;
  company_a_id: string;
  company_b_id: string;
  period: number;
  rows: ComparisonRow[];
  confirmation_kind: string;
  production_calculable: boolean;
  automatic_selection: false;
  formula: {
    absolute_change_id: string;
    percentage_change_id: string;
    version: string;
    absolute_expression: string;
    percentage_expression: string;
    base: string;
  };
}
export type ComparisonSelection = { metric_key: string; a: Fact | null; b: Fact | null };
export function comparisonBody(a: string, b: string, period: number, rows: ComparisonSelection[]) {
  return {
    schema_version: "financial-company-comparison-v1",
    company_a_id: a, company_b_id: b, period,
    selections: rows.map(r => ({ metric_key: r.metric_key,
      a: r.a ? reference(r.a) : null, b: r.b ? reference(r.b) : null })),
  };
}
export function validateComparison(c: Comparison, a: string, b: string, period: number,
  selections: ComparisonSelection[], access: DataAccess): Comparison {
  if (c.schema !== "financial-company-comparison-v1" || c.company_a_id !== a ||
      c.company_b_id !== b || c.period !== period || c.automatic_selection !== false ||
      !Array.isArray(c.rows) || c.rows.length !== selections.length ||
      c.formula?.percentage_change_id !== "financial_company_relative_signed_base_v1" ||
      c.formula.absolute_change_id !== "financial_absolute_change_v1" ||
      c.formula.version !== "1" || c.formula.base !== "company_a" ||
      c.formula.absolute_expression !== "B - A" ||
      c.formula.percentage_expression !== "(B - A) / A * 100")
    throw new ProductError("比较响应身份或公式与当前选择不一致，已撤下结果。");
  const seen = new Set<string>();
  for (const r of c.rows) {
    const s = selections.find(s => s.metric_key === r.metric_key);
    if (!s || seen.has(r.metric_key) || !Array.isArray(r.reasons) || !Array.isArray(r.limitations) ||
        !["compared", "partial", "blocked", "incomplete"].includes(r.status))
      throw new ProductError("比较指标或状态合同不完整。");
    seen.add(r.metric_key);
    for (const side of ["a", "b"] as const) {
      const chosen = s[side], returned = r[side];
      if (chosen ? !sameReference(r.selection[side], reference(chosen)) : r.selection[side] !== null)
        throw new ProductError("比较事实选择不一致。");
      if (returned && (!chosen || !access.eligible(returned) ||
          returned.company_id !== (side === "a" ? a : b) || returned.period !== period ||
          returned.metric_key !== r.metric_key || !sameReference(reference(returned), reference(chosen)) ||
          returned.value_cny_yuan !== chosen.value_cny_yuan ||
          factsIdentity({ facts:[returned] } as FactQuery) !== factsIdentity({ facts:[chosen] } as FactQuery)))
        throw new ProductError("比较事实或来源无效。");
    }
    if (["blocked", "incomplete"].includes(r.status)) {
      if (r.absolute_change !== null || r.percentage_change !== null ||
          (r.status === "blocked" && (r.a !== null || r.b !== null)))
        throw new ProductError("不可比较指标含计算值。");
    } else if (!access.comparisonEligible(c) || !r.a || !r.b ||
        !/^-?\d+(\.\d+)?$/.test(r.absolute_change || "") ||
        (r.status === "compared" && (!/^-?\d+(\.\d+)?$/.test(r.percentage_change || "") || r.percentage_reason !== null)) ||
        (r.status === "partial" && (r.percentage_change !== null || r.percentage_reason !== "zero_base")))
      throw new ProductError("比较金额或计算资格不完整。");
  }
  return c;
}
// Explicit immutable identity + current validity, independent of ordering and incidental metadata.
export function factsIdentity(q: FactQuery): string {
  return JSON.stringify(q.facts.map(f => [f.company_id, f.fact_set_id, f.fact_id,
    f.period, f.metric_key, f.source_revision, f.disclosure_version, f.document_id,
    f.content_sha256, f.attempt, f.parser_version, f.current_valid, f.calculable,
    f.production_calculable, f.confirmation_kind, f.confirmation_status, f.integrity,
    f.value_cny_yuan, f.raw_value, f.raw_unit, f.currency, f.unit, f.scope,
    f.accounting_basis, f.period_start, f.period_end,
    f.evidence.map(e => [e.evidence_id, e.physical_page]),
    (f.basis_evidence || []).map(e => [e.evidence_id, e.physical_page])
  ]).sort((a,b) => String(a[2]).localeCompare(String(b[2]))));
}
// Display only: decimal-string truncation to 4 places; never an analysis operand.
export function compactYi(value: string): string {
  const exact = formatDecimal(value, 8), [left, right = ""] = exact.split(".");
  return `${right.length > 4 ? "≈ " : ""}${left}${right ? `.${right.slice(0, 4)}` : ""}`;
}
