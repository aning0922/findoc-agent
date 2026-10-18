import type { ReportDetail } from "./reportPersistence.ts";

export async function fetchMarkdown(detail: ReportDetail, simulated: boolean, signal: AbortSignal): Promise<{ blob: Blob; filename: string; eligibility: string }> {
  if (detail.current_eligibility.status !== 'current_at_read') throw new Error('当前版本来源已失效，不可导出');
  const r = detail.report;
  const response = await fetch(`/api/reports/${encodeURIComponent(r.report_id)}/revisions/${r.revision}/markdown`, { signal, cache: "no-store" });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error_code || `导出服务错误（${response.status}）`);
  }
  const eligibility = response.headers.get("X-Report-Eligibility");
  if (response.headers.get("X-Report-Id") !== r.report_id || response.headers.get("X-Report-Revision") !== String(r.revision) || response.headers.get("X-Report-Payload-SHA256") !== detail.payload_sha256 || response.headers.get("X-Markdown-Renderer") !== "trusted-markdown-v1" || !response.headers.get("Content-Type")?.startsWith("text/markdown") || eligibility !== (simulated ? "simulated_test" : "qualified_at_export")) throw new Error("导出版本、内容或资格身份不一致");
  const disposition = response.headers.get("Content-Disposition") || "";
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/)?.[1];
  if (!encodedName) throw new Error("缺少安全下载文件名");
  const filename = decodeURIComponent(encodedName);
  if (!filename.startsWith("FinDoc-") || !filename.endsWith(`-${r.report_id}-v${r.revision}.md`) || /[/\\<>:"|?*]/.test(filename) || [...filename].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127)) throw new Error("下载文件名不安全");
  const bytes = await response.arrayBuffer();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  signal.throwIfAborted();
  if (bytes.byteLength === 0 || digest !== response.headers.get("X-Markdown-SHA256")) throw new Error("下载内容不完整或 SHA 不一致");
  return { blob: new Blob([bytes], { type: "text/markdown;charset=utf-8" }), filename, eligibility };
}
