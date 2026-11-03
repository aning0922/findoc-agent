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
  period: string;
  report_year: number;
  value_decimal: string;
  source_revision: string;
  document_id: string;
  fact_ref: string | null;
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
  useEffect(() => {
    const c = new AbortController();
    get<Overview>("/api/dashboard/overview", c.signal)
      .then(setOverview)
      .catch((e) => {
        if (!c.signal.aborted) setError(String(e));
      });
    return () => c.abort();
  }, []);
  useEffect(() => {
    const c = new AbortController();
    setChart(null);
    setChartError("");
    const q = new URLSearchParams({
      company_id: selected,
      metric_key: "revenue",
      sample_mode: String(sample),
    });
    get<Charts>(`/api/dashboard/charts?${q}`, c.signal)
      .then(setChart)
      .catch((e) => {
        if (!c.signal.aborted) setChartError(String(e));
      });
    return () => c.abort();
  }, [selected, sample]);
  const points =
    chart?.points
      .filter((p) => Number.isFinite(Number(p.value_decimal)))
      .map((p) => ({ ...p, coordinate: Number(p.value_decimal) })) ?? [];
  return (
    <div className="showcase-dashboard">
      <header>
        <p>FINANCIAL RESEARCH WORKSPACE</p>
        <h1>让每一次研究，都更有依据。</h1>
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
        <p role="alert">概览读取失败：{error}</p>
      ) : !overview ? (
        <p role="status">正在读取概览…</p>
      ) : (
        <>
          <p>
            数据来源：{overview.data_origin} · {overview.limitations.join("；")}
          </p>
          <section className="sd-kpis">
            {Object.entries(overview.kpis).map(([key, value]) => (
              <article key={key}>
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
              <p role="alert">图表读取失败：{chartError}</p>
            ) : !chart ? (
              <p role="status">正在读取图表…</p>
            ) : (
              <>
                <p>
                  来源：{chart.origin} · 指标：{chart.metric_key} · 单位：
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
                            {p.document_id} / {p.source_revision} /{" "}
                            {p.source_state} / {p.fact_ref || "无事实引用"}
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
