import { ResearchIntentRecovery } from "./ResearchIntentRecovery.tsx";
import "./uxP1.css";
import {
  recoverTaskSources,
  sourceCoverage,
  intentOf,
  revalidateIntents,
  savedSourceIntents,
  saveSourceIntents,
} from "./sourceIntent.ts";
import type { SourceIntent } from "./sourceIntent.ts";
import { taskRequest } from "./operatingResearch.ts";
import { ResearchHome } from "./ResearchHome.tsx";
import { DocumentLibrary } from "./DocumentLibrary.tsx";
import { ReportPreview } from "./ReportPreview.tsx";
import { ResearchWorkbench } from "./ResearchWorkbench.tsx";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { AppShell, pathFor } from "./AppShell.tsx";
import { readProductRoute } from "./productRoutes.ts";
import { CompanyDirectory } from "./CompanyDirectory.tsx";
import type { Page } from "./AppShell.tsx";
import { METRICS } from "../evidence/contracts.ts";
import {
  json,
  productionAccess,
  validateAnalysis,
  formatDecimal,
  factsIdentity,
  compactYi,
} from "./api.ts";
import type {
  Analysis,
  Company,
  DataAccess,
  Fact,
  FactQuery,
  Report,
} from "./api.ts";
import { reportsFor } from "./reports.ts";
import { CompanyComparison } from "./CompanyComparison.tsx";
import { FactEvidence } from "./FactEvidence.tsx";
import "./tokens.css";
import "./shell.css";
import "./product.css";
import './foundation.css';
const FinancialChart = lazy(() => import("./FinancialChart.tsx"));
function readRoute() {
  try { return { ...readProductRoute(new URL(window.location.href)), routeError: '' }; }
  catch (e) { return { ...readProductRoute(new URL('/', location.origin)), key: location.pathname + location.search, routeError: (e as Error).message }; }
}
export default function FinancialProduct({
  access = productionAccess,
}: {
  access?: DataAccess;
}) {
  const [route, setRoute] = useState(readRoute);
  const [historyEpoch, setHistoryEpoch] = useState(0);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    // Child workspaces may have advanced the URL after validated reads. Every history
    // traversal revokes their old view, even when the URL equals the parent's earlier key.
    const pop = () => { setRoute(readRoute()); setHistoryEpoch(n => n + 1); };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void json<Company[]>("/companies", controller.signal)
      .then((rows) => {
        if (controller.signal.aborted) return;
        setCompanies(rows);
        setCompaniesLoading(false);
        setError("");

      })
      .catch((e) => {
        if (!controller.signal.aborted) { setError(e.message); setCompaniesLoading(false); }
      });
    return () => controller.abort();
  }, [retry]);
  function navigate(page: Page, company: string) {
    const q = new URLSearchParams(location.search);
    let path = pathFor(page, company);
    if (page === 'research' && route.page === 'research') {
      const mode = q.get('mode') === 'qa' ? 'qa' : 'operating';
      path = `/research?${new URLSearchParams({ ...(company ? { company } : {}), mode, ...(q.get('new') === '1' ? { new: '1' } : {}) })}`;
    }
    // Navigation never carries an old task/run/report into a different company scope.
    window.history.pushState(null, '', path);
    setRoute(readRoute());
    window.requestAnimationFrame(() => document.getElementById('main-content')?.focus());
  }

  const company = companies.find((c) => c.company_id === route.company);
  return (
    <AppShell
      key={`${route.key}:${historyEpoch}`}
      page={route.page}
      company={route.company}
      companies={companies}
      navigate={navigate}
      label={access.label}
      contextLocked={!!(route.task || route.run || route.report)}
    >
      {route.routeError ? <section className="product-message" role="alert"><h1>地址身份无法核验</h1><p>{route.routeError}</p><a href="/">返回我的研究</a></section> : error ? (
        <section className="product-message" role="alert">
          <h1>企业目录暂不可用</h1>
          <p>{error}</p>
          <button onClick={() => setRetry((n) => n + 1)}>重试读取</button>
        </section>
      ) : route.home ? (
        <ResearchHome
          key={route.company}
          companies={companies}
          company={route.company}
          access={access}
        />
      ) : route.page === "companies" ? (
        <CompanyDirectory companies={companies} loading={companiesLoading} />
      ) : route.page === "research" ? (
        <ResearchWorkbench
          key={route.key}
          company={route.company}
          companies={companies}
          access={access}
          chooseCompany={(id) => navigate("research", id)}
        />
      ) : route.page === "reports" ? (
        <ReportPreview
          key={route.key}
          companies={companies}
          access={access}
          company={route.company}
        />
      ) : route.page === "documents" ? (
        <DocumentLibrary
          key={route.key}
          company={route.company}
          companies={companies}
        />
      ) : company ? (
        <CompanySession
          key={route.key}
          company={company}
          companies={companies}
          page={route.page}
          access={access}
          navigate={navigate}
        />
      ) : (
        <section className="product-message" role="status">
          <h1>
            {companies.length ? "请选择有效企业" : "建立你的企业研究空间"}
          </h1>
          <p>
            {companies.length
              ? "当前地址中的企业不可用，请通过顶部选择器选择企业。"
              : "企业目录为空或正在加载。建立企业并绑定年报后，即可核对事实并开展分析。"}
          </p>
          <a href="/evidence">打开原文审阅入口</a>
        </section>
      )}
    </AppShell>
  );
}
function CompanySession({
  company,
  companies,
  page,
  access,
  navigate,
}: {
  company: Company;
  companies: Company[];
  page: Page;
  access: DataAccess;
  navigate: (p: Page, c: string) => void;
}) {
  const [mode, setMode] = useState("single");
  const [data, setData] = useState<{
    query: FactQuery;
    reports: Report[];
  } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let busy = false;
    async function read() {
      if (busy) return;
      busy = true;
      try {
        const results = await Promise.allSettled([
          access.query(company.company_id, controller.signal),
          reportsFor(company.company_id, controller.signal),
        ]);
        for (const r of results) if (r.status === "rejected") throw r.reason;
        if (!controller.signal.aborted) {
          const next = {
            query: (results[0] as PromiseFulfilledResult<FactQuery>).value,
            reports: (results[1] as PromiseFulfilledResult<Report[]>).value,
          };
          setData(next);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setData(null);
          setError((e as Error).message);
        }
      } finally {
        busy = false;
      }
    }
    void read();
    const interval = window.setInterval(() => void read(), 30_000);
    const focus = () => {
      if (!document.hidden) void read();
    };
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", focus);
    return () => {
      controller.abort();
      clearInterval(interval);
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", focus);
    };
  }, [company.company_id, access, retry]);
  function fatal(message: string) {
    setData(null);
    setError(message);
  }
  return (
    <>
      <header className="page-heading">
        <p className="eyebrow">
          {page === "overview"
            ? "企业概览"
            : page === "analysis"
              ? "财务分析 · 同口径已确认事实"
              : "财报资料库"}
        </p>
        <h1>{company.name}</h1>
        <p>
          {company.security_code} <span className="dot">·</span>{" "}
          {company.exchange === "SZSE"
            ? "深圳证券交易所"
            : company.exchange === "SSE"
              ? "上海证券交易所"
              : company.exchange}{" "}
          <span className="dot">·</span> 合并年度财务
        </p>
      </header>
      {page === "analysis" && (
        <div className="analysis-modes" role="group" aria-label="分析模式">
          <button
            aria-pressed={mode === "single"}
            onClick={() => setMode("single")}
          >
            单企业跨年分析
          </button>
          <button
            aria-pressed={mode === "compare"}
            onClick={() => setMode("compare")}
          >
            双企业同期间比较
          </button>
        </div>
      )}
      {page === "analysis" && mode === "compare" ? (
        <CompanyComparison
          company={company}
          companies={companies}
          access={access}
        />
      ) : error ? (
        <section className="product-message" role="alert">
          <h2>数据或来源不可用</h2>
          <p>{error}</p>
          <p>旧金额、分析与引用已撤下。重新读取会再次核验当前来源。</p>
          <button
            onClick={() => {
              setError("");
              setRetry((n) => n + 1);
            }}
          >
            重试读取
          </button>
          <a href="/evidence">进入原文审阅</a>
        </section>
      ) : !data ? (
        <section className="product-message" role="status">
          正在读取年报覆盖、确认事实与来源状态…
        </section>
      ) : (
        <FinancialView
          company={company}
          page={page}
          data={data}
          access={access}
          fatal={fatal}
          navigate={navigate}
        />
      )}
    </>
  );
}
function reviewPath(company: string, report?: Report) {
  const q = new URLSearchParams({ company });
  if (report) q.set("document", report.document_id);
  return `/evidence?${q}`;
}
function FinancialView({
  company,
  page,
  data,
  access,
  fatal,
  navigate,
}: {
  company: Company;
  page: Page;
  data: { query: FactQuery; reports: Report[] };
  access: DataAccess;
  fatal: (m: string) => void;
  navigate: (p: Page, c: string) => void;
}) {
  const facts = data.query.facts.filter(access.eligible);
  const years = [
    ...new Set([
      ...data.reports.map((r) => r.report_year),
      ...facts.map((f) => f.period),
    ]),
  ].sort((a, b) => b - a);
  const explicitTask = new URLSearchParams(location.search).get("task");
  const [currentYear, setCurrentYear] = useState(
    explicitTask ? 0 : years[0] || 0,
  );
  const [previousYear, setPreviousYear] = useState(
    explicitTask ? 0 : years[1] || 0,
  );
  const [metrics, setMetrics] = useState(Object.keys(METRICS));
  const [localHints] = useState(() => savedSourceIntents(company.company_id));
  const [choices, setChoices] = useState<Record<string, string>>(() =>
    explicitTask
      ? {}
      : revalidateIntents(localHints, data.query.facts, access.eligible),
  );
  const identities = useRef<SourceIntent[]>(
    explicitTask
      ? []
      : data.query.facts
          .filter(
            (f) =>
              choices[`${f.period}/${f.metric_key}`] === f.fact_id &&
              access.eligible(f),
          )
          .map(intentOf),
  );
  const [intentMessage, setIntentMessage] = useState("");
  const [intentOrigin, setIntentOrigin] = useState(
    explicitTask
      ? "正在核验指定研究"
      : Object.keys(choices).length
        ? "本地明确选择"
        : "尚未选择来源",
  );
  const [recoveringIntent, setRecoveringIntent] = useState(!!explicitTask);
  const selectionChanged = useRef(false);
  const recoveryEpoch = useRef(0);
  function claimSelection() {
    selectionChanged.current = true;
    ++recoveryEpoch.current;
    setRecoveringIntent(false);
    setIntentOrigin("本次手动选择");
    setIntentMessage("已修改范围或来源。以下覆盖数量按当前范围核验。");
  }
  useEffect(() => {
    if (selectionChanged.current) return;
    const c = new AbortController();
    const epoch = ++recoveryEpoch.current;
    let id = explicitTask;
    // A local source intent has priority over a recent task identity hint,
    // including an invalid intent that needs explicit replacement.
    if (!id && Array.isArray(localHints) && localHints.length)
      return () => c.abort();
    if (!id)
      try {
        id = JSON.parse(
          localStorage.getItem(
            `findoc:operating-identity:${company.company_id}`,
          ) || "null",
        )?.task_id;
      } catch {
        /* only an identity hint */
      }
    const owns = () =>
      !c.signal.aborted &&
      !selectionChanged.current &&
      epoch === recoveryEpoch.current;
    if (id) {
      setRecoveringIntent(true);
      void taskRequest(`/${encodeURIComponent(id)}`, c.signal)
        .then((task) => {
          const restored = recoverTaskSources(
            task,
            company.company_id,
            data.query.facts,
            access.eligible,
          );
          if (!owns()) return;
          identities.current = restored.intents;
          setCurrentYear(restored.scope.currentYear);
          setPreviousYear(restored.scope.previousYear);
          setMetrics(restored.scope.metrics);
          setChoices(restored.choices);
          setIntentOrigin(
            `${explicitTask ? "沿用指定研究" : "核验最近研究线索"}：${restored.scope.currentYear} / ${restored.scope.previousYear} 年 · ${new Date(task.created_at).toLocaleString("zh-CN")}`,
          );
          setIntentMessage(
            "仅采用该研究冻结来源的当前有效匹配；缺项需明确重新选择。",
          );
          setRecoveringIntent(false);
        })
        .catch((e) => {
          if (!owns()) return;
          setIntentOrigin("研究来源未能核验");
          setIntentMessage(
            e.message || "研究来源暂无法核验，请更换研究来源或明确重新选择。",
          );
          setRecoveringIntent(false);
        });
    }
    return () => c.abort();
  }, [company.company_id, data.query, access, explicitTask, localHints]);
  const coverage = sourceCoverage(
    { company: company.company_id, currentYear, previousYear, metrics },
    choices,
    identities.current,
    data.query.facts,
    access.eligible,
  );
  const validChoices = coverage.choices;
  const choiceIdentity = JSON.stringify(validChoices);
  useEffect(() => {
    if (!recoveringIntent)
      saveSourceIntents(company.company_id, validChoices, data.query.facts);
    // Persist only the exact identities that survived the current server query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choiceIdentity, company.company_id, data.query.facts, recoveringIntent]);
  const [unit, setUnit] = useState("yuan");
  const [evidence, setEvidence] = useState<Fact | null>(null);
  const [analysis, setAnalysis] = useState<{
    key: string;
    rows: Record<string, Analysis>;
  } | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  const [running, setRunning] = useState(false);
  const [retry, setRetry] = useState(0);
  const factIdentity = factsIdentity(data.query);
  // Preserve PDF reading state across equivalent polling responses, after the
  // full fact/source identity passes the current eligibility query again.
  const visibleEvidence =
    evidence &&
    facts.some(
      (f) =>
        factsIdentity({ ...data.query, facts: [f] }) ===
        factsIdentity({ ...data.query, facts: [evidence] }),
    ) ? evidence : null;
  const key = JSON.stringify({
    factIdentity,
    currentYear,
    previousYear,
    choices: validChoices,
    metrics,
    retry,
  });
  function candidates(metric: string, year: number) {
    return facts.filter((f) => f.metric_key === metric && f.period === year);
  }
  function selected(metric: string, year: number) {
    return candidates(metric, year).find(
      (f) => f.fact_id === validChoices[`${year}/${metric}`],
    );
  }
  function reset() {
    setEvidence(null);
    setAnalysis(null);
    setAnalysisError("");
  }
  const selectedPairs = metrics.map((metric) => ({
    metric,
    current: selected(metric, currentYear),
    previous: selected(metric, previousYear),
  }));
  const canAnalyze =
    selectedPairs.some((p) => p.current && p.previous) &&
    currentYear > previousYear &&
    previousYear > 0;
  useEffect(() => {
    if (!canAnalyze || page === "documents") return;
    const controller = new AbortController();
    setRunning(true);
    setAnalysisError("");
    void (async () => {
      const pairs = selectedPairs.filter((p) => p.current && p.previous);
      const results = await Promise.allSettled(
        pairs.map(async (p) => {
          const a = await access.analyze(
            company.company_id,
            p.metric,
            p.current!,
            p.previous!,
            controller.signal,
          );
          return [
            p.metric,
            validateAnalysis(
              a,
              company.company_id,
              p.metric,
              p.current!,
              p.previous!,
              access,
            ),
          ] as const;
        }),
      );
      for (const r of results) if (r.status === "rejected") throw r.reason;
      if (!controller.signal.aborted)
        setAnalysis({
          key,
          rows: Object.fromEntries(
            results.map(
              (r) =>
                (r as PromiseFulfilledResult<readonly [string, Analysis]>)
                  .value,
            ),
          ),
        });
    })()
      .catch((e) => {
        if (!controller.signal.aborted) {
          setAnalysis(null);
          setEvidence(null);
          setAnalysisError(e.message);
          fatal(e.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setRunning(false);
      });
    return () => controller.abort();
    // Selection key includes every fact choice/year/metric. Ownership is revoked on any change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, canAnalyze, access, company.company_id, page]);
  const rows = analysis?.key === key ? analysis.rows : {};
  const shift = unit.startsWith("yi") ? 8 : 0,
    unitLabel = unit.startsWith("yi") ? "亿元" : "元";
  function amount(f?: Fact) {
    return f ? (
      <button
        className="money-link"
        onClick={() => setEvidence(f)}
        title={`规范精确金额：${formatDecimal(f.value_cny_yuan)} 元；原披露：${f.raw_value} ${f.raw_unit}。点击查看原 PDF。`}
        data-fact-id={f.fact_id}
      >
        {unit === "yi-short"
          ? compactYi(f.value_cny_yuan)
          : formatDecimal(f.value_cny_yuan, shift)}
        <small> {unitLabel}</small>
      </button>
    ) : (
      <span className="muted">未选择或缺失</span>
    );
  }
  function notes(a?: Analysis) {
    if (!a) return null;
    return (
      <>
        {a.reasons.map((r) => (
          <p key={r.code}>{r.message}</p>
        ))}
        {a.limitations.map((r) => (
          <p key={r.code}>{r.message}</p>
        ))}
        {a.sign_transition && a.sign_transition !== "ordinary" && (
          <p>
            金额符号变化：
            {(
              {
                loss_to_profit: "由亏转盈",
                profit_to_loss: "由盈转亏",
                both_negative: "两期均为负数",
                negative_to_positive: "负转正",
                positive_to_negative: "正转负",
              } as Record<string, string>
            )[a.sign_transition] || a.sign_transition}
            。不构成经营原因判断。
          </p>
        )}
      </>
    );
  }
  function versionPicker(metric: string, year: number) {
    const options = candidates(metric, year),
      id = `${year}/${metric}`;
    return (
      <label className="version-field" key={id}>
        <span>
          {year} · {METRICS[metric]}
          {options.length > 1 && <b className="status warning">多披露版本</b>}
        </span>
        <select
          aria-label={`${year} ${METRICS[metric]}披露版本`}
          value={validChoices[id] || ""}
          disabled={!options.length}
          onChange={(e) => {
            if ((choices[id] || "") === e.target.value) return;
            claimSelection();
            identities.current = identities.current.filter(
              (h) => `${h.period}/${h.metric_key}` !== id,
            );
            const chosen = options.find((f) => f.fact_id === e.target.value);
            if (chosen) identities.current.push(intentOf(chosen));
            reset();
            setChoices((c) => ({ ...c, [id]: e.target.value }));
          }}
        >
          <option value="">
            {options.length ? "明确选择披露版本" : "缺少有效已确认事实"}
          </option>
          {options.map((f) => {
            const report = data.reports.find(
              (r) => r.document_id === f.document_id,
            );
            return (
              <option key={f.fact_id} value={f.fact_id}>
                {report
                  ? `${report.report_year} 年报 · ${report.source_file}`
                  : f.document_id}{" "}
                · 原值 {f.raw_value} {f.raw_unit} · 物理第{" "}
                {f.evidence[0]?.physical_page} 页 ·{" "}
                {f.disclosure_version.slice(-8)}
              </option>
            );
          })}
        </select>
        {selected(metric, year) && (
          <details>
            <summary>事实与来源身份</summary>
            <dl className="source-identity">
              {[
                "disclosure_version",
                "source_revision",
                "fact_set_id",
                "fact_id",
                "candidate_id",
                "document_id",
              ].map((field) => (
                <div key={field}>
                  <dt>{field}</dt>
                  <dd>
                    {String(selected(metric, year)![field as keyof Fact])}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        )}
      </label>
    );
  }
  const reportList = (
    <section className="surface reports-card">
      <div className="section-title">
        <h2>{page === "documents" ? "已绑定年度报告" : "最近的财报来源"}</h2>
        <span className="muted">{data.reports.length} 份年报</span>
      </div>
      {data.reports.length ? (
        <ul className="report-list">
          {[...data.reports]
            .sort((a, b) => b.report_year - a.report_year)
            .map((r) => (
              <li key={r.document_id}>
                <div>
                  <strong>{r.report_year} 年度报告</strong>
                  <p>{r.source_file}</p>
                </div>
                <span className="status">
                  {(
                    {
                      ready: "资料就绪 · 财务需核对",
                      failed: "处理失败",
                      uploaded: "已上传",
                      processing: "处理中",
                      queued: "等待处理",
                    } as Record<string, string>
                  )[r.status] || r.status}
                </span>
                <a href={reviewPath(company.company_id, r)}>原文与人工审阅 →</a>
              </li>
            ))}
        </ul>
      ) : (
        <p className="muted">尚未绑定年报，请上传资料并核对企业及年度归属。</p>
      )}
      <p className="footnote">
        资料就绪仅表示文档处理状态。财务是否可用以已确认事实及当前来源复验为准。
      </p>
      <a href="/legacy">打开已有上传工作台</a>
    </section>
  );
  if (page === "documents")
    return (
      <>
        {reportList}
        <p className="footnote">
          本阶段复用已有上传、绑定 API
          和人工审阅入口。新的资料管理界面尚未完整开发。
        </p>
      </>
    );
  return (
    <>
      <section className="surface financial-controls" aria-label="财务选择">
        <div className="control-row">
          <label>
            本期年度
            <select
              aria-label="本期年度"
              value={currentYear}
              onChange={(e) => {
                if (currentYear === Number(e.target.value)) return;
                claimSelection();
                reset();
                setCurrentYear(Number(e.target.value));
              }}
            >
              {(!years.length || !currentYear) && (
                <option value={0}>
                  {recoveringIntent ? "读取指定研究期间" : "选择本期"}
                </option>
              )}
              {[
                ...new Set(
                  [...years, currentYear, previousYear].filter((y) => y > 0),
                ),
              ]
                .sort((a, b) => b - a)
                .map((y) => (
                  <option key={y} value={y}>
                    {y} 年
                  </option>
                ))}
            </select>
          </label>
          <label>
            上期年度
            <select
              aria-label="上期年度"
              value={previousYear}
              onChange={(e) => {
                if (previousYear === Number(e.target.value)) return;
                claimSelection();
                reset();
                setPreviousYear(Number(e.target.value));
              }}
            >
              <option value={0}>选择上期</option>
              {[
                ...new Set(
                  [...years, currentYear, previousYear].filter((y) => y > 0),
                ),
              ]
                .sort((a, b) => b - a)
                .map((y) => (
                  <option key={y} value={y}>
                    {y} 年
                  </option>
                ))}
            </select>
          </label>
          <label>
            展示单位
            <select
              aria-label="展示单位"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            >
              <option value="yuan">人民币元（精确）</option>
              <option value="yi">人民币亿元（精确）</option>
              <option value="yi-short">亿元（约值 · 截取4位）</option>
            </select>
          </label>
          <button
            onClick={() => {
              reset();
              setRetry((n) => n + 1);
            }}
          >
            重新核验分析
          </button>
        </div>
        {page === "analysis" && (
          <fieldset className="metric-checks">
            <legend>指标</legend>
            {Object.entries(METRICS).map(([m, title]) => (
              <label key={m}>
                <input
                  type="checkbox"
                  checked={metrics.includes(m)}
                  onChange={(e) => {
                    claimSelection();
                    reset();
                    setMetrics((old) =>
                      e.target.checked
                        ? [...old, m]
                        : old.filter((x) => x !== m),
                    );
                  }}
                />
                {title}
              </label>
            ))}
          </fieldset>
        )}
      </section>
      {!facts.length && (
        <section className="product-message empty-facts">
          <h2>尚无可用于正式分析的已确认事实</h2>
          <p>
            {data.query.facts.some(
              (f) => f.confirmation_kind === "simulated_test",
            )
              ? "查询含自动化模拟事实，正式 KPI 已隔离。模拟接受不等于真人确认。"
              : "当前年度财务数据尚未确认或来源已失效。请逐项核对原 PDF、明确接受并保存事实。"}
          </p>
          <a
            href={reviewPath(
              company.company_id,
              data.reports.find((r) => r.report_year === currentYear),
            )}
          >
            进入原文核对与确认 →
          </a>
        </section>
      )}
      {data.query.facts.some((f) => !f.current_valid) && (
        <p className="product-notice" role="status">
          存在失效来源事实，已从金额与分析中撤下。请回到原文重新审阅。
        </p>
      )}
      {page === "overview" && (
        <>
          <div className="kpi-grid">
            {Object.entries(METRICS).map(([m, title]) => {
              const f = selected(m, currentYear),
                a = rows[m];
              return (
                <section
                  className="surface kpi-card"
                  key={m}
                  data-testid={`kpi-${m}`}
                >
                  <h2>{title}</h2>
                  <p className="kpi-period">
                    {currentYear || "—"} 年 · 合并口径
                  </p>
                  <div className="kpi-value">{amount(f)}</div>
                  <p className="kpi-yoy">
                    同比：
                    {a?.percentage_change !== null &&
                    a?.percentage_change !== undefined
                      ? `${a.percentage_change}%`
                      : a?.percentage_reason === "zero_base"
                        ? "无法计算同比"
                        : "—"}
                  </p>
                  <span className="status">
                    {f
                      ? access.label
                        ? "隔离模拟测试事实"
                        : "已确认 · 来源有效"
                      : candidates(m, currentYear).length
                        ? "待选择披露版本"
                        : "未确认或缺失"}
                  </span>
                  <div className="analysis-notes">{notes(a)}</div>
                </section>
              );
            })}
          </div>
        </>
      )}
      <section className="surface disclosure-panel">
        <div className="section-title">
          <h2>披露版本与来源</h2>
          <span className="status">
            {recoveringIntent
              ? "正在核验研究范围与来源…"
              : `已核验 ${coverage.valid} / ${coverage.expected} 项`}
          </span>
        </div>
        <p className="muted">
          {data.query.requires_version_selection
            ? `存在 ${data.query.ambiguous_periods.length} 个期间口径的多个披露版本；`
            : ""}
          {data.query.conflicting_periods.length
            ? `其中 ${data.query.conflicting_periods.length} 个存在金额冲突。`
            : ""}
          沿用此前明确选定且当前有效的来源。没有选择记录、版本变更或匹配冲突时，请重新选择。
        </p>
        <p>{intentOrigin}</p>
        {intentMessage && <p>{intentMessage}</p>}
        <p role="status">
          {coverage.expected > 0 &&
          coverage.valid === coverage.expected &&
          currentYear > previousYear &&
          previousYear > 0
            ? "本次所需来源已全部核验。"
            : "当前范围尚有缺项，请明确选择来源或补充比较期间。"}
        </p>
        {!!coverage.unresolved.length && (
          <ul aria-label="当前范围缺项">
            {coverage.unresolved.map((slot) => (
              <li key={slot.key}>
                {slot.year} 年 · {METRICS[slot.metric]}：
                {slot.status === "invalid"
                  ? "原选择已失效"
                  : slot.status === "ambiguous"
                    ? "多个有效来源，需明确选择"
                    : "尚未选择有效来源"}
              </li>
            ))}
          </ul>
        )}
        <ResearchIntentRecovery company={company.company_id} />
        <details
          open={
            coverage.valid < coverage.expected ||
            !coverage.expected ||
            undefined
          }
        >
          <summary>检查与选择各指标披露版本</summary>
          <div className="version-grid">
            {metrics.flatMap((m) => [
              versionPicker(m, currentYear),
              ...(previousYear && previousYear !== currentYear
                ? [versionPicker(m, previousYear)]
                : []),
            ])}
          </div>
        </details>
      </section>
      {previousYear >= currentYear && previousYear > 0 && (
        <p className="product-notice" role="status">
          分析不可比较：本期必须晚于上期。
        </p>
      )}
      {running && canAnalyze && (
        <p role="status" className="product-notice">
          正在核验已选事实并读取服务端分析…
        </p>
      )}
      {analysisError && <p role="alert">{analysisError}</p>}
      {page === "analysis" && (
        <Suspense fallback={<p role="status">正在加载图表…</p>}>
          <FinancialChart
            title="年度财务 · 两期对照"
            access={access}
            open={setEvidence}
            display={(f) =>
              `${unit === "yi-short" ? compactYi(f.value_cny_yuan) : formatDecimal(f.value_cny_yuan, shift)} ${unitLabel}`
            }
            metrics={selectedPairs.map((p) => {
              const a = rows[p.metric];
              const waiting = !!p.current && !!p.previous && !a;
              const blocked =
                a?.status === "blocked" || previousYear >= currentYear;
              return {
                metric: p.metric,
                blocked,
                slots: [
                  {
                    label: `${previousYear || "上期"} 年`,
                    company: company.name,
                    fact: waiting ? null : p.previous || null,
                  },
                  {
                    label: `${currentYear || "本期"} 年`,
                    company: company.name,
                    fact: waiting ? null : p.current || null,
                  },
                ],
                message: blocked
                  ? "不可比较：请核对期间、口径及来源。"
                  : waiting
                    ? "正在核验当前选择，旧图已撤下…"
                    : a
                      ? `服务端绝对变化：${formatDecimal(a.absolute_change || "", shift)} ${unitLabel}；同比：${a.percentage_change === null ? "无定义或不适用" : a.percentage_change + "%"}。${[...a.reasons, ...a.limitations].map((n) => n.message).join(" ")}`
                      : "仅展示已选有效事实；缺少另一期间时不生成同比或差额。",
              };
            })}
          />
        </Suspense>
      )}
      {page === "overview" ? (
        <>
          <div className="overview-action">
            <p>
              报告期间：
              {years.length
                ? years.map((y) => `${y} 年`).join(" / ")
                : "暂无已绑定年度"}{" "}
              · {data.reports.length} 份年报
            </p>
            <a
              href={pathFor("analysis", company.company_id)}
              onClick={(e) => {
                e.preventDefault();
                navigate("analysis", company.company_id);
              }}
            >
              查看跨年财务表格 →
            </a>
          </div>
          {reportList}
        </>
      ) : (
        <section className="surface analysis-card">
          <div className="section-title">
            <h2>跨年度财务指标</h2>
            <span className="muted">
              {previousYear || "—"} → {currentYear || "—"} · 人民币{unitLabel}
            </span>
          </div>
          <div
            className="table-scroll"
            tabIndex={0}
            aria-label="跨年度财务表格滚动区域"
          >
            <table className="financial-table">
              <thead>
                <tr>
                  {[
                    "指标",
                    "上期",
                    "本期",
                    "绝对变化",
                    "同比百分比",
                    "状态",
                    "来源",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => {
                  const c = selected(m, currentYear),
                    p = selected(m, previousYear),
                    a = rows[m];
                  return (
                    <tr key={m} data-testid={`row-${m}`}>
                      <th scope="row">{METRICS[m]}</th>
                      <td>{amount(p)}</td>
                      <td>{amount(c)}</td>
                      <td>
                        {a?.absolute_change && c && p ? (
                          <>
                            <button
                              className="money-link"
                              onClick={() => setEvidence(c)}
                              title="差额由服务端计算；打开本期原文"
                            >
                              {formatDecimal(a.absolute_change, shift)}
                            </button>
                            <p>
                              <button
                                className="text-link"
                                onClick={() => setEvidence(p)}
                              >
                                核对上期原文
                              </button>
                            </p>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {a?.percentage_change !== null &&
                        a?.percentage_change !== undefined
                          ? `${a.percentage_change}%`
                          : a?.percentage_reason === "zero_base"
                            ? "无法计算同比"
                            : "—"}
                      </td>
                      <td>
                        <span className="status">
                          {a
                            ? {
                                analyzed: "已分析",
                                partial: "partial · 部分可比",
                                blocked: "不可比较",
                              }[a.status]
                            : !c || !p
                              ? "指标不完整 / 待选版本"
                              : "等待分析"}
                        </span>
                        <div className="analysis-notes">{notes(a)}</div>
                      </td>
                      <td>
                        {[p, c]
                          .filter((f): f is Fact => !!f)
                          .map((f, index) => (
                            <details key={`${f.fact_id}/${index}`}>
                              <summary>{f.period} · 原值与单位</summary>
                              <p>
                                {f.raw_value} {f.raw_unit}
                              </p>
                              <p>
                                规范金额：{formatDecimal(f.value_cny_yuan)} CNY
                                元
                              </p>
                              <p>倍率：{f.multiplier}</p>
                              <p>
                                {data.reports.find(
                                  (r) => r.document_id === f.document_id,
                                )?.source_file || f.document_id}
                              </p>
                              <button
                                className="text-link"
                                onClick={() => setEvidence(f)}
                              >
                                原 PDF · 物理第 {f.evidence[0].physical_page} 页
                              </button>
                            </details>
                          ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="footnote">
            金额与差额来自服务端 CNY
            Decimal；仅改变显示小数点，不重算同比。缺失值不补零。零基数、非相邻年度和负基数沿服务端限制展示。
          </p>
        </section>
      )}
      {visibleEvidence && (
        <FactEvidence
          key={visibleEvidence.fact_id}
          fact={visibleEvidence}
          close={() => setEvidence(null)}
          fatal={fatal}
        />
      )}
    </>
  );
}
