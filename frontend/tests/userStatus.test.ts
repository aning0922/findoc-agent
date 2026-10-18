import test from 'node:test';
import assert from 'node:assert/strict';
import { statusPresentation, taskUserStatus } from '../src/product/userStatus.ts';
import type { Task } from '../src/product/operatingResearch.ts';
test('presentation keeps eight states distinct without granting semantic qualification', () => {
  assert.equal(Object.keys(statusPresentation).length, 8);
  assert.equal(new Set(Object.values(statusPresentation).map(v => v.title)).size, 8);
  assert.notEqual(statusPresentation.refused.tone, statusPresentation.failed.tone);
  assert.match(statusPresentation.completed.consequence, /待人工/);
  assert.match(statusPresentation.unknown.consequence, /只读/);
});
test('task state uses structured server outcome; a human checkpoint is not running', () => {
  const task = { status: 'awaiting_human_confirmation', execution_status: 'idle' } as Task;
  assert.equal(taskUserStatus(task), null);
  assert.equal(taskUserStatus({ ...task, execution_status: 'running' }), 'waiting');
  assert.equal(taskUserStatus({ ...task, status: 'failed' }), 'failed');
  assert.equal(taskUserStatus({ ...task, status: 'refused' }), 'refused');
  assert.equal(taskUserStatus({ ...task, status: 'completed' }), 'completed');
  assert.equal(taskUserStatus({ ...task, publication_eligibility: { status: 'invalidated' } } as Task), 'invalidated');
  assert.equal(taskUserStatus({ ...task, status: 'completed' }, true), 'unknown');
});
