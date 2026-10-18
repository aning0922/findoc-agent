import test from 'node:test';
import assert from 'node:assert/strict';
import { readProductRoute, taskSectionPath, qaPath, reportPath, pathFor } from '../src/product/productRoutes.ts';
const route = (path: string) => readProductRoute(new URL(path, 'http://localhost'));
test('legacy links retain independent task/run/report/revision identity', () => {
  assert.equal(route('/').page, 'home');
  assert.equal(route('/companies').page, 'companies');
  assert.equal(route('/companies/co%20a/analysis?task=A').task, 'A');
  assert.equal(route('/companies/co%20a/analysis').company, 'co a');
  assert.equal(route('/research?task=A').task, 'A');
  assert.equal(route('/research?mode=qa&run=R&return_task=A').task, '');
  assert.equal(route('/research?mode=qa&run=R&return_task=A').run, 'R');
  assert.equal(route('/reports?report=Q&revision=1&company=B').report, 'Q');
  assert.equal(route('/reports?report=Q&revision=1&company=B').revision, '1');
  assert.throws(() => route('/research?task=A&task=B'));
});
test('navigation builders carry only explicit scope and do not create business objects', () => {
  assert.equal(route(taskSectionPath('A', 'co', 'financial')).section, 'financial');
  assert.equal(route(qaPath('co', 'A')).task, '');
  assert.equal(route(reportPath('Q', 1)).revision, '1');
  assert.equal(pathFor('companies', 'co'), '/companies');
  assert.equal(pathFor('home'), '/');
});
