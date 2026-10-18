import { test } from 'node:test';
import assert from 'node:assert/strict';
import { annualTables, citationGroups } from '../src/product/qaReading.ts';
import { qaFailureTitle, qaRefusalTitle } from '../src/product/recoveryMessages.ts';
import type { ResearchCitation } from '../src/product/researchAnswer.ts';
const version = 'fast-pdf-v4;table-geometry-v2;test=1';
test('annual navigation preserves the entire table and empty columns; surrounding context remains in the saved text', () => {
  const text = '单位：千元；合并口径\n| |项目|2025年|2024年|\n|---|---|---|---|\n| |营业收入|456,451,731|407,149,600|\n| |净利润|43,945,411|38,537,237|\n说明：未重述\n|注册|代码|\n|---|---|\n|公司|123|';
  const c = { text, parser_version: version }; const tables = annualTables(c);
  assert.equal(tables.length, 1);
  if (tables[0].kind === 'table') { assert.deepEqual(tables[0].header, ['', '项目', '2025年', '2024年']); assert.equal(tables[0].rows.length, 2); assert.equal(tables[0].rows[0][2], '456,451,731'); }
  assert.equal(c.text, text); assert.deepEqual(annualTables({ ...c, parser_version: 'fast-pdf-v3;table-geometry-v1;' }), []);
});
test('source groups keep revision identity even when the document and amount are identical', () => {
  const a = { document_id: 'A', source_revision: 'old', number: 1 } as ResearchCitation;
  const b = { ...a, source_revision: 'new', number: 2 };
  const third = { ...a, number: 3 };
  assert.deepEqual(citationGroups([a, b, third]), [[a, third], [b]]);
});
test('six refusal/failure boundaries use distinct user titles', () => {
  const titles = [qaRefusalTitle('insufficient_evidence'), qaRefusalTitle('requires_confirmed_financial_analysis'), qaRefusalTitle('unsupported_table_structure'), qaFailureTitle('llm_error'), qaFailureTitle('context_budget_error'), '研究结果暂时无法确认'];
  assert.equal(new Set(titles).size, 6);
});
