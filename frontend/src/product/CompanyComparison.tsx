import { lazy, Suspense, useEffect, useState } from "react";
import { METRICS } from "../evidence/contracts.ts";
import { factsIdentity, formatDecimal, compactYi, validateComparison } from "./api.ts";
import type { Company, Comparison, DataAccess, Fact, FactQuery, Report } from "./api.ts";
import { reportsFor } from "./reports.ts";
import { FactEvidence } from "./FactEvidence.tsx";

const FinancialChart = lazy(() => import("./FinancialChart.tsx"));
type SideData = { query: FactQuery; reports: Report[] };
export function CompanyComparison({ company, companies, access }: {
  company: Company; companies: Company[]; access: DataAccess;
}) {
  const [b, setB] = useState("");
  const [data, setData] = useState<{ a: SideData; b: SideData } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [year, setYear] = useState(0);
  const [unit, setUnit] = useState("yi-short");
  const [metrics, setMetrics] = useState(Object.keys(METRICS));
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [reportChoices, setReportChoices] = useState({ a: "", b: "" });
  const [result, setResult] = useState<{ key: string; value: Comparison } | null>(null);
  const [evidence, setEvidence] = useState<{ identity: string; fact: Fact } | null>(null);
  useEffect(() => {
    if (!b || b === company.company_id) return;
    const controller = new AbortController();
    let busy = false;
    async function read() {
      if (busy) return;
      busy = true;
      try {
        const values = await Promise.allSettled([
          access.query(company.company_id, controller.signal), reportsFor(company.company_id, controller.signal),
          access.query(b, controller.signal), reportsFor(b, controller.signal),
        ]);
        for (const v of values) if (v.status === "rejected") throw v.reason;
        if (!controller.signal.aborted) {
          const q = (i: number) => (values[i] as PromiseFulfilledResult<FactQuery>).value;
          const r = (i: number) => (values[i] as PromiseFulfilledResult<Report[]>).value;
          setData({ a: { query:q(0), reports:r(1) }, b: { query:q(2), reports:r(3) } });
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) { setData(null); setResult(null); setEvidence(null); setError((e as Error).message); }
      } finally { busy = false; }
    }
    void read();
    const timer = window.setInterval(() => void read(), 30_000);
    const focus = () => { if (!document.hidden) void read(); };
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", focus);
    return () => {
      controller.abort(); clearInterval(timer); window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", focus);
    };
  }, [b, company.company_id, access, retry]);
  const identity = data ? `${factsIdentity(data.a.query)}/${factsIdentity(data.b.query)}` : "";
  const years = [...new Set(data ? [
    ...data.a.query.facts.map(f => f.period), ...data.b.query.facts.map(f => f.period),
    ...data.a.reports.map(r => r.report_year), ...data.b.reports.map(r => r.report_year),
  ] : [])].sort((a,b) => b-a);
  function options(side: "a" | "b", metric: string) {
    return data?.[side].query.facts.filter(f => access.eligible(f) && f.period === year && f.metric_key === metric) || [];
  }
  const selections = metrics.map(metric => ({ metric_key: metric,
    a: options("a", metric).find(f => f.fact_id === choices[`a/${metric}`]) || null,
    b: options("b", metric).find(f => f.fact_id === choices[`b/${metric}`]) || null,
  }));
  const key = JSON.stringify([company.company_id, b, year, metrics, choices, identity]);
  const hasSelected = selections.some(s => s.a || s.b);
  useEffect(() => {
    if (!data || !b || !year || !hasSelected || !metrics.length) return;
    const controller = new AbortController();
    void access.compare(company.company_id, b, year, selections, controller.signal)
      .then(c => validateComparison(c, company.company_id, b, year, selections, access))
      .then(c => { if (!controller.signal.aborted) setResult({ key, value:c }); })
      .catch(e => {
        if (!controller.signal.aborted) { setResult(null); setEvidence(null); setData(null); setError(e.message); }
      });
    return () => controller.abort();
    // Explicit selection/identity key revokes ownership before any late result can render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, access, hasSelected]);
  const rows = result?.key === key ? result.value.rows : [];
  function reset() { setResult(null); setEvidence(null); }
  function chooseReport(side: "a" | "b", document: string) {
    reset();
    setReportChoices(old => ({ ...old, [side]:document }));
    setChoices(old => {
      const next = { ...old };
      for (const metric of Object.keys(METRICS)) {
        const matches = options(side, metric).filter(f => f.document_id === document);
        next[`${side}/${metric}`] = matches.length === 1 ? matches[0].fact_id : "";
      }
      return next;
    });
  }
  function open(f: Fact) { setEvidence({ identity, fact:f }); }
  function amount(f: Fact | null) {
    return f ? <button className="money-link" data-fact-id={f.fact_id} onClick={() => open(f)}
      title={`原披露 ${f.raw_value} ${f.raw_unit}；规范精确金额 ${formatDecimal(f.value_cny_yuan)} 元。点击打开 PDF。`}>
      {unit === "yi-short" ? compactYi(f.value_cny_yuan) : formatDecimal(f.value_cny_yuan)}
      <small> {unit === "yi-short" ? "亿元" : "元"}</small>
    </button> : <span className="muted">未选择或缺失</span>;
  }
  function picker(side: "a" | "b", metric: string) {
    const facts = options(side,metric);
    return <details className="comparison-source"><summary>{side.toUpperCase()} · 来源与版本{facts.length > 1 ? " · 多披露版本" : ""}</summary>
      <label>逐指标覆盖
        <select aria-label={`${side.toUpperCase()} ${METRICS[metric]}披露版本`}
          value={choices[`${side}/${metric}`] || ""} disabled={!facts.length}
          onChange={e => { if ((choices[`${side}/${metric}`] || "") === e.target.value) return;
            reset(); setReportChoices(old => ({ ...old, [side]:"" }));
            setChoices(old => ({ ...old, [`${side}/${metric}`]:e.target.value })); }}>
          <option value="">{facts.length ? "明确选择来源" : "缺少有效事实"}</option>
          {facts.map(f => <option key={f.fact_id} value={f.fact_id}>
            {data?.[side].reports.find(r => r.document_id === f.document_id)?.source_file || f.document_id}
            {` · ${f.raw_value} ${f.raw_unit} · ${f.disclosure_version.slice(-8)}`}
          </option>)}
        </select>
      </label>
      {facts.find(f => f.fact_id === choices[`${side}/${metric}`]) && (() => {
        const f = facts.find(f => f.fact_id === choices[`${side}/${metric}`])!;
        return <div className="source-details"><p>原披露：{f.raw_value} {f.raw_unit}</p>
          <p>规范精确金额：{formatDecimal(f.value_cny_yuan)} 元</p>
          <p>披露版本：{f.disclosure_version}</p><p>来源版本：{f.source_revision}</p>
          <p>已确认 · 当前来源有效 · {f.accounting_basis} · {f.scope}</p>
          <button className="text-link" onClick={() => open(f)}>原 PDF · 物理第 {f.evidence[0].physical_page} 页</button>
        </div>;
      })()}
    </details>;
  }
  return <>
    <section className="surface financial-controls">
      <div className="control-row">
        <label>企业 A（基准）<strong>{company.name}</strong></label>
        <label>企业 B<select aria-label="企业 B" value={b} onChange={e => {
          reset(); setData(null); setChoices({}); setReportChoices({a:"",b:""}); setYear(0); setB(e.target.value);
        }}><option value="">选择另一家企业</option>
          {companies.filter(c => c.company_id !== company.company_id).map(c => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}
        </select></label>
        <label>同期间年度<select aria-label="对比财务年度" value={year} onChange={e => {
          reset(); setChoices({}); setReportChoices({a:"",b:""}); setYear(Number(e.target.value));
        }}><option value={0}>选择年度</option>{years.map(y => <option key={y} value={y}>{y} 年</option>)}</select></label>
        <label>展示单位<select aria-label="比较展示单位" value={unit} onChange={e => setUnit(e.target.value)}>
          <option value="yi-short">亿元（约值 · 截取4位）</option><option value="yuan">人民币元（精确）</option></select></label>
      </div>
      <fieldset className="metric-checks"><legend>比较指标</legend>{Object.entries(METRICS).map(([m,title]) => <label key={m}>
        <input type="checkbox" checked={metrics.includes(m)} onChange={e => { reset();setMetrics(old => e.target.checked ? [...old,m] : old.filter(x => x !== m)); }} />{title}
      </label>)}</fieldset>
    </section>
    {!b && <p className="product-notice">请选择企业 B，然后选择双方共同财务年度与各自披露来源。</p>}
    {error && <section className="product-message" role="alert"><p>{error}</p><p>双方旧金额、比较及原文已撤下。</p>
      <button onClick={() => { setChoices({}); reset(); setRetry(n => n+1); }}>重试比较来源</button></section>}
    {b && !data && !error && <p role="status">正在联合读取两企业当前有效事实与报告…</p>}
    {data && <>
      <section className="surface comparison-report-controls">
        <div className="section-title"><h2>明确选择双方报告</h2><span className="status warning">不自动选择披露版本</span></div>
        <div className="control-row">{(["a","b"] as const).map(side => <label key={side}>
          {side.toUpperCase()} · 按报告批量选择来源<select aria-label={`${side.toUpperCase()} 报告来源`} value={reportChoices[side]}
            disabled={!year} onChange={e => chooseReport(side,e.target.value)}>
            <option value="">选择报告后明确应用三指标</option>
            {data[side].reports.filter(r => data[side].query.facts.some(f => access.eligible(f) && f.period === year && f.document_id === r.document_id))
              .map(r => <option key={r.document_id} value={r.document_id}>{r.report_year} 年报 · {r.source_file}</option>)}
          </select></label>)}</div>
        <p className="footnote">选择报告是明确用户操作；只应用该报告内唯一事实，缺项不跨报告补齐。各指标可在表内检查与覆盖来源。</p>
        {(data.a.query.conflicting_periods.length > 0 || data.b.query.conflicting_periods.length > 0) && <p className="product-notice">存在不同金额披露冲突，请逐指标核对所选版本；系统不会替用户选择。</p>}
        {(data.a.query.facts.some(f => !f.current_valid) || data.b.query.facts.some(f => !f.current_valid)) && <p role="status" className="product-notice">来源发生变化：过期事实与对应旧比较已立即撤下，请重新核对来源。</p>}
      </section>
      <Suspense fallback={<p role="status">正在加载图表…</p>}>
        <FinancialChart title="双企业 · 同期间对照" access={access} open={open}
          display={f => `${unit === "yi-short" ? compactYi(f.value_cny_yuan) : formatDecimal(f.value_cny_yuan)} ${unit === "yi-short" ? "亿元" : "元"}`}
          metrics={selections.map(s => {
            const r = rows.find(row => row.metric_key === s.metric_key);
            return { metric: s.metric_key, blocked: r?.status === "blocked",
              slots: [{ label: `A · ${year || "—"} 年`, company: company.name, fact: r?.a ? s.a : null },
                { label: `B · ${year || "—"} 年`, company: companies.find(c => c.company_id === b)?.name || "企业 B", fact: r?.b ? s.b : null }],
              message: !r ? hasSelected ? "正在联合核验当前选择，旧图已撤下…" : "请选择年度及双方披露来源。"
                : r.status === "blocked" ? `不可比较。${r.reasons.map(n => n.message).join(" ")}`
                : r.status === "incomplete" ? "incomplete · 仅展示服务端核验有效的一侧；缺失不补零。"
                : `服务端 B − A：${unit === "yi-short" ? compactYi(r.absolute_change || "") : formatDecimal(r.absolute_change || "")} ${unit === "yi-short" ? "亿元" : "元"}；相对差异 / A：${r.percentage_change === null ? "无定义（A 为零）" : r.percentage_change + "%"}。${r.limitations.map(n => n.message).join(" ")}` };
          })} />
      </Suspense>
      <section className="surface analysis-card">
        <div className="section-title"><h2>两企业同期间财务比较</h2><span>{year || "—"} 年 · 合并 · PRC_GAAP · CNY</span></div>
        <p className="footnote">绝对差异 = B − A；相对差异 = (B − A) / A × 100%，企业 A 为基准。约值仅用于显示，原值与规范精确金额可在来源中查看。</p>
        <p className="scroll-hint">↔ 表格可局部横向滚动；指标列保持可见。</p>
        <div className="table-scroll" tabIndex={0} aria-label="双企业比较表格滚动区域"><table className="financial-table comparison-table">
          <thead><tr>{["指标","企业 A · 基准","企业 B","绝对差异 B − A","相对差异 / A","状态与限制","双方证据"].map(t => <th key={t}>{t}</th>)}</tr></thead>
          <tbody>{selections.map(s => {
            const r = rows.find(r => r.metric_key === s.metric_key);
            return <tr key={s.metric_key} data-testid={`compare-${s.metric_key}`}>
              <th scope="row">{METRICS[s.metric_key]}</th><td>{amount(r?.status === "blocked" ? null : s.a)}</td><td>{amount(r?.status === "blocked" ? null : s.b)}</td>
              <td>{r?.absolute_change !== null && r?.absolute_change !== undefined ? <span title={`精确差额：${formatDecimal(r.absolute_change)} 元`}>
                {unit === "yi-short" ? compactYi(r.absolute_change) : formatDecimal(r.absolute_change)} {unit === "yi-short" ? "亿元" : "元"}
              </span> : "—"}{r?.a && r?.b && <div className="difference-evidence"><button onClick={() => open(r.a!)}>A 原文</button><button onClick={() => open(r.b!)}>B 原文</button></div>}</td>
              <td>{r?.percentage_change !== null && r?.percentage_change !== undefined ? `${r.percentage_change}%` : r?.percentage_reason === "zero_base" ? "无定义（A 为零）" : "—"}
                {r?.a && r?.b && <div className="difference-evidence"><button onClick={() => open(r.a!)}>A 证据</button><button onClick={() => open(r.b!)}>B 证据</button></div>}</td>
              <td><span className="status">{r ? { compared:"同口径可比",partial:"partial · 部分可比",incomplete:"incomplete · 指标不完整",blocked:"不可比较" }[r.status] : !s.a || !s.b ? "incomplete · 缺失或待选来源" : "核验中"}</span>
                <div className="analysis-notes">{[...(r?.reasons || []),...(r?.limitations || [])].map(n => <p key={n.code}>{n.message}</p>)}</div></td>
              <td>{picker("a",s.metric_key)}{picker("b",s.metric_key)}</td>
            </tr>;
          })}</tbody>
        </table></div>
        {result?.key === key && <p className="footnote">公式：{result.value.formula.percentage_change_id} / v{result.value.formula.version}。当前来源有效性为最后联合复验时状态。财务数据可比不等于两企业业务结构相同。</p>}
      </section>
    </>}
    {evidence && evidence.identity === identity && <FactEvidence key={evidence.fact.fact_id} fact={evidence.fact} close={() => setEvidence(null)}
      fatal={message => { reset();setData(null);setError(message); }} />}
  </>;
}
