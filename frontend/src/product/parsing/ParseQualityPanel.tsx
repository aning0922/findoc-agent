import { useEffect, useRef, useState } from "react";
import "./parseQuality.css";
type Identity = {
  document_id: string;
  source_revision: string;
  identity_assessment: string;
  legacy_source_verified: boolean;
};
type Cell = {
  row: number;
  column: number;
  text: string;
  source_line_index: number;
  bbox: number[];
  row_span: null;
  column_span: null;
};
type Table = {
  table_id: string;
  quality: string;
  warning: string;
  coordinate_system: string;
  row_count: number;
  column_count: number;
  cells: Cell[];
};
type Page = {
  physical_page: number;
  method: string;
  status: string;
  text: string;
  warnings: string[];
  lines?: { text: string; bbox: number[] }[];
  tables: Table[];
};
type Quality = {
  schema_version: string;
  artifact_id: string;
  document_id: string;
  source_revision: string;
  source_status: string;
  state: string;
  legacy_source_verified: boolean;
  identity_assessment: { status: string; financial_facts: string };
  pages_total: number;
  pages_processed: number;
  ocr_pages: number;
  pages: Page[];
  limitations: string[];
  error_code: string | null;
};
type Operation = {
  operation_id: string;
  state: string;
  artifact_id: string | null;
};
const idPattern = /^[a-zA-Z0-9-]{1,200}$/,
  revisionPattern = /^[a-f0-9]{64}$/;
const storageKey = (doc: string) => `findoc:parse-operation:${doc}`;
function operationHint(doc: string) {
  const raw = sessionStorage.getItem(storageKey(doc));
  if (!raw) return "";
  const x = JSON.parse(raw);
  if (
    x.documentId !== doc ||
    typeof x.id !== "string" ||
    !/^[a-f0-9-]{36}$/i.test(x.id)
  )
    throw Error("本机操作线索无法读取，请先核对资料。");
  return x.id as string;
}
class HttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`请求未完成（${status}）`);
    this.status = status;
  }
}
async function json<T>(
  path: string,
  signal: AbortSignal,
  body?: object,
): Promise<T> {
  const r = await fetch(`/api/documents/${path}`, {
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
function validQuality(x: Quality, doc: string) {
  return (
    x?.schema_version === "parse-artifact-v2" &&
    x.document_id === doc &&
    idPattern.test(x.artifact_id) &&
    revisionPattern.test(x.source_revision) &&
    ["current", "stale"].includes(x.source_status) &&
    ["completed", "partial", "failed"].includes(x.state) &&
    x.legacy_source_verified === false &&
    x.identity_assessment?.status === "manual_check" &&
    x.identity_assessment?.financial_facts === "not_verified" &&
    Number.isInteger(x.pages_total) &&
    Number.isInteger(x.pages_processed) &&
    Number.isInteger(x.ocr_pages) &&
    x.pages_total >= 0 &&
    x.pages_processed >= 0 &&
    x.ocr_pages >= 0 &&
    x.ocr_pages <= x.pages_processed &&
    Array.isArray(x.limitations) &&
    Array.isArray(x.pages) &&
    x.pages_processed === x.pages.length &&
    x.pages_processed <= x.pages_total &&
    (x.state !== "completed" || x.pages_processed === x.pages_total) &&
    x.pages.every(
      (p) =>
        Number.isInteger(p.physical_page) &&
        p.physical_page > 0 &&
        p.physical_page <= x.pages_total &&
        typeof p.text === "string" &&
        Array.isArray(p.warnings) &&
        Array.isArray(p.tables) &&
        p.tables.every(
          (t) =>
            t.quality === "needs_review" &&
            t.coordinate_system === "normalized_top_left" &&
            Number.isInteger(t.row_count) &&
            t.row_count >= 0 &&
            t.row_count <= 500 &&
            Number.isInteger(t.column_count) &&
            t.column_count >= 0 &&
            t.column_count <= 100 &&
            Array.isArray(t.cells) &&
            t.cells.every(
              (c) =>
                Number.isInteger(c.row) &&
                c.row >= 0 &&
                c.row < t.row_count &&
                Number.isInteger(c.column) &&
                c.column >= 0 &&
                c.column < t.column_count &&
                typeof c.text === "string" &&
                Number.isInteger(c.source_line_index) &&
                c.row_span === null &&
                c.column_span === null &&
                Array.isArray(c.bbox) &&
                c.bbox.length === 4 &&
                c.bbox.every(
                  (v) => typeof v === "number" && v >= 0 && v <= 1,
                ) &&
                !!p.lines?.[c.source_line_index] &&
                p.lines[c.source_line_index].text === c.text &&
                JSON.stringify(p.lines[c.source_line_index].bbox) ===
                  JSON.stringify(c.bbox),
            ),
        ),
    )
  );
}
export function ParseQualityPanel({
  documentId,
  sourceFile,
}: {
  documentId: string;
  sourceFile?: string;
}) {
  const [open, setOpen] = useState(false),
    [identity, setIdentity] = useState<Identity | null>(null),
    [quality, setQuality] = useState<Quality | null>(null),
    [op, setOp] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [storageBlocked, setStorageBlocked] = useState(false),
    [history, setHistory] = useState("");
  const epoch = useRef(0),
    ctrl = useRef<AbortController | null>(null),
    lock = useRef(false);
  useEffect(() => {
    epoch.current++;
    ctrl.current?.abort();
    lock.current = false;
    setOpen(false);
    setIdentity(null);
    setQuality(null);
    setHistory("");
    setBusy(false);
    try {
      const x = operationHint(documentId);
      setOp(x);
      setStorageBlocked(false);
      setMessage(x ? "存在上次解析操作，请只读查询原操作。" : "");
    } catch {
      setOp("");
      setMessage("本机操作线索不可读取，暂不能开始解析。");
      setStorageBlocked(true);
    }
    return () => {
      epoch.current++;
      ctrl.current?.abort();
    };
  }, [documentId]);
  const base = encodeURIComponent(documentId);
  const begin = () => {
    if (lock.current || !idPattern.test(documentId)) return null;
    lock.current = true;
    setBusy(true);
    const n = epoch.current,
      c = new AbortController();
    ctrl.current = c;
    return { n, c };
  };
  const end = (n: number) => {
    if (n === epoch.current) {
      lock.current = false;
      setBusy(false);
      ctrl.current = null;
    }
  };
  async function readQuality(
    c: AbortController,
    n: number,
    artifact = "",
    expectedState = "",
  ) {
    const q = artifact
      ? `?${new URLSearchParams({ artifact_id: artifact })}`
      : "";
    const x = await json<Quality>(`${base}/parse-quality${q}`, c.signal);
    if (
      !validQuality(x, documentId) ||
      (artifact && x.artifact_id !== artifact) ||
      (expectedState && x.state !== expectedState)
    )
      throw Error("解析结果身份或结构无法核验。");
    if (n === epoch.current) setQuality(x);
  }
  async function preview() {
    const task = begin();
    if (!task) return;
    const { n, c } = task;
    setOpen(true);
    setQuality(null);
    setMessage("正在读取资料身份与解析结果…");
    try {
      const x = await json<Identity>(`${base}/parse-identity`, c.signal);
      if (
        x.document_id !== documentId ||
        !revisionPattern.test(x.source_revision) ||
        x.identity_assessment !== "manual_check" ||
        x.legacy_source_verified !== false
      )
        throw Error("资料身份无法核验。");
      if (n !== epoch.current) return;
      setIdentity(x);
      try {
        await readQuality(c, n);
        if (n === epoch.current) setMessage("已读取当前完整解析产物。");
      } catch (e) {
        if (e instanceof HttpError && e.status === 404) {
          if (n === epoch.current)
            setMessage("尚无可读取的当前完整产物，可明确开始新解析。");
        } else throw e;
      }
    } catch (e) {
      if (n === epoch.current && !c.signal.aborted)
        setMessage((e as Error).message);
    } finally {
      end(n);
    }
  }
  async function start() {
    if (
      storageBlocked ||
      !identity ||
      identity.document_id !== documentId ||
      op ||
      !open
    )
      return;
    const task = begin();
    if (!task) return;
    const { n, c } = task,
      id = crypto.randomUUID();
    let submitted = false;
    try {
      sessionStorage.setItem(
        storageKey(documentId),
        JSON.stringify({ documentId, id }),
      );
      setOp(id);
      setMessage("正在解析；离开页面后可使用原操作只读查证。");
      submitted = true;
      const x = await json<Operation>(`${base}/parse-retry`, c.signal, {
        operation_id: id,
        expected_source_revision: identity.source_revision,
      });
      if (n === epoch.current) await handle(x, id, c, n);
    } catch {
      if (n === epoch.current && !c.signal.aborted)
        setMessage(
          submitted
            ? "解析结果未知，请只读查询原操作，勿重复提交。"
            : "无法保存操作身份，未提交解析。",
        );
    } finally {
      end(n);
    }
  }
  async function handle(
    x: Operation,
    id: string,
    c: AbortController,
    n: number,
  ) {
    if (
      x?.operation_id !== id ||
      !["unknown", "completed", "partial", "failed"].includes(x.state)
    )
      throw Error("操作身份或状态无法核验。");
    if (x.state === "unknown") {
      setMessage("解析结果未知，请只读查询原操作。");
      return;
    }
    if (x.artifact_id) {
      if (!idPattern.test(x.artifact_id)) throw Error("产物身份无效。");
      await readQuality(c, n, x.artifact_id, x.state);
    } else if (x.state !== "failed") throw Error("操作缺少产物身份。");
    if (n !== epoch.current) return;
    sessionStorage.removeItem(storageKey(documentId));
    setOp("");
    setMessage(
      x.state === "completed"
        ? "解析完成；转录和版面仍需人工核对。"
        : x.state === "partial"
          ? "解析部分完成，未处理页面不会显示为成功。"
          : "解析失败，请查看限制与处理状态。",
    );
  }
  async function check() {
    if (!op) return;
    const task = begin();
    if (!task) return;
    const { n, c } = task;
    try {
      const x = await json<Operation>(
        `${base}/parse-operations/${encodeURIComponent(op)}`,
        c.signal,
      );
      if (n === epoch.current) await handle(x, op, c, n);
    } catch (e) {
      if (n === epoch.current && !c.signal.aborted)
        setMessage((e as Error).message || "只读查询未完成。");
    } finally {
      end(n);
    }
  }
  async function readHistory() {
    if (!idPattern.test(history)) {
      setMessage("请输入有效的历史产物标识。");
      return;
    }
    const task = begin();
    if (!task) return;
    setQuality(null);
    try {
      await readQuality(task.c, task.n, history);
      if (task.n === epoch.current) setMessage("已读取指定历史产物。");
    } catch (e) {
      if (task.n === epoch.current && !task.c.signal.aborted)
        setMessage((e as Error).message);
    } finally {
      end(task.n);
    }
  }
  return (
    <section className="parse-quality" aria-label="解析质量">
      <div className="parse-head">
        <div>
          <span>文档解析</span>
          <h2>查看解析质量</h2>
          <p>
            {sourceFile || "当前资料"} · OCR
            转录和版面均为候选，需要对照原页人工核对。
          </p>
        </div>
        <button onClick={() => void preview()} disabled={busy}>
          打开预览
        </button>
      </div>
      {op && (
        <div className="parse-notice">
          解析操作待查证。{" "}
          <button onClick={() => void check()} disabled={busy}>
            只读查询原操作
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {open && (
        <>
          <div className="parse-controls">
            <button
              disabled={busy || storageBlocked || !identity || !!op}
              onClick={() => void start()}
            >
              明确开始新解析
            </button>
            <label>
              历史产物 ID{" "}
              <input
                value={history}
                onChange={(e) => setHistory(e.target.value)}
                placeholder="输入产物标识"
              />
            </label>
            <button
              disabled={busy || !history}
              onClick={() => void readHistory()}
            >
              只读查看历史
            </button>
          </div>
          <p>封面身份：待人工核对 · 旧来源未验证 · 财务数据未核准</p>
        </>
      )}
      {quality?.document_id === documentId && (
        <>
          <div className="parse-tags">
            <b>
              {quality.source_status === "stale"
                ? "历史产物 · 来源已变化"
                : "当前来源身份匹配"}
            </b>
            <b>候选转录未核对</b>
            <b>财务未核准</b>
          </div>
          <p>
            状态：
            {
              { completed: "完成", partial: "部分完成", failed: "失败" }[
                quality.state
              ]
            }{" "}
            · 已处理 {quality.pages_processed}/{quality.pages_total} 页 · OCR{" "}
            {quality.ocr_pages} 页
          </p>
          {quality.error_code && <p>处理未完成，请核对限制。</p>}
          {quality.limitations.map((x, i) => (
            <p key={i}>{x}</p>
          ))}
          {quality.source_status === "current" && (
            <a
              href={`/api/documents/${base}/parse-artifacts/${encodeURIComponent(quality.artifact_id)}/file`}
              target="_blank"
              rel="noreferrer"
            >
              打开受控 PDF ↗
            </a>
          )}
          {quality.pages.map((page) => (
            <article key={page.physical_page}>
              <div className="parse-page-head">
                <h3>物理页 {page.physical_page}</h3>
                <span>
                  {page.method === "ocr" ? "OCR 候选" : "文本层候选"} ·{" "}
                  {page.status === "completed" ? "已处理" : "未完成"}
                </span>
              </div>
              <div className="parse-page-grid">
                <div className="parse-image">
                  {quality.source_status === "current" ? (
                    <img
                      src={`/api/documents/${base}/parse-artifacts/${encodeURIComponent(quality.artifact_id)}/pages/${page.physical_page}/image`}
                      alt={`原 PDF 物理页 ${page.physical_page}`}
                      loading="lazy"
                    />
                  ) : (
                    <p>来源已变化，历史产物不借用当前原图。</p>
                  )}
                  {quality.source_status === "current" && <a
                    href={`/api/documents/${base}/parse-artifacts/${encodeURIComponent(quality.artifact_id)}/pages/${page.physical_page}/image`}
                    target="_blank" rel="noreferrer">查看原页大图 ↗</a>}
                </div>
                <div>
                  <h4>候选转录 · 未核对</h4>
                  <pre>{page.text || "无可展示转录"}</pre>
                  {page.warnings.length > 0 && (
                    <details>
                      <summary>查看本页限制</summary>
                      {page.warnings.map((w, i) => (
                        <p key={i}>{w}</p>
                      ))}
                    </details>
                  )}
                </div>
              </div>
              {page.tables.map((table, ti) => (
                <div
                  key={`${quality.artifact_id}-${page.physical_page}-${table.table_id}-${ti}`}
                >
                  <h4>版面候选 · 需人工核对</h4>
                  <p>{table.warning} 跨度未知；行列仅为候选布局。</p>
                  <p>候选布局 {table.row_count} 行 / {table.column_count} 列 · 左右滚动查看全部列</p>
                  <div className="parse-scroll" role="region" aria-label="可横向滚动的候选表格" tabIndex={0}>
                    <table>
                      <tbody>
                        {Array.from({ length: table.row_count }, (_, row) => (
                          <tr key={row}>
                            {Array.from(
                              { length: table.column_count },
                              (_, column) => (
                                <td key={column}>
                                  {table.cells
                                    .filter(
                                      (c) =>
                                        c.row === row && c.column === column,
                                    )
                                    .map((cell, i) => (
                                      <span
                                        key={`${cell.source_line_index}-${i}`}
                                        title={`原行 ${cell.source_line_index} · 坐标 ${cell.bbox.join(", ")}`}
                                      >
                                        {cell.text}
                                      </span>
                                    ))}
                                </td>
                              ),
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
