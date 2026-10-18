import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validateAnswerFocus, textSha, type FocusProjection } from '../src/product/answerFocus.ts';
import type { ResearchRun } from '../src/product/researchHistory.ts';
import { qaRefusalMessage, qaRefusalTitle } from '../src/product/recoveryMessages.ts';
const samples: {case: string; run: ResearchRun; projection: FocusProjection}[] = JSON.parse(readFileSync(new URL('./fixtures/answer-focus.json', import.meta.url), 'utf8'));
const canonical = (v: any): string => Array.isArray(v) ? `[${v.map(canonical).join(',')}]` : v && typeof v === 'object' ? `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}` : JSON.stringify(v);
async function rehash(v: FocusProjection) {
  const {projection_sha256: _projection_sha256, ...payload} = v;
  v.projection_sha256 = await textSha(canonical(payload)); return v;
}
for (const item of samples) test(`${item.case}: actual captured-source projection binds exact Run, query, table and row`, async () => {
  const original = JSON.stringify(item.run);
  assert.equal(await validateAnswerFocus(item.projection, item.run), item.projection);
  assert.equal(JSON.stringify(item.run), original);
});
test('same historical answer SHA cannot authorize another question or Run focus', async () => {
  assert.equal(samples[0].projection.answer_sha256, samples[1].projection.answer_sha256);
  await assert.rejects(validateAnswerFocus(samples[0].projection, samples[1].run));
  await assert.rejects(validateAnswerFocus(samples[1].projection, samples[0].run));
});
for (const fault of ['value', 'unit', 'year', 'row', 'column', 'revision', 'parser', 'page', 'query', 'answer', 'table', 'raw_refs', 'bbox', 'hash']) test(`reject ${fault} even with a freshly computed projection digest`, async () => {
  const item=samples[0], v=structuredClone(item.projection), f=v.focus!;
  if(fault==='value')f.raw_value='32,184,570,372.28';
  if(fault==='unit')f.raw_unit='千元';
  if(fault==='year')f.financial_year=2023;
  if(fault==='row')f.row_index=2;
  if(fault==='column')f.column_index=4;
  if(fault==='revision')f.source_revision='f'.repeat(64);
  if(fault==='parser')f.parser_version='fast-pdf-v3';
  if(fault==='page')f.physical_page=8;
  if(fault==='query')v.query_sha256='f'.repeat(64);
  if(fault==='answer')v.answer_sha256='f'.repeat(64);
  if(fault==='table') { f.table_text=f.table_text.replace(f.raw_value,'999.00'); f.table_text_sha256=await textSha(f.table_text); }
  if(fault==='raw_refs')f.raw_cells=[[1,-1]];
  if(fault==='bbox')f.bbox=['NaN','1','2','3'];
  await rehash(v);if(fault==='hash')v.projection_sha256='0'.repeat(64);
  await assert.rejects(validateAnswerFocus(v,item.run));
});
test('unlocated explicitly contains no financial value and remains read only', async () => {
  const item=samples[0], v=structuredClone(item.projection);
  v.status='unlocated';v.reason='missing_or_ambiguous_cell';v.focus=null;await rehash(v);
  assert.equal((await validateAnswerFocus(v,item.run)).focus,null);
  v.focus=item.projection.focus;await rehash(v);await assert.rejects(validateAnswerFocus(v,item.run));
});
test('unsupported currency and aggregation refusals cannot promise a fact-authorized calculation', () => {
  for (const query of ['请计算这四份年报全部营业收入的美元金额。', '请计算跨年度营业收入合计']) {
    assert.equal(qaRefusalTitle('requires_confirmed_financial_analysis', query), '当前不支持这类财务计算');
    assert.match(qaRefusalMessage('requires_confirmed_financial_analysis', query), /不会启用/);
  }
  assert.match(qaRefusalMessage('requires_confirmed_financial_analysis', '不要算同比，但计算格力与美的2025年度营业收入差额。'), /确定性分析服务/);
  assert.equal(qaRefusalTitle('unsupported_table_structure', '美元'), '表格列关系暂未通过核验');
  assert.equal(qaRefusalTitle('insufficient_evidence', '美元'), '所选资料证据不足');
});
