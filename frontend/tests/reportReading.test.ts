import test from 'node:test';
import assert from 'node:assert/strict';
import { reportExcerptReading, reportRateLabel, reportSummaryDisplay, reportDecimalDisplay } from '../src/product/reportReading.ts';
import type { Draft } from '../src/product/reportDraft.ts';
const version = 'fast-pdf-v4;table-geometry-v2;test=1';
const table = '|项目|2025年|2024年|\n|---|---|---|\n|营业收入（千元）|456,451,731|407,149,600|\n|现金流||-10|';
test('report navigation preserves complete annual columns and units; repeated tables remain in original bytes', () => {
  const text = `说明：合并口径\n${table}\n周边审计内容\n${table}`;
  const r = reportExcerptReading(text, version); assert.equal(r.tables.length, 1); assert.equal(r.duplicates, 1);
  assert.deepEqual(r.tables[0].rows[1], ['现金流', '', '-10']); assert.equal(r.tables[0].header[1], '2025年');
  assert.equal(r.tables[0].rows[0][0], '营业收入（千元）'); assert.equal(text.includes('周边审计内容'), true);
});
test('malformed annual rows, legacy parser and absent versions retain full literal text without guessed cells', () => {
  for (const text of [`${table}\n|bad|short|`, `${table}\n|broken`, `${table}\n|---|---|---|`]) {
    const r = reportExcerptReading(text, version); assert.equal(r.literal, true); assert.deepEqual(r.tables, []);
  }
  for (const v of [undefined, 'fast-pdf-v3;table-geometry-v1;']) assert.equal(reportExcerptReading(table, v).literal, true);
  assert.equal(reportExcerptReading('真实经营原文\n<script>alert(1)</script>', version).tables.length, 0);
});
test('a neighboring valid audit table does not get merged into an annual table or guessed into annual columns', () => {
  const r = reportExcerptReading(`${table}\n|审计师|地址|\n|---|---|\n|甲|乙|`, version);
  assert.equal(r.literal, false); assert.equal(r.tables.length, 1); assert.equal(r.tables[0].rows.length, 2);
});
const draft = { report_type: 'company_period_change', financial_facts: [{ side: 'first', period: 2025 }, { side: 'second', period: 2023 }], financial_analysis: [{ absolute_change: '12345678901234567890.00100' }] } as unknown as Draft;
test('nonadjacent report summary and rates use actual frozen years without changing exact strings or export text', () => {
  assert.equal(reportRateLabel(draft), '跨年比较 · 2025 年较 2023 年');
  assert.equal(reportRateLabel({ ...draft, financial_facts: [{ ...draft.financial_facts[0] }, { ...draft.financial_facts[1], period: 2024 }] }), '同比 · 2025 年较 2024 年');
  assert.equal(reportRateLabel({ ...draft, report_type: 'company_same_period_comparison' }), '比较期间不一致 · 请核对实际年度');
  assert.equal(reportRateLabel({ ...draft, report_type: 'company_same_period_comparison', financial_facts: draft.financial_facts.map(f => ({ ...f, period: 2025 })) }), '2025 年 · 以 A 为基准的相对差异');
  assert.equal(reportDecimalDisplay('-1234567890.00000'), '-1,234,567,890.00000');
  assert.equal(reportRateLabel({ ...draft, financial_facts: [] }), '期间变化 · 请核对实际年度');
  const raw = '营业收入：本期−上期差额 12345678901234567890.00100 CNY 元；同比 -7.00%。';
  const frozen = JSON.stringify(draft);
  assert.equal(reportSummaryDisplay(raw, draft), '营业收入：本期−上期差额 12,345,678,901,234,567,890.00100 人民币元；跨年比较 · 2025 年较 2023 年变化率 -7.00%。');
  assert.equal(JSON.stringify(draft), frozen); assert.equal(draft.financial_analysis[0].absolute_change, '12345678901234567890.00100');
});
