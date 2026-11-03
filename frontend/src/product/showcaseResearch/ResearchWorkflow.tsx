import { useEffect, useRef, useState } from "react";
type Mode = "synthesis" | "deep";
type Intent = {
  schema_version: string;
  intent_id: string;
  conversation_id: string;
  mode: string;
  goal: string;
  company_ids: string[];
  periods: number[];
  metric_keys: string[];
  clarifying_question: string | null;
  requires_confirmed_facts: boolean;
  provider_error?: string | null;
  scope: { scope_hash: string };
};
type Plan = {
  schema_version: string;
  plan_id: string;
  intent_id: string;
  conversation_id: string;
  mode: string;
  goal: string;
  revision: number;
  plan_sha256: string;
  company_ids: string[];
  periods: number[];
  metric_keys: string[];
  roles: string[];
  provider_error?: string | null;
  limits: Record<string, number>;
  scope: { scope_hash: string };
};
type Finding = {
  schema_version: string;
  finding_id: string;
  kind: string;
  text: string;
  source_status: string;
  transcription_review_status?: string;
  interpretation_review_status?: string;
  origin: string;
  financial_refs?: unknown[];
  numeric_claim_status?: string;
  unresolved_question?: string;
  actions?: { kind: string; label: string; href: string }[];
  evidence_refs?: Record<string, unknown>[];
};
type Job = {
  schema_version: string;
  job_id: string;
  plan_id: string;
  conversation_id: string;
  mode: string;
  state: string;
  created_at?: string;
  scope?: { scope_hash: string };
  error_code?: string | null;
  steps?: { agent_id: string; state: string; tools: string[] }[];
  usage?: Record<string, unknown>;
  result?: {
    schema_version: string;
    job_id: string;
    mode: string;
    scope_hash: string;
    data_origin: string;
    findings: Finding[];
    limitations: string[];
  } | null;
};
type Event = {
  schema_version: string;
  job_id: string;
  event_seq: number;
  label: string;
  state: string;
  agent_id: string;
  public_summary: string;
  event_type: string;
};
type Pending = {
  id: string;
  action: "intent" | "plan" | "job" | "handoff" | "draft" | "report";
  mode: Mode;
  conversationId: string;
  intentId?: string;
  planId?: string;
  jobId?: string;
};
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i,
  hash = /^[a-f0-9]{64}$/;
const key = (id: string) => `findoc:showcase-research-operation:${id}`;
function readPending(cid: string): {
  pending: Pending | null;
  blocked: boolean;
} {
  try {
    const x = JSON.parse(sessionStorage.getItem(key(cid)) || "null");
    if (
      x &&
      (!uuid.test(x.id) ||
        x.conversationId !== cid ||
        !["intent", "plan", "job", "handoff", "draft", "report"].includes(
          x.action,
        ) ||
        !["synthesis", "deep"].includes(x.mode) ||
        (x.intentId !== undefined && !uuid.test(x.intentId)) ||
        (x.planId !== undefined && !uuid.test(x.planId)) ||
        (x.jobId !== undefined && !uuid.test(x.jobId)))
    )
      throw Error();
    return { pending: x, blocked: false };
  } catch {
    return { pending: null, blocked: true };
  }
}
function same(a: unknown, b: unknown) {
  return JSON.stringify(a) === JSON.stringify(b);
}
async function api<T>(
  path: string,
  signal: AbortSignal,
  body?: object,
): Promise<T> {
  const r = await fetch("/api" + path, {
    signal,
    credentials: "same-origin",
    cache: "no-store",
    ...(body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  if (!r.ok) throw Error(`请求未完成（${r.status}），请只读查证。`);
  return r.json() as Promise<T>;
}
function validIntent(x: Intent, cid: string, mode: Mode) {
  return (
    x?.schema_version === "intent-v2" &&
    uuid.test(x.intent_id) &&
    x.conversation_id === cid &&
    x.mode === mode &&
    typeof x.goal === "string" &&
    typeof x.requires_confirmed_facts === "boolean" &&
    !!x.scope &&
    hash.test(x.scope.scope_hash) &&
    Array.isArray(x.company_ids) &&
    Array.isArray(x.periods) &&
    Array.isArray(x.metric_keys) &&
    (x.clarifying_question === null ||
      typeof x.clarifying_question === "string")
  );
}
function validPlan(x: Plan, intent: Intent, cid: string, mode: Mode) {
  return (
    x?.schema_version === "research-plan-v2" &&
    uuid.test(x.plan_id) &&
    x.intent_id === intent.intent_id &&
    x.conversation_id === cid &&
    x.mode === mode &&
    x.goal === intent.goal &&
    Number.isInteger(x.revision) &&
    x.revision > 0 &&
    hash.test(x.plan_sha256) &&
    same(x.company_ids, intent.company_ids) &&
    same(x.periods, intent.periods) &&
    same(x.metric_keys, intent.metric_keys) &&
    Array.isArray(x.roles) &&
    !!x.scope &&
    hash.test(x.scope.scope_hash) &&
    x.scope.scope_hash === intent.scope.scope_hash
  );
}
function validJob(x: Job, cid: string, mode: Mode, id?: string) {
  if (!(
    x?.schema_version === "showcase-job-v2" &&
    uuid.test(x.job_id) &&
    (!id || x.job_id === id) &&
    x.conversation_id === cid &&
    x.mode === mode &&
    ["queued", "running", "completed", "partial", "interrupted"].includes(
      x.state,
    )
  ))
    return false;
  if (x.result == null) return x.state !== "completed" && x.state !== "partial";
  return (
    ["completed", "partial"].includes(x.state) &&
    x.result.schema_version === "showcase-research-result-v2" &&
    x.result.job_id === x.job_id &&
    x.result.mode === mode &&
    !!x.scope &&
    hash.test(x.scope.scope_hash) &&
    x.result.scope_hash === x.scope.scope_hash &&
    ["live", "seed", "fake"].includes(x.result.data_origin) &&
    Array.isArray(x.result.limitations) &&
    Array.isArray(x.result.findings) &&
    x.result.findings.every(
      (f) =>
        f?.schema_version === "research-finding-v2" &&
        uuid.test(f.finding_id) &&
        typeof f.text === "string" &&
        [
          "confirmed_financial",
          "sourced_excerpt",
          "model_interpretation",
          "unresolved_question",
        ].includes(f.kind) &&
        ["current_valid", "not_applicable", "unresolved"].includes(
          f.source_status,
        ) &&
        Array.isArray(f.evidence_refs) &&
        Array.isArray(f.financial_refs) &&
        (f.kind !== "confirmed_financial" ||
          (f.origin === "deterministic_tool" &&
            f.source_status === "current_valid" &&
            !!f.financial_refs?.length)) &&
        (f.kind !== "sourced_excerpt" || !!f.evidence_refs?.length) &&
        (f.kind !== "unresolved_question" ||
          (typeof f.unresolved_question === "string" &&
            Array.isArray(f.actions) &&
            f.actions.every(
              (a) =>
                typeof a.kind === "string" &&
                typeof a.label === "string" &&
                typeof a.href === "string",
            ))) &&
        (f.kind !== "model_interpretation" ||
          ["no_numeric_claim", "numeric_claim_unverified"].includes(
            f.numeric_claim_status || "",
          )),
    )
  );
}
function evidenceHref(e: Record<string, unknown>, f: Finding) {
  if (
    f.source_status !== "current_valid" ||
    typeof e.company_id !== "string" ||
    typeof e.document_id !== "string" ||
    typeof e.source_revision !== "string" ||
    !hash.test(e.source_revision) ||
    typeof e.content_sha256 !== "string" ||
    !hash.test(e.content_sha256) ||
    !Number.isInteger(e.physical_page) ||
    Number(e.physical_page) < 1 ||
    !(
      (typeof e.text === "string" && !!e.text.trim()) ||
      (typeof e.excerpt === "string" && !!e.excerpt.trim())
    ) ||
    typeof e.parser_version !== "string" ||
    !e.parser_version ||
    typeof e.evidence_id !== "string" ||
    !e.evidence_id
  )
    return undefined;
  return `/evidence?${new URLSearchParams({ company: e.company_id, document: e.document_id, revision: e.source_revision, page: String(e.physical_page) })}`;
}
export function ResearchWorkflow({
  conversationId,
  mode,
  initialQuestion = "",
  initialJobId,
}: {
  conversationId: string;
  mode: Mode;
  initialQuestion?: string;
  initialJobId?: string;
}) {
  const [initialPending] = useState(() => readPending(conversationId));
  const [question, setQuestion] = useState(initialQuestion),
    [intent, setIntent] = useState<Intent | null>(null),
    [plan, setPlan] = useState<Plan | null>(null),
    [approved, setApproved] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [events, setEvents] = useState<Event[]>([]),
    [pollTick, setPollTick] = useState(0),
    [pending, setPending] = useState<Pending | null>(initialPending.pending),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(
      initialPending.blocked ? "本机会话操作线索无法读取，暂不发起写入。" : "",
    ),
    [draft, setDraft] = useState(""),
    [title, setTitle] = useState(""),
    [notes, setNotes] = useState(""),
    [report, setReport] = useState<{ id: string; revision: number } | null>(
      null,
    ),
    [history, setHistory] = useState<Job[]>([]),
    [taskId, setTaskId] = useState("");
  const epoch = useRef(0),
    lock = useRef(false),
    controller = useRef<AbortController | null>(null);
  const prefix = mode === "deep" ? "/deep-research" : "/synthesis";
  const blocked = initialPending.blocked;
  useEffect(() => {
    const n = ++epoch.current,
      c = new AbortController();
    if (uuid.test(conversationId))
      void api<{ schema_version: string; items: Job[] }>(
        `${prefix}/jobs?${new URLSearchParams({ conversation_id: conversationId })}`,
        c.signal,
      )
        .then((x) => {
          if (
            x.schema_version !== "showcase-job-list-v2" ||
            !Array.isArray(x.items) ||
            !x.items.every((j) => validJob(j, conversationId, mode))
          )
            throw Error("研究历史身份无法核验。");
          if (n === epoch.current) setHistory(x.items);
        })
        .catch((e) => {
          if (n === epoch.current && !c.signal.aborted)
            setMessage((e as Error).message);
        });
    if (initialJobId && uuid.test(initialJobId))
      void api<Job>(`${prefix}/jobs/${initialJobId}`, c.signal)
        .then((x) => {
          if (!validJob(x, conversationId, mode, initialJobId))
            throw Error("研究任务身份不匹配。");
          if (n === epoch.current) setJob(x);
        })
        .catch((e) => {
          if (n === epoch.current && !c.signal.aborted)
            setMessage((e as Error).message);
        });
    return () => {
      epoch.current++;
      c.abort();
      controller.current?.abort();
    };
  }, [conversationId, mode, initialJobId]);
  useEffect(() => {
    if (!job) return;
    const c = new AbortController(),
      n = epoch.current,
      id = job.job_id;
    let timer = 0;
    const poll = async () => {
      try {
        const [j, ev] = await Promise.all([
          api<Job>(`${prefix}/jobs/${id}`, c.signal),
          api<{
            schema_version: string;
            job_id: string;
            events: Event[];
            next_after_seq: number;
          }>(`${prefix}/jobs/${id}/events?after_seq=0`, c.signal),
        ]);
        if (
          !validJob(j, conversationId, mode, id) ||
          ev.schema_version !== "execution-events-v1" ||
          ev.job_id !== id ||
          !Array.isArray(ev.events) ||
          !ev.events.every(
            (e, i) =>
              e.schema_version === "execution-event-v1" &&
              e.job_id === id &&
              Number.isInteger(e.event_seq) &&
              e.event_seq > 0 &&
              (i === 0 || e.event_seq > ev.events[i - 1].event_seq) &&
              typeof e.label === "string" &&
              typeof e.state === "string",
          )
        )
          throw Error("研究事件身份无法核验。");
        if (n !== epoch.current) return;
        setJob(j);
        setEvents(ev.events);
        if (["queued", "running"].includes(j.state))
          timer = window.setTimeout(poll, 1500);
      } catch (e) {
        if (n === epoch.current && !c.signal.aborted)
          setMessage((e as Error).message);
      }
    };
    void poll();
    return () => {
      c.abort();
      window.clearTimeout(timer);
    };
  }, [job?.job_id, job?.state, conversationId, mode, pollTick]);
  const begin = () => {
    if (lock.current) return null;
    lock.current = true;
    setBusy(true);
    const n = epoch.current,
      c = new AbortController();
    controller.current = c;
    return { n, c };
  };
  const end = (n: number) => {
    if (n === epoch.current) {
      lock.current = false;
      setBusy(false);
      controller.current = null;
    }
  };
  function accept(
    action: Pending["action"],
    value: unknown,
    currentIntent: Intent | null = intent,
    currentPlan: Plan | null = plan,
    currentJob: Job | null = job,
  ) {
    if (!value || typeof value !== "object")
      throw Error("服务端结果无法核验。");
    const v = value as Record<string, unknown>;
    if (action === "intent") {
      const x = v as unknown as Intent;
      if (!validIntent(x, conversationId, mode))
        throw Error("提案会话或研究模式不匹配。");
      setIntent(x);
      setPlan(null);
      setJob(null);
      setEvents([]);
      setDraft("");
      setReport(null);
      setTitle("");
      setNotes("");
      setTaskId("");
    } else if (action === "plan") {
      const x = v as unknown as Plan;
      if (!currentIntent || !validPlan(x, currentIntent, conversationId, mode))
        throw Error("计划与提案范围不匹配。");
      setIntent(currentIntent);
      setPlan(x);
      setApproved(false);
    } else if (action === "job") {
      const x = v as unknown as Job;
      if (
        !currentPlan ||
        !currentIntent ||
        !validPlan(currentPlan, currentIntent, conversationId, mode) ||
        !validJob(x, conversationId, mode) ||
        x.plan_id !== currentPlan.plan_id
      )
        throw Error("任务与已确认计划不匹配。");
      setIntent(currentIntent);
      setPlan(currentPlan);
      setJob(x);
      setEvents([]);
      setDraft("");
      setReport(null);
      setTitle("");
      setNotes("");
    } else if (action === "handoff") {
      if (
        !currentIntent ||
        typeof v.task_id !== "string" ||
        !uuid.test(v.task_id) ||
        !(
          (v.schema_version === "research-handoff-v2" &&
            v.intent_id === currentIntent.intent_id &&
            v.automatic_confirmation === false &&
            v.automatic_resume === false) ||
          v.observed_by_read_only_lookup === true
        )
      )
        throw Error("任务交接身份无法核验。");
      setTaskId(v.task_id);
      setMessage("研究任务已创建，请从关联任务进入并由真人核对。");
    } else if (action === "draft") {
      const snapshot = v.snapshot as
        | {
            schema_version?: string;
            job_id?: string;
            state?: string;
            data_origin?: string;
            findings?: unknown[];
            workspace_id?: string;
          }
        | undefined;
      if (
        typeof v.draft_id !== "string" ||
        !uuid.test(v.draft_id) ||
        snapshot?.schema_version !== "verified-report-job-v2" ||
        snapshot?.job_id !== currentJob?.job_id ||
        snapshot?.state !== "completed" ||
        !["live", "seed", "fake"].includes(snapshot?.data_origin || "") ||
        !Array.isArray(snapshot?.findings) ||
        typeof snapshot?.workspace_id !== "string"
      )
        throw Error("报告草稿身份无法核验。");
      if (currentJob) setJob(currentJob);
      setDraft(v.draft_id);
    } else {
      const snapshot = v.snapshot as
        | {
            schema_version?: string;
            job_id?: string;
            state?: string;
            data_origin?: string;
            findings?: unknown[];
            workspace_id?: string;
          }
        | undefined;
      if (
        v.schema_version !== "showcase-report-v2" ||
        typeof v.report_id !== "string" ||
        !uuid.test(v.report_id) ||
        !Number.isInteger(v.revision) ||
        snapshot?.schema_version !== "verified-report-job-v2" ||
        snapshot?.state !== "completed" ||
        !["live", "seed", "fake"].includes(snapshot?.data_origin || "") ||
        !Array.isArray(snapshot?.findings) ||
        typeof snapshot?.workspace_id !== "string" ||
        snapshot?.job_id !== currentJob?.job_id
      )
        throw Error("报告版本身份无法核验。");
      if (currentJob) setJob(currentJob);
      setReport({ id: v.report_id, revision: Number(v.revision) });
    }
  }
  async function write(action: Pending["action"], path: string, body: object) {
    if (pending || blocked || !uuid.test(conversationId)) return;
    const t = begin();
    if (!t) return;
    const op: Pending = {
      id: crypto.randomUUID(),
      action,
      mode,
      conversationId,
      ...(intent ? { intentId: intent.intent_id } : {}),
      ...(plan ? { planId: plan.plan_id } : {}),
      ...(job ? { jobId: job.job_id } : {}),
    };
    let sent = false;
    try {
      sessionStorage.setItem(key(conversationId), JSON.stringify(op));
      setPending(op);
      sent = true;
      setMessage("正在处理；请勿重复提交。");
      const x = await api<unknown>(path, t.c.signal, {
        operation_id: op.id,
        ...body,
      });
      if (t.n !== epoch.current) return;
      accept(action, x);
      sessionStorage.removeItem(key(conversationId));
      setPending(null);
      if (action !== "handoff") setMessage("已保存；可继续下一步。");
    } catch (e) {
      if (t.n === epoch.current && !t.c.signal.aborted)
        setMessage(
          sent
            ? "操作结果未知，请保留原操作并只读查证。"
            : "无法保存操作身份，尚未提交。",
        );
    } finally {
      end(t.n);
    }
  }
  async function recover() {
    if (!pending || pending.conversationId !== conversationId) return;
    const t = begin();
    if (!t) return;
    try {
      const reportAction =
        pending.action === "draft" || pending.action === "report";
      const x = await api<{
        operation_id: string;
        state: string;
        result: unknown;
        error_code: string | null;
      }>(
        `${reportAction ? "/showcase-reports" : "/research"}/operations/${pending.id}`,
        t.c.signal,
      );
      if (t.n !== epoch.current) return;
      if (
        x.operation_id !== pending.id ||
        !["unknown", "completed", "failed"].includes(x.state)
      )
        throw Error("操作身份无法核验。");
      if (x.state === "unknown") {
        setMessage("操作仍未知，请稍后只读查询。");
        return;
      }
      if (x.state === "failed") {
        sessionStorage.removeItem(key(conversationId));
        setPending(null);
        setMessage("服务端记录操作失败，请检查范围后重新选择。");
        return;
      }
      if (pending.mode !== mode) throw Error("请切回原研究模式查询本次操作。");
      let recoveredIntent = intent,
        recoveredPlan = plan;
      if (
        ["plan", "job", "handoff"].includes(pending.action) &&
        !recoveredIntent &&
        pending.intentId
      ) {
        recoveredIntent = await api<Intent>(
          `/research/intents/${encodeURIComponent(pending.intentId)}`,
          t.c.signal,
        );
        if (!validIntent(recoveredIntent, conversationId, mode))
          throw Error("恢复的提案身份不匹配。");
      }
      if (pending.action === "job" && !recoveredPlan && pending.planId) {
        recoveredPlan = await api<Plan>(
          `/synthesis/plans/${encodeURIComponent(pending.planId)}`,
          t.c.signal,
        );
        if (
          !recoveredIntent ||
          !validPlan(recoveredPlan, recoveredIntent, conversationId, mode)
        )
          throw Error("恢复的计划身份不匹配。");
      }
      if (t.n !== epoch.current) return;
      let recoveredJob = job;
      if (reportAction && !recoveredJob && pending.jobId) {
        recoveredJob = await api<Job>(
          `${prefix}/jobs/${encodeURIComponent(pending.jobId)}`,
          t.c.signal,
        );
        if (
          !validJob(recoveredJob, conversationId, mode, pending.jobId) ||
          recoveredJob.state !== "completed"
        )
          throw Error("原研究任务当前不可核验。");
      }
      if (reportAction && !recoveredJob)
        throw Error("缺少原研究任务身份，请先只读核对报告历史。");
      if (t.n !== epoch.current) return;
      accept(
        pending.action,
        x.result,
        recoveredIntent,
        recoveredPlan,
        recoveredJob,
      );
      sessionStorage.removeItem(key(conversationId));
      setPending(null);
      setMessage("已只读恢复原操作结果。");
    } catch (e) {
      if (t.n === epoch.current && !t.c.signal.aborted)
        setMessage((e as Error).message);
    } finally {
      end(t.n);
    }
  }
  return (
    <div className="sr-card sr-workflow">
      <h3>{mode === "deep" ? "深度研究" : "综合研究"}</h3>
      <details open={!job}>
      <summary>{job ? "研究问题与已批准计划" : "准备研究问题与计划"}</summary>
      <label>
        研究问题
        <textarea
          aria-label="研究问题"
          value={question}
          maxLength={2000}
          disabled={busy || !!pending}
          onChange={(e) => {
            setQuestion(e.target.value);
            setIntent(null);
            setPlan(null);
            setApproved(false);
            setJob(null);
            setEvents([]);
            setDraft("");
            setReport(null);
            setTaskId("");
          }}
          placeholder="例如：梳理经营变化与风险"
        />
      </label>
      <button
        disabled={
          busy ||
          blocked ||
          !!pending ||
          !question.trim() ||
          !uuid.test(conversationId)
        }
        onClick={() =>
          void write("intent", "/research/intent", {
            conversation_id: conversationId,
            text: question,
            requested_mode: mode,
          })
        }
      >
        明确解析意图
      </button>
      {pending && (
        <div className="sr-notice">
          <p>
            上次操作结果待查证；不会自动重发。
            {pending.mode !== mode ? " 请切回原研究模式。" : ""}
          </p>
          <button disabled={busy} onClick={() => void recover()}>
            只读查询原操作
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {intent && (
        <section>
          <h3>研究提案</h3>
          <p>{intent.goal}</p>
          <p>
            企业：
            {intent.company_ids.length
              ? `已选择 ${intent.company_ids.length} 家`
              : "待明确"}{" "}
            · 期间：
            {intent.periods.join("、") || "待明确"} · 指标：
            {intent.metric_keys
              .map(
                (k) =>
                  (
                    ({
                      revenue: "营业收入",
                      net_profit_parent: "归母净利润",
                      operating_cash_flow: "经营现金流",
                      total_assets: "总资产",
                      total_liabilities: "总负债",
                      debt_asset_ratio: "资产负债率",
                    }) as Record<string, string>
                  )[k] || "待核对指标",
              )
              .join("、") || "未指定"}
          </p>
          {intent.provider_error && (
            <p>模型服务未完成意图解析，当前为规则提案，请核对范围。</p>
          )}
          {intent.clarifying_question && (
            <p>需要澄清：{intent.clarifying_question}</p>
          )}
          {intent.requires_confirmed_facts && (
            <p>需要已确认财务事实；缺失时应由真人在任务中核对。</p>
          )}
          <button
            disabled={busy || !!pending || !!intent.clarifying_question}
            onClick={() =>
              void write("plan", "/synthesis/plans", {
                intent_id: intent.intent_id,
              })
            }
          >
            明确准备研究计划
          </button>
          {(intent.requires_confirmed_facts && ((intent.company_ids.length === 1 && intent.periods.length === 2) || (intent.company_ids.length === 2 && intent.periods.length === 1)) && intent.metric_keys.every(key => ['revenue', 'net_profit_parent', 'operating_cash_flow'].includes(key))) && <>
          <button
            disabled={
              busy || !!pending || !!intent.clarifying_question || !!taskId
            }
            onClick={() =>
              void write("handoff", "/research/handoffs", {
                conversation_id: conversationId,
                intent_id: intent.intent_id,
                confirmed: true,
              })
            }
          >
            明确准备财务核对任务
          </button>
          </>}
        </section>
      )}
      {plan && (
        <section>
          <h3>研究计划</h3>
          <p>
            {plan.goal} ·{" "}
            {plan.roles
              .map(
                (role) =>
                  (
                    ({
                      evidence: "资料核对",
                      finance: "财务核对",
                      risk_operations: "经营风险",
                      generalist: "综合研究",
                    }) as Record<string, string>
                  )[role] || "研究步骤",
              )
              .join("、")}
          </p>
          <p>
            范围已由服务端固定；模型调用预算上限{" "}
            {plan.limits?.model_attempts ?? "待确认"} 次。
          </p>
          {plan.provider_error && (
            <p>模型规划未完成，当前为受控规则计划，请核对后再决定。</p>
          )}
          <label>
            <input
              type="checkbox"
              checked={approved}
              onChange={(e) => setApproved(e.target.checked)}
            />{" "}
            我已阅读并确认此计划
          </label>
          <button
            disabled={busy || !!pending || !approved || !!job}
            onClick={() =>
              void write("job", `${prefix}/jobs`, {
                approved_plan_id: plan.plan_id,
                approved_plan_revision: plan.revision,
                approved_plan_sha256: plan.plan_sha256,
                confirmed: true,
              })
            }
          >
            确认并开始研究
          </button>
        </section>
      )}
      {taskId && (
        <a
          href={`/research?${new URLSearchParams({ task: taskId, mode: "operating" })}`}
        >
          进入研究任务，由真人核对 →
        </a>
      )}
      </details>
      {job && (
        <section>
          <h3>研究进度</h3>
          <button type="button" onClick={() => setPollTick((x) => x + 1)}>
            只读刷新进度
          </button>
          <p>
            状态：
            {{
              queued: "已排队",
              running: "进行中",
              completed: "已完成",
              partial: "部分完成",
              interrupted: "已中断",
            }[job.state] || "待核对"}
          </p>
          {job.error_code && (
            <details>
              <summary>执行失败详情</summary>
              <p>{job.error_code}</p>
            </details>
          )}
          <details open={job.state === "queued" || job.state === "running"}><summary>真实执行轨迹 · {events.length} 个阶段事件</summary>
          <ol>
            {events.map((e) => (
              <li key={e.event_seq}>
                {({ search_evidence: "检索冻结资料", read_confirmed_facts: "读取已确认财务事实", recall_notes: "召回研究笔记" } as Record<string, string>)[e.label] || e.label} ·{" "}
                {e.state === "completed"
                  ? "完成"
                  : e.state === "running"
                    ? "进行中"
                    : e.state === "failed"
                      ? "失败"
                      : e.state}
              </li>
            ))}
          </ol></details>
          <details>
            <summary>执行分工与用量</summary>
            {job.steps?.map((s, i) => (
              <p key={i}>
                {(
                  {
                    evidence: "资料核对",
                    finance: "财务核对",
                    risk_operations: "经营风险",
                    generalist: "综合研究",
                  } as Record<string, string>
                )[s.agent_id] || "研究步骤"}{" "}
                ·{" "}
                {(
                  {
                    completed: "完成",
                    failed: "失败",
                    running: "进行中",
                    interrupted: "已中断",
                  } as Record<string, string>
                )[s.state] || "待核对"}{" "}
                ·{" "}
                {s.tools
                  ?.map(
                    (t) =>
                      (
                        ({
                          search_evidence: "检索资料",
                          read_confirmed_facts: "读取已确认事实",
                          recall_notes: "读取研究笔记",
                        }) as Record<string, string>
                      )[t] || "受控工具",
                  )
                  .join("、")}
              </p>
            ))}
            <p>
              工具调用：{String(job.usage?.tools ?? "未提供")}；未知结果：
              {String(job.usage?.unknown_attempts ?? "未提供")}
            </p>
            <p>
              模型调用：{String(job.usage?.attempts ?? "未提供")}
              ；实际 token 用量：
              {String(job.usage?.provider_tokens_actual ?? "未知")}
            </p>
          </details>
          {job.result && (
            <>
              <p>
                数据来源：
                {(
                  {
                    live: "本次运行",
                    seed: "预置样例",
                    fake: "模拟数据",
                  } as Record<string, string>
                )[job.result.data_origin] || "未标明"}{" "}
                · AI 解释待人工审阅
              </p>
              {job.result.limitations.length > 0 && (
                <details>
                  <summary>结果限制</summary>
                  {job.result.limitations.map((text, i) => (
                    <p key={i}>{text}</p>
                  ))}
                </details>
              )}
              <div className="sr-result-summary">
                <h3>综合解读</h3>
                <p>{job.result.findings.filter(f => f.kind === 'sourced_excerpt').length} 段原文 · {job.result.findings.filter(f => f.kind === 'confirmed_financial').length} 项已核准财务引用 · {job.result.findings.filter(f => f.kind === 'unresolved_question').length} 项待核实</p>
                {job.result.findings.filter(f => f.kind === 'model_interpretation').slice(-2).map(f => <article key={f.finding_id}><p>{f.text}</p><small>AI 解释待人工审阅{f.numeric_claim_status === 'numeric_claim_unverified' ? ' · 含待核实数字' : ''}</small>{f.evidence_refs?.map((ref, index) => { const href = evidenceHref(ref, f); return href ? <a key={index} href={href} target="_blank" rel="noreferrer">原 PDF · 物理第 {String(ref.physical_page)} 页 ↗</a> : null; })}</article>)}
                {!job.result.findings.some(f => f.kind === 'model_interpretation') && <p>本次尚未形成可发布的综合解读，请查看执行限制和待核实问题。</p>}
              </div>
              <details><summary>展开全部发现、原文及待核实项 · {job.result.findings.length} 条</summary>
              {job.result.findings.map((f) => (
                <article key={f.finding_id}>
                  <b>
                    {(
                      {
                        confirmed_financial: "已保存财务结论 · 当前资格须核验",
                        sourced_excerpt: "来源摘录",
                        model_interpretation: "AI 解释 · 待审",
                        unresolved_question: "待核实问题",
                      } as Record<string, string>
                    )[f.kind] || "待核实"}
                  </b>
                  <p>{f.text}</p>
                  <small>保存时来源：{f.source_status === 'current_valid' ? '核验通过' : f.source_status === 'not_applicable' ? '无原文资格主张' : '尚未核实'} · 转录：{f.transcription_review_status === 'human_reviewed' ? '已人工核对' : f.transcription_review_status === 'fast_extraction_unreviewed' ? '机器提取，待对照原文' : '不适用或待核验'} · 解释：{f.interpretation_review_status === 'ai_unreviewed' ? 'AI 草稿，待人工审阅' : f.interpretation_review_status === 'deterministic' ? '确定性规则结果' : '不适用'}</small>
                  {f.numeric_claim_status === "numeric_claim_unverified" && (
                    <p>数字陈述未核实</p>
                  )}
                  {f.unresolved_question && (
                    <p>下一步：{f.unresolved_question}</p>
                  )}
                  {f.actions
                    ?.filter(
                      (a) =>
                        a.kind === "review_sources" &&
                        a.href === "/research?mode=operating",
                    )
                    .map((a, i) => (
                      <a key={i} href={a.href}>
                        {a.label} →
                      </a>
                    ))}
                  {f.evidence_refs?.map((e, i) => {
                    const href = evidenceHref(e, f);
                    return href ? (
                      <a key={i} href={href} target="_blank" rel="noreferrer">
                        原 PDF · 物理第 {String(e.physical_page)} 页 ↗
                      </a>
                    ) : (
                      <span key={i}>来源暂不可定位 </span>
                    );
                  })}
                </article>
              ))}
              </details>
            </>
          )}
          {job.state === "completed" && job.result && (
            <section>
              <h3>研究报告</h3>
              <p>先创建报告草稿，再明确填写标题与备注；不创建财务确认。</p>
              <button
                disabled={busy || !!pending || !!draft}
                onClick={() =>
                  void write("draft", "/showcase-reports/drafts", {
                    job_id: job.job_id,
                  })
                }
              >
                准备报告草稿
              </button>
              {draft && (
                <>
                  <label>
                    报告标题
                    <input
                      maxLength={200}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    备注
                    <textarea
                      maxLength={8000}
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                    />
                  </label>
                  <button
                    disabled={busy || !!pending || !title.trim()}
                    onClick={() =>
                      void write("report", "/showcase-reports", {
                        draft_id: draft,
                        title,
                        notes,
                      })
                    }
                  >
                    明确创建报告
                  </button>
                </>
              )}
              {report && (
                <a
                  href={`/api/showcase-reports/${encodeURIComponent(report.id)}/revisions/${report.revision}/print`}
                  target="_blank"
                  rel="noreferrer"
                >
                  打开报告版本 {report.revision} ↗
                </a>
              )}
            </section>
          )}
        </section>
      )}
      {history.length > 0 && (
        <details>
          <summary>查看研究历史（只读）</summary>
          {history.map((j) => (
            <button
              key={j.job_id}
              onClick={() => {
                setJob(j);
                setEvents([]);
              }}
            >
              {j.state === "completed"
                ? "已完成"
                : j.state === "partial"
                  ? "部分完成"
                  : "查看任务"}{" "}
              · {j.created_at || "已保存"}
            </button>
          ))}
        </details>
      )}
    </div>
  );
}
