import { correctionInvalidates, currentSource, invalidFactReason, taskInvalidated, verificationFailure, verificationText, VerificationInvalidated } from './researchVerification.ts';
import type { VerificationState } from './researchVerification.ts';
import type { Readiness } from './ResearchTaskHeader.tsx';
import { resultReading } from "./resultReading.ts";
import { taskReviewPath } from "./researchJourney.ts";
import { receiptStates, type ReceiptState } from "./researchReceiptStatus.ts";
import { useCallback, useEffect, useRef, useState } from "react";
import { METRICS } from "../evidence/contracts.ts";
import type { Company, DataAccess, Fact, Analysis, Comparison } from "./api.ts";
import {
  json,
  ProductError,
  validateAnalysis,
  validateComparison,
  formatDecimal,
} from "./api.ts";
import { FactEvidence } from "./FactEvidence.tsx";
import {
  errorLabel,
  metrics,
  resumeFacts,
  sides,
  slotFacts,
  taskLabels,
} from "./operatingResearch.ts";
import { OperatingLimitedResult } from "./OperatingLimitedResult.tsx";
import { taskReviewTarget } from './externalReview.ts';
import type { Task } from "./operatingResearch.ts";
import type { ResearchSection } from './productRoutes.ts';
const stepLabels: Record<string, string> = {
  approve_input_and_sources: "核准资料",
  read_candidates_or_fact_status: "读取指标状态",
  verify_evidence_and_versions: "复验来源与版本",
  require_human_confirmation: "等待人工确认",
  deterministic_analysis: "确定性财务分析",
  retrieve_business_excerpts: "收集经营原文",
  validate_result_eligibility: "原文语义审阅",
  produce_versioned_limited_result: "研究解释待完成",
};
const stepStates: Record<string, string> = {
  validated_provenance_semantic_review_pending: "来源与协议通过 · 语义待审",
  done: "已执行",
  pending: "待执行",
  pending_review: "待人工审阅",
  pending_semantic_review: "语义审阅待完成",
  unsupported_until_d21: "D21 待实现",
  failed: "失败",
  insufficient_evidence: "证据不足",
};
export function TaskPanel({
  task,
  companies,
  access,
  busy,
  resume,
  readiness,
  initialSelection,
  section = 'operating',
  taskReadState = null,
}: {
  task: Task;
  companies: Company[];
  access: DataAccess;
  busy: boolean;
  resume: (selected: Record<string, string>) => Promise<void>;
  initialSelection?: Record<string, string>;
  section?: ResearchSection;
  taskReadState?: 'checking' | 'unavailable' | null;
  readiness?: (value: Readiness) => void;
}) {
  const [facts, setFacts] = useState<Fact[]>([]),
    [selected, setSelected] = useState<Record<string, string>>(
      initialSelection || {},
    );
  const [verification, setVerification] = useState<{ taskId: string; revision: number; state: VerificationState }>({ taskId: task.task_id, revision: task.revision, state: "checking" }),
    [failure, setFailure] = useState("");
  const guard: VerificationState = taskInvalidated(task) ? "invalidated" : taskReadState
    || (verification.taskId === task.task_id && verification.revision === task.revision ? verification.state : "checking");
  const setGuard = useCallback((state: VerificationState) => setVerification({ taskId: task.task_id, revision: task.revision, state }), [task.task_id, task.revision]);
  const [evidence, setEvidence] = useState<Fact | null>(null);
  const [issues, setIssues] = useState<Record<string, string>>({});
  const [receipts, setReceipts] = useState<Record<string, ReceiptState>>({});
  const [showAll, setShowAll] = useState(false);
  const owner = useRef(0);
  useEffect(() => {
    let disposed = false;
    let pending: AbortController | null = null;
    async function verify() {
      if (disposed || pending) return;
      const c = new AbortController();
      pending = c;
      const own = ++owner.current;
      let timedOut = false;
      const timeout = window.setTimeout(() => { timedOut = true; c.abort(); }, 15000);
      setGuard("checking");
      setEvidence(null);
      const currentIssues: Record<string, string> = {};
      try {
        const sourceReads = await Promise.allSettled(
          task.input.reports.map(async (r) => {
            const company = sides.find((s) =>
              task.input[s].choices.some(
                (c) => c.document_id === r.document_id,
              ),
            )!;
            const companyId = task.input[company].company_id;
            try { return currentSource(
              await json(
                `/documents/${encodeURIComponent(r.document_id)}/source?${new URLSearchParams({ company_id: companyId, source_revision: r.expected_source_revision })}`,
                c.signal,
              ),
              companyId,
              r.document_id,
              r.expected_source_revision,
            ); } catch (e) {
              if (e instanceof ProductError && e.status === 409 && e.code === 'source_not_ready') {
                const history = await json(`/documents/${encodeURIComponent(r.document_id)}/binding-corrections`, c.signal);
                if (correctionInvalidates(history, task, companyId, r.document_id, r.expected_source_revision))
                  throw new VerificationInvalidated('不可变来源纠错记录已确认冻结版本失效。');
              }
              throw e;
            }
          }),
        );
        const rejected = sourceReads.filter(r => r.status === 'rejected');
        const invalidation = rejected.find(r => verificationFailure(r.reason) === 'invalidated');
        if (invalidation) throw invalidation.reason;
        if (rejected.length) throw rejected[0].reason;
        const reportSources = sourceReads.map(r => (r as PromiseFulfilledResult<ReturnType<typeof currentSource>>).value);
        if (reportSources.length !== task.input.reports.length)
          throw new Error("来源资格不完整");
        const values = (
          await Promise.all(
            [...new Set(sides.map((s) => task.input[s].company_id))].map((id) =>
              access.query(id, c.signal),
            ),
          )
        ).flatMap((q) => q.facts);
        if (disposed || c.signal.aborted || own !== owner.current) return;
        for (const side of sides)
          for (const choice of task.active_input[side].choices) {
            const s = task.active_input[side],
              key = `${side}:${choice.metric_key}`;
            const matches = values.filter(
              (f) =>
                f.company_id === s.company_id &&
                f.period === s.period.year &&
                f.metric_key === choice.metric_key &&
                f.document_id === choice.document_id &&
                f.disclosure_version === choice.disclosure_version &&
                (!choice.fact_id || f.fact_id === choice.fact_id),
            );
            const invalid = matches.find((f) => f.invalid_reason);
            currentIssues[key] = invalid
              ? errorLabel(invalid.invalid_reason!)
              : matches.some(access.eligible)
                ? "该项 D10 事实有效；整任务资格仍需复验。"
                : "缺少符合当前准入要求的确认事实 ID。";
          }
        const relevant = values.filter(f => sides.some(side => task.active_input[side].choices.some(choice =>
          f.company_id === task.active_input[side].company_id && f.period === task.active_input[side].period.year
          && f.metric_key === choice.metric_key && f.document_id === choice.document_id
          && f.disclosure_version === choice.disclosure_version && (!choice.fact_id || f.fact_id === choice.fact_id))));
        if (relevant.some(f => invalidFactReason(f.invalid_reason)))
          throw new VerificationInvalidated('服务端已确认原事实的来源或接受资格失效。');
        if (relevant.some(f => f.invalid_reason)) throw new Error('事实资格暂不能完整复验。');
        setIssues(currentIssues);
        // A historical task GET is not new authorization. Current D10 IDs are required before publishing amounts.
        if (["collecting_explanation", "completed"].includes(task.status))
          resumeFacts(task.active_input, values, {}, access.eligible);
        const receiptStatus = Object.assign(
          {},
          ...(await Promise.all(
            reportSources.map(async (source) => {
              const status = await receiptStates(
                source,
                c.signal,
                !!access.label?.includes("simulated_test"),
                sides.filter(side => task.active_input[side].company_id === source.company_id)
                  .map(side => ({ year: task.active_input[side].period.year,
                    metrics: task.active_input[side].choices.filter(choice => choice.document_id === source.document_id).map(choice => choice.metric_key) }))
                  .filter(group => group.metrics.length > 0),
              );
              return Object.fromEntries(
                Object.entries(status).map(([key, value]) => [
                  `${source.document_id}:${key}`,
                  value,
                ]),
              );
            }),
          )),
        );
        if (disposed || c.signal.aborted || own !== owner.current) return;
        setReceipts(receiptStatus);
        setFacts(values);
        setGuard("current");
        setFailure("");
      } catch (e) {
        if (!disposed && (!c.signal.aborted || timedOut) && own === owner.current) {
          const state = verificationFailure(e);
          setGuard(state);
          setIssues(currentIssues);
          setEvidence(null);
          setFailure(state === 'invalidated'
            ? `服务端已确认来源或事实资格失效，旧金额与 PDF 引用已撤下。${(e as Error).message}`
            : `暂时无法核验当前来源与事实，暂停旧金额与引用的使用资格。原任务、操作与事实身份已保留，请只读重新核验。${timedOut ? '读取超时。' : (e as Error).message}`);
        }
      } finally {
        window.clearTimeout(timeout);
        if (pending === c) pending = null;
      }
    }
    // oxlint-disable-next-line react/set-state-in-effect
    setGuard("checking");
    setIssues({});
    setEvidence(null);
    void verify();
    const timer = window.setInterval(() => void verify(), 30000),
      focus = () => void verify();
    window.addEventListener("focus", focus);
    return () => {
      disposed = true;
      // Scalar ownership token, not a DOM ref: invalidate late responses on cleanup.
      // oxlint-disable-next-line react-hooks/exhaustive-deps
      owner.current++;
      pending?.abort();
      pending = null;
      clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, [task, access, setGuard]);
  let refs: ReturnType<typeof resumeFacts> | null = null,
    notReady = "";
  try {
    if (guard === "current")
      refs = resumeFacts(task.active_input, facts, selected, access.eligible);
  } catch (e) {
    notReady = (e as Error).message;
  }
  const terminal = ["failed", "refused"].includes(task.status),
    safe =
      guard === "current" &&
      !terminal &&
      task.execution_status === "idle" &&
      task.publication_eligibility?.status !== "invalidated";
  let results: {
    metric: string;
    first: Fact;
    second: Fact;
    absolute: string | null;
    percentage: string | null;
    formula: string;
    limitations: string[];
  }[] = [];
  let resultError = "";
  if (
    safe &&
    refs &&
    ["collecting_explanation", "completed"].includes(task.status)
  )
    try {
      const stored = task.snapshot?.analysis_results || [];
      if (stored.length !== 3) throw new Error("三项确定性分析合同不完整");
      results = metrics.map((metric) => {
        const a = facts.find(
            (f) =>
              f.fact_id ===
              refs!.find((r) => r.side === "first" && r.metric_key === metric)!
                .fact_id,
          )!,
          b = facts.find(
            (f) =>
              f.fact_id ===
              refs!.find((r) => r.side === "second" && r.metric_key === metric)!
                .fact_id,
          )!;
        if (task.input.template === "company_period_change") {
          const value = stored.find(
            (r) => r.metric_key === metric,
          ) as unknown as Analysis;
          const r = validateAnalysis(
            value,
            task.input.first.company_id,
            metric,
            a,
            b,
            access,
          );
          const formula = (
            value as Analysis & { formula: Comparison["formula"] }
          ).formula;
          if (
            formula?.absolute_change_id !== "financial_absolute_change_v1" ||
            formula.percentage_change_id !== "financial_yoy_signed_base_v1" ||
            formula.version !== "1" ||
            formula.absolute_expression !== "current - previous" ||
            formula.percentage_expression !==
              "(current - previous) / previous * 100"
          )
            throw new Error("服务端公式合同不完整");
          return {
            metric,
            first: a,
            second: b,
            absolute: r.absolute_change,
            percentage: r.percentage_change,
            formula: `${formula.absolute_change_id} / ${formula.percentage_change_id} v${formula.version} · ${formula.absolute_expression}；${formula.percentage_expression}`,
            limitations: [...r.reasons, ...r.limitations].map((r) => r.message),
          };
        }
        const value = stored.find((r) =>
          (r.rows as { metric_key: string }[])?.some(
            (r) => r.metric_key === metric,
          ),
        ) as unknown as Comparison;
        const c = validateComparison(
            value,
            task.input.first.company_id,
            task.input.second.company_id,
            task.input.first.period.year,
            [{ metric_key: metric, a, b }],
            access,
          ),
          r = c.rows[0];
        return {
          metric,
          first: a,
          second: b,
          absolute: r.absolute_change,
          percentage: r.percentage_change,
          formula: `${c.formula.absolute_change_id} / ${c.formula.percentage_change_id} v${c.formula.version} · ${c.formula.absolute_expression}；${c.formula.percentage_expression}`,
          limitations: [...r.reasons, ...r.limitations].map((r) => r.message),
        };
      });
    } catch (e) {
      resultError = (e as Error).message;
      results = [];
    }
  const canContinue = !!refs && safe;
  const blocked =
    guard === "invalidated" ||
    task.publication_eligibility?.status === "invalidated";
  const checklist = sides.map((side) => ({
    side,
    input: task.active_input[side],
    rows: task.active_input[side].choices.map((choice) => {
      const key = `${side}:${choice.metric_key}`;
      const options =
        guard === "current"
          ? slotFacts(task.active_input, side, choice, facts, access.eligible)
          : [];
      const chosen =
        options.find((f) => f.fact_id === selected[key]) ||
        (options.length === 1 ? options[0] : null);
      const receipt =
        receipts[
          `${choice.document_id}:${task.active_input[side].period.year}:${choice.metric_key}`
        ];
      const invalid =
        guard === "invalidated" ||
        facts.some(
          (f) =>
            f.company_id === task.active_input[side].company_id &&
            f.period === task.active_input[side].period.year &&
            f.metric_key === choice.metric_key &&
            f.document_id === choice.document_id &&
            f.disclosure_version === choice.disclosure_version &&
            f.invalid_reason,
        );
      return {
        key,
        choice,
        options,
        chosen,
        receipt,
        invalid,
        state:
          guard === "checking"
            ? "正在核验"
            : guard === 'unavailable'
              ? '暂时无法核验'
            : invalid
              ? "失效"
              : chosen
                ? "已入库"
                : receipt?.status === "accepted-unpersisted"
                  ? "已接受待入库"
                  : "待核对",
      };
    }),
  }));
  const completed = checklist
    .flatMap((g) => g.rows)
    .filter((r) => r.chosen).length;
  const unfinished = checklist.filter(g => g.rows.some(r => !r.chosen && !r.invalid));
  const recentSide = new URLSearchParams(location.hash.slice(1)).get('reviewed');
  const nextGroup = guard === 'current' ? unfinished.find(g => g.side === recentSide)
    || unfinished.find(g => g.rows.some(r => r.receipt && !r.chosen)) || unfinished[0] : undefined;
  const nextRow = nextGroup?.rows.find((r) => !r.chosen && !r.invalid);
  const nextHref =
    nextGroup && nextRow && guard === "current"
      ? nextRow.options.length > 1
        ? `#fact-${nextGroup.side}-${nextRow.choice.metric_key}`
        : taskReviewPath(task, nextGroup.side, nextRow.choice.metric_key)
      : "";
  const nextLabel =
    nextGroup && nextRow
      ? nextRow.options.length > 1
        ? "选择已核准事实"
        : `${nextRow.receipt?.status === "unknown" ? "查证接受结果：" : nextRow.state === "已接受待入库" ? "保存已接受数据：" : "核对"} ${nextGroup.input.period.year} 年财务数据`
      : "";
  function groupEntries(group: typeof checklist[number]) {
    const entries = new Map<string, typeof group.rows>();
    for (const row of group.rows) {
      const key = `${row.choice.document_id}:${row.choice.disclosure_version}`;
      entries.set(key, [...(entries.get(key) || []), row]);
    }
    return [...entries].filter(([, rows]) => rows.some(r => !r.chosen && !r.invalid && r.options.length <= 1)).map(([key, rows]) => ({ key, rows,
      href: taskReviewPath(task, group.side, rows.find(r => !r.chosen && !r.invalid && r.options.length <= 1)!.choice.metric_key),
      label: `${rows.some(r => r.receipt?.status === 'unknown') ? '查证接受结果' : rows.some(r => r.receipt?.status === 'accepted-unpersisted') ? '保存已接受数据' : '核对'} ${group.input.period.year} 年 · ${rows.length} 项数据`,
    }));
  }
  useEffect(() => {
    readiness?.({
      taskId: task.task_id,
      revision: task.revision,
      ready: canContinue,
      checked: guard === "current" || guard === "invalidated",
      verification: guard,
      selected,
      next: nextHref ? { href: nextHref, label: nextLabel } : undefined,
      completed,
      blocked,
    });
  }, [
    task.task_id,
    task.revision,
    canContinue,
    guard,
    selected,
    readiness,
    nextHref,
    nextLabel,
    completed,
    blocked,
  ]);
  const b = task.budget;
  const factList = (
    <section
      id="research-facts"
      tabIndex={-1}
      className="operating-card"
      aria-label="六项事实准备状态"
    >
      <div className="operating-heading">
        <h2>六项财务核对清单</h2>
        <strong>{guard === 'current' ? `${completed} / 6 项已入库` : verificationText[guard]}</strong>
      </div>
      <p className="muted">
        按企业与财务年度核对，每组通常包含三项。明确接受后独立保存；六项保存齐备后仍需点击继续研究。
      </p>
      <button onClick={() => setShowAll(!showAll)}>{showAll ? '收起已完成组' : '查看全部六项'}</button>
      {[...checklist].sort((a, b) => Number(b === nextGroup) - Number(a === nextGroup)).map((group) => (
        <details open={showAll || group.rows.some(r => !r.chosen)}
          key={group.side}
          className="fact-group"
          data-side={group.side}
          data-current={group === nextGroup ? 'true' : undefined}
          aria-label={`${group.input.period.year} 年财务清单`}
        >
          <summary>
            {group === nextGroup && <span className="fact-group-current">当前核对组</span>}
            {
              companies.find((c) => c.company_id === group.input.company_id)
                ?.name
            }{" "}
            · {group.input.period.year} 年财务期间 · {guard === 'current' ? `${group.rows.filter(r => r.chosen).length}/${group.rows.length} 项已入库` : '保存身份保留 · ' + verificationText[guard]}
          </summary>
          {safe && <div className="fact-group-actions">
            {groupEntries(group).map(entry => <a key={entry.key} href={entry.href}>{entry.label} →</a>)}
          </div>}
          <ul className="fact-checklist">
            {group.rows.map((row) => (
              <li
                key={row.key}
                id={`fact-${group.side}-${row.choice.metric_key}`}
                tabIndex={-1}
                data-testid={`slot-${row.key}`}
              >
                <div className="fact-row">
                  <div>
                    <strong>{METRICS[row.choice.metric_key]}</strong>
                    <p
                      className={
                        row.chosen ? "operating-ready" : "operating-pending"
                      }
                    >
                      {row.state}
                      {row.state === "待核对" && " · 财报已准备"}
                    </p>
                  </div>
                  {row.chosen ? (
                    <span className="confirmed-amount">
                      {row.chosen.raw_value || "—"}{" "}
                      {row.chosen.raw_unit}
                    </span>
                  ) : null}
                </div>
                {row.options.length > 1 && (
                  <label>
                    多个有效事实，请明确选择
                    <select
                      aria-label={`${row.key} 恢复事实`}
                      value={selected[row.key] || ""}
                      onChange={(e) =>
                        setSelected((old) => ({
                          ...old,
                          [row.key]: e.target.value,
                        }))
                      }
                    >
                      <option value="">明确选择已确认事实</option>
                      {row.options.map((f) => (
                        <option key={f.fact_id} value={f.fact_id}>
                          {formatDecimal(f.value_cny_yuan)} 元 ·{" "}
                          {f.confirmation_kind === "local_operator"
                            ? "人工核准"
                            : "隔离模拟"}{" "}
                          · {f.fact_id.slice(-8)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {row.receipt && !row.chosen && row.receipt.status === "unknown" && <p>{row.receipt.message}</p>}
                {row.invalid && (
                  <p role="alert">
                    {issues[row.key] ||
                      "来源或事实资格失效。旧金额已撤下，请核对来源后明确新建研究。"}
                  </p>
                )}
                {row.chosen && (
                  <details>
                    <summary>已入库事实与证据</summary>
                    <p>
                      已经具备有效核准事实 · 财务年度 {row.chosen.period} ·
                      合并口径 ·{" "}
                      {row.chosen.confirmation_kind === "simulated_test"
                        ? "模拟测试接受"
                        : "人工明确接受"}
                    </p>
                    <button onClick={() => setEvidence(row.chosen)}>
                      查看原 PDF
                    </button>
                    <a
                      href={taskReviewPath(
                        task,
                        group.side,
                        row.choice.metric_key,
                        row.chosen,
                      )}
                    >
                      查看已保存核对记录（只读） →
                    </a>
                    <details>
                      <summary>高级审计：披露与事实身份</summary>
                      <p>{row.choice.disclosure_version}</p>
                      <p>
                        {row.chosen.fact_set_id} / {row.chosen.fact_id}
                      </p>
                    </details>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </details>
      ))}
      {task.waiting_checkpoint && (
        <p>
          {refs
            ? "六项已齐备，请在顶部复核并继续研究。"
            : guard === 'unavailable' || guard === 'invalidated'
              ? verificationText[guard]
            : notReady
              ? "请完成六项入库；有多个有效事实时需明确选择。"
              : "正在核验当前来源与事实资格。"}
        </p>
      )}
      {task.waiting_checkpoint && !readiness && (
        <button
          className="operating-primary"
          disabled={busy || !safe || !refs}
          onClick={() => void resume(selected)}
        >
          复核并继续研究
        </button>
      )}
    </section>
  );
  return (
    <>
      {guard === "checking" && (
        <p role="status">正在重新核验当前来源与财务事实…</p>
      )}
      {failure && guard !== 'checking' && guard !== 'current' && (
        <p role="alert" className="operating-alert">
          {failure}
        </p>
      )}
      {task.publication_eligibility?.status === "invalidated" && (
        <p role="alert" className="operating-alert">
          当前发布资格已失效：
          {errorLabel(task.publication_eligibility.reason || "source_changed")}
          。历史记录仅供审计。
        </p>
      )}
      {task.error_code && (
        <p role="alert" className="operating-alert">
          {errorLabel(task.error_code)}
        </p>
      )}
      <div data-verification-state={guard} role="status">{verificationText[guard]}</div>
      {(section === 'sources' || (task.status !== "completed" && section === 'operating')) && factList}
      {section === 'financial' && task.status !== 'completed' && <section id="research-results" tabIndex={-1} className="operating-card"><h2>财务分析尚未取得完整结果</h2><p>完成数据核对与独立保存后，再明确继续经营研究。浏览此页不会执行研究。</p><a href={`/research?${new URLSearchParams({ task: task.task_id, company: task.input.first.company_id, mode: 'operating', section: 'sources' })}#research-facts`}>查看资料与核对</a></section>}
      {task.status === "completed" && section !== 'sources' && (
        <section
          id="research-results"
          tabIndex={-1}
          className="operating-card"
          aria-label="确定性分析结果"
        >
          <div className="operating-heading">
            <h2>三项财务指标的变化</h2>
            <span className="muted">{guard === 'current' && results.length === 3 && !resultError ? '已核准数字 · 合并口径' : `${verificationText[guard]} · 金额与引用暂停使用`}</span>
          </div>
          {resultError && (
            <p role="alert">{resultError}；已撤下所有金额与引用。</p>
          )}
          {!results.length && (
            <p>
              {terminal
                ? "任务未取得可发布结果。"
                : guard !== "current"
                  ? "来源与事实待复验，暂不展示旧金额。"
                  : "暂未取得完整分析结果。"}
            </p>
          )}
          <div className="result-summary">
            {results.map((r) => {
              const comparison = task.input.template !== 'company_period_change';
              const current = comparison ? r.second : r.first, base = comparison ? r.first : r.second;
              const companyName = (id: string) => companies.find(c => c.company_id === id)?.name || id;
              const reading = resultReading({ absolute: r.absolute, percentage: r.percentage,
                current: current.value_cny_yuan, base: base.value_cny_yuan,
                currentLabel: companyName(current.company_id), baseLabel: companyName(base.company_id),
                currentYear: current.period, baseYear: base.period, comparison });
              return <article key={r.metric} className="operating-result">
                <h3>{METRICS[r.metric]}</h3>
                <p>{reading.period}</p>
                <strong className="result-change">{reading.rate}</strong>
                <p>{reading.amount}</p>
                <p className="result-exact">精确差额：{reading.exact}</p>
                <small>{reading.kind}</small>
                <p className="result-original">{companyName(current.company_id)} · {current.period} 年原值：{current.raw_value} {current.raw_unit}<br />{companyName(base.company_id)} · {base.period} 年原值：{base.raw_value} {base.raw_unit}</p>
                {reading.note && <p className="result-limitation">{reading.note}</p>}
                {(reading.note || r.percentage === null) && r.limitations.map((l, i) => <p key={i}>{l}</p>)}
                <details>
                  <summary>核准数字与计算依据</summary>
                  <p>精确差额：{reading.exact}</p>
                  {[current, base].map((f, i) => (
                    <p key={f.fact_id}>
                      {comparison ? i === 0 ? "比较企业：" : "基准企业：" : i === 0 ? "本期：" : "比较期："}
                      {
                        companies.find((c) => c.company_id === f.company_id)
                          ?.name
                      }{" "}
                      · {f.period}：
                      <button onClick={() => setEvidence(f)}>
                        {formatDecimal(f.value_cny_yuan)} 元 ↗
                      </button>
                    </p>
                  ))}
                  <p>{r.formula}</p>
                  {r.limitations.map((l, i) => (
                    <p key={i}>{l}</p>
                  ))}
                  <p>{r.first.disclosure_version}</p>
                  <p>{r.second.disclosure_version}</p>
                </details>
              </article>;
            })}
          </div>
          {safe && results.length === 3 && !resultError && (
            <div className="result-next">
              <div>
                <strong>研究已完成 · 经营解释待人工审阅</strong>
                <p>数字已核准；模型推断仍需语义复核。</p>
              </div>
              <a
                className="operating-primary"
                href={`/reports?${new URLSearchParams({ company: task.input.first.company_id, task: task.task_id })}`}
              >
                整理报告 →
              </a>
            </div>
          )}
        </section>
      )}
      {section === 'operating' && safe &&
        results.length === 3 &&
        !resultError &&
        task.final_research_content && (
          <OperatingLimitedResult
            companyNames={Object.fromEntries(companies.map(c => [c.company_id, c.name]))}
            content={task.final_research_content}
            reviewTarget={taskReviewTarget(task)}
            compact
          />
        )}
      {task.status === "completed" && section === 'operating' && (
        <details className="result-evidence">
          <summary>六项事实与原 PDF 证据</summary>
          {factList}
        </details>
      )}
      {task.status === "collecting_explanation" && (
        <p className="operating-notice">
          财务分析已执行，经营解释待完成。只读刷新可查看最新进展。
        </p>
      )}
      <details className="operating-card">
        <summary>高级审计：任务、预算与执行记录</summary>
        <section aria-label="当前经营研究任务">
          <h2>{taskLabels[task.status]}</h2>
          <p>
            任务版本 {task.revision} · {task.task_id}
          </p>
          <p>创建操作 {task.operation_id}</p>
          <time>{new Date(task.created_at).toLocaleString("zh-CN")}</time>
          <div className="operating-budget" aria-label="真实执行预算">
            {[
              ["steps", "步骤"],
              ["tool_calls", "工具调用"],
              ["retrieval_total", "检索槽"],
              ["model_calls", "模型调用"],
            ].map(([key, label]) => (
              <div key={key}>
                <span>{label}</span>
                <strong>
                  {b.used[key]} / {b.limits[key]}
                </strong>
              </div>
            ))}
            <div>
              <span>活动执行时间</span>
              <strong>
                {b.elapsed_seconds.toFixed(2)} / {b.limits.elapsed_seconds}s
              </strong>
            </div>
          </div>
          <p>人工等待不累计活动执行时间；刷新不会重置预算。</p>
          <pre>{JSON.stringify(b, null, 2)}</pre>
          <section aria-label="真实执行步骤">
            <ol className="operating-steps">
              {Object.entries(stepLabels).map(([key, label]) => {
                const state = task.snapshot?.steps.find(
                  (s) => s.step === key,
                )?.status;
                return (
                  <li key={key}>
                    <span>{label}</span>
                    <strong>
                      {state ? stepStates[state] || state : "等待读回"}
                    </strong>
                  </li>
                );
              })}
            </ol>
          </section>
          <details>
            <summary>完整任务快照与日志</summary>
            <pre>{JSON.stringify(task, null, 2)}</pre>
          </details>
        </section>
      </details>
      {safe && evidence && !resultError && (
        <FactEvidence
          key={`${task.task_id}:${task.revision}:${evidence.fact_id}`}
          fact={evidence}
          close={() => setEvidence(null)}
          fatal={(m, cause) => {
            setGuard(verificationFailure(cause));
            setEvidence(null);
            setFailure(`${verificationText[verificationFailure(cause)]}，金额与引用暂停使用。${m}`);
          }}
        />
      )}
    </>
  );
}
