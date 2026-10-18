import { excerptBlocks, type ExcerptBlock } from './excerptBlocks.ts';
export function ExcerptTable({ block }: { block: Extract<ExcerptBlock, { kind: 'table' }> }) {
  return <div className="report-table-scroll" tabIndex={0} role="region" aria-label="原文表格横向阅读">
    <table aria-label="来源原文表格"><thead><tr>{block.header.map((cell, c) => <th scope="col" key={c}>{cell}</th>)}</tr></thead>
      <tbody>{block.rows.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c} data-cell-kind={!cell ? "empty" : /^[+-]?\d[\d,.%]*$/.test(cell) ? "number" : "text"}>{cell}</td>)}</tr>)}</tbody></table>
  </div>;
}
export function VerifiedExcerpt({ text, allowTables = true }: { text: string; allowTables?: boolean }) {
  return <div>{excerptBlocks(text, allowTables).map((block, i) => block.kind === 'text'
    ? <div key={i} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{block.text}</div>
    : <ExcerptTable key={i} block={block} />)}</div>;
}
