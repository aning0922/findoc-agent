import { test as nodeTest } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { matchRunReview, matchOperatingReviews, taskReviewTarget, reportReviewTarget } from '../src/product/externalReview.ts';
import { externalReviewManifest } from '../src/product/d28ExternalReviews.ts';
// Exact historical Run/Report payloads are kept in the private archive.
// Explicitly configured but missing fixtures must still fail, not silently skip.
const configuredRoot = process.env.FINDOC_REVIEW_FIXTURES;
const root = configuredRoot
  ? pathToFileURL(resolve(configuredRoot) + sep)
  : new URL('../../product/d28/evidence/', import.meta.url);
const test = !configuredRoot && !existsSync(new URL('qa-real/A01.json', root))
  ? nodeTest.skip
  : nodeTest;
const load = (path: string) => JSON.parse(readFileSync(new URL(path, root), 'utf8'));
const clone = <T>(v: T): T => structuredClone(v);
for (const record of externalReviewManifest.records.filter(r => r.kind === 'qa')) {
  const id = record.question_id!;
  test(`${id}: exact Run/query/answer/source, rejects changed identity and stays native pending/null`, async () => {
    const run = load(`qa-real/${id}.json`).response, before = JSON.stringify(run);
    const match = await matchRunReview(run);
    assert.equal(match.status, 'matched'); assert.equal(match.records[0].question_id, id);
    assert.equal(run.result.human_review, id.startsWith('A') ? 'pending' : null);
    const changes = [
      (v: any) => { v.run_id = '00000000-0000-4000-8000-000000000000'; },
      (v: any) => { v.query += ' '; },
      (v: any) => { v.operation_id = '00000000-0000-4000-8000-000000000000'; },
      (v: any) => { v.workspace_id = 'foreign'; },
      (v: any) => { v.result.content += 'changed'; },
      (v: any) => { v.integrity_sha256 = '0'.repeat(64); },
      (v: any) => { v.documents[0].source_revision = '0'.repeat(64); },
      (v: any) => { v.documents[0].content_sha256 = '0'.repeat(64); },
      (v: any) => { v.documents[0].parser_version += '-changed'; },
      (v: any) => { v.result.human_review = 'accepted'; },
    ];
    for (const change of changes) { const value = clone(run); change(value); assert.notEqual((await matchRunReview(value)).status, 'matched'); }
    assert.equal(JSON.stringify(run), before);
  });
}
test('same answer and source with another query or Run cannot inherit approval, including empty refusals', async () => {
  for (const ids of [['A01', 'A02', 'A03'], ['R01', 'R02', 'R03']]) {
    const a = load(`qa-real/${ids[0]}.json`).response;
    for (const id of ids.slice(1)) {
      const b = load(`qa-real/${id}.json`).response;
      assert.equal(a.result.content, b.result.content);
      const wrong = clone(a); wrong.query = b.query;
      assert.equal((await matchRunReview(wrong)).status, 'mismatch');
      const own = await matchRunReview(b); assert.equal(own.records[0].question_id, id);
    }
  }
});
test('historical expired source preserves exact historical scope without granting current eligibility', async () => {
  const run = load('qa-real/A01.json').response; run.source_states[0].status = 'expired';
  assert.equal((await matchRunReview(run)).status, 'matched');
});
test('Midea four statements bind revision, all source/citation bytes, and original wording; rewrites stay sidecar', async () => {
  const task = load('human-followup/midea-user-resume-completed.json').task, before = JSON.stringify(task);
  const target = taskReviewTarget(task)!;
  const match = await matchOperatingReviews(target);
  assert.equal(match.status, 'matched'); assert.equal(match.records.length, 4);
  assert.deepEqual(match.records.map(r => r.decision), ['approved_with_rewrite', 'approved_as_written', 'approved_with_rewrite', 'approved_as_written']);
  assert.deepEqual(match.records.map(r => !!r.rewrite), [true, false, true, false]);
  const original = load('human-followup/operating-semantic-review.json');
  for (const r of match.records) assert.equal(r.rewrite ?? null, original.interpretations[r.statement_index!].approved_rewrite ?? null);
  const changes = [
    (v: any) => { v.task_id = '00000000-0000-4000-8000-000000000000'; },
    (v: any) => { v.task_revision++; },
    (v: any) => { v.workspace_id = 'foreign'; },
    (v: any) => { v.model_interpretations[0].text += 'changed'; },
    (v: any) => { v.model_interpretations[0].citations = [3]; },
    (v: any) => { v.sources[0].content_sha256 = '0'.repeat(64); },
    (v: any) => { v.sources[0].source_revision = '0'.repeat(64); },
    (v: any) => { v.descriptions[0].citation.chunk_id += 'changed'; },
    (v: any) => { v.descriptions[0].text += 'changed'; },
    (v: any) => { v.test_mode = 'simulated_test'; },
    (v: any) => { v.model_interpretations[0].verified_operating_attribution = true; },
  ];
  for (const change of changes) { const value = clone(target); change(value); assert.notEqual((await matchOperatingReviews(value)).status, 'matched'); }
  assert.equal(JSON.stringify(task), before);
});
for (const name of ['gree', 'comparison']) test(`${name}: four unreviewed explanations never inherit Midea`, async () => {
  const task = load(`human-followup/${name}-user-resume-completed.json`).task;
  assert.equal(task.final_research_content.model_interpretations.length, 4);
  assert.equal((await matchOperatingReviews(taskReviewTarget(task))).status, 'absent');
  assert.equal(task.final_research_content.human_review_status, 'pending');
  assert.equal(task.final_research_content.verified_operating_attribution, false);
});
for (const revision of [1, 2]) test(`report v${revision}: original snapshot and user declarations unchanged; external notes only bind Task wording`, async () => {
  const detail = load(`human-followup/midea-report-v${revision}-user-saved.json`).detail;
  const before = JSON.stringify(detail), target = reportReviewTarget(detail.report.trusted_snapshot);
  assert.equal((await matchOperatingReviews(target)).records.length, 4);
  assert.equal(detail.report.editor_revision.qualification_limit, 'user_assertions_unverified');
  assert.equal(detail.report.editor_revision.verified_operating_attribution, false);
  assert.equal(detail.report.editor_revision.validation_status, 'pending_semantic_review');
  assert.equal(JSON.stringify(detail), before);
});
