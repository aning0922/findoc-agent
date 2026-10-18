import { tableCells, verifiedTableVersion, type ExcerptBlock } from './excerptBlocks.ts';
import type { Draft } from './reportDraft.ts';
export function reportDecimalDisplay(value: string) {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return value;
  const [whole, fraction] = value.split('.');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction === undefined ? '' : `.${fraction}`);
}
type Table = Extract<ExcerptBlock, { kind: 'table' }>;
const separator = (cells: string[] | null) => !!cells?.length && cells.every(c => /^:?-{3,}:?$/.test(c));

/** Read-only navigation over complete, version-qualified annual tables. Never infer missing cells. */
export function reportExcerptReading(text: string, parserVersion?: string) {
  const tables: Table[] = [], lines = text.split('\n'); let malformed = false, otherMalformed = false;
  const qualified = verifiedTableVersion(parserVersion);
  if (qualified) for (let i = 0; i < lines.length - 1; i++) {
    const header = tableCells(lines[i]), rule = tableCells(lines[i + 1]);
    if (!header || rule?.length !== header.length || !separator(rule)) continue;
    const annual = header.filter(c => /^\d{4}年(?:末)?$/.test(c)).length >= 2;
    const rows: string[][] = []; let j = i + 2, blockMalformed = false;
    for (; j < lines.length; j++) {
      const row = tableCells(lines[j]), next = tableCells(lines[j + 1] || '');
      // A new valid table begins a separate block, even if it has different columns.
      if (row && next?.length === row.length && separator(next)) {
        if (row.length === header.length && row.filter(c => /^\d{4}年(?:末)?$/.test(c)).length < 2) blockMalformed = true;
        break;
      }
      if (!row) { if (lines[j].trim().startsWith('|')) blockMalformed = true; break; }
      if (row.length !== header.length || separator(row)) { blockMalformed = true; break; }
      rows.push(row);
    }
    if (annual && rows.length) tables.push({ kind: 'table', header, rows });
    if (annual) malformed ||= blockMalformed;
    else otherMalformed ||= blockMalformed;
    i = j - 1;
  }
  const unique = [...new Map(tables.map(t => [JSON.stringify(t), t])).values()];
  const literal = !qualified || malformed || (!tables.length && otherMalformed);
  return { tables: literal ? [] : unique, literal, duplicates: tables.length - unique.length,
    reason: malformed ? '年度表存在无法可靠对齐的行，完整原文按原样展示。' : !qualified ? '此解析版本未提供可核验的表格列关系，完整原文按原样展示。' : '' };
}

/** Label from frozen fact years only; server deltas/percentages are never recalculated. */
export function reportRateLabel(draft: Pick<Draft, 'financial_facts' | 'report_type'>) {
  const years = (side: 'first' | 'second') => [...new Set(draft.financial_facts.filter(f => f.side === side).map(f => f.period))];
  const a = years('first'), b = years('second');
  if (a.length !== 1 || b.length !== 1 || !Number.isSafeInteger(a[0]) || !Number.isSafeInteger(b[0])) return '期间变化 · 请核对实际年度';
  if (draft.report_type === 'company_same_period_comparison') return a[0] === b[0] ? `${a[0]} 年 · 以 A 为基准的相对差异` : '比较期间不一致 · 请核对实际年度';
  if (draft.report_type !== 'company_period_change' || a[0] <= b[0]) return '期间变化 · 请核对实际年度';
  return `${a[0] === b[0] + 1 ? '同比' : '跨年比较'} · ${a[0]} 年较 ${b[0]} 年`;
}
export function reportSummaryDisplay(text: string, draft: Draft) {
  let displayed = text;
  for (const r of draft.financial_analysis) displayed = displayed.replace(`差额 ${r.absolute_change} CNY 元`, `差额 ${reportDecimalDisplay(r.absolute_change)} 人民币元`);
  const label = reportRateLabel(draft);
  if (label.startsWith('跨年比较')) displayed = displayed.replace('；同比 ', `；${label}变化率 `);
  return displayed;
}
