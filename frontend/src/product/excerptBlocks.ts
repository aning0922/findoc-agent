/** Render only server-restored text and pipe tables; never execute source HTML. */
export type ExcerptBlock = { kind: "text"; text: string } | { kind: "table"; header: string[]; rows: string[][] };
export function tableCells(line: string): string[] | null {
  if (!line.startsWith("|") || !line.endsWith("|")) return null;
  const cells: string[] = []; let cell = "";
  for (let i = 1; i < line.length - 1; i++) {
    if (line[i] === "\\" && line[i + 1] === "|") { cell += "|"; i++; }
    else if (line[i] === "|") { cells.push(cell.trim()); cell = ""; }
    else cell += line[i];
  }
  cells.push(cell.trim()); return cells;
}
export function excerptBlocks(text: string, allowTables = true): ExcerptBlock[] {
  if (!allowTables) return [{kind: "text", text}];
  const lines = text.split("\n"), blocks: ExcerptBlock[] = []; let plain: string[] = [];
  const flush = () => { if (plain.length) blocks.push({ kind: "text", text: plain.join("\n") }); plain = []; };
  for (let i = 0; i < lines.length; i++) {
    const header = tableCells(lines[i]), separator = tableCells(lines[i + 1] || "");
    if (header && separator?.length === header.length && separator.every(c => /^:?-{3,}:?$/.test(c))) {
      const rows: string[][] = []; let end = i + 2;
      while (end < lines.length) {
        const row = tableCells(lines[end]);
        if (!row || row.length !== header.length) break;
        rows.push(row); end++;
      }
      flush(); blocks.push({ kind: "table", header, rows }); i = end - 1;
    } else plain.push(lines[i]);
  }
  flush(); return blocks;
}

export function verifiedTableVersion(parserVersion?: string): boolean {
  return Boolean(parserVersion?.startsWith("fast-pdf-v4;table-geometry-v2;"));
}
