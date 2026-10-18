import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { METRICS } from "../evidence/contracts.ts";
import { chartData } from "./chartData.ts";
import type { ChartPoint, ChartSlot } from "./chartData.ts";
import type { DataAccess, Fact } from "./api.ts";

export type ChartMetric = { metric: string; slots: ChartSlot[]; message: string; blocked?: boolean };
const colors = ["var(--color-primary)", "var(--color-success)"];
function PointDetails({ point, display }: { point: ChartPoint; display: (f: Fact) => string }) {
  const f = point.fact;
  if (!f) return null;
  return <div className="chart-tooltip" role="status">
    <strong>{point.company} · {f.period} 年 · {METRICS[f.metric_key]}</strong>
    <p>展示值：{display(f)}</p><p>规范精确值：<span>{f.value_cny_yuan}</span> 元</p>
    <p>原披露：{f.raw_value} {f.raw_unit}</p>
    <p>{f.confirmation_kind === "simulated_test" ? "隔离 simulated_test · 非真人确认" : "已确认 · 来源有效"}</p>
    <p>披露版本：{f.disclosure_version}</p><p>来源版本：{f.source_revision}</p>
    <p>事实：{f.fact_id} · 事实组：{f.fact_set_id}</p>
    <p>原 PDF · 物理第 {f.evidence[0].physical_page} 页</p>
  </div>;
}
export default function FinancialChart({ title, metrics, access, open, display }: {
  title: string; metrics: ChartMetric[]; access: DataAccess; open: (f: Fact) => void;
  display: (f: Fact) => string;
}) {
  const [choice, setChoice] = useState("");
  const active = metrics.find(m => m.metric === choice) || metrics[0];
  const { points, unit } = chartData(active?.blocked ? [] : active?.slots || [], access);
  const drawable = points.some(p => p.coordinate !== null);
  return <section className="surface financial-chart" aria-label={title}>
    <div className="section-title"><h2>{title}</h2>
      <label>图表指标<select aria-label="图表指标" value={active?.metric || ""} onChange={e => setChoice(e.target.value)}>
        {metrics.map(m => <option value={m.metric} key={m.metric}>{METRICS[m.metric]}</option>)}
      </select></label>
    </div>
    <div className="chart-caption"><span>纵轴：{unit} · 近似绘图坐标</span><span>点击图点或下方原文入口核对 PDF</span></div>
    <p className="chart-result" role="status">{active?.message || "请选择指标及有效披露来源。"}</p>
    {drawable ? <div className="chart-plot">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={points} margin={{ top: 12, right: 20, bottom: 8, left: 8 }} accessibilityLayer>
          <CartesianGrid vertical={false} stroke="var(--color-border)" />
          <XAxis dataKey="label" tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} tickLine={false} interval={0} />
          <YAxis tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} width={70} tickLine={false}
            domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max) || 1]}
            tickFormatter={(n: number) => Number(n.toPrecision(5)).toLocaleString("zh-CN")} />
          <ReferenceLine label={{ value: "零基线", position: "insideTopRight", fill: "var(--color-text-muted)", fontSize: 11 }} y={0} stroke="var(--color-text-secondary)" strokeWidth={1.5} />
          <Tooltip cursor={{ fill: "var(--color-primary-soft)" }} shared={false} isAnimationActive={false}
            content={({ active: hovering, payload }) => {
              const point = payload?.[0]?.payload as ChartPoint | undefined;
              return hovering && point?.fact ? <PointDetails point={point} display={display} /> : null;
            }} />
          <Bar dataKey="coordinate" isAnimationActive={false} maxBarSize={100}
            shape={(props: unknown) => {
              const p = props as { x: number; y: number; width: number; height: number; index: number; payload: ChartPoint };
              const f = p.payload.fact;
              if (!f || p.payload.coordinate === null || ![p.x, p.y, p.width, p.height].every(Number.isFinite)) return <g />;
              const attr = { "data-chart-point": f.fact_id, "data-chart-identity": p.payload.id,
                fill: colors[p.index % colors.length], onClick: () => open(f), style: { cursor: "pointer" } };
              return p.payload.coordinate === 0 ? <circle {...attr} cx={p.x + p.width / 2} cy={p.y} r={5}><title>零值 · 点击原文</title></circle>
                : <rect {...attr} x={p.x} y={Math.min(p.y, p.y + p.height)} width={Math.max(0, p.width)} height={Math.abs(p.height)} rx={3} />;
            }} />
        </BarChart>
      </ResponsiveContainer>
    </div> : <div className="chart-empty" role="status">{active?.blocked ? "当前指标不可比较，未绘制金额。" : "暂无可绘制的有效图点；缺失金额不会补零。"}</div>}
    <div className="chart-evidence" aria-label="图例与可访问原文入口">
      {points.map((p, i) => <div key={p.id} className="chart-evidence-item">
        <span className="chart-swatch" style={{ background: colors[i % colors.length] }} />
        <div><strong>{p.label} · {p.company}</strong>{p.fact ? <>
          <button className="text-link" data-chart-fact-id={p.fact.fact_id} title={`规范精确值 ${p.fact.value_cny_yuan} 元；${p.fact.disclosure_version}`}
            onClick={() => open(p.fact!)}>{display(p.fact)} · 原 PDF</button>
          <small>{p.fact.confirmation_kind === "simulated_test" ? "simulated_test · 非生产结果" : "已确认 · 来源有效"}</small>
        </> : <p>{p.reason}</p>}{p.fact && p.reason && <p>{p.reason}</p>}</div>
      </div>)}
    </div>
    <p className="footnote">图表与表格共享显式选择的事实；坐标为约值，精确金额以原始 Decimal 字符串为准。零值以圆点标记，缺失留空。差额与百分比仅来自服务端。</p>
  </section>;
}
