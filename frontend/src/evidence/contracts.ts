export interface Source {
  company_id: string; document_id: string; source_revision: string; content_sha256: string
  attempt: number; parser_version: string; physical_pages: number; report_year: number
  metadata_status: string
}
export type Box = [number, number, number, number]
export interface Cell { text: string | null; bbox: Box | null }
export interface Evidence {
  company_id: string; document_id: string; source_revision: string; evidence_id: string
  physical_page: number; text: string; layout: { strategy: string; rows: Cell[][] } | null
}
export interface Reference {
  evidence_id: string; physical_page: number; role: string; raw_value: string | null
  bbox: Box | null; label: string; raw_unit: string | null
}
export interface Candidate {
  company_id: string; document_id: string; source_revision: string; content_sha256: string
  attempt: number; parser_version: string; candidate_id: string; metric_key: string; period: number
  status: string; raw_value: string | null; raw_unit: string | null; evidence: Reference[]
  failure_reason: string | null; confirmation_status: string
  value_cny_yuan?: string | null; multiplier?: string | null; currency?: string | null
  scope?: string; accounting_basis?: string
  basis_evidence?: { evidence_id: string; physical_page: number; excerpt: string }[]
}
export interface Selection { company: string; document: string; revision: string; evidence: string; page: string }
export const METRICS: Record<string, string> = {
  revenue: '营业收入', net_profit_parent: '归母净利润', operating_cash_flow: '经营活动现金流量净额',
}
export function sourceKey(s: Pick<Source, 'company_id' | 'document_id' | 'source_revision'>): string {
  return `${s.company_id}/${s.document_id}/${s.source_revision}`
}
export function sameSource(a: Source, b: Source): boolean {
  return sourceKey(a) === sourceKey(b) && a.content_sha256 === b.content_sha256
    && a.attempt === b.attempt && a.parser_version === b.parser_version && a.physical_pages === b.physical_pages
}
export function validateSource(value: Source, company: string, document: string, revision = ''): Source {
  if (value.company_id !== company || value.document_id !== document
    || (revision && value.source_revision !== revision)
    || !/^[a-f0-9]{64}$/.test(value.source_revision) || !/^[a-f0-9]{64}$/.test(value.content_sha256)
    || !Number.isSafeInteger(value.attempt) || value.attempt < 1
    || !Number.isSafeInteger(value.physical_pages) || value.physical_pages < 1
    || !Number.isSafeInteger(value.report_year) || value.report_year < 1 || value.report_year > 9999
    || typeof value.parser_version !== 'string' || !value.parser_version) throw new Error('来源身份或版本不匹配。')
  return value
}
export function validateEvidence(e: Evidence, s: Source, id: string, page?: number): Evidence {
  if (sourceKey(e) !== sourceKey(s) || e.evidence_id !== id || typeof e.text !== 'string'
    || !Number.isSafeInteger(e.physical_page) || e.physical_page < 1 || e.physical_page > s.physical_pages
    || (page !== undefined && page !== e.physical_page)) throw new Error('证据身份、版本或物理页不匹配。')
  return e
}

export interface Citation { key: string; candidate: Candidate; reference: Reference }
export function citations(candidates: Candidate[]): Citation[] {
  return candidates.flatMap(candidate => candidate.evidence.map((reference, index) => ({ key: `${candidate.candidate_id}:${index}`, candidate, reference })))
}
