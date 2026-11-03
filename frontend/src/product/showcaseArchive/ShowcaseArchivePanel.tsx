import { useEffect, useRef, useState } from "react";
import "./showcaseArchive.css";

type Kind = "job" | "report";
type Item = { archive_id: string; kind: Kind; revision: number; title: string; saved_at: string; current_source_status: string; data_origin: string; historical_snapshot: boolean; snapshot?: { findings?: Finding[]; snapshot?: { findings?: Finding[] } }; provenance?: unknown };
type Finding = { finding_id: string; kind: string; text: string; source_status?: string; interpretation_review_status?: string; numeric_claim_status?: string; evidence_refs?: { document_id?: string; source_revision?: string; physical_page?: number }[] };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const labels: Record<string,string> = { confirmed_financial: "已保存财务结论", sourced_excerpt: "原文引用", model_interpretation: "AI 待审核解释", unresolved_question: "待解决问题" };
const statuses: Record<string,string> = { current: "当前有效", current_valid: "保存时有效", stale: "已变化", unavailable: "无法复验", not_applicable: "不适用", unresolved: "待解决" };
function valid(item: Item, kind: Kind): boolean { return !!item && uuid.test(item.archive_id) && item.kind === kind && Number.isSafeInteger(item.revision) && (kind === "job" ? item.revision === 0 : item.revision >= 1) && typeof item.title === "string" && typeof item.saved_at === "string" && ["current", "stale", "unavailable"].includes(item.current_source_status) && item.data_origin === "preset_demo" && item.historical_snapshot === true; }
export function ShowcaseArchivePanel({ kind = "report" }: { kind?: Kind }) { return <Archive key={kind} kind={kind} />; }
function Archive({ kind }: { kind: Kind }) {
  const [items, setItems] = useState<Item[]>([]), [detail, setDetail] = useState<Item | null>(null);
  const [listState, setListState] = useState("loading"), [detailState, setDetailState] = useState("");
  const seq = useRef(0), controller = useRef<AbortController | null>(null);
  useEffect(() => {
    let active = true; const abort = new AbortController();
    async function choose(item: Item) {
      const n = ++seq.current; controller.current?.abort(); controller.current = new AbortController();
      setDetail(null); setDetailState("loading");
      const path = kind === "job" ? `jobs/${item.archive_id}` : `reports/${item.archive_id}/revisions/${item.revision}`;
      try {
        const response = await fetch(`/api/showcase-archive/${path}`, { signal: controller.current.signal, cache: "no-store" });
        if (!response.ok) throw Error();
        const value = await response.json() as Item;
        const findings = kind === "job" ? value.snapshot?.findings : value.snapshot?.snapshot?.findings;
        if (!valid(value, kind) || value.archive_id !== item.archive_id || value.revision !== item.revision || !Array.isArray(findings) || !findings.every(f => f && typeof f.finding_id === "string" && Object.hasOwn(labels, f.kind) && typeof f.text === "string")) throw Error();
        if (active && n === seq.current) { setDetail(value); setDetailState("ready"); }
      } catch { if (active && n === seq.current) { setDetail(null); setDetailState("error"); } }
    }
    chooseRef.current = choose;
    async function list() {
      try {
        const response = await fetch(`/api/showcase-archive/items?kind=${kind}`, { signal: abort.signal, cache: "no-store" });
        if (!response.ok) throw Error();
        const data = await response.json();
        if (data.schema_version !== "showcase-archive-list-v1" || data.data_origin !== "preset_demo" || !Array.isArray(data.items) || !data.items.every((x: Item) => valid(x, kind))) throw Error();
        if (!active) return;
        setItems(data.items); setListState("ready");
        if (kind === "job") {
          const params = new URLSearchParams(window.location.search), id = params.get("case");
          if (id && uuid.test(id) && params.getAll("case").length === 1) {
            const item = data.items.find((candidate: Item) => candidate.archive_id === id);
            if (item) void choose(item);
          }
        }
        if (kind === "report") {
          const params = new URLSearchParams(window.location.search), id = params.get("case"), revision = params.get("revision");
          if (id && revision && uuid.test(id) && /^[1-9]\d*$/.test(revision) && params.getAll("case").length === 1 && params.getAll("revision").length === 1) {
            const version = Number(revision);
            if (Number.isSafeInteger(version)) void choose({ archive_id: id, kind, revision: version, title: "", saved_at: "", current_source_status: "unavailable", data_origin: "preset_demo", historical_snapshot: true });
          }
        }
      } catch { if (active) setListState("error"); }
    }
    void list();
    return () => { active = false; ++seq.current; abort.abort(); controller.current?.abort(); chooseRef.current = null; };
  }, [kind]);
  const chooseRef = useRef<((item: Item) => Promise<void>) | null>(null);
  const findings = detail ? (kind === "job" ? detail.snapshot?.findings : detail.snapshot?.snapshot?.findings) || [] : [];
  return <section className="showcase-archive" aria-label={kind === "report" ? "预置报告" : "预置研究"}>
    <h2>{kind === "report" ? "预置报告" : "预置研究"}</h2><p>预置演示案例 · 历史已保存结果，当前查看没有生成新内容。</p>
    {listState === "loading" && <p role="status">正在读取预置案例…</p>}{listState === "error" && <p role="alert">预置案例暂时无法读取。</p>}
    {listState === "ready" && !items.length && <p>暂无预置案例。</p>}
    <div className="showcase-archive__list">{items.map(item => <button type="button" key={`${item.archive_id}-${item.revision}`} onClick={() => void chooseRef.current?.(item)}><strong>{item.title}</strong><span>预置历史 · {statuses[item.current_source_status]}</span></button>)}</div>
    {detailState === "loading" && <p role="status">正在读取历史结果…</p>}{detailState === "error" && <p role="alert">历史结果无法读取，请重新选择。</p>}
    {detail && <article className="showcase-archive__detail"><h3>{detail.title}</h3><p>预置演示案例 · 历史快照</p><p>保存时间：{detail.saved_at} · 当前来源：{statuses[detail.current_source_status]}</p>
      {kind === "report" && <p><a href={`/api/showcase-archive/reports/${detail.archive_id}/revisions/${detail.revision}/print`} target="_blank" rel="noreferrer">打开打印版</a></p>}
      {findings.length === 0 && <p>该历史结果没有可展示的发现。</p>}
      {findings.map((f, index) => <section className="showcase-archive__finding" key={`${f.finding_id}-${index}`}><h4>{labels[f.kind]}</h4><p>{f.text}</p><small>保存时来源状态：{statuses[f.source_status || ""] || "未记录"} · 当前来源状态：{statuses[detail.current_source_status]}{f.kind === "confirmed_financial" ? " · 当前财务资格须另行核验" : ""}{f.kind === "model_interpretation" ? " · AI解释待审核" : ""}{f.numeric_claim_status === "numeric_claim_unverified" ? " · 数字未核准" : ""}</small>
        {(Array.isArray(f.evidence_refs) ? f.evidence_refs : []).map((ref, i) => typeof ref.document_id === "string" && /^[a-f0-9]{64}$/.test(ref.source_revision || "") && Number.isSafeInteger(ref.physical_page) && (ref.physical_page || 0) > 0 ? <p key={i}><a href={`/api/documents/${encodeURIComponent(ref.document_id)}/file?source_revision=${ref.source_revision}#page=${ref.physical_page}`} target="_blank" rel="noreferrer">查看原 PDF · 第 {ref.physical_page} 页</a></p> : null)}
      </section>)}<details><summary>技术溯源</summary><pre>{JSON.stringify(detail.provenance ?? {}, null, 2)}</pre></details></article>}
  </section>;
}
