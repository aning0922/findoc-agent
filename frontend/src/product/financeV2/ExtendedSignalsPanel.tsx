import { useEffect, useRef, useState } from "react";
import "./extendedSignals.css";

type Props = { companyId: string; documentId: string; sourceRevision: string; refreshToken?: string | number };
type Signal = { metric_key: string; status: string; reason?: string; from_date?: string; to_date?: string; delta_decimal?: string; change_percent_decimal?: string | null; percent_unavailable_reason?: string | null; from_percent_decimal?: string; to_percent_decimal?: string; delta_percentage_points_decimal?: string };
type Result = { signals: Signal[]; notices: { text: string }[] };
const decimal = (v: unknown): v is string => typeof v === "string" && /^-?\d+(?:\.\d+)?$/.test(v);
const day = (v: unknown): v is string => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
const names: Record<string, string> = { total_assets: "总资产", total_liabilities: "总负债", debt_asset_ratio: "资产负债率" };
const reasons: Record<string, string> = { two_confirmed_dates_required: "缺少两个时点的已核准数据", matched_confirmed_dates_required: "缺少相同两个时点的已核准资产与负债", assets_must_be_positive_liabilities_nonnegative: "资产须为正数且负债不能为负数", zero_baseline: "前值为零，无法计算变化百分比", negative_balance: "余额为负，无法计算变化百分比" };
function validate(x: unknown, p: Props): Result {
  const v = x as { schema_version?: string; source_status?: string; source?: Record<string, unknown>; signals?: Signal[]; notices?: { text: string }[] };
  if (!v || v.schema_version !== "extended-signals-v1" || v.source_status !== "current_valid" || v.source?.company_id !== p.companyId || v.source?.document_id !== p.documentId || v.source?.source_revision !== p.sourceRevision || !Array.isArray(v.signals) || v.signals.length !== 3 || !Array.isArray(v.notices) || !v.notices.every(n => n && typeof n.text === "string")) throw Error("invalid");
  const keys = new Set<string>();
  for (const s of v.signals) {
    if (!s || !Object.hasOwn(names, s.metric_key) || keys.has(s.metric_key) || !["available", "missing"].includes(s.status)) throw Error("invalid");
    keys.add(s.metric_key);
    if (s.status === "missing") { if (typeof s.reason !== "string") throw Error("invalid"); continue; }
    if (!day(s.from_date) || !day(s.to_date) || s.from_date >= s.to_date) throw Error("invalid");
    if (s.metric_key === "debt_asset_ratio") { if (!decimal(s.from_percent_decimal) || !decimal(s.to_percent_decimal) || !decimal(s.delta_percentage_points_decimal)) throw Error("invalid"); }
    else if (!decimal(s.delta_decimal) || !(s.change_percent_decimal === null || decimal(s.change_percent_decimal))) throw Error("invalid");
  }
  return { signals: v.signals, notices: v.notices };
}
export function ExtendedSignalsPanel(props: Props) {
  return <Signals key={JSON.stringify([props.companyId, props.documentId, props.sourceRevision])} {...props} />;
}
function Signals(props: Props) {
  const [result, setResult] = useState<Result | null>(null);
  const [status, setStatus] = useState("loading");
  const serial = useRef(0);
  const { companyId, documentId, sourceRevision, refreshToken } = props;
  useEffect(() => {
    let active = true;
    let controller: AbortController | undefined;
    async function load() {
      const seq = ++serial.current;
      controller?.abort(); controller = new AbortController();
      setResult(null); setStatus("loading");
      if (!companyId || !documentId || !/^[a-f0-9]{64}$/.test(sourceRevision)) { setStatus("empty"); return; }
      try {
        const query = new URLSearchParams({ company_id: companyId, document_id: documentId, source_revision: sourceRevision });
        const response = await fetch(`/api/financial/extended-signals?${query}`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw Error("request");
        const data = validate(await response.json(), { companyId, documentId, sourceRevision });
        if (active && serial.current === seq) { setResult(data); setStatus("ready"); }
      } catch {
        if (active && serial.current === seq) { setResult(null); setStatus("error"); }
      }
    }
    void load();
    const timer = window.setInterval(() => { void load(); }, 15000);
    const focus = () => { void load(); };
    window.addEventListener("focus", focus);
    return () => { active = false; ++serial.current; controller?.abort(); window.clearInterval(timer); window.removeEventListener("focus", focus); };
  }, [companyId, documentId, sourceRevision, refreshToken]);
  return <section className="extended-signals" aria-label="财务变化信号"><h3>财务变化信号</h3>
    <p>按所选资料的实际时点比较，数据须经人工核准；仅供核查。</p>
    {status === "loading" && <p role="status">正在核验当前来源与财务数据…</p>}
    {status === "empty" && <p>请先选择明确的企业与资料版本。</p>}
    {status === "error" && <p role="alert">当前信号不可用，来源可能已失效或日期存在歧义。请重新核对资料与确认状态。</p>}
    {result && <><div className="extended-signals__grid">{result.signals.map(s => <article key={s.metric_key}>
      <h4>{names[s.metric_key]}</h4>{s.status === "missing" ? <p>缺项：{reasons[s.reason || ""] || "当前数据不足，请核对资料与确认状态"}。</p> : <>
        <p>{s.from_date} → {s.to_date}</p>
        {s.metric_key === "debt_asset_ratio" ? <><p>比率：{s.from_percent_decimal}% → {s.to_percent_decimal}%</p><strong>变化：{s.delta_percentage_points_decimal} 个百分点</strong></> : <><strong>差额：{s.delta_decimal} 元</strong><p>变化百分比：{s.change_percent_decimal === null ? reasons[s.percent_unavailable_reason || ""] || "无法计算" : `${s.change_percent_decimal}%`}</p></>}
      </>}
    </article>)}</div>{result.notices.map((n, i) => <p key={i}>{n.text}</p>)}<small>百分比按六位小数、四舍六入五成双计算；期初日期不自动代表上一年年末。</small></>}
  </section>;
}
