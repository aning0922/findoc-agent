# Final independent integration review — 2026-11-03

## Decision and immutable scope

No demonstrated P0/P1 blocker in the inspected root-owned intersections of the isolated job-seeking candidate. This is a bounded source review plus offline checks, not production SaaS approval or complete end-to-end acceptance. P2 limits and evidence gaps below remain open.

Exact reviewed commit: **`9f4993cf3463fa0d3c4520799435f3bf45eefeac`**. Review branch `codex/showcase-final-review` was created directly from that commit; this review did not follow moving integration files. Workspace `/Users/aipuli/.codex/worktrees/3f05/findoc-agent`. Only this document is changed. Reviewer focused on root integration, not a repeat acceptance of the leaf UI previously authored in this chat. Later root UI/recording repairs are outside this exact review.

## Root intersections inspected

1. **Single runtime assembly.** `runtime_factory.py` constructs one research service, report service, archive service and dashboard service in the runtime construction path. Dashboard receives those same instances. Archive shares the fixed source service and parse service; research shares conversation, source, task and memory objects. Report default reader fails; request-bound reader derives private identity and calls `verified_job`. The child makes one `create_runtime_app(root, ...)` call with generation/seed metadata. An AST check confirmed one construction site per named integrated service; this is not proof of arbitrary multi-process concurrency behavior.
2. **Dashboard historical/live counts and labels.** `overview_enriched` adds independent job states and showcase reports to legacy counts. Persisted job results must equal the immutable research record before display. Archived report revisions are deduplicated by original report ID for the KPI; seeded jobs carry `origin=preset_demo` and current source review status. Dynamic jobs remain local-runtime historical records with source recheck required. A completed KPI is explicitly historical completion, not current source/financial approval or a new model run. Archived jobs are imported only from eligible completed results; archive creation rejects financial grants. Bounded count and ordering issues are recorded as P2 below.
3. **Archive print projection and old leases.** The new print endpoint uses `deepcopy(item['snapshot'])`, relabels only that presentation copy's snapshot/findings as seed, adds current source status and preset title, then invokes the existing escaped renderer. It neither writes the archive nor calls execution services. Archive reads use current source/reference checks and expose false execution capabilities; preserved old scope/lease is provenance, never an execution credential. The public gateway captures/fences the current session before forwarding and before delivery, including GET/print; private child requires loopback+secret+generation+instance. The archive router alone is not an authentication layer. Fake route probe verified immutable original object, preset labeling, stale banner, HTML escaping and POST 405; gateway boundary tests separately verify stale delivery fencing. No claim that a fake print response is an actual exported PDF.
4. **Conversation entry deep links.** `entryResearch` captures original conversation/job/research_mode before `showConversation` normalizes the URL. Only the matching conversation retains these parameters and receives the initial mode/job props. History traversal remounts the keyed AppShell; switching conversations does not transfer the original job into another scope. `initialJobId` is UUID-checked, fetched by GET and checked against job ID/CID/mode; the effect does not plan, approve or resume. Source review only in this turn; full Chromium deep-link acceptance is not claimed here.
5. **Launcher/private config/5 CNY ledger.** Login config remains in the integration checkout. Optional provider config may come from a sibling worktree only when Git common-directory identity matches; ambient GIT overrides are stripped from discovery. Config must be ignored, regular, non-symlink, one-link, mode 0600; dotenv interpolation is disabled. Provider host/model/path are restricted. Both process environments use a positive host allowlist, with provider values supplied only to backend; Vite receives `FINDOC_E2E_DISABLE_ENV_FILES=1`, and its config sets envDir false. Child inherits backend's budget configuration while removing DEMO credentials. Launcher requires an existing fixed `data/showcase-cost-control/provider-budget.db` with cap 5, outside generation/control trees; it does not create a replacement allowance. SDK guard persists reservations before calls, disables retries and retains unknown usage. Tests used fabricated private config in temporary Git repos, never the user's `.env`. Actual active environment, real shared-ledger balance, provider prices and account billing were not read or independently verified.

## Checks actually performed

All commands ran against the exact reviewed checkout with `/tmp/findoc-m3-independent-env/bin/python`, no paid provider, real development DB, human financial receipt or real seed launch.

```sh
python -m pytest tests/test_showcase_local_launcher.py tests/test_showcase_seed.py tests/test_provider_budget.py tests/test_runtime_startup.py -q -p no:cacheprovider
# 15 passed, 5 dependency deprecation warnings, 3.07s
python -m pytest tests/test_demo_gateway.py tests/test_demo_auth.py tests/test_dashboard.py::test_empty_missing_storage_and_isolated_samples -q -p no:cacheprovider
# 8 passed, 5 dependency deprecation warnings, 1.32s
```

The 23 passes cover temporary same-Git sibling config acceptance/unrelated repository rejection; private-file controls, frontend environment isolation; existing allowance/UNKNOWN behavior; synthetic archive materialization/current-stale-unavailable preservation and no financial grants; isolated startup rejection; fake gateway ownership/lease/late PDF/SSE fencing; empty-dashboard and illustrative chart separation. They do not exercise a true BGE/Milvus production runtime or real LLM.

Three additional inline probes used temporary/fake data only: (a) route print projects fake original data labeled live into seed HTML without mutating the returned original object, preserves stale status, escapes script text and rejects POST; (b) `overview_enriched` with one fake archived job and two revisions of one fake report produces research=1/report=1 and preset/stale metadata; (c) static AST counts one construction site per integrated service. No test files or backend files were added. `git diff --check` passed.

## Open P2 and limits

- **Dashboard total truncation:** `overview_enriched` uses archive `list` (default limit 20) and report `list` (limit 100) to compute KPIs. Many revisions can consume the archive window before distinct original reports are counted. Reproduction condition: more than those limits, or >20 versions spanning reports. Counts will understate inventory; in the stated 2-job/2-report seed this does not trigger. Minimal fix when scale matters: separate count queries over unique IDs; retain capped detail lists.
- **Legacy recent ordering:** legacy entries from `overview()` lack `saved_at`; enrichment sorts missing dates as an empty string, so any five timestamped v2/archive entries can displace a newer legacy task. This affects recent navigation, not financial authority. Minimal fix: supply the legacy persisted creation/update timestamp before the merged sort, preserving the original status.
- **Broad regression remains incomplete:** controller reports `141 PASS + 57 ERROR` caused by absent `product/validation/d21-real-research.json`. That run was not reproduced here, and no replacement fixture was synthesized. Tests depending on the imported legacy `saved` fixture were deliberately not used as evidence of passing. This remains unverified regression coverage, not a full-suite PASS or demonstrated new business regression.
- **Prior M3 P2 remain open:** authorization-denial versus historical-report-unavailability handling, report draft COMMIT outside the research memory guard, and repeated finance-read deduplication were previously documented. This final scope does not close them. Production SaaS, high concurrency, performance, actual billing and real financial approval remain outside this candidate review.

## Evidence tiers and controller reports

`docs/showcase/EVIDENCE.md` at the reviewed commit distinguishes fake/UI/real stages and retains the `ybr4pane` overall runner failure after its completed research phase; its in-process seed-material completion is explicitly not external HTTP UI proof. The committed record reports real single/multiple-agent runs and five-page PDF output, while maintaining zero human financial confirmation and `actual_billed_cny=not_observed`. Reading that record does not reproduce the runs.

The controller additionally reported full-seed prefix `efc10a4...`, two independent Chromium/HTTP reset run `ouunry1_` (2 companies/3 READY docs/2 research/2 reports/2 notes/1 conversation, dirty additions removed, old lease 401/UI unmounted, unchanged seed), archive/PDF/print/OCR GET-only run `k0nw23vk`, completed live single/multiple research, and old task reaching `awaiting_human_confirmation`. These exact latest artifacts and their full hashes were **not inspected in this review**. They are controller-reported evidence, not new independent real-model, reset, PDF or human-approval evidence. The prefix alone is not a verified full seed SHA. Root's final corrected UI/recording rerun was still pending in the request and must be recorded separately.

## SHA256 file fingerprints at the reviewed commit

| File | SHA256 |
|---|---|
| `app/api/runtime_factory.py` | `3bd1873db40d931aef46c7f889547b006e1bc2ac1947504d1843260c3d7be290` |
| `app/dashboard/service.py` | `9e1f7104dbac1b397046a71e9a95ec445a436f66452f3a6fefc4fea86428044c` |
| `app/showcase_seed/api.py` | `98b094a5d8a2be6d92a8276df522e6e98183cc5615f33861a9aeae01b391d91f` |
| `app/showcase_seed/archive.py` | `6f0d1d3a933d529da48b0f47f81246783b461cadb4d5b6a6b3524f6c8427821c` |
| `scripts/run_showcase_local.py` | `47ffe8aea3ad6e2d27b528299507c44f6a4c3b05b8b98dcb24acf0c9fa2fa13c` |
| `frontend/vite.config.ts` | `829d67bd477724e2755d2b046780b6f32f7dd7e3c74499afef818171645671d7` |
| `frontend/src/product/Conversations.tsx` | `685df8b263fe78243e1737696a4319cd314c4f867ba65e863f676d031520dbab` |
| `frontend/src/product/FinancialProduct.tsx` | `4088076c201976dcc5086fb2a45de46d25f35a6c28c87215de2d58b5457dab7c` |
| `app/demo/process.py` | `d70ef7e2d87ea2e103a9834c6711eb7356bbc0e7b0967a4af2326d1d656c6fec` |
| `app/demo/gateway.py` | `f97fe493e82ff7c6fd9f8f51dd21a62a1378ece9ab49d929dcde826377642946` |
| `app/demo/child.py` | `d82077fa55b95dd26af91e2da29d5545f37099f8abbb8df04a58a22af99f35f3` |
| `docs/showcase/EVIDENCE.md` | `1aa93f2e7dfb4a1bf172a20615f136a1344f85c9efa26f084205a2f7c7875720` |
