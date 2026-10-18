export interface ResearchCitation {
  number: number; document_id: string; company_id: string; report_year: number;
  source_revision: string; chunk_id: string; physical_page: number;
  source_file: string; text: string; kind: string; parser_version?: string;
}
export interface ResearchAnswer {
  schema_version: "research-answer-v1"; selection_id: string;
  outcome: "answered" | "refused" | "system_error";
  answer_mode?: "verified_excerpts"; human_review?: "pending";
  content: string; citations: ResearchCitation[]; reason?: string; error_code?: string;
  documents?: { document_id: string; company_id: string; source_revision: string }[];
}
export function validateResearchAnswer(value: ResearchAnswer, selected: string[]): ResearchAnswer {
  if (value.schema_version !== "research-answer-v1" || !/^[a-f0-9]{64}$/.test(value.selection_id)
      || !["answered", "refused", "system_error"].includes(value.outcome)
      || typeof value.content !== "string" || !Array.isArray(value.citations)) throw new Error("问答响应不完整");
  if (value.outcome === "system_error") {
    if (value.content || value.citations.length) throw new Error("异常响应包含未验证内容");
    return value;
  }
  if (!Array.isArray(value.documents)
      || JSON.stringify(value.documents.map(d => d.document_id).sort()) !== JSON.stringify([...selected].sort()))
    throw new Error("回答来源范围不一致");
  if (value.outcome === "refused" && (value.content || value.citations.length)) throw new Error("拒答包含答案");
  if (value.outcome === "answered" && (!value.content || !value.citations.length)) throw new Error("回答没有证据");
  for (const c of value.citations) {
    const d = value.documents.find(d => d.document_id === c.document_id);
    if (!d || d.company_id !== c.company_id || d.source_revision !== c.source_revision
        || !/^[a-f0-9]{64}$/.test(c.source_revision) || !c.chunk_id || !c.text
        || !Number.isSafeInteger(c.number) || c.number < 1
        || !Number.isSafeInteger(c.physical_page) || c.physical_page < 1) throw new Error("引用来源不一致");
  }
  return value;
}
export function researchPdfUrl(c: ResearchCitation): string {
  const q = new URLSearchParams({ company_id: c.company_id, source_revision: c.source_revision });
  return `/api/documents/${encodeURIComponent(c.document_id)}/file?${q}#page=${c.physical_page}`;
}
