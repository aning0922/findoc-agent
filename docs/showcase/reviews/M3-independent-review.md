# M3 independent backend review — 2026-11-03

## Decision and evidence scope

No demonstrated P0/P1 blocker in the current isolated, per-generation demo main path in this bounded review. This is not production SaaS authorization approval, real-provider acceptance, financial sign-off, or release approval. Three P2 follow-ups below remain open.

Reviewer independently read backend implementation (did not implement it). Review branch `codex/showcase-m3-review` starts at `6bcb386`; source of truth was the **current files** in `/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent`, not this review branch's older backend. Integration HEAD observed at final checks: `17e82bb85cb3bbc3c07172c6d729acdb4b9c3643`. Read all Python files under `app/showcase_research/` and `app/showcase_reports/`, relevant runtime assembly in `app/api/runtime_factory.py`, `app/demo/provider_budget.py`, `app/demo/policy.py`, and memory guard implementation/tests.

The reviewed uncommitted `agents.py` accepts up to three native function calls, validates role names before execution, executes sequentially through the same tool gate, and discards accompanying prose. Its SHA256 was `0c1247e2de33aebe467ca07894b1018b902658a4d6f316d45e208a5eeb7b503f`. Other anchor hashes: `jobs.py` `39cc468d097fdcf9fa2d35e953dc8f00a40a27666a89b11aed741050fce5e44e`; report `service.py` `babb28eec45900279320d4766bdfd26a94341e6e21231c2797d1ea4644218a76`; `runtime_factory.py` `4c81302503fe423afe2bc3e52f682933886d19cb67542065b3e1a320adadb0ac`; `provider_budget.py` `d9d1c4fd58c8a025b5187363ecbf93274ddb91a90f95deed2c169b9c2bcc69fe`. Later edits require their own review.

## Confirmed controls

- **Scope and authority:** `Scopes.freeze` obtains source identities, conversation, selected fact references, memory generation, and trusted runtime identity server-side. Strict requests do not accept these authority fields from clients. Intent proposals must match goal, selected companies, periods and allowed mode. Plan roles are selected by code; model suggestions cannot change them. Job requires explicit confirmation of stored revision/hash and a plan executes at most once. Tools expose no confirm/save/resume capability. Handoff creates the old task only on explicit request; it does not sign or resume it.
- **Exact evidence:** `Findings.quote` checks selected document, workspace, source revision, physical page, and an exact nonempty excerpt with one matching parsed record. Reference includes content hash and parser version. Revalidation checks the exact evidence ID, excerpt, page and pinned source identity; final publication rechecks sources inside attached rollback-journal transaction. PDF links retain revision. Retrieval chunk identity alone is not treated as evidence proof.
- **Financial truth:** model drafts cannot submit financial references. Confirmed findings come from explicitly selected `local_operator` facts, deterministic amount rendering and financial admission, with another persisted-fact check in final publication. Numeric model text remains `model_interpretation` / `ai_unreviewed` / `numeric_claim_unverified`; it is not converted into confirmed finance. Offline tests used no real receipts.
- **Report reader assembly:** runtime factory lines 446–462 install a failing default reader and a request-bound reader derived from private gateway identity; that reader calls `verified_job`, including scope, completion, references, financial and memory checks. Browser-supplied findings are forbidden. Read/print do not call a model. Historical-content authorization caveat is recorded below.
- **Memory to research COMMIT:** `Scopes.publication` enters the memory publication guard before the source/research transaction and exits it after `ResearchStore.tx` commits. Real memory guard holds a rollback-journal SHARED lock and checks generation and recalled revisions; unsupported WAL fails closed. Final research result cannot commit against a deletion already committed before guard acquisition. Concurrent deletion waits until the protected publication completes. Tests cover generation changes during merge, guard lifetime through research COMMIT, actual memory deletion serialization, and late embedding/query deletion races.
- **UNKNOWN and budgets:** research operation reservation and provider/tool attempt counters commit before execution; timeout is not refunded or automatically replayed. SDK has retry zero and bounded output. The separate CNY ledger reserves before physical SDK call, survives restart, retains unknown/missing-usage reservations, cannot silently change allowance, and remains outside reset generations when configured through the factory. Call count/token budget is separate from CNY cost. The 5 CNY guard is **conditional on `FINDOC_PROVIDER_BUDGET_DB` configuration**, not an unconditional property of every runtime launch. No environment/real ledger was read here, so actual launch configuration, nine-call count, account billing and current vendor tariff were not independently verified. Root's real-provider updates are reports from the controller, not evidence produced by this review.
- **Gateway mutation inventory:** research/report write routes are explicit native-operation entries; financial confirmations/revocations and old task resume retain owner requirements. Allowlisting does not itself confer financial authority.

## Open P2 findings / limits

### P2: distinguish report authorization denial from historical source unavailability

`app/showcase_reports/service.py:202–218` catches every reader exception and returns the saved snapshot with `current_source_status=unavailable`. Reproduced using a temporary fixture report and a reader raising `ReportError('job_scope_invalid', 403)`: full historical findings were returned. The factory validates current request identity before invoking revision, but a denial raised inside `verified_job` is still swallowed. List and operation lookup also return historical payloads without that per-job reader.

Under the present private child/per-generation storage model and fixed demo principal, this review did **not** establish a reachable cross-instance/user disclosure; therefore P2 in this task scope, not a claimed production exploit. Minimum fix if the adapter's access-denial contract must be enforced: propagate authorization/lease/runtime-scope errors, and downgrade only source/history invalidation errors to historical unavailable. Keep access checking separate from freshness checking; apply it to other snapshot-returning endpoints if they gain distinct principals. Add a denied-reader route test. No broad SaaS refactor required.

### P2: report draft commit is outside the research memory publication guard

`ShowcaseReportService.draft` awaits `verified_job` at line 93, then persists a draft in a separate database transaction at lines 94–100. `verified_job` has already exited its memory guard. An independent writer can commit a memory deletion between verification and report draft COMMIT. Report `save` intentionally copies an existing historical snapshot without revalidating it. This is a static concurrency boundary observation; a delete-between-report-transactions race was not executed here. It does not negate the verified guard around **research result** COMMIT.

If the deletion guarantee also covers creation of new report snapshots, carry an appropriate publication guard through report insertion, or add a guarded report publication callback. Otherwise explicitly describe report saves as preserving historical snapshots; do not claim a report-DB COMMIT is covered by the research guard. Keep this high-concurrency follow-up out of the current narrow main-path repair.

### P2: repeated finance reads can duplicate confirmed findings and interrupt publication

Latest compatibility change legitimately permits multiple calls. Each `read_confirmed_facts` appends its full results; `jobs.py:103–106` compares the resulting confirmed-financial list against one fresh deterministic read. Two successful reads of the same selected facts therefore produce duplicate actual entries and `financial_rendering_changed`. This follows directly from code; no genuine confirmed receipt or live-provider reproduction was performed. It fails closed rather than publishing wrong amounts.

Minimum follow-up: normalize/deduplicate confirmed results by full stable financial reference plus deterministic text before comparison/publication, or reuse one verified read per step. Do not relax financial reference/value equality. A synthetic admitted-fact double-read test should accompany that narrow fix.

## Offline checks actually executed

Initial `python3 -m pytest ...` could not collect because the default interpreter had no pytest. Used existing offline uv package cache to create `/tmp/findoc-m3-independent-env`; no dependency download or real runtime creation. Command from the integration working tree:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/findoc-m3-independent-env uv run --offline --only-group checks python -m pytest tests/test_showcase_research.py tests/test_showcase_jobs.py tests/test_showcase_reports.py tests/test_provider_budget.py tests/test_research_memory.py -q -p no:cacheprovider
```

Result: **19 passed, 5 dependency deprecation warnings, 17.58s**. These are UNIT_FAKE provider/vector and temporary synthetic-source/SQLite tests, not fresh real-model or real financial business acceptance.

Additional independent inline probes (temporary directories only) subclassed `NativeFake` to duplicate calls: two calls per deep agent completed with four total tool reservations; four calls per agent yielded partial with zero tool reservations; accompanying prose never appeared in findings. The denied-reader probe above reproduced historical snapshot return with unavailable status. No probe wrote production data, called an external model, read `.env`, or created real financial signatures. No backend source or test file was edited by this reviewer. Only this document is committed.

Root's reported real intent/plan success, provider protocol diagnostics and subsequent full-chain rerun remain controller-owned evidence. Neither seeded history nor these fake tests count as a new real-provider run.
