import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Company, DataAccess } from "../api.ts";
import "./dashboard.css";

type Overview = {
  lease_generation: number | null;
  snapshot_at: string;
  seed_version: string | null;
  schema_version: string;
  data_origin: string;
  kpis: {
    companies: number;
    reports_ready: number;
    research_completed: number;
    reports: number;
  };
  task_distribution: { status: string; count: number }[];
  recent_research: {
    id: string;
    title: string;
    status: string;
    href: string;
    origin: string;
    review_status: string;
  }[];
  suggested_questions: { id: string; text: string; href: string }[];
  companies: { company_id: string; name: string; security_code: string }[];
  limitations: string[];
};
type Point = {
  period: string | number;
  report_year: number;
  value_decimal: string;
  source_revision: string | null;
  document_id: string | null;
  fact_ref?: {
    fact_set_id: string;
    fact_id: string;
    receipt_id: string;
    disclosure_version: string;
    source_revision: string;
  } | null;
  source_state: string;
};
type Charts = {
  schema_version: string;
  company_id: string;
  metric_key: string;
  unit: string;
  origin: string;
  points: Point[];
  comparison: unknown[];
  empty_reason: string | null;
  limitations: string[];
};
function safeHref(href: string): string | undefined {
  return href.startsWith("/") && !href.startsWith("//") && !href.includes("\\")
    ? href
    : undefined;
}
function questionHref(href: string): string | undefined {
  if (!safeHref(href)) return undefined;
  const url = new URL(href, location.origin);
  if (
    url.pathname !== "/conversations" ||
    url.searchParams.getAll("question").length !== 1 ||
    url.searchParams.getAll("company").length > 1 ||
    (url.searchParams.get("question") || "").length > 1000
  )
    return undefined;
  return url.pathname + url.search;
}
function validOverview(x: Overview): boolean {
  return (
    x?.schema_version === "dashboard-overview-v1" &&
    ["local_runtime", "preset_demo"].includes(x.data_origin) &&
    !!x.kpis &&
    ["companies", "reports_ready", "research_completed", "reports"].every(
      (k) =>
        Number.isInteger((x.kpis as unknown as Record<string, number>)[k]) &&
        (x.kpis as unknown as Record<string, number>)[k] >= 0,
    ) &&
    Array.isArray(x.task_distribution) &&
    x.task_distribution.every(
      (v) =>
        typeof v.status === "string" &&
        Number.isInteger(v.count) &&
        v.count >= 0,
    ) &&
    Array.isArray(x.recent_research) &&
    x.recent_research.every(
      (v) =>
        typeof v.id === "string" &&
        typeof v.title === "string" &&
        typeof v.href === "string",
    ) &&
    Array.isArray(x.suggested_questions) &&
    x.suggested_questions.every(
      (v) =>
        typeof v.id === "string" &&
        typeof v.text === "string" &&
        typeof v.href === "string",
    ) &&
    Array.isArray(x.companies) &&
    x.companies.every(
      (v) =>
        typeof v.company_id === "string" &&
        typeof v.name === "string" &&
        typeof v.security_code === "string",
    ) &&
    Array.isArray(x.limitations)
  );
}
function validChart(
  x: Charts,
  company: string,
  metric: string,
  sample: boolean,
): boolean {
  return (
    x?.schema_version === "dashboard-charts-v1" &&
    x.metric_key === metric &&
    (sample
      ? x.origin === "illustrative" && x.company_id === "illustrative-company-a"
      : x.origin === "confirmed_financial" && x.company_id === company) &&
    typeof x.unit === "string" &&
    Array.isArray(x.comparison) &&
    Array.isArray(x.limitations) &&
    Array.isArray(x.points) &&
    x.points.every(
      (p) =>
        (typeof p.period === "string" || Number.isInteger(p.period)) &&
        Number.isInteger(p.report_year) &&
        typeof p.value_decimal === "string" &&
        /^-?\d+(\.\d+)?$/.test(p.value_decimal) &&
        Number.isFinite(Number(p.value_decimal)) &&
        typeof p.source_state === "string" &&
        (sample
          ? p.source_state === "illustrative" && !p.fact_ref
          : typeof p.document_id === "string" &&
            typeof p.source_revision === "string" &&
            !!p.fact_ref &&
            [
              "fact_set_id",
              "fact_id",
              "receipt_id",
              "disclosure_version",
              "source_revision",
            ].every(
              (k) =>
                typeof (p.fact_ref as unknown as Record<string, unknown>)[k] ===
                "string",
            )),
    )
  );
}
async function get<T>(url: string, signal: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal, credentials: "same-origin" });
  if (!r.ok) throw new Error(`请求失败 (${r.status})`);
  return r.json() as Promise<T>;
}
export function ShowcaseDashboard({
  company,
}: {
  companies: Company[];
  company: string;
  access?: DataAccess;
}) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [chart, setChart] = useState<Charts | null>(null);
  const [error, setError] = useState("");
  const [chartError, setChartError] = useState("");
  const [selected, setSelected] = useState(company);
  const [search, setSearch] = useState("");
  const [sample, setSample] = useState(false);
  const [metric, setMetric] = useState("revenue");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    get<Overview>("/api/dashboard/overview", c.signal)
      .then((x) => {
        if (!validOverview(x)) throw new Error("概览数据格式无效");
        setOverview(x);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(String(e));
      });
    return () => c.abort();
  }, [retry]);
  const effectiveCompany = selected || overview?.companies[0]?.company_id || "";
  useEffect(() => {
    const c = new AbortController();
    if (!effectiveCompany && !sample) {
      setChart(null);
      return () => c.abort();
    }
    setChart(null);
    setChartError("");
    const q = new URLSearchParams({
      company_id: effectiveCompany,
      metric_key: metric,
      sample_mode: String(sample),
    });
    get<Charts>(`/api/dashboard/charts?${q}`, c.signal)
      .then((x) => {
        if (!validChart(x, effectiveCompany, metric, sample))
          throw new Error("图表数据身份或格式无效");
        setChart(x);
      })
      .catch((e) => {
        if (!c.signal.aborted) setChartError(String(e));
      });
    return () => c.abort();
  }, [effectiveCompany, sample, metric, retry]);
  const points =
    chart?.points.map((p) => ({ ...p, coordinate: Number(p.value_decimal) })) ??
    [];
  return (
    <div className="showcase-dashboard">
      <header>
        <p>FINANCIAL RESEARCH WORKSPACE</p>
        <h1>
          让每一次研究，
          <br />
          <em>都更有依据。</em>
        </h1>
        <div className="sd-orbit" aria-hidden="true">
          <span>✦</span>
        </div>
        <p>从资料到洞察，探索你的研究工作空间。</p>
        <label>
          搜索本地企业{" "}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="企业名称或代码"
          />
        </label>
        {selected && (
          <p>
            <a
              href={`/conversations?${new URLSearchParams({ company: selected, question: "帮我开始研究这家企业" })}`}
            >
              进入研究助手 →
            </a>
          </p>
        )}
        {search && (
          <ul>
            {overview?.companies
              .filter((c) => `${c.name} ${c.security_code}`.includes(search))
              .map((c) => (
                <li key={c.company_id}>
                  <button
                    onClick={() => {
                      setSelected(c.company_id);
                      setSearch("");
                    }}
                  >
                    {c.name} {c.security_code}
                  </button>
                </li>
              ))}
          </ul>
        )}
      </header>
      {error ? (
        <p role="alert">
          概览读取失败：{error}{" "}
          <button
            onClick={() => {
              setError("");
              setRetry((x) => x + 1);
            }}
          >
            重试
          </button>
        </p>
      ) : !overview ? (
        <p role="status">正在读取概览…</p>
      ) : (
        <>
          <p>
            数据来源：
            {overview.data_origin === "local_runtime"
              ? "本地研究空间"
              : "预置演示"}{" "}
            · {overview.limitations.join("；")}
          </p>
          <section className="sd-kpis">
            {Object.entries(overview.kpis).map(([key, value]) => (
              <article key={key}>
                <span className="sd-icon">✧</span>
                <span>
                  {(
                    {
                      companies: "跟踪企业",
                      reports_ready: "已准备年报",
                      research_completed: "已完成研究",
                      reports: "研究报告",
                    } as Record<string, string>
                  )[key] || key}
                </span>
                <strong>{value}</strong>
              </article>
            ))}
          </section>
          <section>
            <h2>研究图表</h2>
            <label>
              指标{" "}
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                <option value="revenue">营业收入</option>
                <option value="net_profit_parent">归母净利润</option>
                <option value="operating_cash_flow">经营现金流</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={sample}
                onChange={(e) => setSample(e.target.checked)}
              />{" "}
              查看独立示意数据
            </label>
            {(sample || chart?.origin === "illustrative") && (
              <p className="sd-watermark">界面示意数据 · 不是真实财报</p>
            )}
            {chartError ? (
              <p role="alert">
                图表读取失败：{chartError}{" "}
                <button onClick={() => setRetry((x) => x + 1)}>重试</button>
              </p>
            ) : !chart ? (
              <p role="status">
                {!effectiveCompany && !sample
                  ? "暂无企业，请添加企业或选择界面示意数据。"
                  : "正在读取图表…"}
              </p>
            ) : (
              <>
                <p>
                  来源：
                  {chart.origin === "illustrative"
                    ? "界面示意"
                    : "已确认财务数据"}{" "}
                  · 指标：
                  {
                    (
                      {
                        revenue: "营业收入",
                        net_profit_parent: "归母净利润",
                        operating_cash_flow: "经营现金流",
                      } as Record<string, string>
                    )[chart.metric_key]
                  }{" "}
                  · 单位：
                  {chart.unit}
                </p>
                {chart.limitations.map((x) => (
                  <p key={x}>{x}</p>
                ))}
                {points.length ? (
                  <div className="sd-charts">
                    <figure>
                      <figcaption>趋势 · {chart.unit}</figcaption>
                      <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={points}>
                          <CartesianGrid />
                          <XAxis dataKey="period" />
                          <YAxis />
                          <Tooltip
                            formatter={(_, __, item) => [
                              item.payload.value_decimal + " " + chart.unit,
                              "数值",
                            ]}
                          />
                          <Line
                            dataKey="coordinate"
                            stroke="#4878d4"
                            isAnimationActive={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </figure>
                    <figure>
                      <figcaption>各期对比 · {chart.unit}</figcaption>
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={points}>
                          <XAxis dataKey="period" />
                          <YAxis />
                          <Tooltip
                            formatter={(_, __, item) => [
                              item.payload.value_decimal + " " + chart.unit,
                              "数值",
                            ]}
                          />
                          <Bar
                            dataKey="coordinate"
                            fill="#4878d4"
                            isAnimationActive={false}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </figure>
                  </div>
                ) : (
                  <p>{chart.empty_reason || "暂无可展示数据"}</p>
                )}
                <details>
                  <summary>查看图表数据及来源</summary>
                  <table>
                    <thead>
                      <tr>
                        <th>期间</th>
                        <th>报告年</th>
                        <th>数值（{chart.unit}）</th>
                        <th>来源</th>
                      </tr>
                    </thead>
                    <tbody>
                      {chart.points.map((p, i) => (
                        <tr key={i}>
                          <td>{p.period}</td>
                          <td>{p.report_year}</td>
                          <td>{p.value_decimal}</td>
                          <td>
                            {p.document_id ? (
                              <a
                                href={`/companies/${encodeURIComponent(effectiveCompany)}/documents`}
                              >
                                {p.document_id}
                              </a>
                            ) : (
                              "示意"
                            )}{" "}
                            / {p.source_revision} / {p.source_state} /{" "}
                            {p.fact_ref?.fact_id || "无事实引用"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              </>
            )}
          </section>
          <section>
            <h2>任务状态</h2>
            {overview.task_distribution.length ? (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={overview.task_distribution}
                      dataKey="count"
                      innerRadius={45}
                      outerRadius={70}
                      nameKey="status"
                      fill="#4878d4"
                      isAnimationActive={false}
                    />
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <table>
                  <tbody>
                    {overview.task_distribution.map((x) => (
                      <tr key={x.status}>
                        <td>{x.status}</td>
                        <td>{x.count} 项</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <p>暂无任务</p>
            )}
          </section>
          <section>
            <h2>近期研究</h2>
            {overview.recent_research.length ? (
              overview.recent_research.map((r) => (
                <p key={r.id}>
                  <a href={safeHref(r.href)}>{r.title}</a> · {r.status} ·{" "}
                  {r.origin} · {r.review_status}
                </p>
              ))
            ) : (
              <p>暂无研究记录</p>
            )}
          </section>
          <section>
            <h2>建议问题</h2>
            {overview.suggested_questions.length ? (
              overview.suggested_questions.map((q) => (
                <p key={q.id}>
                  <a href={questionHref(q.href)}>{q.text}</a>
                </p>
              ))
            ) : (
              <p>暂无建议问题</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
