import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
import { validPreference } from "../memoryApi.ts";
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
  display_preferences?: { analysis_focus: string; display_unit: string; research_habit: string };
  limitations: string[];
};
type Point = {
  period: string | number;
  report_year: number;
  value_decimal: string;
  source_revision: string | null;
  document_id: string | null;
  fact_ref?: {
    period: number;
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
    (x.lease_generation === null || Number.isInteger(x.lease_generation)) &&
    typeof x.snapshot_at === "string" &&
    (x.seed_version === null || typeof x.seed_version === "string") &&
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
        typeof v.href === "string" &&
        ["local_runtime", "preset_demo"].includes(v.origin) &&
        typeof v.status === "string" &&
        typeof v.review_status === "string",
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
    Array.isArray(x.limitations) &&
    (x.display_preferences === undefined || !!x.display_preferences &&
      Object.entries(x.display_preferences).length === 3 &&
      Object.entries(x.display_preferences).every(([k, v]) => validPreference(k, v)))
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
    x.unit === "CNY_YUAN" &&
    Array.isArray(x.comparison) &&
    Array.isArray(x.limitations) &&
    Array.isArray(x.points) &&
    x.points.every(
      (p) =>
        Number.isInteger(p.period) &&
        Number.isInteger(p.report_year) &&
        typeof p.value_decimal === "string" &&
        /^-?\d+(\.\d+)?$/.test(p.value_decimal) &&
        Number.isFinite(Number(p.value_decimal)) &&
        typeof p.source_state === "string" &&
        (sample
          ? p.source_state === "illustrative" &&
            p.source_revision === null &&
            p.document_id === null &&
            !p.fact_ref
          : typeof p.document_id === "string" &&
            typeof p.source_revision === "string" &&
            !!p.fact_ref &&
            p.fact_ref.period === p.period &&
            p.fact_ref.source_revision === p.source_revision &&
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
  const [sample, setSample] = useState(import.meta.env.VITE_FINDOC_SHOWCASE_PREVIEW_CHARTS === "1");
  const [metricChoice, setMetric] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    get<Overview>("/api/dashboard/overview", c.signal)
      .then((x) => {
        if (!validOverview(x)) throw new Error("概览数据格式无效");
        if (!c.signal.aborted) setOverview(x);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(String(e));
      });
    return () => c.abort();
  }, [retry]);
  useEffect(() => {
    const refresh = () => setRetry(x => x + 1);
    window.addEventListener('findoc-preferences-updated', refresh);
    return () => window.removeEventListener('findoc-preferences-updated', refresh);
  }, []);
  const preferences = overview?.display_preferences;
  const preferredMetric = { cash_flow: 'operating_cash_flow', profitability: 'net_profit_parent', revenue: 'revenue' }[preferences?.analysis_focus || ''] || 'revenue';
  const metric = metricChoice || preferredMetric;
  const displayUnit = preferences?.display_unit || 'CNY_HUNDRED_MILLION';
  const scale = displayUnit === 'CNY_YUAN' ? 0 : displayUnit === 'CNY_TEN_THOUSAND' ? 4 : 8;
  const axisUnit = scale === 0 ? '元' : scale === 4 ? '万元' : '亿元';
  const axisLabel = (v: number) => `${Number(v) / 10 ** scale}${axisUnit}`;
  const evidenceFirst = preferences?.research_habit !== 'compare_periods_first';
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
        if (!c.signal.aborted) setChart(x);
      })
      .catch((e) => {
        if (!c.signal.aborted) setChartError(String(e));
      });
    return () => c.abort();
  }, [effectiveCompany, sample, metric, retry]);
  const points =
    chart?.points.map((p) => ({ ...p, coordinate: Number(p.value_decimal) })) ??
    [];
  const labels: Record<string, string> = {
    completed: "已完成",
    running: "进行中",
    queued: "待开始",
    partial: "部分完成",
    interrupted: "已中断",
    waiting: "待处理",
    waiting_confirmation: "待核对",
    failed: "失败",
    refused: "已拒绝",
    created: "待开始",
    cancelled: "已取消",
  };
  const unit = chart?.unit === "CNY_YUAN" ? "元" : chart?.unit || "元";
  const colors = ["#4878d4", "#75b5c0", "#e4b665", "#ba829b"];
  const distribution =
    overview?.task_distribution.map((x) => ({
      ...x,
      label: labels[x.status] || "其他状态",
    })) || [];
  const total = distribution.reduce((n, x) => n + x.count, 0);
  const title = {
    revenue: "营业收入",
    net_profit_parent: "归母净利润",
    operating_cash_flow: "经营现金流",
  }[metric];
  const chartBody = (bar = false) =>
    chartError ? (
      <div role="alert" className="sd-empty">
        图表读取失败：{chartError}
        <button onClick={() => setRetry((x) => x + 1)}>重试</button>
      </div>
    ) : !chart ? (
      <p className="sd-empty" role="status">
        {!effectiveCompany && !sample
          ? "添加企业与年报后，可查看财务图表。"
          : "正在读取图表…"}
      </p>
    ) : !points.length ? (
      <p className="sd-empty">暂无可展示的已确认数据</p>
    ) : (
      <ResponsiveContainer width="100%" height={205}>
        {bar ? (
          <BarChart data={points} margin={{ left: 0, right: 12 }}>
            <CartesianGrid vertical={false} stroke="#edf1f5" />
            <XAxis dataKey="period" />
            <YAxis tickFormatter={(v) => axisLabel(Number(v))} />
            <Tooltip
              formatter={(_, __, item) => [
                item.payload.value_decimal + " " + unit,
                title,
              ]}
            />
            <Bar
              dataKey="coordinate"
              fill="#4878d4"
              radius={[5, 5, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        ) : (
          <LineChart data={points} margin={{ left: 0, right: 12 }}>
            <CartesianGrid vertical={false} stroke="#edf1f5" />
            <XAxis dataKey="period" />
            <YAxis tickFormatter={(v) => axisLabel(Number(v))} />
            <Tooltip
              formatter={(_, __, item) => [
                item.payload.value_decimal + " " + unit,
                title,
              ]}
            />
            <Line
              type="monotone"
              dataKey="coordinate"
              stroke="#4878d4"
              strokeWidth={3}
              dot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        )}
      </ResponsiveContainer>
    );
  return (
    <div className="showcase-dashboard">
      <header className="sd-hero">
        <div className="sd-hero-copy">
          <p className="sd-eyebrow">AI 财报研究工作空间</p>
          <h1>
            让每一次研究，
            <br />
            <em>都更有依据。</em>
          </h1>
          <p>从财报资料到研究洞察，在一个工作空间里清晰探索。</p>
          <div className="sd-search">
            <input
              aria-label="搜索本地企业"
              value={search}
              placeholder="输入企业名称或代码，开启研究"
              onChange={(e) => setSearch(e.target.value)}
            />
            <a
              className="sd-primary"
              href={`/conversations?${new URLSearchParams({ ...(effectiveCompany ? { company: effectiveCompany } : {}), question: search || "帮我开始一项企业研究" })}`}
            >
              开始研究 →
            </a>
          </div>
          {search && (
            <div className="sd-results">
              {overview?.companies
                .filter((c) => (c.name + c.security_code).includes(search))
                .map((c) => (
                  <button
                    key={c.company_id}
                    onClick={() => {
                      setSelected(c.company_id);
                      setSearch("");
                    }}
                  >
                    {c.name} {c.security_code}
                  </button>
                ))}
            </div>
          )}
          <div className="sd-secondary">
            <a href="/companies">导入年报 ↗</a>
            <a href="/tasks">查看研究 ↗</a>
          </div>
        </div>
        <div className="sd-orbit" aria-hidden="true">
          <span>✦</span>
          <small>从资料到洞察</small>
        </div>
      </header>
      <div className="sd-section-title">
        <div>
          <small>你的研究工作空间</small>
          <h2>研究概览</h2>
        </div>
        <label>
          <input
            type="checkbox"
            checked={sample}
            onChange={(e) => setSample(e.target.checked)}
          />{" "}
          界面示意数据
        </label>
      </div>
      {sample && (
        <p className="sd-watermark">界面示意数据 · 虚构企业与财务数字</p>
      )}
      {error ? (
        <div role="alert">
          概览读取失败：{error}
          <button
            onClick={() => {
              setError("");
              setRetry((x) => x + 1);
            }}
          >
            重试
          </button>
        </div>
      ) : !overview ? (
        <p role="status">正在读取概览…</p>
      ) : (
        <>
          <div className="sd-kpis">
            {(
              [
                ["companies", "跟踪企业", "▦", "/companies"],
                ["reports_ready", "已准备年报", "▤", "/companies"],
                ["research_completed", "已完成研究", "◷", "/tasks"],
                ["reports", "研究报告", "▧", "/reports"],
              ] as const
            ).map(([key, label, icon, href]) => (
              <a key={key} href={href}>
                <span className="sd-icon">{icon}</span>
                <span>{label}</span>
                <strong>{overview.kpis[key]}</strong>
                <small>查看详情 ↗</small>
              </a>
            ))}
          </div>
          <div className="sd-grid">
            <section className="sd-card" style={{ order: evidenceFirst ? 0 : 2 }}>
              <div className="sd-card-head">
                <div>
                  <h3>财务趋势</h3>
                  <p>
                    {sample
                      ? "虚构企业 A"
                      : overview.companies.find(
                          (x) => x.company_id === effectiveCompany,
                        )?.name || "企业财务"}{" "}
                    · {unit}（坐标以{axisUnit}显示）
                  </p>
                </div>
                <select
                  aria-label="财务指标"
                  value={metric}
                  onChange={(e) => setMetric(e.target.value)}
                >
                  <option value="revenue">营业收入</option>
                  <option value="net_profit_parent">归母净利润</option>
                  <option value="operating_cash_flow">经营现金流</option>
                </select>
              </div>
              {chartBody()}
              <details key={String(evidenceFirst)} open={evidenceFirst}>
                <summary>查看数据与来源</summary>
                <p>
                  {chart?.origin === "illustrative"
                    ? "界面示意"
                    : "已确认财务数据"}{" "}
                  · {chart?.limitations.join("；")}
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>期间</th>
                      <th>报告年</th>
                      <th>数值（{unit}）</th>
                      <th>来源</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chart?.points.map((p, i) => (
                      <tr key={i}>
                        <td>{p.period}</td>
                        <td>{p.report_year}</td>
                        <td>{p.value_decimal}</td>
                        <td>
                          {p.document_id ? (
                            <a
                              href={`/companies/${encodeURIComponent(effectiveCompany)}/documents`}
                            >
                              查看资料
                            </a>
                          ) : (
                            "界面示意"
                          )}
                          <details>
                            <summary>技术标识</summary>
                            {p.source_revision} / {p.fact_ref?.fact_id}
                          </details>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </section>
            <section className="sd-card" style={{ order: 1 }}>
              <div className="sd-card-head">
                <div>
                  <h3>任务状态</h3>
                  <p>当前工作空间 · 共 {total} 项</p>
                </div>
              </div>
              {total ? (
                <div className="sd-donut">
                  <ResponsiveContainer width="100%" height={185}>
                    <PieChart>
                      <Pie
                        data={distribution}
                        dataKey="count"
                        nameKey="label"
                        innerRadius={53}
                        outerRadius={76}
                        paddingAngle={3}
                        isAnimationActive={false}
                      >
                        {distribution.map((x, i) => (
                          <Cell
                            key={x.status}
                            fill={colors[i % colors.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v) => [`${v} 项`, "任务"]} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="sd-donut-total">
                    <b>{total}</b>
                    <span>全部任务</span>
                  </div>
                </div>
              ) : (
                <p className="sd-empty">暂无任务</p>
              )}
              <div className="sd-legend">
                {distribution.map((x, i) => (
                  <span key={x.status}>
                    <i style={{ background: colors[i % colors.length] }} />
                    {x.label} {x.count}
                  </span>
                ))}
              </div>
              <details>
                <summary>任务数据表</summary>
                <table>
                  <tbody>
                    {distribution.map((x) => (
                      <tr key={x.status}>
                        <td>{x.label}</td>
                        <td>{x.count} 项</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </section>
            <section className="sd-card" style={{ order: evidenceFirst ? 2 : 0 }}>
              <div className="sd-card-head">
                <div>
                  <h3>各期财务对比</h3>
                  <p>
                    {title} · {unit}（坐标以{axisUnit}显示）
                  </p>
                </div>
              </div>
              {chartBody(true)}
            </section>
            <section className="sd-card" style={{ order: 3 }}>
              <div className="sd-card-head">
                <div>
                  <h3>近期研究</h3>
                  <p>继续探索你的研究记录</p>
                </div>
                <a href="/tasks">全部 →</a>
              </div>
              {overview.recent_research.length ? (
                overview.recent_research.map((r) => (
                  <a className="sd-recent" key={r.id} href={safeHref(r.href)}>
                    <span className="sd-icon">▧</span>
                    <div>
                      <b>{r.title}</b>
                      <small>{r.origin === "preset_demo" ? "预置演示 · 历史模型结果，本次未重新生成" : "已保存研究 · 打开后重新核验来源"}</small>
                    </div>
                    <span className="sd-badge">
                      {labels[r.status] || "待处理"}
                    </span>
                  </a>
                ))
              ) : (
                <p className="sd-empty">暂无研究记录</p>
              )}
            </section>
          </div>
          <section className="sd-card sd-suggestions">
            <div className="sd-card-head">
              <div>
                <h3>推荐问题</h3>
                <p>从一个问题开始探索 · 点击仅预填</p>
              </div>
              <span>✦</span>
            </div>
            <div>
              {overview.suggested_questions.map((q) => (
                <a key={q.id} href={questionHref(q.href)}>
                  ✧　{q.text}
                  <span>↗</span>
                </a>
              ))}
            </div>
          </section>
          <details className="sd-meta">
            <summary>数据来源与限制</summary>
            <p>本地研究空间 · {overview.limitations.join("；")}</p>
            <p>
              快照 {overview.snapshot_at} · 代际 {overview.lease_generation}
            </p>
          </details>
        </>
      )}
    </div>
  );
}
