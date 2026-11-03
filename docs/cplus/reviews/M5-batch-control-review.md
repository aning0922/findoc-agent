# M5 bounded batch ACK/cancellation review

Read-only review of root WIP on `0add53fdf2bff258293f1c1a1988d441dd0999ea`.
Exact reviewed service/API/tools/UI hashes are in `M5-batch-control-proof.json`.
Root owns those files; this commit changes review documentation/fixtures only.

## Disposition

**The two proposed cancellation changes pass this bounded review.** Accepting a
past revision while rejecting a future revision is safe for the current immutable
plan: no cells are added after creation, and the atomic UPDATE targets only cells
still `queued`. Cells which moved to `dispatching` or a terminal state are excluded.
An old revision therefore cannot broaden cancellation to later-added work.

Cancellation resolves the batch and immutable plan under the caller's owner,
then uses an empty selected_sources fence and an identity pre-COMMIT check. It
does not need to validate failed source material in order to stop unstarted work.
The original execution path keeps its per-cell checked/guard/COMMIT checks.

No reproduced P0 or cancellation-boundary P1 was found. One concrete **P1 in AI
plan recovery/approval UI** was independently reproduced and should be fixed
before calling the AI-enabled batch confirmation path complete.

## P1: recovered AI plan is presented as zero-model before approval

**Trigger:** prepare an AI-enabled plan, lose its response/reload while the plan
operation marker is pending, then choose “查询原操作” and approve the recovered plan.

**Cause in BatchResearchPanel:** `generateAI` initializes to false; `consume()`
recovers the immutable plan but never restores/derives its execution mode. The
confirmation banner reads `generateAI`, not the returned plan's `limits` or frozen
prepared flags. Once `plan` is set the AI checkbox is disabled. The approval POST
sends the original AI plan ID/revision/hash, so the server correctly retains the
AI behavior despite the displayed zero-model description.

**Actual controlled React/browser reproduction:** the saved fixture plan had
`limits.execution_mode=ai_review`, `max_provider_attempts=4`, and four prepared
cells with `generate_explanation=true`. Recovery rendered an unchecked **disabled**
AI checkbox and this confirmation text:

> 共 4 项，使用 1 份来源。串行执行；模型调用为零；不请求财务核准。

Clicking “批准并开始” emitted `confirmed=true` for that same AI plan. The actual
React component was served by an isolated Vite instance with cache/config confined
to a temporary directory; all API responses were intercepted synthetic fixtures.
No real backend/provider was contacted and neither 14540 nor 14542 was used.
This demonstrates misleading paid-operation confirmation, not actual expenditure.

Evidence: `M5-batch-ui-recovery-proof.json`. Reproduction fixture:
`M5-batch-ui-recovery-fixture.cjs` (run with bundled Node and root checkout as argv[2]).

**Minimum repair:** render approval mode and upper bound from the validated saved
plan. The pre-plan checkbox controls only preparation. Recovery must show the
saved mode; missing/inconsistent AI metadata must not silently become “0 calls”.
Legacy plans whose prepared flags are all absent/false can retain their original
pure-tools behavior. Re-run the same recovered-AI case: show at-most-four/unknown
actual cost, and preserve the original operation/plan identity without replay.

## Executed cancellation and no-replay checks

Ran three independent temporary-SQLite fixtures against root WIP plus root's two
async and two original batch tests: **7 passed in 0.32s**. Fixture code is retained
in `M5-batch-control-fixture.py`. No real provider, ledger or source files were used.

| Controlled case | Observed result |
| --- | --- |
| Background start with first child blocked by Event | Completed durable ACK returns while child is still active; matrix shows one dispatching and three queued |
| Same start operation repeated | Same original ACK; no second child dispatch |
| Other principal or expired identity attempts cancellation | Rejected; active/queued cells unchanged |
| Future expected_revision | Rejected; no cells cancelled |
| ACK revision 1 after first dispatch advances revision | Accepted; exactly three queued cells cancelled, active cell unchanged |
| Source-sensitive guard deliberately fails for nonempty source fences | Cancellation still succeeds using empty source fence |
| Cancel operation repeated | Same saved receipt/count; no replay |
| Active cell released after cancellation | One completed, three cancelled; exactly one execute call |
| Lease expires inside cancellation pre-COMMIT hook | Queued-cell updates roll back; cancel operation stays UNKNOWN |
| Background task interrupted | All unfinished cells become UNKNOWN in the same private store |
| Service reconstructed, then GET/list/same start operation | UNKNOWN remains, original ACK is returned, zero new task/execute calls |
| Old pure-tools plan request replayed with new default false | Original receipt retained; switching same operation to true conflicts |

These fixtures establish the bounded state/transaction mechanisms. Root's real
browser cancel and source-fault evidence is separate and was reported as in
progress; no new native/socket/BGE PASS is inferred from these tests.

## AI adapter and UI source audit

- HTTP explicitly calls `start(..., background=True)`; ACK is persisted before
  create_task. Completion is read through the matrix. GET/list do not dispatch.
- Pure-tools is the default. AI mode is frozen during plan creation and covered
  by its hash, then requires explicit start approval. Risk uses the saved context
  operation UUID plus saved answer UUID; annual uses its saved child UUID. There
  is no automatic UNKNOWN retry. Original guarded providers remain responsible
  for actual physical-call and shared-budget enforcement.
- Matrix cost metadata correctly uses unknown actual calls/reservation for AI
  and a one-attempt upper bound, while pure tools show zero. This audit performs
  no real-provider cardinality test and does not certify observed billing.
- Completed ACK clears pending in the UI, supplies four cells for polling and
  enables queued cancellation; historical matrix reads remain read-only. The
  recovered-plan cost disclosure issue above is distinct from ACK/cancel safety.

No full-site, production concurrency or additional provider-health review was
performed. Initial local UI harness dependency resolution was corrected before
the successful browser reproduction; those setup failures are not counted as
application failures or passing tests.
