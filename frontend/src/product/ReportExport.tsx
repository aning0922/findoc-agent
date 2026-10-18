import { useEffect, useRef, useState } from "react";
import type { ReportDetail } from "./reportPersistence.ts";
import { fetchMarkdown } from "./reportExport.ts";

export function ReportExport({ detail, simulated, compact = false, sourceBlocked = false }: { detail: ReportDetail; simulated: boolean; compact?: boolean; sourceBlocked?: boolean }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [status, setStatus] = useState("");
  const lock = useRef(false), controller = useRef<AbortController | null>(null);
  useEffect(() => () => { controller.current?.abort(); }, []);
  async function download() {
    if (lock.current || sourceBlocked || detail.current_eligibility.status !== "current_at_read") return;
    lock.current = true; setBusy(true); setError(""); setStatus("");
    const c = new AbortController(); controller.current = c;
    let url: string | undefined;
    try {
      const result = await fetchMarkdown(detail, simulated, c.signal);
      c.signal.throwIfAborted();
      url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = result.filename;
      document.body.appendChild(anchor);
      try { anchor.click(); } finally { anchor.remove(); }
      setStatus(`v${detail.report.revision} 导出核验通过${simulated ? "（simulated_test，仅供测试）" : ""}，已交给浏览器下载。文件保存状态请查看浏览器下载记录。`);
    } catch (e) {
      if (!c.signal.aborted) setError(`v${detail.report.revision} 导出或下载失败：${e instanceof Error ? e.message : "网络或下载错误"}。可重新点击导出以再次核验。`);
    } finally {
      if (url) { const release = url; window.setTimeout(() => URL.revokeObjectURL(release), 60000); }
      lock.current = false; if (!c.signal.aborted) setBusy(false);
    }
  }
  return <section className={compact ? "report-export-compact" : "surface report-controls"} aria-label="报告 Markdown 导出">
    {!compact && <p>正在阅读与下载已保存 v{detail.report.revision}。点击下载会重新核验冻结研究、事实与来源。</p>}
    {detail.current_eligibility.status === 'invalidated' && <p>来源已失效，仅供历史审计。此版本暂不可导出。</p>}
    <button disabled={busy || sourceBlocked || detail.current_eligibility.status !== "current_at_read"} onClick={() => void download()}>{busy ? `正在核验并导出 v${detail.report.revision}…` : `下载 v${detail.report.revision} · Markdown`}</button>
    {error && <p role="alert" className="operating-alert">{error}</p>}
    {status && <p role="status">{status}</p>}
  </section>;
}
