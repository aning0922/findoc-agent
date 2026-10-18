import { useEffect, useRef, useState } from "react";
import {
  createRequestSnapshot,
  isCurrentRequest,
} from "../requestOwnership.ts";
import type { RequestSnapshot } from "../requestOwnership.ts";
import { checkSource, forgetPdf, loadEvidence } from "./api.ts";
import type { Citation, Evidence, Selection, Source } from "./contracts.ts";
import { METRICS } from "./contracts.ts";
import { PdfPage } from "./PdfPage.tsx";
export function EvidenceViewer({
  source,
  bytes,
  items,
  selection,
  citation,
  onNavigate,
  onClose,
  onFatal,
  contextLabel = "指标候选待人工核对。",
  drawerAt = 1024,
  panelMode,
  active = true,
}: {
  drawerAt?: number;
  panelMode?: boolean;
  active?: boolean;
  source: Source;
  bytes: Uint8Array;
  items: Citation[];
  selection: Selection;
  citation: string;
  contextLabel?: string;
  onNavigate: (
    update: Partial<Selection> & { cite?: string },
    replace?: boolean,
  ) => void;
  onClose: () => void;
  onFatal: (message: string, cause?: unknown) => void;
}) {
  const selected = items.find((item) => item.key === citation);
  const id =
    selection.evidence ||
    selected?.reference.evidence_id ||
    items[0]?.reference.evidence_id ||
    "";
  const activeItem = selected ?? (selection.evidence ? undefined : items[0]);
  const activeRef = activeItem?.reference ?? null;
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(true);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [locationToken, setLocationToken] = useState(0);
  const [draft, setDraft] = useState(selection.page || "1");
  const [pageError, setPageError] = useState("");
  const [viewportNarrow, setNarrow] = useState(
    window.matchMedia(`(max-width: ${drawerAt}px)`).matches,
  );
  const narrow = panelMode ?? viewportNarrow;
  const request = useRef<RequestSnapshot | null>(null);
  const next = useRef(0);
  const ref = useRef<HTMLElement>(null);
  const fatal = useRef(onFatal);
  useEffect(() => {
    fatal.current = onFatal;
  }, [onFatal]);
  const close = useRef(onClose);
  close.current = onClose;
  const navigate = useRef(onNavigate);
  navigate.current = onNavigate;
  const sourcePage = Number(
    selection.page || activeRef?.physical_page || evidence?.physical_page || 1,
  );
  const page =
    Number.isSafeInteger(sourcePage) &&
    sourcePage >= 1 &&
    sourcePage <= source.physical_pages
      ? sourcePage
      : 1;
  const visibleEvidence = evidence?.evidence_id === id ? evidence : null;
  useEffect(() => {
    setDraft(String(page));
    setPageError(sourcePage === page ? "" : "物理页码无效，已定位第 1 页。");
  }, [page, sourcePage]);
  useEffect(() => {
    const media = window.matchMedia(`(max-width: ${drawerAt}px)`);
    const change = () => setNarrow(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, [drawerAt]);
  useEffect(() => {
    if (!narrow || !active) return;
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = [
        ...(ref.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), select, input, summary, [tabindex="0"]',
        ) ?? []),
      ].filter((element) => element.getClientRects().length > 0);
      if (event.shiftKey && document.activeElement === controls[0]) {
        event.preventDefault();
        controls.at(-1)?.focus();
      } else if (
        !event.shiftKey &&
        document.activeElement === controls.at(-1)
      ) {
        event.preventDefault();
        controls[0]?.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      document.body.style.overflow = previousOverflow;
      previous?.focus();
    };
  }, [narrow, active]);
  useEffect(() => {
    const controller = new AbortController();
    const snapshot = createRequestSnapshot(
      ++next.current,
      source.document_id,
      id || "page-only",
    );
    request.current = snapshot;
    setEvidence(null);
    setEvidenceLoading(Boolean(id));
    if (id)
      void loadEvidence(source, id, activeRef?.physical_page, controller.signal)
        .then((e) => {
          if (!isCurrentRequest(request.current, snapshot)) return;
          setEvidence(e);
          setEvidenceLoading(false);
          if (!selection.page)
            navigate.current(
              {
                page: String(e.physical_page),
                evidence: e.evidence_id,
                revision: source.source_revision,
                cite: activeItem?.key,
              },
              true,
            );
        })
        .catch((error) => {
          if (
            isCurrentRequest(request.current, snapshot) &&
            !controller.signal.aborted
          ) {
            forgetPdf(source);
            fatal.current(error.message, error);
          }
        });
    return () => {
      request.current = null;
      controller.abort();
    };
    // Navigation in the PDF must not refetch an unchanged citation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, id, activeRef, activeItem?.key]);
  function go(target: number) {
    if (
      !Number.isSafeInteger(target) ||
      target < 1 ||
      target > source.physical_pages
    ) {
      setPageError(`请输入 1–${source.physical_pages} 的物理页码。`);
      return;
    }
    onNavigate({ page: String(target), revision: source.source_revision });
  }
  return (
    <>
      {narrow && active && <div className="evidence-backdrop" onClick={onClose} />}
      <aside
        hidden={!active}
        ref={ref}
        className={`evidence-viewer ${narrow ? "drawer" : ""}`}
        role={narrow ? "dialog" : "complementary"}
        aria-modal={narrow || undefined}
        aria-label="PDF 原文证据"
      >
        <header className="evidence-header">
          <div>
            <strong>{activeItem ? METRICS[activeItem.candidate.metric_key] : '原文证据'}</strong>
            <small>{activeItem ? `财务 ${activeItem.candidate.period} 年 · 披露于 ${source.report_year} 年报` : '真实 PDF · 物理页定位'}</small>
          </div>
          <button aria-label="返回核对" onClick={onClose}>
            返回核对
          </button>
        </header>
        <label className="reference-select">
          切换引用
          <select
            aria-label="切换引用"
            value={activeItem?.key || ""}
            onChange={(event) => {
              const item = items.find((i) => i.key === event.target.value)!;
              onNavigate({
                evidence: item.reference.evidence_id,
                page: String(item.reference.physical_page),
                revision: source.source_revision,
                cite: item.key,
              });
            }}
          >
            <option value="" disabled>
              选择引用
            </option>
            {items.map((item) => (
              <option key={item.key} value={item.key}>
                {METRICS[item.candidate.metric_key]} ·{" "}
                {item.reference.role === "summary"
                  ? "摘要"
                  : item.reference.role === "basis"
                    ? "口径"
                    : "报表"}{" "}
                · 物理第 {item.reference.physical_page} 页 ·{" "}
                {item.reference.raw_value}
              </option>
            ))}
          </select>
        </label>
        <div className="pdf-toolbar">
          <button
            aria-label="上一页"
            disabled={page <= 1}
            onClick={() => go(page - 1)}
          >
            上一页
          </button>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              go(/^\d+$/.test(draft) ? Number(draft) : NaN);
            }}
          >
            <label>
              物理页
              <input
                aria-label="物理页码"
                inputMode="numeric"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </label>
            <button>跳转</button>
          </form>
          <button
            aria-label="下一页"
            disabled={page >= source.physical_pages}
            onClick={() => go(page + 1)}
          >
            下一页
          </button>
          <label>
            缩放
            <select
              aria-label="缩放"
              value={zoom}
              onChange={(event) =>
                setZoom(
                  event.target.value === "fit"
                    ? "fit"
                    : Number(event.target.value),
                )
              }
            >
              <option value="fit">适宽</option>
              {[0.5, 0.75, 1, 1.25, 1.5, 2].map((z) => (
                <option key={z} value={z}>
                  {Math.round(z * 100)}%
                </option>
              ))}
            </select>
          </label>
          <button
            disabled={!visibleEvidence}
            onClick={() => {
              setLocationToken((n) => n + 1);
              setZoom("fit");
              go(visibleEvidence!.physical_page);
            }}
          >
            返回引用位置
          </button>
        </div>
        {pageError && (
          <p role="alert" className="evidence-error">
            {pageError}
          </p>
        )}
        <PdfPage
          bytes={bytes}
          source={source}
          page={page}
          zoom={zoom}
          evidence={visibleEvidence}
          reference={activeRef}
          locationToken={locationToken}
          onFatal={onFatal}
          onPage={go}
          onZoom={setZoom}
        />
        <details className="evidence-excerpt" open>
          <summary>
            原文片段 ·{" "}
            {visibleEvidence
              ? `物理第 ${visibleEvidence.physical_page} 页`
              : "读取中"}
          </summary>
          {evidenceLoading ? (
            <p role="status">正在核验引用来源…</p>
          ) : (
            <pre>
              {visibleEvidence?.text || "此文档暂无指标引用，可自行阅读 PDF。"}
            </pre>
          )}
        </details>
        <footer className="evidence-footer">
          PDF 印刷页码可能与物理页不同。{contextLabel}
          <details>
            <summary>来源版本</summary>
            <code>{source.source_revision}</code>
            <span>
              attempt {source.attempt} · {source.parser_version}
            </span>
          </details>
        </footer>
      </aside>
    </>
  );
}
/** Lightweight guard remains mounted when the reader is collapsed. No PDF redownload. */
export function SourceGuard({
  source,
  onFatal,
}: {
  source: Source;
  onFatal: (message: string, cause?: unknown) => void;
}) {
  const fatal = useRef(onFatal);
  useEffect(() => {
    fatal.current = onFatal;
  }, [onFatal]);
  useEffect(() => {
    const controller = new AbortController();
    let busy = false;
    const validate = async () => {
      if (document.visibilityState === "hidden" || busy) return;
      busy = true;
      try {
        await checkSource(source, controller.signal);
      } catch (error) {
        if (!controller.signal.aborted) {
          forgetPdf(source);
          fatal.current((error as Error).message, error);
        }
      } finally {
        busy = false;
      }
    };
    const onFocus = () => {
      void validate();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    const timer = window.setInterval(onFocus, 30_000);
    return () => {
      controller.abort();
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [source]);
  return null;
}
