import { test } from 'node:test';
import assert from 'node:assert/strict';
import { changeDraftScope, changeDraftTemplate } from '../src/product/researchDraft.ts';
const config = () => ({ first: { company: 'A', year: '2025', document: 'docA', versions: { revenue: 'disclosureA' }, facts: { revenue: 'factA' } }, second: { company: 'B', year: '2025', document: 'docB', versions: { revenue: 'disclosureB' }, facts: { revenue: 'factB' } } });
test('dual company edits preserve the other company/source/fact and common year', () => {
  for (const side of ['first', 'second'] as const) {
    const old = config(), other = side === 'first' ? 'second' : 'first';
    const value = changeDraftScope(old, 'company_same_period_comparison', side, { company: 'C' });
    assert.deepEqual(value[other], old[other]); assert.equal(value[side].year, '2025');
    assert.equal(value[side].document, ''); assert.deepEqual(value[side].facts, {});
    assert.equal(old[side].document, side === 'first' ? 'docA' : 'docB');
  }
});
test('common year edits invalidate both sources while single period edits preserve other year/source', () => {
  const old = config();
  const dual = changeDraftScope(old, 'company_same_period_comparison', 'first', { year: '2024' });
  assert.deepEqual([dual.first.year, dual.second.year], ['2024', '2024']); assert.equal(dual.second.document, '');
  const single = changeDraftScope(old, 'company_period_change', 'first', { year: '2026' });
  assert.deepEqual(single.second, old.second); assert.equal(single.first.document, '');
});
test('single company edits synchronize both companies, preserve both years and revoke both dependencies', () => {
  const old = config(); old.second.year = '2024';
  const value = changeDraftScope(old, 'company_period_change', 'first', { company: 'C' });
  assert.deepEqual([value.first.company, value.second.company], ['C', 'C']);
  assert.deepEqual([value.first.year, value.second.year], ['2025', '2024']);
  assert.deepEqual([value.first.facts, value.second.facts], [{}, {}]);
});
test('document edits and template edits keep valid scope fields and never retain dependent facts', () => {
  const old = config();
  const doc = changeDraftScope(old, 'company_same_period_comparison', 'first', { document: 'newA' });
  assert.deepEqual(doc.second, old.second); assert.deepEqual(doc.first.versions, {}); assert.deepEqual(doc.first.facts, {});
  const single = changeDraftTemplate(old, 'company_period_change');
  assert.deepEqual([single.first.company, single.second.company], ['A', 'A']);
  assert.deepEqual([single.first.year, single.second.year], ['2025', '2025']);
  assert.equal(single.first.document, ''); assert.equal(single.second.document, '');
});
