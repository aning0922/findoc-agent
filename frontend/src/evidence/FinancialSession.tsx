import { useEffect, useMemo, useRef, useState } from "react";
import { citations, METRICS, sourceKey } from "./contracts.ts";
import type { Candidate, Citation, Selection, Source } from "./contracts.ts";
import { EvidenceViewer, SourceGuard } from "./EvidenceViewer.tsx";
import {
  acceptReview,
  loadReview,
  recoverReceipt,
  ReviewError,
  request,
  validateReview,
  validateReceipt,
} from "./reviewApi.ts";
import { recoverAcceptance, matchesReviewScope } from "./receiptRecovery.ts";
import { readRecord, recordSelection } from "./recordApi.ts";
import { persistFacts, readFacts } from "./factsApi.ts";
import type { FactSet } from "./factsApi.ts";
import type {
  AcceptanceRequest,
  Receipt,
  Review,
  ReviewSelection,
} from "./reviewApi.ts";

const STATUS: Record<string, string> = {
  candidate: "系统抽取成功 · 待人工核对",
  conflict: "冲突 · 禁止接受",
  unsupported: "未支持 · 无有效值",
  needs_manual_review: "待人工复核 · 禁止接受",
};
function pendingSelection(
  source: Source,
  suffix = "",
): AcceptanceRequest | null {
  try {
    const q = JSON.parse(
      sessionStorage.getItem(
        `financial-acceptance-pending-v1:${sourceKey(source)}${suffix}`,
      ) || "null",
    ) as AcceptanceRequest | null;
    if (
      q &&
      q.company_id === source.company_id &&
      q.document_id === source.document_id &&
      q.source_revision === source.source_revision &&
      Array.isArray(q.periods) &&
      q.periods.length &&
      q.periods.every((y) => Number.isSafeInteger(y) && y >= 1 && y <= 9999) &&
      Array.isArray(q.metric_keys) &&
      q.metric_keys.length &&
      q.metric_keys.every((k) => k in METRICS)
    )
      return q;
  } catch {
    /* Local storage is only a recovery hint, never a trusted fact. */
  }
  return null;
}
export function FinancialSession({
  data,
  recordId,
  expectedFactSet,
  readOnly = false,
  openSave,
  groupMetrics,
  continuation = [],
  returnHref,
  route,
  navigate,
  onFatal,
}: {
  recordId?: string;
  expectedFactSet?: string;
  readOnly?: boolean;
  openSave?: () => void;
  groupMetrics?: string[];
  continuation?: { href: string; label: string }[];
  returnHref?: string;
  data: { source: Source; candidates: Candidate[]; bytes: Uint8Array };
  route: Selection & {
    cite: string;
    task?: string;
    period?: string;
    metric_key?: string;
    review_session?: string;
  };
  navigate: (
    update: Partial<Selection> & { cite?: string },
    replace?: boolean,
  ) => void;
  onFatal: (message: string) => void;
}) {
  const source = data.source;
  const suffix = route.task ? `:period:${route.period}${groupMetrics && groupMetrics.length !== Object.keys(METRICS).length ? `:metrics:${[...groupMetrics].sort().join(",")}` : ""}` : "";
  const recoverySuffix = suffix + (route.review_session ? `:session:${route.review_session}` : "");
  const targetYear = route.task ? Number(route.period) : source.report_year;
  const [prior] = useState(() => {
    if (recordId || route.review_session) return null;
    const old = pendingSelection(source);
    return suffix &&
      old &&
      (!matchesReviewScope(old, targetYear, groupMetrics || Object.keys(METRICS)))
      ? old
      : null;
  });
  const [restored] = useState(() => {
    if (recordId) return null;
    const hint = pendingSelection(source, recoverySuffix) || (route.review_session || prior ? null : pendingSelection(source));
    return hint && (!route.task || matchesReviewScope(hint, targetYear, groupMetrics || Object.keys(METRICS))) ? hint : null;
  });
  const [priorMessage, setPriorMessage] = useState("");
  const [checkedItems, setCheckedItems] = useState<string[]>([]);
  const [restoredFactId] = useState(() =>
    sessionStorage.getItem(
      `financial-facts-pending-v1:${sourceKey(source)}${recoverySuffix}`,
    ),
  );
  const [years, setYears] = useState(
    restored ? restored.periods.join(",") : String(targetYear),
  );
  const [metrics, setMetrics] = useState(
    restored?.metric_keys || groupMetrics || Object.keys(METRICS),
  );
  const [values, setValues] = useState(
    recordId ? [] : restored &&
      (restored.periods.length !== 1 ||
        restored.periods[0] !== targetYear ||
        restored.metric_keys.length !== Object.keys(METRICS).length)
      ? []
      : data.candidates.filter(c => !groupMetrics || groupMetrics.includes(c.metric_key)),
  );
  const [review, setReview] = useState<Review | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [pending, setPending] = useState<AcceptanceRequest | null>(null);
  const [facts, setFacts] = useState<FactSet | null>(null);
  const [factPhase, setFactPhase] = useState("idle");
  const [factMessage, setFactMessage] = useState("");
  const [phase, setPhase] = useState(recordId || restored ? "recovering" : "extracted");
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(() => window.innerWidth > 760);
  const workspace = useRef<HTMLDivElement>(null);
  const [workspaceWidth, setWorkspaceWidth] = useState<number | null>(null);
  const [fullReader, setFullReader] = useState(false);
  const panelReader = (workspaceWidth !== null && workspaceWidth < 900) || fullReader;
  useEffect(() => {
    const element = workspace.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWorkspaceWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const [modal, setModal] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const busy = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const factStorageKey = `financial-facts-pending-v1:${sourceKey(source)}${recoverySuffix}`;
  const storageKey = `financial-acceptance-pending-v1:${sourceKey(source)}${recoverySuffix}`;
  useEffect(() => {
    if (route.metric_key)
      document
        .getElementById(`candidate-${route.metric_key}`)
        ?.scrollIntoView({ block: "nearest" });
  }, [route.metric_key]);
  useEffect(
    () => () => {
      ++sequence.current;
      controller.current?.abort();
    },
    [],
  );
  useEffect(() => {
    if (recordId) void restoreRecord();
    else if (restored) void restoreKnown();
    // These refs own requests, not DOM nodes. Cleanup invalidates late responses.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
    return () => { ++sequence.current; controller.current?.abort(); busy.current = false; };
    // Restoration belongs to this mounted source/period session, not citation changes.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const nextAction = useRef<HTMLAnchorElement>(null);
  useEffect(() => { if (facts) nextAction.current?.focus(); }, [facts]);
  const items: Citation[] = useMemo(
    () => [
      ...citations(values),
      ...(review
        ? values.flatMap((candidate) =>
            (candidate.basis_evidence || []).map((e, index) => ({
              key: `${candidate.candidate_id}:basis:${index}`,
              candidate,
              reference: {
                ...e,
                role: "basis",
                raw_value: null,
                raw_unit: null,
                bbox: null,
                label: "企业会计准则口径",
              },
            })),
          )
        : []),
    ],
    [values, review],
  );
  if (
    route.cite &&
    (!restored || review) &&
    (!items.some((i) => i.key === route.cite) ||
      items.find((i) => i.key === route.cite)?.reference.evidence_id !==
        route.evidence)
  ) {
    return (
      <section className="source-failure" role="alert">
        引用与证据身份不匹配，未展示 PDF。
        <button onClick={() => navigate({ evidence: "", cite: "", page: "" })}>
          返回当前选择
        </button>
      </section>
    );
  }
  const active =
    route.cite ||
    (route.evidence
      ? ""
      : items.find(
          (i) => i.candidate.metric_key === (route.metric_key || "revenue"),
        )?.key || items[0]?.key) ||
    "";
  function clear() {
    ++sequence.current;
    controller.current?.abort();
    busy.current = false;
    setFacts(null);
    setFactPhase("idle");
    setFactMessage("");
    setCheckedItems([]);
    setReview(null);
    setReceipt(null);
    setPending(null);
    setModal(false);
    setValues([]);
    setMessage("");
    setPhase("modified");
    navigate({ evidence: "", cite: "", page: "" });
  }
  function selection(): ReviewSelection {
    const tokens = years.split(/[,，\s]+/).filter(Boolean);
    const periods = tokens.map(Number);
    if (
      !tokens.length ||
      tokens.some((t) => !/^\d{1,4}$/.test(t)) ||
      periods.some((y) => y < 1 || y > 9999) ||
      new Set(periods).size !== periods.length ||
      !metrics.length
    )
      throw new Error("请选择指标，并输入不重复的完整年度（1–9999）。");
    return {
      review_schema: "financial-review-v1",
      company_id: source.company_id,
      document_id: source.document_id,
      source_revision: source.source_revision,
      metric_keys: metrics,
      periods,
    };
  }
  function start() {
    busy.current = true;
    controller.current?.abort();
    controller.current = new AbortController();
    return { id: ++sequence.current, signal: controller.current.signal };
  }
  function current(id: number) {
    return id === sequence.current;
  }
  function errorState(error: unknown, id: number) {
    if (!current(id)) return;
    busy.current = false;
    const e = error instanceof Error ? error : new Error("本次操作未完成。");
    if (e instanceof ReviewError && e.state === "source") {
      onFatal(e.message);
      return;
    }
    setPhase(e instanceof ReviewError ? e.state : "failed");
    setMessage(e.message);
    if (e instanceof ReviewError && e.state === "rejected") {
      setReview(null);
      setModal(false);
      setPending(null);
      sessionStorage.removeItem(storageKey);
    }
  }
  async function generate() {
    if (recordId || readOnly) return;
    if (busy.current) return;
    let q: ReviewSelection;
    try {
      q = selection();
    } catch (e) {
      setPhase("failed");
      setMessage((e as Error).message);
      return;
    }
    setFacts(null);
    setFactPhase("idle");
    setFactMessage("");
    const own = start();
    setCheckedItems([]);
    setReview(null);
    setReceipt(null);
    setPending(null);
    setValues([]);
    setPhase("loading");
    setMessage("");
    navigate({ evidence: "", cite: "", page: "" });
    try {
      const r = await loadReview(source, q, own.signal);
      if (!current(own.id)) return;
      busy.current = false;
      setReview(r);
      setValues(r.candidates);
      setPhase(r.review_status === "blocked" ? "blocked" : "pending");
      // Refresh recovery restores only a query key, never an acceptance or trusted amount.
      const saved =
        sessionStorage.getItem(storageKey) ||
        (restored ? JSON.stringify(restored) : null);
      if (saved) {
        const old = JSON.parse(saved) as AcceptanceRequest;
        if (
          old.snapshot_id === r.snapshot_id &&
          old.document_id === source.document_id &&
          old.company_id === source.company_id &&
          old.source_revision === source.source_revision
        ) {
          setPending(old);
          setPhase("unknown");
          setMessage("发现此前接受请求。保存结果待查询，不会自动重发接受。");
        }
      }
    } catch (e) {
      errorState(e, own.id);
    }
  }
  async function accept() {
    if (
      busy.current || readOnly || !!recordId ||
      !review ||
      review.review_status !== "ready_for_acceptance" ||
      !modal ||
      review.candidates.some((c) => !checkedItems.includes(c.candidate_id))
    )
      return;
    const q: AcceptanceRequest = {
      ...selection(),
      accepted: true,
      snapshot_id: review.snapshot_id,
      request_id: crypto.randomUUID(),
    };
    const own = start();
    setPending(q);
    setPhase("sending");
    setMessage("");
    try {
      const old = sessionStorage.getItem(storageKey);
      if (old) {
        const previous = JSON.parse(old);
        if (previous.request_id)
          sessionStorage.setItem(
            `${storageKey}:history:${previous.request_id}`,
            old,
          );
      }
      sessionStorage.setItem(
        `${storageKey}:history:${q.request_id}`,
        JSON.stringify(q),
      );
      sessionStorage.setItem(storageKey, JSON.stringify(q));
      const r = await acceptReview(source, q, review, own.signal);
      if (!current(own.id)) return;
      busy.current = false;
      setReceipt(r);
      setPhase("saved");
      setMessage("");
      setModal(false);
      // Keep only the known query key for future receipt/fact reads.
    } catch (e) {
      errorState(e, own.id);
    }
  }
  async function recover() {
    if (busy.current || !pending || !review) return;
    const own = start();
    setPhase("recovering");
    try {
      const r = await recoverReceipt(source, pending, review, own.signal);
      if (!current(own.id)) return;
      busy.current = false;
      setReceipt(r);
      setPhase("saved");
      setMessage("");
      setModal(false);
      if (sessionStorage.getItem(factStorageKey) === r.receipt_id)
        setFactPhase("unknown");
    } catch (e) {
      errorState(e, own.id);
    }
  }
  async function saveFacts(onlyRead = false) {
    if (busy.current || !receipt || (!onlyRead && (readOnly || factPhase !== "idle"))) return;
    const own = start();
    setFactPhase(onlyRead ? "recovering" : "sending");
    setFactMessage("");
    if (!onlyRead) sessionStorage.setItem(factStorageKey, receipt.receipt_id);
    try {
      const result = await (onlyRead ? readFacts : persistFacts)(
        source,
        receipt,
        own.signal,
      );
      if (!current(own.id)) return;
      busy.current = false;
      setFacts(result);
      setFactPhase("saved");
    } catch (error) {
      if (!current(own.id)) return;
      busy.current = false;
      const e =
        error instanceof ReviewError
          ? error
          : new ReviewError("unknown", "事实保存结果未知，请只读查询。");
      if (e.state === "source") {
        setFacts(null);
        onFatal(e.message);
        return;
      }
      setFacts(null);
      setFactPhase(e.code === "facts_not_found" ? "failed" : e.state);
      setFactMessage(e.message);
    }
  }
  async function restoreRecord() {
    if (busy.current || !recordId) return;
    const own = start();
    setPhase('recovering');
    try {
      const result = await readRecord(source, recordId, recordSelection(source, [targetYear], groupMetrics || Object.keys(METRICS)), own.signal);
      if (!current(own.id)) return;
      setReview(result.review); setValues(result.review.candidates); setReceipt(result.receipt); setPhase('saved'); setFactPhase('recovering');
      try {
        const saved = await readFacts(source, result.receipt, own.signal);
        if (!current(own.id)) return;
        if (route.task && new URLSearchParams(location.search).get("disclosure") !== saved.disclosure_version) throw new Error("记录披露版本与任务不一致");
        if (expectedFactSet && saved.fact_set_id !== expectedFactSet) throw new Error('事实组身份不一致');
        setFacts(saved); setFactPhase('saved');
      } catch (e) {
        if (!current(own.id)) return;
        if (e instanceof ReviewError && e.state === 'source') throw e;
        setFactPhase(e instanceof ReviewError && e.code === 'facts_not_found' && !expectedFactSet ? 'idle' : 'unknown');
        setFactMessage(e instanceof ReviewError && e.code === 'facts_not_found' && !expectedFactSet ? '服务端只读查询确认：本凭证尚无已保存事实。' : '保存结果暂不可核验，请按原凭证只读查证。');
      }
      if (current(own.id)) busy.current = false;
    } catch (e) {
      if (!current(own.id)) return;
      busy.current = false;
      if (e instanceof ReviewError && e.state === 'source') { onFatal(e.message); return; }
      setPhase('unknown'); setMessage('记录暂不可核验，请只读重试。');
    }
  }
  async function restoreKnown() {
    if (busy.current || !restored) return;
    const own = start();
    setPhase("recovering");
    setMessage("");
    try {
      const result = await recoverAcceptance(source, restored, own.signal);
      if (!current(own.id)) return;
      setReview(result.review);
      setValues(result.review.candidates);
      setReceipt(result.receipt);
      setPending(restored);
      setPhase("saved");
      setFactPhase("recovering");
      // Even without a local persistence hint another tab may have saved this receipt.
      try {
        const saved = await readFacts(source, result.receipt, own.signal);
        if (!current(own.id)) return;
        setFacts(saved);
        setFactPhase("saved");
      } catch (error) {
        if (!current(own.id)) return;
        if (error instanceof ReviewError && error.state === "source") throw error;
        // A known persistence attempt remains read-only, even if a GET returns 404.
        if (error instanceof ReviewError && error.code === "facts_not_found" && !restoredFactId) {
          setFactPhase("idle");
        } else {
          setFactPhase("unknown");
          setFactMessage("数据保存结果尚未确认，请查询保存结果。");
        }
      }
      if (current(own.id)) busy.current = false;
    } catch (error) {
      if (!current(own.id)) return;
      busy.current = false;
      if (error instanceof ReviewError && error.state === "source") { onFatal(error.message); return; }
      setPhase("unknown");
      setMessage("暂时无法查到确认结果。查询不会重新确认或保存数据。");
    }
  }
  function stopFacts() {
    ++sequence.current;
    controller.current?.abort();
    busy.current = false;
    setFactPhase("unknown");
    setFactMessage("已停止等待。事实操作结果未知，请按已知凭证 ID 只读查询。");
  }
  function close() {
    setModal(false);
    trigger.current?.focus();
  }
  function stopWait() {
    ++sequence.current;
    controller.current?.abort();
    busy.current = false;
    setPhase("unknown");
    setMessage("已停止等待。服务端保存结果未知，请只读查询凭证。");
    setModal(false);
  }
  const frozen =
    phase === "sending" ||
    phase === "recovering" ||
    factPhase === "sending" ||
    factPhase === "recovering";
  return (
    <div ref={workspace} data-reader-mode={panelReader ? "panel" : "split"} className={`evidence-layout ${open ? "is-open" : ""}`}>
      <SourceGuard source={source} onFatal={onFatal} />
      <section className="candidate-panel" inert={open && panelReader || undefined}>
        {!recordId && !receipt && !["unknown", "sending", "recovering"].includes(phase) && <p role="status">本次未提交核对 · 勾选仅为本地意图，尚未接受或保存。</p>}
        {prior && (
          <section className="pending-notice">
            <h3>另一次确认操作待查证</h3>
            <p>
              保留了 {prior.periods.join(" / ")} 年的原接受请求，本次核对{" "}
              {targetYear} 年，两次核对范围分别保留查询身份。
            </p>
            <button
              disabled={frozen}
              onClick={async () => {
                const own = start();
                try {
                  const params = new URLSearchParams({
                    review_schema: prior.review_schema,
                    company_id: prior.company_id,
                    document_id: prior.document_id,
                    source_revision: prior.source_revision,
                    snapshot_id: prior.snapshot_id,
                  });
                  prior.metric_keys.forEach((k) =>
                    params.append("metric_keys", k),
                  );
                  prior.periods.forEach((y) =>
                    params.append("periods", String(y)),
                  );
                  const r = (await request(
                    `/financial-facts/confirmations/${encodeURIComponent(prior.request_id)}?${params}`,
                    { signal: own.signal },
                  )) as Receipt;
                  const v = validateReview(
                    {
                      ...r.review,
                      snapshot_id: r.snapshot_id,
                      review_status: "ready_for_acceptance",
                      facts_status: "unconfirmed",
                    },
                    source,
                    prior,
                  );
                  validateReceipt(r, prior, v);
                  if (current(own.id))
                    setPriorMessage(
                      "原期间接受凭证已读回，仅供原操作查证，不替代当前期间事实。",
                    );
                } catch (e) {
                  if (current(own.id)) setPriorMessage((e as Error).message);
                } finally {
                  if (current(own.id)) busy.current = false;
                }
              }}
            >
              只读查证原期间接受
            </button>
            {priorMessage && <p role="status">{priorMessage}</p>}
          </section>
        )}
        <div className="candidate-heading">
          <div>
            <h2>{recordId ? "阅读核对记录 ·" : "核对"} {years.replaceAll(",", " / ")} 年财务 · 共 {review?.candidates.length ?? metrics.length} 项</h2>
            <p>披露于 {source.report_year} 年报 · 合并口径</p>
          </div>
          <button aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "返回核对" : "查看原PDF"}
          </button>
          {!panelReader && <button onClick={() => { setFullReader(true); setOpen(true); }}>放大原PDF</button>}
        </div>
        {!recordId && <ol className="approval-steps">
          <li aria-current={!receipt ? "step" : undefined}>核对原文</li>
          <li aria-current={receipt && !facts ? "step" : undefined}>
            确认数据
          </li>
          <li aria-current={facts ? "step" : undefined}>保存数据</li>
        </ol>}
        {recordId && receipt && <aside className="pending-notice" aria-label="持久记录状态">
          <strong>{facts ? `已保存 ${facts.facts.length} 项财务事实 · 当前来源有效` : factPhase === 'idle' ? '已接受未保存' : '已接受 · 保存结果待查证'}</strong>
          <p>接受时间：{receipt.accepted_at}<br />保存时间：{facts?.saved_at || '尚无可核验的保存时间'}</p>
          <p>{receipt.confirmation_kind === 'simulated_test' ? '隔离模拟记录 · 不具备生产计算资格' : '人工接受记录'} · {readOnly ? '只读阅读' : '独立保存流程'}</p>
        </aside>}
        <details className="review-range" open={!recordId && !route.task || undefined}>
          <summary>
            {recordId ? `记录范围 · ${years} 年 · ${metrics.length} 项指标` : route.task
              ? `本期核对范围 · ${targetYear} 年 · ${metrics.length} 项指标`
              : "选择财务期间与指标"}
          </summary>
          <div className="review-selection">
            <label>
              财务年度
              <input
                aria-label="财务年度"
                value={years}
                disabled={frozen || !!route.task || !!recordId}
                onChange={(e) => {
                  clear();
                  setYears(e.target.value);
                }}
                placeholder="如 2030, 2031"
              />
            </label>
            <small>实际财务年度与披露报告年度分别核对。</small>
            <fieldset disabled={frozen || !!route.task || !!recordId}>
              <legend>指标选择</legend>
              {Object.entries(METRICS).map(([key, name]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={metrics.includes(key)}
                    onChange={(e) => {
                      clear();
                      setMetrics((old) =>
                        e.target.checked
                          ? [...old, key]
                          : old.filter((k) => k !== key),
                      );
                    }}
                  />
                  {name}
                </label>
              ))}
            </fieldset>
          </div>
        </details>
        {!review && !restored && !recordId && (
          <button
            className="approval-primary"
            disabled={frozen || phase === "loading"}
            onClick={() => void generate()}
          >
            开始本组核对
          </button>
        )}
        {review && !receipt && (
          <p className="muted">
            已核对 {checkedItems.length} / {review.candidates.length}{" "}
            项。逐项查看 PDF 并勾选后，才能明确接受。
          </p>
        )}
        <p className="pending-notice" role="status">
          {phase === "extracted"
            ? "请先开始本组核对，再逐项核对年度、原值、单位与 PDF 证据。"
            : phase === "modified"
              ? "选择已修改，旧核对资格已清除。请重新准备核对。"
              : phase === "loading"
                ? "正在重新核验来源并生成审阅快照…"
                : phase === "blocked"
                  ? "审阅被阻断：冲突、缺失或待人工复核项不能作为有效值接受。"
                  : phase === "unknown"
                    ? "接受结果未知 · 尚无可核验的保存结果。"
                    : phase === "sending"
                      ? "正在复验并保存人工接受凭证…"
                      : phase === "recovering"
                        ? "正在只读查询接受凭证…"
                        : phase === "saved"
                          ? facts
                            ? "本组数据已保存并重新核验，研究尚未自动继续。请返回原研究查看下一步。"
                            : factPhase === "unknown" || factPhase === "recovering" ? "本组已接受，保存结果尚未核验。请按原凭证只读查证。" : "本组数据已接受，数据尚未保存，研究尚未执行。请独立保存已接受数据。"
                          : phase === "rejected"
                            ? "接受被拒绝，请重新审阅。"
                            : phase === "failed"
                              ? "本次操作失败，请检查状态后继续。"
                              : "待人工确认 · 系统抽取候选尚未成为已确认事实。"}
        </p>
        {!review && restored && phase !== "unknown" && (
          <button disabled={frozen} onClick={() => void restoreKnown()}>
            查证接受结果（只读）
          </button>
        )}
        {message && (
          <p role="alert" className="review-error">
            {message}
          </p>
        )}
        {(phase === "unknown" || (pending && phase === "failed")) && (
          <button className="approval-primary" onClick={() => void (recordId ? restoreRecord() : review ? recover() : restoreKnown())}>查证接受结果（只读）</button>
        )}
        {phase === "sending" && <button onClick={stopWait}>停止等待</button>}
        {receipt && !facts && (
          <details className="acceptance-result" data-testid="acceptance-result">
            <summary>查看确认记录</summary>
            <strong>
              {receipt.confirmation_kind === "simulated_test"
                ? "自动化模拟接受凭证"
                : "人工接受凭证"}
            </strong>
            <p>
              接受已保存 ·{" "}
              {facts ? "对应财务事实已入库并读回" : "财务事实入库待完成"}
              。此凭证不会启动分析。
            </p>
            <details>
              <summary>接受凭证详情</summary>
              <p>
                凭证 {receipt.receipt_id}
                <br />
                时间 {receipt.accepted_at}
              </p>
            </details>
          </details>
        )}
        {readOnly && receipt && !facts && factPhase === "idle" && <button onClick={openSave}>继续独立保存这条接受记录</button>}
        {receipt && (
          <div className="fact-result" data-testid="fact-result">
            <p role="status">
              {factPhase === "saved"
                ? `${facts?.confirmation_kind === "simulated_test" ? "自动化模拟 · " : ""}已确认财务事实 · 保存成功并已重新查询`
                : factPhase === "sending"
                  ? "正在保存整组财务事实…"
                  : factPhase === "recovering"
                    ? "正在按凭证 ID 只读查询财务事实…"
                    : factPhase === "unknown"
                      ? "事实操作结果未知 · 请只读查询，勿重复保存"
                      : factPhase === "failed" || factPhase === "rejected"
                        ? "财务事实保存失败 · 当前没有完整有效的读回结果"
                        : "本组数据待保存，保存后可用于研究"}
            </p>
            {factMessage && (
              <p role="alert" className="review-error">
                {factMessage}
              </p>
            )}
            {!readOnly && (factPhase === "idle" || factPhase === "sending") && (
              <button
                disabled={factPhase !== "idle" || frozen}
                className="approval-primary"
                onClick={() => void saveFacts()}
              >
                保存已接受数据
              </button>
            )}
            {["unknown", "failed", "rejected", "saved"].includes(factPhase) && (
              <button onClick={() => void saveFacts(true)}>
                查证数据保存结果（只读）
              </button>
            )}
            {factPhase === "sending" && (
              <button onClick={stopFacts}>停止等待事实保存</button>
            )}
            {facts && (
              <details>
                <summary>事实组与披露来源详情</summary>
                <p>
                  接受凭证 {receipt.receipt_id} · {receipt.accepted_at}
                  <br />
                  事实组 {facts.fact_set_id}
                  <br />共 {facts.facts.length} 条 · 完整性已验证
                  <br />
                  披露版本 {facts.disclosure_version}
                  <br />
                  保存时间 {facts.saved_at}
                </p>
              </details>
            )}
          </div>
        )}
        {facts && returnHref && <nav className="review-continuation" aria-label="保存后的下一步">
          {continuation.map((next, i) => <a key={next.href} ref={i === 0 ? nextAction : undefined} className={i === 0 ? 'approval-primary' : undefined} href={next.href}>{next.label} →</a>)}
          <a ref={!continuation.length ? nextAction : undefined} href={returnHref}>返回研究，检查进度 →</a>
        </nav>}
        <p className="review-scope">本次确认包含 {review?.candidates.length ?? metrics.length} 项数据；当前阅读：{METRICS[items.find(i => i.key === active)?.candidate.metric_key || ''] || '请选择指标'}。切换阅读指标不改变整组接受与保存范围。</p>
        {[...values]
          .sort(
            (a, b) =>
              Object.keys(METRICS).indexOf(a.metric_key) -
                Object.keys(METRICS).indexOf(b.metric_key) ||
              b.period - a.period,
          )
          .map((candidate) => (
            <details
              open={
                items.find((i) => i.key === active)?.candidate.candidate_id ===
                candidate.candidate_id
              }
              className="candidate-item"
              key={candidate.candidate_id}
            >
              <summary
                onClick={(e) => {
                  e.preventDefault();
                  const item = items.find((i) => i.candidate === candidate);
                  if (item) {
                    if (!panelReader) setOpen(true);
                    navigate({
                      revision: source.source_revision,
                      evidence: item.reference.evidence_id,
                      page: String(item.reference.physical_page),
                      cite: item.key,
                    });
                  }
                }}
              >
                {METRICS[candidate.metric_key]} · {candidate.period} 年 ·{" "}
                {facts
                  ? "已入库"
                  : receipt
                    ? factPhase === "unknown" || factPhase === "recovering" ? "已接受 · 保存待查证" : "已接受待入库"
                    : checkedItems.includes(candidate.candidate_id)
                      ? "已核对待接受"
                      : "待核对"}
              </summary>
              <article
                id={`candidate-${candidate.metric_key}`}
                key={candidate.candidate_id}
                className="candidate-card"
                data-testid="review-candidate"
              >
                <div>
                  <h3>
                    {METRICS[candidate.metric_key] || candidate.metric_key}
                  </h3>
                  <span>
                    {candidate.period} 年 ·{" "}
                    {facts
                      ? "已入库 · 来源已复验"
                      : receipt
                        ? factPhase === "unknown" || factPhase === "recovering" ? "已接受 · 保存待查证" : "已接受待入库"
                        : checkedItems.includes(candidate.candidate_id)
                          ? "已核对待接受"
                          : STATUS[candidate.status] || "状态不可用"}
                  </span>
                </div>
                <button
                  className="amount-link"
                  disabled={!candidate.evidence.length}
                  onClick={() => {
                    const item = items.find((i) => i.candidate === candidate)!;
                    setOpen(true);
                    navigate({
                      revision: source.source_revision,
                      evidence: item.reference.evidence_id,
                      page: String(item.reference.physical_page),
                      cite: item.key,
                    });
                  }}
                >
                  <span className="candidate-value">
                    {candidate.raw_value || "暂不可用"}{" "}
                    <small>{candidate.raw_unit}</small>
                  </span>
                </button>
                <dl className="amount-comparison">
                  <dt>财务年度</dt>
                  <dd>{candidate.period} 年</dd>
                  <dt>披露年度</dt>
                  <dd>{source.report_year} 年报</dd>
                  <dt>财务口径</dt>
                  <dd>
                    {candidate.scope === "consolidated"
                      ? "合并 · 全年"
                      : "合并口径待核验"}
                  </dd>
                  <dt>确认状态</dt>
                  <dd>
                    {facts
                      ? "已确认财务事实 · 当前来源有效"
                      : receipt
                        ? `${receipt.confirmation_kind === "simulated_test" ? "模拟" : "人工"}接受凭证已保存 · 事实尚未入库`
                        : "候选未确认"}
                  </dd>
                </dl>
                <details><summary>规范金额与单位换算</summary><dl className="amount-comparison">
                  <dt>规范化金额</dt>
                  <dd>
                    {candidate.status === "candidate"
                      ? (candidate.value_cny_yuan ?? "未提供")
                      : "无有效值"}{" "}
                    CNY 元
                  </dd>
                  <dt>单位倍率</dt>
                  <dd>
                    {candidate.multiplier || "未核实"} ·{" "}
                    {candidate.raw_unit || "未核实"}
                  </dd>
                </dl></details>
                {review && !receipt && (
                  <label className="acceptance-check">
                    <input
                      type="checkbox"
                      aria-label={`已核对 ${candidate.period} ${METRICS[candidate.metric_key]}`}
                      disabled={
                        frozen ||
                        review.review_status !== "ready_for_acceptance"
                      }
                      checked={checkedItems.includes(candidate.candidate_id)}
                      onChange={(e) =>
                        setCheckedItems((old) =>
                          e.target.checked
                            ? [...old, candidate.candidate_id]
                            : old.filter((id) => id !== candidate.candidate_id),
                        )
                      }
                    />
                    我已核对这项的年度、金额、单位、合并口径和原文来源
                  </label>
                )}
                {candidate.failure_reason && (
                  <p className="review-error">{candidate.failure_reason}</p>
                )}
                <ul>
                  {items
                    .filter((i) => i.candidate === candidate)
                    .map((item) => (
                      <li key={item.key}>
                        <button
                          aria-pressed={active === item.key}
                          onClick={() => {
                            setOpen(true);
                            navigate({
                              revision: source.source_revision,
                              evidence: item.reference.evidence_id,
                              page: String(item.reference.physical_page),
                              cite: item.key,
                            });
                          }}
                        >
                          {item.reference.role === "summary"
                            ? "主要财务指标"
                            : item.reference.role === "basis"
                              ? "会计准则口径证据"
                              : "合并财务报表"}{" "}
                          · 物理第 {item.reference.physical_page} 页
                        </button>
                      </li>
                    ))}
                </ul>
              </article>
            </details>
          ))}
        {review && !receipt && (
          <div className="review-actions">
            <details>
              <summary>高级审计：审阅快照</summary>
              <p className="version-note">{review.snapshot_id}</p>
            </details>
            {!recordId && <button
              ref={trigger}
              disabled={
                review.review_status !== "ready_for_acceptance" ||
                frozen ||
                phase === "unknown" ||
                phase === "saved" ||
                Boolean(pending) ||
                review.candidates.some(
                  (c) => !checkedItems.includes(c.candidate_id),
                )
              }
              className="approval-primary"
              onClick={() => setModal(true)}
            >
              确认本组数据
            </button>}
          </div>
        )}
        <details>
          <summary>高级审计：当前来源身份</summary>
          <p className="version-note">
            当前文档 {source.document_id.slice(0, 12)}…<br />
            版本 {source.source_revision.slice(0, 12)}… · attempt{" "}
            {source.attempt}
            <br />
            PDF 共 {source.physical_pages} 个物理页
            <br />
            {source.parser_version}
          </p>
        </details>
      </section>
      {(!recordId || receipt) && <EvidenceViewer
          active={open}
          panelMode={panelReader}
          source={source}
          bytes={data.bytes}
          items={items}
          selection={route}
          citation={active}
          onNavigate={navigate}
          onClose={() => { setOpen(false); setFullReader(false); }}
          onFatal={onFatal}
        />}
      {modal && review && (
        <AcceptanceDialog
          review={review}
          phase={phase}
          onAccept={() => void accept()}
          onCancel={close}
          onModify={clear}
          onStop={stopWait}
        />
      )}
    </div>
  );
}

function AcceptanceDialog({
  review,
  phase,
  onAccept,
  onCancel,
  onModify,
  onStop,
}: {
  review: Review;
  phase: string;
  onAccept: () => void;
  onCancel: () => void;
  onModify: () => void;
  onStop: () => void;
}) {
  const [checked, setChecked] = useState(false);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current,
      previous = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previous?.focus();
    };
  }, []);
  const sending = phase === "sending";
  return (
    <dialog
      ref={ref}
      className="acceptance-dialog"
      aria-labelledby="acceptance-title"
      onCancel={(e) => {
        e.preventDefault();
        if (sending) onStop();
        else onCancel();
      }}
    >
      <h2 id="acceptance-title">人工核对确认</h2>
      <strong>本次确认全部 {review.candidates.length} 项 · 披露于 {review.source.report_year} 年报 · 合并口径</strong>
      <p>
        {review.company.name} · {review.document.source_file}
      </p>
      <p>
        请逐项核对原 PDF
        的年度、金额、单位、合并口径及所有来源。系统抽取成功仍需要你的明确接受。
      </p>
      <ul>
        {review.candidates.map((c) => (
          <li key={c.candidate_id}>
            {c.period} 年 · {METRICS[c.metric_key]}：{c.raw_value} {c.raw_unit} · 合并全年
          </li>
        ))}
      </ul>
      <p>
        本次保存人工接受凭证。取得凭证后，可另行保存完整财务事实；当前不启动分析。
      </p>
      {phase === "unknown" && (
        <p role="status">
          接受结果未知，请返回页面只读查询凭证。停止等待不代表撤销服务端保存。
        </p>
      )}
      <label className="acceptance-check">
        <input
          type="checkbox"
          checked={checked}
          disabled={sending || phase === "unknown"}
          onChange={(e) => setChecked(e.target.checked)}
        />
        我已逐项核对原 PDF，并明确接受本次审阅内容
      </label>
      <div className="dialog-actions">
        <button onClick={sending ? onStop : onCancel}>
          {sending
            ? "停止等待"
            : phase === "unknown"
              ? "返回查看结果"
              : "取消审阅"}
        </button>
        <button disabled={sending || phase === "unknown"} onClick={onModify}>
          返回修改
        </button>
        <button
          disabled={
            !checked || sending || phase === "unknown" || phase === "failed"
          }
          onClick={onAccept}
        >
          我已核对并接受
        </button>
      </div>
    </dialog>
  );
}
