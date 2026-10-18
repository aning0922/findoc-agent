import { researchFailureMessage } from "./recoveryMessages.ts";
import { eligible, json, validateQuery } from "./api.ts";
import type { Fact, FactQuery, Report } from "./api.ts";
import { METRICS, validateSource } from "../evidence/contracts.ts";
import type { Source } from "../evidence/contracts.ts";
export const metrics = Object.keys(METRICS);
export const sides = ["first", "second"] as const;
export type Side = (typeof sides)[number];
export type Template =
  | "company_period_change"
  | "company_same_period_comparison";
export type Choice = {
  metric_key: string;
  document_id: string;
  disclosure_version: string;
  fact_set_id: string | null;
  fact_id: string | null;
};
export type ResearchSide = {
  company_id: string;
  period: { year: number; start: string; end: string; period_type: "annual" };
  choices: Choice[];
};
export type TemplateInput = {
  schema_version: "operating-research-input-v1";
  template: Template;
  reports: { document_id: string; expected_source_revision: string }[];
  first: ResearchSide;
  second: ResearchSide;
  direction: "business_overview" | "products_and_operations";
};
export const taskLabels: Record<string, string> = {
  completed: "研究执行已完成",
  prepared: "核准资料",
  collecting_evidence: "读取指标状态",
  awaiting_human_confirmation: "等待人工确认",
  ready_for_analysis: "待确定性分析",
  analyzing: "分析中",
  collecting_explanation: "研究解释待完成",
  refused: "研究被拒绝",
  failed: "任务失败",
};
export type Budget = {
  schema_version: string;
  limits: Record<string, number>;
  used: Record<string, number>;
  elapsed_seconds: number;
  error_code: string | null;
};
export type LimitedContent = {
  schema_version: "limited-operating-research-v2";
  task_id: string;
  template: Template;
  run_version: "d21-operating-graph-v2";
  operating_descriptions: { text: string; citation: Record<string, unknown>; verification: string }[];
  model_interpretations: { text: string; citations: number[]; validation_status: "pending_semantic_review"; verified_operating_attribution: false }[];
  unresolved_questions: string[];
  limitations: string[];
  human_review_status: "pending";
  outcome: "completed";
  verified_operating_attribution: false;
  test_mode: "simulated_test" | null;
};
export type Task = {
  schema_version: string;
  graph_version: string;
  task_id: string;
  operation_id: string;
  revision: number;
  created_at: string;
  status: string;
  execution_status: "running" | "idle";
  input: TemplateInput;
  active_input: TemplateInput;
  budget: Budget;
  trace: { event: string; at: string; [key: string]: unknown }[];
  snapshot: {
    schema_version: string;
    status: string;
    steps: { step: string; status: string }[];
    facts: unknown[];
    analysis_results: Record<string, unknown>[];
    operating_evidence: {
      status: string;
      citations: Record<string, unknown>[];
    } | null;
    verified_operating_attribution: false;
    final_research_content: LimitedContent | null;
    test_mode: string | null;
  } | null;
  waiting_checkpoint: boolean;
  error_code: string | null;
  persistence: string;
  checkpointer: boolean;
  final_research_content: LimitedContent | null;
  parent_task_id?: string | null;
  execution_outcome?: string;
  publication_eligibility?: {status: string; reason: string | null};
};
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const hash = /^[a-f0-9]{64}$/;
export function validateInput(v: TemplateInput): TemplateInput {
  if (
    v?.schema_version !== "operating-research-input-v1" ||
    !["company_period_change", "company_same_period_comparison"].includes(
      v.template,
    ) ||
    !["business_overview", "products_and_operations"].includes(v.direction) ||
    !Array.isArray(v.reports) ||
    !v.reports.length ||
    v.reports.length > 4 ||
    new Set(v.reports.map((r) => r.document_id)).size !== v.reports.length ||
    v.reports.some(
      (r) => !r.document_id || !hash.test(r.expected_source_revision),
    )
  )
    throw new Error("模板资料合同无效");
  for (const side of sides) {
    const s = v[side],
      y = s?.period?.year,
      year = String(y).padStart(4, "0");
    if (
      !s?.company_id ||
      !Number.isInteger(y) ||
      y < 1 ||
      y > 9999 ||
      s.period.period_type !== "annual" ||
      s.period.start !== `${year}-01-01` ||
      s.period.end !== `${year}-12-31` ||
      !Array.isArray(s.choices) ||
      s.choices.length !== 3 ||
      new Set(s.choices.map((c) => c.metric_key)).size !== 3 ||
      s.choices.some(
        (c) =>
          !metrics.includes(c.metric_key) ||
          !v.reports.some((r) => r.document_id === c.document_id) ||
          !/^disclosure-v1:[a-f0-9]{64}$/.test(c.disclosure_version) ||
          (c.fact_id === null) !== (c.fact_set_id === null) ||
          (c.fact_id !== null && (!c.fact_id || !c.fact_set_id)),
      )
    )
      throw new Error("六项披露选择不完整");
  }
  if (
    v.template === "company_period_change"
      ? v.first.company_id !== v.second.company_id ||
        v.first.period.year <= v.second.period.year
      : v.first.company_id === v.second.company_id ||
        v.first.period.year !== v.second.period.year
  )
    throw new Error("企业与期间关系不符合模板");
  if (
    new Set(sides.flatMap((s) => v[s].choices.map((c) => c.document_id)))
      .size !== v.reports.length
  )
    throw new Error("来源集合不一致");
  return v;
}
function generatedNumberForbidden(text: string): boolean {
  return /[\d%％¥￥]|[零〇一二两三四五六七八九十百千万亿点负]+(?:个百分点|个点|元|亿|万|倍|成|分之)|百分之|翻番|翻倍/.test(text.normalize("NFKC"));
}
export function validateTask(v: Task, identity?: string): Task {
  const v2 = v?.schema_version === "persistent-template-task-v2";
  if (
    (!v2 && v?.schema_version !== "persistent-template-task-v1") ||
    v.graph_version !== (v2 ? "d21-operating-graph-v2" : "d19-operating-graph-v1") ||
    !uuid.test(v.task_id) ||
    !uuid.test(v.operation_id) ||
    (identity && v.task_id !== identity) ||
    !Number.isSafeInteger(v.revision) ||
    v.revision < 1 ||
    !taskLabels[v.status] ||
    !["running", "idle"].includes(v.execution_status) ||
    v.persistence !== "persisted" ||
    v.checkpointer !== true ||
    (!v2 && (v.final_research_content !== null || v.status === "completed")) ||
    !Array.isArray(v.trace)
  )
    throw new Error("任务身份或状态合同无效");
  validateInput(v.input);
  validateInput(v.active_input);
  const frozen = (input: TemplateInput) =>
    JSON.stringify([
      input.template,
      input.direction,
      [...input.reports].sort((a, b) =>
        a.document_id.localeCompare(b.document_id),
      ),
      ...sides.map((side) => [
        input[side].company_id,
        input[side].period,
        [...input[side].choices]
          .sort((a, b) => a.metric_key.localeCompare(b.metric_key))
          .map((c) => [c.metric_key, c.document_id, c.disclosure_version]),
      ]),
    ]);
  if (frozen(v.input) !== frozen(v.active_input))
    throw new Error("持久任务的冻结来源或披露被改变");
  const b = v.budget;
  if (
    b?.schema_version !== (v2 ? "template-budget-v2" : "template-budget-v1") ||
    !Number.isFinite(b.elapsed_seconds) ||
    b.elapsed_seconds < 0 ||
    ["steps", "tool_calls", "retrieval_total", "model_calls"].some(
      (k) =>
        !Number.isInteger(b.used[k]) ||
        !Number.isInteger(b.limits[k]) ||
        b.used[k] < 0 ||
        b.used[k] > b.limits[k],
    )
  )
    throw new Error("预算合同无效");
  const s = v.snapshot;
  if (
    v.waiting_checkpoint &&
    (v.status !== "awaiting_human_confirmation" ||
      v.execution_status !== "idle")
  )
    throw new Error("等待检查点不一致");
  if (
    s &&
    (!(v2 ? ["operating-research-plan-v2", "operating-research-plan-v1"] : ["operating-research-plan-v1"]).includes(s.schema_version) ||
      s.status !== v.status ||
      (!v2 && s.final_research_content !== null) ||
      s.verified_operating_attribution !== false ||
      !Array.isArray(s.steps) ||
      !Array.isArray(s.analysis_results) ||
      (!["collecting_explanation", "completed"].includes(v.status) &&
        (s.analysis_results.length || s.operating_evidence)))
  )
    throw new Error("结果资格合同无效");
  if (v2) {
    const content = v.final_research_content;
    if (s?.schema_version === "operating-research-plan-v1" && (content !== null || v.status === "completed"))
      throw new Error("旧计划快照不能取得 D21 完成资格");
    if ((v.status === "completed") !== !!content || JSON.stringify(content) !== JSON.stringify(s?.final_research_content ?? null))
      throw new Error("完成状态缺少持久化研究结果");
    if (content) {
      if (content.schema_version !== "limited-operating-research-v2" || content.task_id !== v.task_id ||
          content.run_version !== v.graph_version || content.template !== v.input.template || content.outcome !== "completed" ||
          content.human_review_status !== "pending" || content.verified_operating_attribution !== false ||
          !Array.isArray(content.operating_descriptions) || !content.operating_descriptions.length ||
          !Array.isArray(content.model_interpretations) || !Array.isArray(content.limitations) || !Array.isArray(content.unresolved_questions))
        throw new Error("有限研究结果合同无效");
      const numbers = new Set<number>();
      for (const d of content.operating_descriptions) {
        const c = d.citation;
        if (d.verification !== "exact_original_with_context" || d.text !== c.text || typeof c.number !== "number" ||
            !Number.isSafeInteger(c.physical_page) || Number(c.physical_page) < 1 ||
            !v.input.reports.some((r) => r.document_id === c.document_id && r.expected_source_revision === c.source_revision) ||
            !sides.some((side) => v.input[side].company_id === c.company_id && v.input[side].choices.some((x) => x.document_id === c.document_id)))
          throw new Error("经营描述或引用来源无效");
        numbers.add(c.number);
      }
      for (const i of content.model_interpretations)
        if (i.validation_status !== "pending_semantic_review" || i.verified_operating_attribution !== false ||
            generatedNumberForbidden(i.text) || !i.citations.length || i.citations.some((n) => !numbers.has(n)))
          throw new Error("模型解释含未允许数字或被错误提升为事实");
      if (content.unresolved_questions.some((q) => typeof q !== "string" || generatedNumberForbidden(q)))
        throw new Error("模型问题包含未允许的数值");
    }
  }
  return v;
}
export class TaskError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(errorLabel(code));
    this.code = code;
    this.status = status;
  }
}
export function errorLabel(code: string): string {
  if (code.startsWith("budget_") || ["operating_provider_unknown", "operating_output_invalid", "operating_model_unavailable", "operating_model_protocol_failed", "interrupted_unknown_execution", "task_save_or_execution_unknown"].includes(code))
    return researchFailureMessage(code);
  const labels: Record<string, string> = {
    operating_provider_unknown: "供应商响应未知；已预留的尝试不退款，不自动重发。请只读查证。",
    operating_output_invalid: "模型输出协议、数字或引用校验未通过，没有可发布研究结果。",
    operating_model_unavailable: "当前没有可用的经营研究模型，未生成研究结果。",
    late_task_response: "迟到的旧 revision 响应已拒绝，请再次只读刷新。",
    task_revision_conflict: "任务版本冲突，请重新读取当前 revision 后再操作。",
    operation_request_conflict:
      "操作 ID 冲突：该操作已用于其他请求。请只读查证。",
    task_busy: "任务正在执行，请等待任务刷新或重启读回。",
    acceptance_revoked: "确认凭证已撤销，旧事实和分析已撤下。",
    selection_mismatch:
      "事实披露版本与冻结选择不符，请重新选择来源并显式新建任务。",
    source_changed: "来源已过期，请重新选择来源并显式新建任务。",
    interrupted_unknown_execution: "运行中断且执行结果未知，请显式新建任务。",
    task_save_or_execution_unknown:
      "服务未能确认保存或执行结果，请按操作 ID 只读查询。",
    resource_not_found: "未找到任务或来源；不会自动再次提交。",
  };
  return labels[code] || `服务暂不可用或任务受限：${code}。请只读刷新查证。`;
}
export async function taskRequest(
  path: string,
  signal: AbortSignal,
  body?: unknown,
): Promise<Task> {
  const r = await fetch(`/api/research/tasks${path}`, {
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
  const v = await r.json();
  // D19 409/503 can carry a valid business terminal record. 202 is running/unknown.
  if (
    ["persistent-template-task-v1", "persistent-template-task-v2"].includes(v?.schema_version) &&
    [200, 202, 409, 503].includes(r.status)
  )
    return validateTask(v);
  throw new TaskError(
    v.error_code || v.detail?.code || `http_${r.status}`,
    r.status,
  );
}
export type Disclosure = {
  schema_version: string;
  source: Source;
  disclosure_versions: string[];
  automatic_selection: false;
};
export async function readDisclosure(
  report: Report,
  signal: AbortSignal,
): Promise<Disclosure> {
  const s = validateSource(
    await json<Source>(
      `/documents/${encodeURIComponent(report.document_id)}/source?company_id=${encodeURIComponent(report.company_id)}`,
      signal,
    ),
    report.company_id,
    report.document_id,
  );
  const q = new URLSearchParams({
    company_id: report.company_id,
    source_revision: s.source_revision,
  });
  const v = await json<Disclosure>(
    `/research/disclosures/${encodeURIComponent(report.document_id)}?${q}`,
    signal,
  );
  validateSource(
    v.source,
    report.company_id,
    report.document_id,
    s.source_revision,
  );
  if (
    v.schema_version !== "research-disclosure-options-v1" ||
    v.automatic_selection !== false ||
    !v.disclosure_versions.length ||
    v.disclosure_versions.some((d) => !/^disclosure-v1:[a-f0-9]{64}$/.test(d))
  )
    throw new Error("缺少可信披露版本选项");
  return v;
}
export async function queryFacts(
  company: string,
  signal: AbortSignal,
): Promise<FactQuery> {
  return validateQuery(
    await json(
      `/financial-facts?company_id=${encodeURIComponent(company)}&include_invalid=true`,
      signal,
    ),
    company,
  );
}
export function slotFacts(
  input: TemplateInput,
  side: Side,
  c: Choice,
  facts: Fact[],
  qualify = eligible,
): Fact[] {
  const s = input[side],
    rev = input.reports.find(
      (r) => r.document_id === c.document_id,
    )?.expected_source_revision;
  return facts.filter(
    (f) =>
      qualify(f) &&
      f.company_id === s.company_id &&
      f.period === s.period.year &&
      f.metric_key === c.metric_key &&
      f.document_id === c.document_id &&
      f.source_revision === rev &&
      f.disclosure_version === c.disclosure_version &&
      (!c.fact_id ||
        (c.fact_id === f.fact_id && c.fact_set_id === f.fact_set_id)),
  );
}
export function resumeFacts(
  input: TemplateInput,
  facts: Fact[],
  selected: Record<string, string>,
  qualify = eligible,
) {
  return sides.flatMap((side) =>
    input[side].choices.map((c) => {
      const options = slotFacts(input, side, c, facts, qualify),
        key = `${side}:${c.metric_key}`;
      const f =
        options.find((f) => f.fact_id === selected[key]) ||
        (options.length === 1 ? options[0] : null);
      if (!f)
        throw new Error(
          `尚未核准 ${side} / ${METRICS[c.metric_key]} 的有效事实 ID；披露不匹配需显式新建任务。`,
        );
      return {
        side,
        metric_key: c.metric_key,
        fact_set_id: f.fact_set_id,
        fact_id: f.fact_id,
      };
    }),
  );
}
export function acceptRevision(current: Task | null, next: Task): boolean {
  return (
    !current ||
    (current.task_id === next.task_id && next.revision >= current.revision)
  );
}
export function reviewUrl(
  company: string,
  document: string,
  revision: string,
): string {
  return `/evidence?${new URLSearchParams({ company, document, revision })}`;
}
