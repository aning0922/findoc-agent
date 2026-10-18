import { json } from "./api.ts";
import type { Report } from "./api.ts";
export async function reportsFor(
  company: string,
  signal: AbortSignal,
): Promise<Report[]> {
  const docs = await json<
    { document_id: string; source_file: string; status: string }[]
  >("/documents", signal);
  const results = await Promise.allSettled(
    docs.map(async (d) => {
      // Unbound legacy documents have no company metadata; all other failures remain visible.
      const response = await fetch(
        `/api/documents/${encodeURIComponent(d.document_id)}/metadata`,
        { signal, cache: "no-store" },
      );
      if (response.status === 404) return null;
      if (!response.ok)
        throw new Error(`年报绑定读取失败（${response.status}）`);
      const meta = await response.json();
      return { ...meta, ...d } as Report;
    }),
  );
  signal.throwIfAborted();
  for (const r of results) if (r.status === "rejected") throw r.reason;
  return results.flatMap((r) =>
    r.status === "fulfilled" &&
    r.value?.company_id === company &&
    r.value.report_type === "annual"
      ? [r.value]
      : [],
  );
}
