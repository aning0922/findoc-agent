import { currentSource, VerificationInvalidated } from './researchVerification.ts';
import { useEffect, useState } from "react";
import { checkSource, getJson, loadPdf } from "../evidence/api.ts";
import { citations } from "../evidence/contracts.ts";
import type { Selection, Source } from "../evidence/contracts.ts";
import { EvidenceViewer } from "../evidence/EvidenceViewer.tsx";
import type { Fact } from "./api.ts";
import "../evidence/evidence.css";
export function FactEvidence({
  fact,
  close,
  fatal,
}: {
  fact: Fact;
  close: () => void;
  fatal: (message: string, cause?: unknown) => void;
}) {
  const items = citations([fact]),
    first = items[0];
  const [selection, setSelection] = useState<Selection>({
    company: fact.company_id,
    document: fact.document_id,
    revision: fact.source_revision,
    evidence: first.reference.evidence_id,
    page: String(first.reference.physical_page),
  });
  const [expanded, setExpanded] = useState(false);
  const [cite, setCite] = useState(first.key);
  const [data, setData] = useState<{
    source: Source;
    bytes: Uint8Array;
  } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const q = new URLSearchParams({
        company_id: fact.company_id,
        source_revision: fact.source_revision,
      });
      const source = currentSource(
        await getJson<Source>(
          `/documents/${encodeURIComponent(fact.document_id)}/source?${q}`,
          controller.signal,
        ),
        fact.company_id,
        fact.document_id,
        fact.source_revision,
      );
      if (
        source.content_sha256 !== fact.content_sha256 ||
        source.attempt !== fact.attempt ||
        source.parser_version !== fact.parser_version
      )
        throw new VerificationInvalidated("事实与 PDF 来源不匹配，金额和引用已撤下。");
      const bytes = await loadPdf(source, controller.signal);
      await checkSource(source, controller.signal);
      if (!controller.signal.aborted) setData({ source, bytes });
    })().catch((error) => {
      if (!controller.signal.aborted) fatal(error.message, error);
    });
    return () => controller.abort();
    // Mount is keyed by fact identity; callbacks do not change its source ownership.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fact]);
  if (!data)
    return (
      <aside className="fact-evidence-loading" role="status">
        正在校验原 PDF 与引用…<button onClick={close}>收起</button>
      </aside>
    );
  return (
    <div className={`fact-evidence ${expanded ? "is-expanded" : ""}`}>
      <div className="evidence-width-action">
        <button onClick={() => setExpanded((v) => !v)}>
          {expanded ? "紧凑阅读" : "展开阅读"}
        </button>
      </div>
      <EvidenceViewer
        source={data.source}
        bytes={data.bytes}
        items={items}
        selection={selection}
        citation={cite}
        onNavigate={(update) => {
          setSelection((s) => ({ ...s, ...update }));
          if (update.cite) setCite(update.cite);
        }}
        onClose={close}
        onFatal={fatal}
        contextLabel={
          fact.confirmation_kind === "simulated_test"
            ? "隔离 simulated_test 事实，非真人确认。"
            : "已确认事实的原文来源。"
        }
      />
    </div>
  );
}
