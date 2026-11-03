import { useEffect, useRef, useState } from "react";
import type { Company } from "../api.ts";
import "./disclosure.css";

type Candidate = {
  candidate_id: string;
  company_code: string;
  company_name: string;
  title: string;
  report_year: number;
  kind: string;
  publish_date: string | null;
  is_amendment: boolean | null;
  official_url: string;
  provider: string;
  downloadable: boolean;
};
type Search = {
  schema_version: string;
  source_scope: string;
  items: Candidate[];
  limitations: string[];
  fallback: string;
};
type Operation = {
  schema_version: string;
  operation_id: string;
  state: string;
  phase: string;
  error_code: string | null;
  result: unknown;
};
type Pending = {
  company: string;
  id: string;
  candidateId?: string;
  reportYear?: number;
};
const key = (company: string) => `findoc:disclosure-import:${company}`;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function saved(company: string) {
  const raw = sessionStorage.getItem(key(company));
  if (!raw) return null;
  const x = JSON.parse(raw);
  if (x?.company !== company || typeof x.id !== "string" || !uuid.test(x.id))
    throw new Error("invalid recovery hint");
  const hasCandidate =
    typeof x.candidateId === "string" &&
    x.candidateId.length > 0 &&
    x.candidateId.length <= 200 &&
    Number.isInteger(x.reportYear) &&
    x.reportYear >= 1 &&
    x.reportYear <= 9999;
  if (
    !hasCandidate &&
    (x.candidateId !== undefined || x.reportYear !== undefined)
  )
    throw new Error("invalid recovery hint");
  return x as Pending;
}
function url(value: string) {
  try {
    const u = new URL(value);
    return u.protocol === "https:" &&
      !u.username &&
      !u.password &&
      (!u.port || u.port === "443") &&
      [
        "www.midea.com.cn",
        "static.cninfo.com.cn",
        "disc.static.szse.cn",
      ].includes(u.hostname)
      ? u.href
      : undefined;
  } catch {
    return undefined;
  }
}
function validOperation(x: Operation, id: string) {
  return (
    x?.schema_version === "disclosure-import-v1" &&
    x.operation_id === id &&
    ["unknown", "completed", "failed"].includes(x.state) &&
    typeof x.phase === "string"
  );
}
export function DisclosurePanel({
  company,
  companies,
  onImported,
}: {
  company: string;
  companies: Company[];
  onImported?: () => void;
}) {
  const selected = companies.find((c) => c.company_id === company);
  const [code, setCode] = useState("");
  const [year, setYear] = useState("");
  const [items, setItems] = useState<Candidate[]>([]);
  const [limitations, setLimitations] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [op, setOp] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [searched, setSearched] = useState(false);
  const epoch = useRef(0),
    controller = useRef<AbortController | null>(null),
    lock = useRef(false);
  useEffect(() => {
    epoch.current++;
    controller.current?.abort();
    controller.current = null;
    lock.current = false;
    setCode(selected?.security_code || selected?.name || "");
    setYear("");
    setItems([]);
    setLimitations([]);
    setSearched(false);
    try {
      const pending = saved(company);
      setStorageBlocked(false);
      setOp(pending);
      setMessage(pending ? "发现上次导入待查证，请只读查询原操作。" : "");
    } catch {
      setStorageBlocked(true);
      setOp(null);
      setMessage("本机导入线索无法读取，请先核对资料目录；暂不提交新导入。");
    }
    setBusy(false);
    return () => {
      epoch.current++;
      controller.current?.abort();
    };
  }, [company, selected?.security_code, selected?.name]);
  async function search() {
    if (lock.current) return;
    if (year && !/^\d{4}$/.test(year)) {
      setMessage("请填写四位报告年度。");
      return;
    }
    lock.current = true;
    setBusy(true);
    const n = epoch.current,
      c = new AbortController();
    controller.current = c;
    setMessage("正在查询已验证演示目录…");
    try {
      const q = new URLSearchParams({ code, report_year: year });
      const r = await fetch(`/api/disclosures/search?${q}`, {
        signal: c.signal,
      });
      const x = (await r.json()) as Search;
      if (
        !r.ok ||
        x.schema_version !== "disclosure-search-v1" ||
        x.source_scope !== "verified_demo_catalog" ||
        !Array.isArray(x.items) ||
        !Array.isArray(x.limitations) ||
        !x.items.every(
          (v) =>
            typeof v.candidate_id === "string" &&
            typeof v.title === "string" &&
            typeof v.company_code === "string" &&
            typeof v.company_name === "string" &&
            Number.isInteger(v.report_year) &&
            typeof v.official_url === "string" &&
            typeof v.provider === "string" &&
            v.kind === "annual_full" &&
            (v.publish_date === null || typeof v.publish_date === "string") &&
            (v.is_amendment === null || typeof v.is_amendment === "boolean") &&
            typeof v.downloadable === "boolean",
        )
      )
        throw Error("目录暂不可用，请使用手动上传。");
      if (n !== epoch.current) return;
      setItems(x.items);
      setLimitations(x.limitations);
      setSearched(true);
      setMessage(
        x.items.length
          ? "请选择候选并核对企业后导入。"
          : "没有匹配的目录资料，请使用下方手动上传。",
      );
    } catch (e) {
      if (n === epoch.current && !c.signal.aborted) {
        setItems([]);
        setMessage((e as Error).message || "目录查询失败，请使用手动上传。");
      }
    } finally {
      if (n === epoch.current) {
        lock.current = false;
        setBusy(false);
        controller.current = null;
      }
    }
  }
  function apply(x: Operation, pending: Pending, httpOK: boolean) {
    if (!validOperation(x, pending.id))
      throw Error("操作结果无法核验，请只读查询原操作。");
    if (x.state === "completed") {
      if (
        !httpOK ||
        !pending.candidateId ||
        !pending.reportYear ||
        !x.result ||
        typeof x.result !== "object"
      )
        throw Error("完成结果缺少可核验的操作线索，请只读查询并核对资料目录。");
      const result = x.result as {
        document_id?: unknown;
        metadata?: { company_id?: unknown; report_year?: unknown };
        disclosure_import?: { candidate_id?: unknown };
      };
      if (
        typeof result.document_id !== "string" ||
        !/^[0-9a-f]{64}$/.test(result.document_id) ||
        result.metadata?.company_id !== pending.company ||
        result.metadata?.report_year !== pending.reportYear ||
        result.disclosure_import?.candidate_id !== pending.candidateId
      )
        throw Error("完成结果与原操作不匹配，请只读查询并核对资料目录。");
      sessionStorage.removeItem(key(pending.company));
      setOp(null);
      setMessage(
        "已完成上传与企业绑定。解析状态请在资料目录另行查看；这不代表财务数据已确认。",
      );
      try {
        onImported?.();
      } catch {
        /* Existing directory remains available. */
      }
    } else if (x.state === "failed") {
      sessionStorage.removeItem(key(pending.company));
      setOp(null);
      setMessage("导入失败，请查看资料目录并使用手动上传或重新选择。");
    } else {
      setOp(pending);
      setMessage(
        "导入结果未知，服务端可能仍在处理；请只读查询原操作，不要重复导入。",
      );
    }
  }
  async function submit(candidate: Candidate) {
    if (
      lock.current ||
      op ||
      !selected ||
      candidate.company_code !== selected.security_code
    )
      return;
    const id = crypto.randomUUID();
    const pending: Pending = {
      company,
      id,
      candidateId: candidate.candidate_id,
      reportYear: candidate.report_year,
    };
    try {
      sessionStorage.setItem(key(company), JSON.stringify(pending));
    } catch {
      setMessage("无法保存操作身份，未提交导入。");
      return;
    }
    setOp(pending);
    lock.current = true;
    setBusy(true);
    const n = epoch.current,
      c = new AbortController();
    controller.current = c;
    setMessage("正在从官方来源导入；可继续使用其他页面。");
    try {
      const r = await fetch("/api/disclosures/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          operation_id: id,
          candidate_id: candidate.candidate_id,
          company_id: company,
        }),
        signal: c.signal,
      });
      const x = (await r.json()) as Operation;
      if (n !== epoch.current) return;
      if (!r.ok && x?.state === "completed")
        throw Error("非成功响应不能确认导入完成。");
      if (!r.ok && !validOperation(x, id)) {
        const detail = (
          x as unknown as { detail?: { code?: string; message?: string } }
        ).detail;
        const code = detail?.code || "";
        const safe =
          (r.status === 422 &&
            ["invalid_request", "invalid_operation_id"].includes(code)) ||
          (r.status === 404 && code === "candidate_not_found") ||
          (r.status === 409 && code === "candidate_company_mismatch");
        if (safe) {
          sessionStorage.removeItem(key(company));
          setOp(null);
          setMessage("服务端拒绝导入，请核对企业和年报。");
          return;
        }
        if (r.status >= 400 && r.status < 500) {
          setMessage("服务端拒绝请求；原操作是否执行尚需核对，请只读查询。");
          return;
        }
        throw Error("导入结果未知，请只读查询。");
      }
      apply(x, pending, r.ok);
    } catch {
      if (n === epoch.current && !c.signal.aborted)
        setMessage("导入结果未知，服务端可能仍在处理；请只读查询原操作。");
    } finally {
      if (n === epoch.current) {
        lock.current = false;
        setBusy(false);
        controller.current = null;
      }
    }
  }
  async function check() {
    if (lock.current || !op) return;
    lock.current = true;
    setBusy(true);
    const pending = op,
      id = pending.id,
      n = epoch.current,
      c = new AbortController();
    controller.current = c;
    try {
      const r = await fetch(
        `/api/disclosures/imports/${encodeURIComponent(id)}`,
        { signal: c.signal },
      );
      if (!r.ok) throw Error("暂未查到该操作，请稍后只读查询并核对资料目录。");
      const x = (await r.json()) as Operation;
      if (n === epoch.current) apply(x, pending, r.ok);
    } catch (e) {
      if (n === epoch.current && !c.signal.aborted)
        setMessage((e as Error).message || "只读查询未完成，请稍后重试。");
    } finally {
      if (n === epoch.current) {
        lock.current = false;
        setBusy(false);
        controller.current = null;
      }
    }
  }
  return (
    <section className="disclosure-panel" aria-label="查找官方年报">
      <div className="disclosure-heading">
        <div>
          <span>官方资料目录</span>
          <h2>查找企业年报</h2>
          <p>已验证演示目录 · 美的／格力 2024／2025；不代表全市场实时发现。</p>
        </div>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <label>
          企业名称或证券代码
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="例如 000333"
            required
            maxLength={200}
          />
        </label>
        <label>
          报告年度（可选）
          <input
            value={year}
            onChange={(e) => setYear(e.target.value)}
            inputMode="numeric"
            maxLength={4}
            placeholder="例如 2025"
          />
        </label>
        <button disabled={busy}>查询目录</button>
      </form>
      <p className="disclosure-context">
        当前绑定企业：{selected?.name || "请先选择企业"}
        {selected?.security_code ? ` · ${selected.security_code}` : ""}
      </p>
      {message && (
        <p role={op ? "alert" : "status"} className="disclosure-message">
          {message}
        </p>
      )}
      {op && (
        <div className="disclosure-pending">
          <span>待查证操作已保留，刷新页面后可继续查询。</span>
          <button disabled={busy} onClick={() => void check()}>
            只读查询原操作
          </button>
        </div>
      )}
      {limitations.length > 0 && (
        <details>
          <summary>目录来源与限制</summary>
          {limitations.map((x) => (
            <p key={x}>{x}</p>
          ))}
        </details>
      )}
      {searched &&
        items.map((item) => (
          <article key={item.candidate_id}>
            <div>
              <h3>{item.title}</h3>
              <p>
                {item.company_name} · {item.company_code} · {item.report_year}{" "}
                年报正文
              </p>
              <p>
                发布日期：{item.publish_date || "未知"} · 更正状态：
                {item.is_amendment === null
                  ? "未知"
                  : item.is_amendment
                    ? "更正"
                    : "非更正"}
              </p>
              <p>
                目录来源：{item.provider || "未知"} ·{" "}
                {url(item.official_url) ? (
                  <a
                    href={url(item.official_url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    查看官方来源 ↗
                  </a>
                ) : (
                  <span>来源地址不可用</span>
                )}
              </p>
            </div>
            <button
              disabled={
                busy ||
                !!op ||
                storageBlocked ||
                !selected ||
                !item.downloadable ||
                item.company_code !== selected.security_code
              }
              onClick={() => void submit(item)}
            >
              明确导入此年报
            </button>
          </article>
        ))}
      <p className="disclosure-fallback">
        目录未覆盖、不可用或企业信息不匹配时，可使用下方的手动上传表单。
      </p>
    </section>
  );
}
