import test from 'node:test';
import assert from 'node:assert/strict';
import { resultReading } from '../src/product/resultReading.ts';
const base = { absolute: '49302131000', percentage: '12.11', current: '456451731000', base: '407149600000', currentLabel: '本期企业', baseLabel: '比较企业', currentYear: 2025, baseYear: 2024, comparison: false };
test('results describe current/base, direction, adjacent-year comparison and exact server delta', () => {
  const r = resultReading(base);
  assert.equal(r.period, '2025 年较 2024 年'); assert.equal(r.kind, '同比');
  assert.equal(r.rate, '增加 12.11%'); assert.equal(r.amount, '增加 493.0213 亿元（约）');
  assert.equal(r.exact, '49,302,131,000 元');
});
test('decrease, no change and nonadjacent years do not mislabel direction or yoy', () => {
  assert.equal(resultReading({ ...base, absolute: '-5', percentage: '-10' }).rate, '减少 10%');
  assert.equal(resultReading({ ...base, absolute: '0.00', percentage: '0' }).rate, '持平 · 0%');
  assert.equal(resultReading({ ...base, baseYear: 2023 }).kind, '跨年比较');
});
test('signed negative base and cross-zero preserve server percent instead of calling it a decrease', () => {
  const r = resultReading({ ...base, current: '-50', base: '-100', absolute: '50', percentage: '-50' });
  assert.equal(r.rate, '变化率 -50%'); assert.match(r.amount, /^增加/); assert.match(r.note, /基数为负/);
  assert.match(resultReading({ ...base, current: '50', base: '-100', absolute: '150', percentage: '-150' }).note, /跨越零点/);
});
test('zero base and missing values stay undefined; company comparison names B relative to A', () => {
  const r = resultReading({ ...base, base: '0', percentage: null });
  assert.equal(r.rate, '变化率无定义'); assert.match(r.note, /基数为零/);
  const missing = resultReading({ ...base, current: null, absolute: null, percentage: null });
  assert.equal(missing.amount, '差额无定义'); assert.equal(missing.exact, '无定义');
  const c = resultReading({ ...base, comparison: true, currentLabel: '企业 B', baseLabel: '企业 A' });
  assert.equal(c.period, '2025 年 · 企业 B 相对 企业 A'); assert.equal(c.kind, '以 企业 A 为比较基准');
});
