import "../product/uxP1.css";
import { TaskContextHeader } from "../product/TaskContextHeader.tsx";
import { AppShell, pathFor } from "../product/AppShell.tsx";
import { taskPath, taskReviewPath, validateReviewContext } from "../product/researchJourney.ts";
import { taskRequest } from "../product/operatingResearch.ts";
import type { Task } from "../product/operatingResearch.ts";
import styles from "../product/ResearchJourney.module.css";
import "../product/tokens.css";
import "../product/shell.css";
import "../product/product.css";
import { useEffect, useRef, useState } from "react";
import {
  createRequestSnapshot,
  isCurrentRequest,
} from "../requestOwnership.ts";
import type { RequestSnapshot } from "../requestOwnership.ts";
import { getJson, loadDocument, forgetPdf } from "./api.ts";
import type { Candidate, Selection, Source } from "./contracts.ts";
import { FinancialRecords } from "./FinancialRecords.tsx";
import "./tokens.css";
import "./evidence.css";
import '../product/foundation.css';
interface Company {
  company_id: string;
  name: string;
  security_code: string;
  exchange: string;
}
interface Report {
  document_id: string;
  source_file: string;
  company_id: string;
  report_year: number;
}
interface Route extends Selection {
  cite: string;
  task: string;
  side: string;
  period: string;
  metric_key: string;
  disclosure: string;
  return_to: string;
  record: string;
  receipt: string;
  fact_set: string;
  review_session: string;
}
function readRoute(): Route {
  const url = new URL(window.location.href);
  const q = url.searchParams;
  if (q.get('record') === 'new' && !q.get('review_session')) {
    q.set('review_session', crypto.randomUUID());
    history.replaceState(null, '', url);
  }
  return {
    company: q.get("company") || "",
    document: q.get("document") || "",
    revision: q.get("revision") || "",
    evidence: q.get("evidence") || "",
    page: q.get("page") || "",
    cite: q.get("cite") || "",
    task: q.get("task") || "",
    side: q.get("side") || "",
    period: q.get("period") || "",
    metric_key: q.get("metric_key") || "",
    disclosure: q.get("disclosure") || "",
    return_to: q.get("return_to") || "",
    record: q.get("record") || "",
    receipt: q.get("receipt") || "",
    fact_set: q.get("fact_set") || "",
    review_session: q.get("review_session") || "",
  };
}
export default function EvidenceWorkbench() {
  const [route, setRoute] = useState(readRoute);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [context, setContext] = useState<ReturnType<
    typeof validateReviewContext
  > | null>(null);
  const [contextError, setContextError] = useState("");
  const [parentTask, setParentTask] = useState<Task | null>(null);
  useEffect(() => {
    // Reset external task ownership before the next GET.
    const c = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect
    setContext(null);
    setContextError("");
    setParentTask(null);
    if (route.task)
      void taskRequest(`/${encodeURIComponent(route.task)}`, c.signal)
        .then((t) => {
          if (c.signal.aborted) return;
          setParentTask(t);
          const q = new URLSearchParams(location.search);
          for (const key of q.keys())
            if (q.getAll(key).length !== 1)
              throw new Error("审阅地址参数重复，请返回原任务。");
          const verified = validateReviewContext(t, q);
          if (!c.signal.aborted) setContext(verified);
        })
        .catch((e) => {
          if (!c.signal.aborted) setContextError(e.message);
        });
    return () => c.abort();
  }, [
    route.task,
    route.side,
    route.period,
    route.metric_key,
    route.disclosure,
    route.company,
    route.document,
    route.revision,
  ]);
  useEffect(() => {
    const pop = () => setRoute(readRoute());
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const [companies, documents] = await Promise.all([
        getJson<Company[]>("/companies", controller.signal),
        getJson<{ document_id: string; source_file: string }[]>(
          "/documents",
          controller.signal,
        ),
      ]);
      const rows = await Promise.all(
        documents.map(async (d) => {
          try {
            return {
              ...d,
              ...(await getJson<Report>(
                `/documents/${encodeURIComponent(d.document_id)}/metadata`,
                controller.signal,
              )),
            };
          } catch (e) {
            if (controller.signal.aborted) throw e;
            if (
              e instanceof Error &&
              e.message.includes("企业、文档或证据不可用")
            )
              return null;
            throw e;
          }
        }),
      );
      if (!controller.signal.aborted) {
        setCompanies(companies);
        setReports(rows.filter((r): r is Report => r !== null));
        setCatalogLoading(false);
      }
    })().catch((error) => {
      if (!controller.signal.aborted) {
        setCatalogError(error.message);
        setCatalogLoading(false);
      }
    });
    return () => controller.abort();
  }, []);
  function navigate(update: Partial<Route>, replace = false) {
    const next = { ...readRoute(), ...update };
    const q = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => {
      if (v) q.set(k, v);
    });
    window.history[replace ? "replaceState" : "pushState"](
      null,
      "",
      `/evidence?${q}`,
    );
    setRoute(next);
  }
  const contextReady =
    context &&
    context.task.task_id === route.task &&
    context.side === route.side &&
    String(context.year) === route.period &&
    context.metric === route.metric_key &&
    context.document === route.document &&
    context.revision === route.revision &&
    context.task.active_input[context.side].company_id === route.company;
  return (
    <AppShell
      page="research"
      contextLocked={!!route.task}
      company={route.company}
      companies={companies}
      navigate={(page, company) =>
        window.location.assign(pathFor(page, company))
      }
    >
      <div className={`evidence-app ${styles.review}`}>
        {route.task && (
          <section className={styles.sticky} aria-label="原研究核对上下文">
            {parentTask && <TaskContextHeader task={parentTask} companies={companies} section="sources" />}
            <h2>
              {context
                ? `核对 ${context.year} 年财务`
                : "正在核验研究任务上下文"}
            </h2>
            <p>
              核对原文 → 确认数据 → 保存数据
            </p>
            {parentTask && (
              <a
                href={
                  taskPath(parentTask) +
                  (contextReady
                    ? `#reviewed=${context!.side}`
                    : "")
                }
              >
                返回原研究任务（只读） →
              </a>
            )}
            {contextError && <p role="alert">{contextError}</p>}
          </section>
        )}
        <div className="product-body">
          {!route.task && (
            <>
              <div className="product-intro">
                <p className="eyebrow">财务候选 · 原文核对</p>
                <h1>让每个数字回到原文</h1>
                <p>
                  选择财务年度和指标，逐项核对真实年报，再明确接受本次审阅。
                </p>
              </div>
              <section className="source-picker" aria-label="证据来源选择">
                <label>
                  企业
                  <select
                    aria-label="企业"
                    value={route.company}
                    onChange={(e) =>
                      navigate({
                        record: "", receipt: "", fact_set: "", review_session: "",
                        company: e.target.value,
                        document: "",
                        revision: "",
                        evidence: "",
                        cite: "",
                        page: "",
                      })
                    }
                  >
                    <option value="">选择企业</option>
                    {companies.map((c) => (
                      <option key={c.company_id} value={c.company_id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  年报文档
                  <select
                    aria-label="年报文档"
                    value={route.document}
                    disabled={!route.company}
                    onChange={(e) =>
                      navigate({
                        record: "", receipt: "", fact_set: "", review_session: "",
                        document: e.target.value,
                        revision: "",
                        evidence: "",
                        cite: "",
                        page: "",
                      })
                    }
                  >
                    <option value="">选择年报</option>
                    {reports
                      .filter((r) => r.company_id === route.company)
                      .map((r) => (
                        <option key={r.document_id} value={r.document_id}>
                          {r.report_year} · {r.source_file}
                        </option>
                      ))}
                  </select>
                </label>
              </section>
            </>
          )}
          {catalogLoading && <p role="status">正在读取企业与年报…</p>}
          {catalogError && <p role="alert">{catalogError}</p>}
          {route.task && !contextReady ? (
            !contextError && (
              <p role="status">正在核验期间与冻结来源，尚未读取 PDF…</p>
            )
          ) : route.company && route.document ? (
            <DocumentSession
              key={`${route.company}/${route.document}/${route.task}/${route.side}/${route.period}`}
              route={route}
              context={context}
              navigate={navigate}
            />
          ) : (
            <section className="product-empty">
              选择企业和年报，打开对应版本的真实 PDF。
            </section>
          )}
        </div>
      </div>
    </AppShell>
  );
}
function DocumentSession({
  route,
  context,
  navigate,
}: {
  context: ReturnType<typeof validateReviewContext> | null;
  route: Route;
  navigate: (update: Partial<Route>, replace?: boolean) => void;
}) {
  const [data, setData] = useState<{
    source: Source;
    candidates: Candidate[];
    bytes: Uint8Array;
  } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const request = useRef<RequestSnapshot | null>(null);
  const seq = useRef(0);
  const loadedSource = useRef<Source | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const snapshot = createRequestSnapshot(
      ++seq.current,
      route.document,
      `${route.company}/${route.revision}`,
    );
    request.current = snapshot;
    loadedSource.current = null;
    // Loading state synchronizes an external revision-bound request.
    // oxlint-disable-next-line react/set-state-in-effect
    setData(null);
    setError("");
    void loadDocument(
      route.company,
      route.document,
      route.revision,
      controller.signal,
      route.task ? Number(route.period) : undefined,
      !!route.receipt && route.record !== "new",
    )
      .then((value) => {
        if (isCurrentRequest(request.current, snapshot)) {
          loadedSource.current = value.source;
          setData(value);
        }
      })
      .catch((error) => {
        if (
          isCurrentRequest(request.current, snapshot) &&
          !controller.signal.aborted
        )
          setError(error.message);
      });
    return () => {
      request.current = null;
      controller.abort();
    };
  }, [
    route.company,
    route.document,
    route.revision,
    route.period,
    route.task,
    route.record,
    route.receipt,
    retry,
  ]);
  function fail(message: string) {
    loadedSource.current = null;
    if (data) forgetPdf(data.source);
    setData(null);
    setError(message);
  }
  if (error)
    return (
      <section className="source-failure" role="alert">
        <h2>原文来源不可用</h2>
        <p>{error}</p>
        <p>来源问题不代表财务数据已确认。</p>
        <button onClick={() => setRetry((n) => n + 1)}>重试同一版本</button>
        <button
          disabled={!!route.task}
          onClick={() =>
            navigate({ revision: "", evidence: "", cite: "", page: "" }, true)
          }
        >
          重新读取当前来源
        </button>
      </section>
    );
  if (
    !data ||
    (route.revision && route.revision !== data.source.source_revision)
  )
    return (
      <section className="product-empty" role="status">
        正在校验来源版本并加载 PDF…
      </section>
    );
  return (
    <FinancialRecords
      record={route.record}
      receiptId={route.receipt}
      factSetId={route.fact_set}
      selectMode={(record, receipt = "", fact_set = "") => navigate({ record, receipt, fact_set, review_session: record === "new" ? crypto.randomUUID() : "", evidence: "", cite: "", page: "" })}
      key={`${data.source.source_revision}:${route.period}:${route.record}:${route.receipt}:${route.fact_set}:${route.review_session}`}
      data={data}
      groupMetrics={context ? context.task.active_input[context.side].choices.filter(c => c.document_id === route.document && c.disclosure_version === route.disclosure).map(c => c.metric_key) : undefined}
      continuation={context ? ['first', 'second'].flatMap(side => {
        const s = side as 'first' | 'second';
        return context.task.active_input[s].choices.filter((c, i, choices) =>
          (s !== context.side || c.document_id !== route.document || c.disclosure_version !== route.disclosure) &&
          choices.findIndex(other => other.document_id === c.document_id && other.disclosure_version === c.disclosure_version) === i
        ).map(c => ({ href: taskReviewPath(context.task, s, c.metric_key), label: `查看 ${context.task.active_input[s].period.year} 年另一组数据` }));
      }) : []}
      returnHref={context ? taskPath(context.task) : undefined}
      route={route}
      navigate={navigate}
      onFatal={fail}
    />
  );
}
