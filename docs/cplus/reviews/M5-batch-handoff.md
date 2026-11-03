# M5: real OS / socket HTTP 2x2 batch and bilateral annual text

Fixed business baseline: `dd8cca72a734c01c4d203af1989ee4af5cb1bb7e` (after the authorized `18a2a98`). Date: 2026-11-03, Asia/Taipei. Owner changes are limited to the new `experiments/cplus/verify_real_batch.py`, `docs/cplus/eval/results/batch*`, and this handoff. No backend/UI/business changes.

**Result: P1 reproduced; full four-cell acceptance is incomplete.** The one corrected batch start returned HTTP 503 `runtime_unavailable` after **260.007 seconds**. Last separate readonly observation of its own database was three cells `completed`, Midea annual cell `dispatching`. The whole start's final effect is **UNKNOWN_NO_REPLAY**; that observation is not a final matrix. No operation was re-sent.

Root-owned issue pointers: `app/demo/process.py:217-218` creates the shared upstream client with a 260-second read timeout; `app/batch_research/service.py:163-215` awaits the complete serial matrix before responding; `app/demo/gateway.py:207-209` treats upstream HTTP errors as runtime failure and marks the slot degraded via `app/demo/controller.py:233-236`. The exact 260.007-second response supports a timeout interaction. This run did not independently capture the internal exception type, so the timeout attribution is an inference from measured timing and these code paths, not a captured stack trace. A final public matrix GET was not performed before harness cleanup; degraded recovery rejection is code-read, not an observed endpoint assertion.

A bounded asynchronous start that durably returns a batch ID and leaves GET read-only, or another explicitly bounded execution design compatible with the gateway deadline, needs root implementation review. Increasing/evading the deadline in this worker would not establish acceptance of the current public gateway. No business files were changed.

## Method and boundaries

The script launches a fresh loopback Uvicorn controller in an owned OS process group, with a new temporary control directory and randomly generated per-run login account/password hash. A minimal environment enables C+, sets `DEMO_CHILD_MODE=real`, offline cached BGE, real Milvus, and `LLM_MODEL=disabled-no-calls`. The generated dummy model endpoint is loopback port 9. There is no inherited root login configuration, dotenv, provider allowance, paid model client activity, root active-runtime access, browser cookie, or owner financial authorization.

The actual public controller login → readiness → claim protocol starts its own real OS child. All business calls traverse a real `httpx.Client` socket connection, controller gateway, private child boundary, actual root assembly, and original guard/commit hooks. There is no TestClient/ASGI marker fixture, mock HTTP route, fake embedding, fake vector store, or null publication guard. The controller owns its child birth/PID/process-group identity and readiness validation.

Public immutable seed: `showcase-cplus-seed-v3`, manifest `d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d`. The controller materializes it to its never-before-existing generation directory. The script verifies the seed before and after; neither readonly seed nor root's port 14540 session is mutated. Login secrets/cookies/internal secrets are never included in result files or logs.

## Harness protocol and stage reached

1. Login once, wait on the original login operation's GET, claim the ready runtime, read companies/documents/metadata and the four exact source refs through real HTTP. The fifth READY document is outside this selected batch.
2. Bind Gree and Midea 2024/2025 explicitly; verify downloaded HTTP PDF bytes against each source `content_sha256`, retaining full source_revision/parser/attempt/year/basis identity.
3. Explicitly POST one FTS build over the four selected refs.
4. POST a four-cell plan with `preparation_confirmed=true`: two companies × `risk_excerpt` / `annual_changes`, each cell bound to its company's exact two annual sources. Four distinct child operation UUIDs are allocated in the stored plan.
5. Verify no child operation exists after planning, child retrieval/annual stores are unchanged by preparation, and plan GET leaves all measured domain state unchanged.
6. Explicitly approve the stored plan ID/revision/hash once with `confirmed=true`, then POST start once. No mutating request is retried or replayed.
7. **Not reached after start failed.** Intended check: GET the resulting matrix twice. Compare both matrices and complete row-count/content fingerprints of operations, result objects, immutable snapshots, batches and cells in the three owned domain databases before/after GET. This is actual persisted no-dispatch evidence, not inference from HTTP 200 or source inspection.
8. **Not reached.** Intended check: verify every completed child result binds the saved operation UUID. For each quote, require exact selected SourceRef membership, a current source snapshot, correct physical page/evidence ID, canonical evidence digest, and the complete quoted text as an exact substring of that original source record. Downloaded HTTP PDF SHA and page bounds independently bind it to the actual PDF. Raw page-text and whitespace-only page matching are separately recorded, never substituted for source-record exact verification.
9. **Not reached.** Intended check: for each annual cell, inspect all three default topics (经营风险、主要业务、研发) and both 2024/2025 sides. Retain missing/insufficient/unknown/partial states as returned; neither completed dispatch nor API success means semantic answer acceptance.
10. **Question probes not reached.** The fixed-24 inventory is supplemented with actual source availability and the failed batch tier; the exact Midea E01-02/E01-09 provider-disabled excerpt-tool probes remain not completed. E01-03's preceding-turn/pronoun model behavior is not simulated by a standalone query.

`basis=unknown` on Midea 2024 is explicitly retained. Annual text comparisons do not establish comparable financial accounting inputs, ratios, financial approval, causes, or investment conclusions.

## Result receipts

The failed execution and prepared plan are recorded in `docs/cplus/eval/results/batch-v3-corrected/result.json`, including the complete plan, explicit start approval, 260.007-second error receipt, source/PDF hashes, child identities, last live readonly observation, fixed-24 gaps, and cleanup. No final matrix or per-cell payload/quote verification is claimed. Plan GET no-dispatch was actually asserted; final matrix GET no-dispatch was not reached. Full answer model PASS remains zero; this is a serial pure-tool matrix, not paid or multi-agent research.

The first startup is separately retained in `results/batch-v3/`: preflight found the harness expected an annual payload field `annual_diff_id` while the actual contract is `result_id`. The script was interrupted **before any batch plan/start** (only its login request had been sent), its owned controller/child groups were proven exited, and its scratch directory was removed. That startup is `HARNESS_STOPPED_BEFORE_BATCH_REQUESTS`, not an application failure or batch retry. Its exact script snapshot hash is retained. The corrected run starts a separate controller/account/runtime and never replaces the first receipt.

No additional failure/UNKNOWN injection or wider boundary sweep is required if the four actual results satisfy the intended tool and bilateral evidence checks. Existing failed/UNKNOWN root provider receipts are untouched and are not reclassified by this run.

## Reproduce

Use a new empty result directory whose name starts with `batch`; existing results are refused:

```sh
PYTHONPATH=. .venv/bin/python experiments/cplus/verify_real_batch.py \
  --seed /absolute/path/to/readonly/showcase-cplus-seed-v3 \
  --output docs/cplus/eval/results/batch-new-owned-run
```

The script creates its own login configuration in memory and an independent loopback port. It does not accept root login configuration, provider configuration, or an allowance path. It closes only its Popen-owned controller and birth-bound child groups, checks the seed again, and removes its own scratch directory after process exit is proven.

`fixed24-supplement.json` retains all 24 exact questions and required tiers. Prior v1 evidence is labelled separately. Added Midea 2024 text availability closes a missing-fixture prerequisite, while real-model planning, clarification/refusal, causal explanation, paired-agent comparison, partial-failure recovery, browser acceptance and human financial axes retain their actual unverified status.


## Retained artifacts and final checks

- `results/batch-v3/result.json`: stopped preflight-startup receipt; only login sent, no plan/start. Owned controller PID 50389 and child group 50391 exited; scratch removed.
- `results/batch-v3-corrected/result.json`: original corrected execution on loopback port 60203 (see receipt for authoritative origin), plan `770c8a3d-b544-4fd5-b10f-f21c9452e652`, four fixed distinct child operation IDs, HTTP 503 at 260.007 seconds, UNKNOWN effect and cleanup.
- `results/batch-v3-corrected/fixed24-supplement.json`: 24 exact questions/tiers, no complete model answer PASS; E01-02/E01-09 source prerequisites now present but probes not completed; CP-19/21 explicitly not accepted.
- Both run directories retain exact executed-script snapshots matching their receipt hashes. Final evaluator corrects the id-field bug and, for future failures, captures available owned SQLite cell/result snapshots plus a bounded readonly matrix recovery attempt before cleanup. Those added failure-capture steps were not executed retroactively; the original failed runtime was already removed, and no result reconstruction is fabricated.

The corrected run's controller and child group are proven exited, owned scratch removed, and V3 seed unchanged. Its business baseline is untouched. Ruff, Python compilation, receipt/hash consistency, 24-case identity preservation, and code ownership checks pass. Provider/model calls and human financial approvals remain zero. This is an actual local public-gateway batch timeout, not a provider ReadTimeout or a paid MultiAgent result. The next full four-cell check requires a root-owned bounded-start/gateway fix; the original start must not be replayed.
