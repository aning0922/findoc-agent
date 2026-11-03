import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Company } from "../api.ts";
import { listDocuments } from "../documentLibraryApi.ts";
import type { DocumentRow } from "../documentLibraryApi.ts";
import { validateSource } from "../../evidence/contracts.ts";
import type { Source } from "../../evidence/contracts.ts";
import "./extendedFinance.css";
type Metric = {
  schema_version: string;
  metric_id: string;
  company_id: string;
  document_id: string;
  source_revision: string;
  report_year: number;
  as_of_date: string | null;
  period: number | null;
  period_kind: string;
  scope: string;
  basis: string | null;
  metric_key: string;
  value_decimal: string | null;
  unit: string;
  status: string;
  source_status?: string;
  confirmation_ref?: { receipt_id: string; confirmation_kind: string } | null;
  evidence_refs: { physical_page: number; text?: string }[];
  unsupported_reasons: string[];
};
type Review = {
  schema_version: string;
  review_id: string;
  review_sha256: string;
  metrics: Metric[];
  acceptable: boolean;
};
type Pending = { id: string; action: string };
const key = (company: string) => `findoc:finance-v2-operation:${company}`;
const hash = /^[a-f0-9]{64}$/,
  uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const labels: Record<string, string> = {
  total_assets: "总资产",
  total_liabilities: "总负债",
  debt_asset_ratio: "资产负债率",
  candidate: "候选 · 未核准",
  confirmed: "已核对",
  unsupported: "不支持／来源失效",
};
function validMetric(x: Metric, company: string) {
  return (
    x?.schema_version === "extended-metric-v2" &&
    uuid.test(x.metric_id) &&
    x.company_id === company &&
    hash.test(x.source_revision) &&
    typeof x.document_id === "string" &&
    Number.isInteger(x.report_year) &&
    x.report_year >= 1 &&
    x.report_year <= 9999 &&
    (x.metric_key === "debt_asset_ratio"
      ? x.unit === "PERCENT"
      : x.unit === "CNY_YUAN") &&
    x.period_kind === "instant" &&
    x.scope === "consolidated" &&
    (x.basis === null || typeof x.basis === "string") &&
    ["total_assets", "total_liabilities", "debt_asset_ratio"].includes(
      x.metric_key,
    ) &&
    ["candidate", "confirmed", "unsupported"].includes(x.status) &&
    (x.status !== "confirmed" ||
      x.metric_key === "debt_asset_ratio" ||
      (x.confirmation_ref?.confirmation_kind === "local_operator" &&
        uuid.test(x.confirmation_ref.receipt_id))) &&
    Array.isArray(x.evidence_refs) &&
    x.evidence_refs.every(
      (e) => Number.isInteger(e.physical_page) && e.physical_page > 0,
    ) &&
    Array.isArray(x.unsupported_reasons) &&
    (x.status === "unsupported"
      ? x.value_decimal === null
      : typeof x.value_decimal === "string" &&
        /^-?\d+(\.\d+)?$/.test(x.value_decimal) &&
        Number.isFinite(Number(x.value_decimal)) &&
        typeof x.as_of_date === "string" &&
        /^\d{4}-\d{2}-\d{2}$/.test(x.as_of_date) &&
        Number.isFinite(Date.parse(x.as_of_date)) &&
        new Date(x.as_of_date).toISOString().slice(0, 10) === x.as_of_date &&
        x.period === Number(x.as_of_date.slice(0, 4)))
  );
}
class HttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`请求未完成（${status}），请核对当前来源与授权。`);
    this.status = status;
  }
}
async function request<T>(
  path: string,
  signal: AbortSignal,
  body?: object,
): Promise<T> {
  const r = await fetch(`/api${path}`, {
    signal,
    credentials: "same-origin",
    cache: "no-store",
    ...(body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  if (!r.ok) throw new HttpError(r.status);
  return r.json() as Promise<T>;
}
export function ExtendedFinancePanel({ company }: { company: Company }) {
  const [docs, setDocs] = useState<DocumentRow[]>([]),
    [document, setDocument] = useState(""),
    [source, setSource] = useState<Source | null>(null),
    [metrics, setMetrics] = useState<Metric[]>([]),
    [chosen, setChosen] = useState<string[]>([]),
    [review, setReview] = useState<Review | null>(null),
    [checked, setChecked] = useState<string[]>([]),
    [owner, setOwner] = useState(false),
    [pending, setPending] = useState<Pending | null>(null),
    [message, setMessage] = useState(""),
    [snapshot, setSnapshot] = useState(""),
    [busy, setBusy] = useState(false),
    [blocked, setBlocked] = useState(false);
  const epoch = useRef(0),
    control = useRef<AbortController | null>(null),
    lock = useRef(false),
    listSeq = useRef(0);
  async function readMetrics(signal: AbortSignal, n: number) {
    const seq = ++listSeq.current;
    setMetrics([]);
    try {
      const x = await request<{
        schema_version: string;
        company_id: string;
        metrics: Metric[];
      }>(
        "/financial/extended-metrics?" +
          new URLSearchParams({ company_id: company.company_id }),
        signal,
      );
      if (
        x.schema_version !== "extended-metric-list-v2" ||
        x.company_id !== company.company_id ||
        !Array.isArray(x.metrics) ||
        !x.metrics.every(
          (m) =>
            validMetric(m, company.company_id) &&
            ["current_valid", "unavailable"].includes(m.source_status || ""),
        )
      )
        throw Error("指标身份或结构无法核验。");
      if (n === epoch.current && seq === listSeq.current) setMetrics(x.metrics);
    } catch (e) {
      if (n === epoch.current && seq === listSeq.current && !signal.aborted) {
        setMetrics([]);
        setMessage((e as Error).message);
      }
      throw e;
    }
  }
  useEffect(() => {
    const n = ++epoch.current,
      c = new AbortController();
    control.current?.abort();
    lock.current = false;
    setBusy(false);
    setDocs([]);
    setDocument("");
    setSource(null);
    setChosen([]);
    setReview(null);
    setChecked([]);
    setMetrics([]);
    setOwner(false);
    setSnapshot("");
    setMessage("");
    try {
      const x = JSON.parse(
        sessionStorage.getItem(key(company.company_id)) || "null",
      );
      if (
        x &&
        (!uuid.test(x.id) ||
          !["collect", "review", "confirm", "analyse", "revoke"].includes(
            x.action,
          ))
      )
        throw Error();
      setPending(x);
      setBlocked(false);
    } catch {
      setBlocked(true);
      setPending(null);
      setMessage("本机操作线索无法读取，新写入已关闭。");
    }
    void listDocuments(c.signal)
      .then((x) => {
        if (n === epoch.current)
          setDocs(
            x.filter(
              (d) =>
                d.metadata?.company_id === company.company_id &&
                d.status === "ready",
            ),
          );
      })
      .catch(() => {
        if (n === epoch.current && !c.signal.aborted)
          setMessage("资料目录暂不可读。");
      });
    void readMetrics(c.signal, n).catch(() => {});
    const refresh = () => {
      if (!lock.current)
        void readMetrics(c.signal, epoch.current).catch(() => {});
    };
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => {
      epoch.current++;
      c.abort();
      control.current?.abort();
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [company.company_id]);
  const selected = metrics.filter((m) => chosen.includes(m.metric_id));
  const current = metrics.filter(
    (m) =>
      source &&
      m.document_id === source.document_id &&
      m.source_revision === source.source_revision,
  );
  const confirmed = current.filter(
    (m) =>
      m.status === "confirmed" &&
      m.value_decimal !== null &&
      m.source_status === "current_valid" &&
      m.confirmation_ref?.confirmation_kind === "local_operator" &&
      ["total_assets", "total_liabilities"].includes(m.metric_key),
  );
  const reviewCurrent =
    !!review &&
    review.metrics.every((r) =>
      metrics.some(
        (m) =>
          m.metric_id === r.metric_id &&
          m.status === "candidate" &&
          m.source_status === "current_valid" &&
          m.document_id === source?.document_id &&
          m.source_revision === source?.source_revision,
      ),
    );
  const chart = confirmed.map((m) => ({
    ...m,
    name: labels[m.metric_key],
    coordinate: Number(m.value_decimal),
  }));
  const pair =
    selected.length === 2 &&
    new Set(selected.map((m) => m.metric_key)).size === 2 &&
    selected.every(
      (m) =>
        ["total_assets", "total_liabilities"].includes(m.metric_key) &&
        m.document_id === source?.document_id &&
        m.source_revision === source?.source_revision &&
        m.as_of_date === selected[0].as_of_date,
    );
  const begin = () => {
    if (lock.current) return null;
    lock.current = true;
    setBusy(true);
    const c = new AbortController(),
      n = epoch.current;
    control.current = c;
    return { c, n };
  };
  const end = (n: number) => {
    if (n === epoch.current) {
      lock.current = false;
      setBusy(false);
      control.current = null;
    }
  };
  async function loadSource() {
    const t = begin();
    if (!t) return;
    setSource(null);
    setReview(null);
    setChecked([]);
    setChosen([]);
    try {
      const x = validateSource(
        await request<Source>(
          `/documents/${encodeURIComponent(document)}/source?${new URLSearchParams({ company_id: company.company_id })}`,
          t.c.signal,
        ),
        company.company_id,
        document,
      );
      if (t.n === epoch.current) {
        setSource(x);
        setMessage("已读取明确来源版本；收集候选需要下一步显式操作。");
      }
    } catch (e) {
      if (t.n === epoch.current && !t.c.signal.aborted)
        setMessage((e as Error).message);
    } finally {
      end(t.n);
    }
  }
  async function authorize(signal: AbortSignal) {
    const n = epoch.current;
    const x = await request<{
      schema_version: string;
      state: string;
      can_review: boolean;
      lease_generation: number;
      remaining_seconds: number;
      server_now: string;
      expires_at: string;
      owner_elevated_until: string | null;
    }>("/demo/session", signal);
    const can =
      x.schema_version === "demo-session-v1" &&
      x.state === "active" &&
      x.can_review === true &&
      Number.isInteger(x.lease_generation) &&
      x.lease_generation >= 0 &&
      x.remaining_seconds > 0 &&
      Number.isFinite(Date.parse(x.server_now)) &&
      Date.parse(x.expires_at) > Date.parse(x.server_now) &&
      typeof x.owner_elevated_until === "string" &&
      Date.parse(x.owner_elevated_until) > Date.parse(x.server_now);
    if (n !== epoch.current) throw Error("企业或来源已切换，请重新操作。");
    setOwner(can);
    if (!can)
      throw Error("请先使用页面上方的所有者授权入口；财务接受须由真人操作。");
  }
  async function write(action: string, path: string, body: object) {
    if (pending || blocked) return;
    const t = begin();
    if (!t) return;
    const op = { id: crypto.randomUUID(), action };
    let sent = false;
    setMessage("");
    try {
      if (action === "confirm" || action === "revoke")
        await authorize(t.c.signal);
      if (t.n !== epoch.current) return;
      sessionStorage.setItem(key(company.company_id), JSON.stringify(op));
      setPending(op);
      sent = true;
      const result = await request<Record<string, unknown>>(path, t.c.signal, {
        operation_id: op.id,
        ...body,
      });
      if (t.n !== epoch.current) return;
      if (action === "collect") {
        if (
          result.schema_version !== "extended-metric-collection-v2" ||
          !Array.isArray(result.metrics) ||
          !result.metrics.every(
            (m) =>
              validMetric(m as Metric, company.company_id) &&
              (m as Metric).document_id === source?.document_id &&
              (m as Metric).source_revision === source?.source_revision,
          )
        )
          throw Error("候选集合无法核验。");
      } else if (action === "review") {
        const x = result as unknown as Review;
        if (
          x.schema_version !== "extended-review-v2" ||
          !uuid.test(x.review_id) ||
          !hash.test(x.review_sha256) ||
          typeof x.acceptable !== "boolean" ||
          !Array.isArray(x.metrics) ||
          !x.metrics.every((m) => validMetric(m, company.company_id)) ||
          x.metrics.length !== chosen.length ||
          x.metrics.some(
            (m) =>
              !chosen.includes(m.metric_id) ||
              m.document_id !== source?.document_id ||
              m.source_revision !== source?.source_revision,
          )
        )
          throw Error("核对快照身份无法核验。");
        setReview(x);
        setChecked([]);
      } else if (action === "analyse") {
        if (
          !validMetric(result as unknown as Metric, company.company_id) ||
          result.document_id !== source?.document_id ||
          result.source_revision !== source?.source_revision ||
          result.as_of_date !== selected[0]?.as_of_date ||
          !Array.isArray(result.input_refs) ||
          result.input_refs.length !== 2 ||
          result.input_refs.some((id) => !chosen.includes(String(id))) ||
          result.metric_key !== "debt_asset_ratio" ||
          typeof result.value_decimal !== "string"
        )
          throw Error("比率快照无法核验。");
        setSnapshot(
          `${result.value_decimal}%（服务端保存的分析快照，非当前资格凭据）`,
        );
      } else if (action === "confirm") {
        if (
          !review ||
          result.schema_version !== "extended-confirmation-v2" ||
          !uuid.test(String(result.receipt_id)) ||
          result.review_id !== review?.review_id ||
          result.review_sha256 !== review?.review_sha256 ||
          result.confirmation_kind !== "local_operator" ||
          !Array.isArray(result.metric_refs) ||
          result.metric_refs.length !== review.metrics.length ||
          result.metric_refs.some(
            (x) => !review.metrics.some((m) => m.metric_id === x),
          )
        )
          throw Error("回执身份无法核验。");
        setReview(null);
        setChecked([]);
      }
      sessionStorage.removeItem(key(company.company_id));
      setPending(null);
      setMessage(
        action === "review"
          ? "核对快照已准备，尚未产生财务确认。"
          : "操作已返回，正在只读重新核验当前指标。",
      );
      await readMetrics(t.c.signal, t.n);
    } catch (e) {
      if (t.n === epoch.current && !t.c.signal.aborted) {
        setMetrics([]);
        setSnapshot("");
        setOwner(false);
        setMessage(
          sent
            ? "操作结果待查证，保留原操作号；请只读查询，不要重复提交。"
            : (e as Error).message,
        );
      }
    } finally {
      end(t.n);
    }
  }
  async function recover() {
    if (!pending) return;
    const t = begin();
    if (!t) return;
    try {
      const x = await request<{
        operation_id: string;
        state: string;
        historical_snapshot: boolean;
        result: unknown;
      }>(`/financial/extended-operations/${pending.id}`, t.c.signal);
      if (t.n !== epoch.current) return;
      if (
        x.operation_id !== pending.id ||
        x.historical_snapshot !== true ||
        !["completed", "failed", "unknown"].includes(x.state)
      )
        throw Error("操作身份无法核验。");
      setSnapshot("历史操作结果仅为保存快照，不能恢复当前财务授权。");
      if (x.state !== "unknown") {
        sessionStorage.removeItem(key(company.company_id));
        setPending(null);
      }
      setReview(null);
      setChecked([]);
      await readMetrics(t.c.signal, t.n);
      if (t.n === epoch.current)
        setMessage(
          x.state === "unknown"
            ? "操作结果仍未知，仅允许继续只读查证。"
            : "历史操作已读回，当前资格以重新查询的指标为准。",
        );
    } catch (e) {
      if (t.n === epoch.current && !t.c.signal.aborted) {
        setMetrics([]);
        setMessage((e as Error).message);
      }
    } finally {
      end(t.n);
    }
  }
  async function refresh() {
    const t = begin();
    if (!t) return;
    setReview(null);
    setChecked([]);
    try {
      await readMetrics(t.c.signal, t.n);
    } catch {
    } finally {
      end(t.n);
    }
  }
  return (
    <section className="finance-v2">
      <div className="fv-head">
        <div>
          <span>扩展财务研究 · v2</span>
          <h2>资产与负债</h2>
          <p>来源 → 候选 → 核对快照 → 真人接受 → 服务端比率</p>
        </div>
        <button disabled={busy} onClick={() => void refresh()}>
          只读核验指标
        </button>
      </div>
      <p>
        本流程独立于旧六事实 ACCEPT／SAVE／RESUME；候选、OCR
        与模型输出不会自动核准。
      </p>
      <div className="fv-source">
        <label>
          明确选择已就绪年报
          <select
            value={document}
            onChange={(e) => {
              epoch.current++;
              control.current?.abort();
              lock.current = false;
              setBusy(false);
              setDocument(e.target.value);
              setSource(null);
              setReview(null);
              setChosen([]);
              setChecked([]);
              setSnapshot("");
            }}
          >
            <option value="">请选择，不自动选择披露版本</option>
            {docs.map((d) => (
              <option key={d.document_id} value={d.document_id}>
                {d.source_file} · 报告年 {d.metadata?.report_year}
              </option>
            ))}
          </select>
        </label>
        <button disabled={busy || !document} onClick={() => void loadSource()}>
          读取所选来源
        </button>
      </div>
      {source && (
        <div className="fv-notice">
          <p>
            已选择报告年 {source.report_year} ·
            来源版本已固定；财务时点以各指标列为准。
          </p>
          <details>
            <summary>查看来源版本</summary>
            {source.source_revision}
          </details>
          <button
            disabled={busy || !!pending || blocked}
            onClick={() =>
              void write("collect", "/financial/extended-metrics/collect", {
                company_id: company.company_id,
                document_id: source.document_id,
                expected_source_revision: source.source_revision,
              })
            }
          >
            明确收集资产负债候选
          </button>
        </div>
      )}
      {pending && (
        <div className="fv-notice">
          本次操作待查证，刷新页面后保留原操作号。
          <button disabled={busy} onClick={() => void recover()}>
            只读查询原操作
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      <div className="fv-scroll">
        <table>
          <thead>
            <tr>
              <th>选择</th>
              <th>指标／状态</th>
              <th>报告年／财务时点</th>
              <th>原始值</th>
              <th>原文证据</th>
            </tr>
          </thead>
          <tbody>
            {current.map((m) => (
              <tr key={m.metric_id}>
                <td>
                  <input
                    aria-label={`选择 ${labels[m.metric_key]} ${m.as_of_date}`}
                    type="checkbox"
                    disabled={m.status === "unsupported" || busy}
                    checked={chosen.includes(m.metric_id)}
                    onChange={(e) => {
                      setChosen(
                        e.target.checked
                          ? [...chosen, m.metric_id]
                          : chosen.filter((x) => x !== m.metric_id),
                      );
                      setReview(null);
                      setChecked([]);
                    }}
                  />
                </td>
                <td>
                  {labels[m.metric_key]}
                  <small>{labels[m.status]}</small>
                  <small>
                    合并口径 ·{" "}
                    {m.basis === "PRC_GAAP" ? "中国企业会计准则" : "准则待核对"}
                  </small>
                  {m.status === "confirmed" &&
                    m.confirmation_ref?.receipt_id && (
                      <button
                        disabled={busy || !!pending}
                        onClick={() =>
                          void write(
                            "revoke",
                            `/financial/extended-confirmations/${encodeURIComponent(m.confirmation_ref!.receipt_id)}/revoke`,
                            { reason: "真人通过 v2 面板明确撤销核对" },
                          )
                        }
                      >
                        真人撤销此 v2 核对
                      </button>
                    )}
                  {m.unsupported_reasons.length > 0 && (
                    <details>
                      <summary>限制</summary>
                      {m.unsupported_reasons.join("；")}
                    </details>
                  )}
                </td>
                <td>
                  {m.report_year}
                  <small>{m.as_of_date || "时点未知"}</small>
                </td>
                <td>
                  {m.value_decimal ?? "不可用"}{" "}
                  {m.unit === "PERCENT" ? "%" : "元"}
                </td>
                <td>
                  {m.evidence_refs.map((e, i) => (
                    <a
                      key={i}
                      href={`/evidence?${new URLSearchParams({ company: company.company_id, document: m.document_id, revision: m.source_revision, page: String(e.physical_page) })}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      原 PDF 第 {e.physical_page} 页 ↗
                    </a>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!current.length && (
          <p>尚无当前所选来源的扩展指标；请先选择来源并收集候选。</p>
        )}
      </div>
      <div className="fv-actions">
        <button
          disabled={
            busy ||
            !!pending ||
            !pair ||
            selected.some((m) => m.status !== "candidate")
          }
          onClick={() =>
            void write("review", "/financial/extended-reviews", {
              metric_refs: chosen,
            })
          }
        >
          准备两项核对快照
        </button>
        <button
          disabled={
            busy ||
            !!pending ||
            !pair ||
            selected.some(
              (m) => !confirmed.some((c) => c.metric_id === m.metric_id),
            )
          }
          onClick={() =>
            void write("analyse", "/financial/extended-analyses", {
              metric_refs: chosen,
            })
          }
        >
          请求服务端计算资产负债率
        </button>
      </div>
      {review && (
        <div className="fv-review">
          <h3>真人核对快照 · 尚未接受</h3>
          <p>请逐项打开原 PDF 核对数值、单位、合并口径与财务时点。</p>
          {review.metrics.map((m) => (
            <label key={m.metric_id}>
              <input
                type="checkbox"
                checked={checked.includes(m.metric_id)}
                onChange={(e) =>
                  setChecked(
                    e.target.checked
                      ? [...checked, m.metric_id]
                      : checked.filter((x) => x !== m.metric_id),
                  )
                }
              />
              我已对照原文核对 {labels[m.metric_key]}：{m.value_decimal}{" "}
              元，时点 {m.as_of_date}
            </label>
          ))}
          <button
            disabled={busy || !!pending}
            onClick={async () => {
              const t = begin();
              if (!t) return;
              try {
                await authorize(t.c.signal);
              } catch (e) {
                if (t.n === epoch.current) {
                  setOwner(false);
                  setMetrics([]);
                  setMessage((e as Error).message);
                }
              } finally {
                end(t.n);
              }
            }}
          >
            只读检查真人授权
          </button>
          <button
            disabled={
              busy ||
              !!pending ||
              !owner ||
              !review.acceptable ||
              !reviewCurrent ||
              checked.length !== review.metrics.length
            }
            onClick={() =>
              void write("confirm", "/financial/extended-confirmations", {
                review_id: review.review_id,
                review_sha256: review.review_sha256,
                confirmed: true,
              })
            }
          >
            真人明确接受 v2 核对
          </button>
        </div>
      )}
      <div className="fv-charts">
        <div>
          <h3>已核准原始指标 · 当前所选版本</h3>
          <p>坐标单位：亿元 · 悬停查看原始元值</p>
          {chart.length ? (
            <ResponsiveContainer width="100%" height={230}>
              <LineChart data={chart} margin={{ right: 24 }}>
                <XAxis dataKey="name" interval={0} tick={{ fontSize: 11 }} />
                <YAxis
                  width={52}
                  tickFormatter={(v) => `${Number(v) / 100000000}亿`}
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  formatter={(_, __, item) => [
                    item.payload.value_decimal + " 元",
                    "已核准值",
                  ]}
                />
                <Line
                  dataKey="coordinate"
                  stroke="#4878d4"
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p>暂无当前有效的真人核准指标，图表保持为空。</p>
          )}
        </div>
        <div>
          <h3>已核准值对比</h3>
          <p>坐标单位：亿元 · 财务时点见原始指标表</p>
          {chart.length ? (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={chart}>
                <XAxis dataKey="name" interval={0} tick={{ fontSize: 11 }} />
                <YAxis
                  width={52}
                  tickFormatter={(v) => `${Number(v) / 100000000}亿`}
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  formatter={(_, __, item) => [
                    item.payload.value_decimal + " 元",
                    "已核准值",
                  ]}
                />
                <Bar
                  dataKey="coordinate"
                  fill="#4878d4"
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p>候选和失效来源不进入图表。</p>
          )}
        </div>
      </div>
      {snapshot && <p className="fv-notice">{snapshot}</p>}
    </section>
  );
}
