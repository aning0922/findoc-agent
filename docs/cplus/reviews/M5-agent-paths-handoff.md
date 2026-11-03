# M5: operator-run original C synthesis/deep harness

Baseline audited: **`e510876`**. Delivery tier: **CODE_REVIEW + CONTROLLED_HTTP_MOCK_PROTOCOL_ONLY**, **11 fixture checks pass**. This worker made **zero real provider/SDK calls, zero real socket requests, zero private login/LLM configuration or original budget-ledger reads**, and did not connect to 14540 or 14542. Preparation/fixture completion is not real LLM acceptance.

Owned changes: new `experiments/cplus/verify_real_agent_paths.py`, its isolated fixture tests, `docs/cplus/eval/results/agent-paths-fixture/*`, and this handoff. No original C business contract, provider client, runtime_factory, AppShell, batch service/API or root async-ACK tests were changed. No leaf repair was needed to prepare these paths.

## Current API wiring supports this demonstration

The script follows actual source contracts:

| Stage | Actual route and body |
| --- | --- |
| Dedicated login / fixed lease | `/demo/login` → GET original `/demo/operations/{id}` → `/demo/claim` |
| Exact Gree 2025 scope | GET companies/documents/metadata, `/cplus/documents/{id}/research-source`, SHA-checked original PDF |
| New frozen conversation | POST `/conversations` `{operation_id,document_ids,title}`; compare every Identity field and source_scope_sha |
| LLM intent | POST `/research/intent` `{operation_id,conversation_id,text,requested_mode}` |
| Supervisor plan | POST `/synthesis/plans` `{operation_id,intent_id}` |
| Explicit bounded approval | Persist checked plan ID/revision/hash/roles, then POST `/deep-research/jobs` or `/synthesis/jobs` with `{operation_id,approved_plan_id,approved_plan_revision,approved_plan_sha256,confirmed:true}` |
| Async execution / original stages | 202 queued ACK, GET original job until terminal, GET `.../{job_id}/events?after_seq=...` |
| Exact citations | GET `/documents/{id}/evidence/{evidence_id}` with original source_revision/company_id; compare identity, complete exact quote and physical page against the SHA-checked PDF bounds |
| Verified report | POST `/showcase-reports/drafts` `{operation_id,job_id}`, then POST `/showcase-reports` `{operation_id,draft_id,title,notes}`, then GET its exact revision |

`/research/handoffs` is the legacy task adapter and is deliberately absent from the script's write allowlist. The requested deep handoff is the actual `ResearchJobs` supervisor → two `AgentRunner` roles → verifier/controller flow, evidenced by role steps, native tool traces and phase events. It does not create or resume a financial task. No conversation turn POST is needed: the exact fixed question goes in IntentRequest, avoiding an additional legacy quick-model execution.

For the chosen risk question, expected deep roles are **`evidence` and `risk_operations`**, with maximum parallelism two. Single synthesis expects **`generalist`**. Intent must be `model_proposal_program_validated`, plan must be `supervisor_model_program_validated`, and both provider_error fields must be null. A finite fallback with HTTP 200 is retained and stops the next model phase rather than being counted as LLM success.

## Fixed cases and explicit 12-call admission

Default order is **E01-06 deep first**, then **E01-01 synthesis**, using their exact unchanged questions from `fixed-cases.json`. Both freeze one explicitly selected Gree 2025 document; a missing or ambiguous company/report is an error, with no latest-source fallback. Each mode gets its own conversation/intent/approved plan/job. These are different questions, so the result is not E01-15's paired same-question comparison and makes no claim that multiple agents outperform one.

Current server logical caps include intent and plan: deep ten model attempts, synthesis five. Each of intent and plan is a single no-retry provider attempt. Before starting a mode, the harness conservatively requires its **entire** cap as remaining physical guard-row headroom. Before starting its job it requires cap minus the two validated intent/plan calls. This uses the actual advertised server caps, not an optimistic assumption about the number of agent iterations.

A typical successful deep path uses 7 calls (intent + plan + two tool/draft role pairs + merge), followed by a typical synthesis path using 4, total 11. These are expected protocol counts, not observations of a real run by this worker. If deep consumes more than seven, fewer than five remain under `--max-new-calls 12`; the script stops **before any synthesis intent**. Thus both paths are not guaranteed to complete in every 12-call window. It does not increase the limit, retry, trim history silently, change server budgets, or invent a successful pair.

The main CLI admits only an existing canonical same-repository 5-CNY ledger via `existing_shared_budget`. Its reader uses SQLite `mode=ro`; it never creates, migrates, copies, chmods, replenishes, reserves or refunds an allowance. The existing deployed guarded SDK remains the only writer. New UNKNOWN/unsettled guard rows stop subsequent writes; baseline UNKNOWN rows do not get replayed/refunded. Missing historical rows fail closed as a reset/replacement. Cap is explicit 1..12; no new task starts without conservative headroom.

The root should run this as an exclusive provider window. Existing ledger rows have no run-id attribution; other concurrent jobs or late usage changes are recorded as denominator/read-only mismatches and stop further task starts. The client cannot prevent another process from spending the shared allowance. It can bound its own admitted server paths and refuse subsequent starts, while the existing server CNY guard remains authoritative.

## Counters, UNKNOWN and report evidence

The receipt separates:

- Existing ledger **new guarded SDK reservation/attempt rows**, including their states and reported tokens. This is the physical-attempt denominator used by this deployment; it is not an account bill or answer-acceptance count.
- `job.usage.attempts`: the original C logical model-attempt denominator, including intent/plan and role/merge calls. Tool reservations are separate; `provider_tokens_actual` is not silently fabricated.
- Per-case logical minus physical row counts, pre/post window snapshots, existing UNKNOWN state changes, model-interpretation count and exact quote receipts.
- Job/events/source reads and report draft/save/revision reads must append **zero** model guard rows after terminal completion.

Every mutating request gets one UUID and a durable intent written before send. Transport failure, HTTP error, invalid result, fallback, partial/interrupted job, new UNKNOWN or exhausted headroom stops the run. At most one read-only operation reconciliation is attempted after an uncertain POST. Even a recovered completed operation or a GET 404 never automatically resumes writes, repeats the POST, allocates a replacement run, or launches the next mode. Existing output directories are refused. Login takeover, owner authorization, financial accept/save/confirm and task resume routes are absent from the allowlist. Saving the specifically requested verified **report** uses only `/showcase-reports`; it grants no financial authority.

A completed path verifies job mode/plan/scope, completed role agents, required `search_evidence` traces, controller/supervisor/roles/verifier events, exact HTTP source evidence and unchanged report finding IDs/text/refs. Unexpected confirmed_financial findings fail closed because these fresh conversations select no financial facts. Report creation is attempted only for completed verified jobs. Partial/failed jobs and their original events remain in the receipt without a report or subsequent mode. Model interpretations and unresolved questions remain visible; neither path completion nor HTTP 200 establishes human semantic completeness, relevance, financial approval, or accuracy.

## Operator command

Run only from the full project venv against the root's deliberately selected isolated real-provider origin:

```sh
PYTHONPATH=. .venv/bin/python experiments/cplus/verify_real_agent_paths.py \
  --origin http://127.0.0.1:OWNED_PORT \
  --login-config /ABSOLUTE/PATH/TO/DEDICATED-DEMO-LOGIN.env \
  --existing-budget-db /ABSOLUTE/CANONICAL/REPO/data/showcase-cost-control/provider-budget.db \
  --output docs/cplus/eval/results/agent-paths-NEW-OPERATOR-RUN \
  --max-new-calls 12
```

The selected controller slot must be available. A `ready` status can also describe an existing active lease; if the root already holds that lease, the root must deliberately manage it before this fresh-login command. HTTP 409 stops this script; it never takes over or resets another session.

The login file must contain **only** nonempty `DEMO_USERNAME` and `DEMO_PASSWORD`. The script does not accept owner or LLM settings from it and never persists the login body, password hash, raw cookie or authorization header. Use an exact loopback origin without a path; port placeholders above are not literal executable values. The runner records its own checkout HEAD and audited source-contract hashes; the operator must ensure the target child serves the intended candidate, since this API does not expose a verified server commit SHA.

Optional `--only-mode deep` / `--only-mode synthesis` selects one mode; it is an explicit operator choice for a fresh run, not automatic recovery/replacement of an UNKNOWN. The script leaves the selected lease to the root's lifecycle management rather than logging out/resetting and deleting the just-verified report generation. Credentials/cookies are not exported for browser reuse. Root owns subsequent cleanup and any browser demonstration.

## Controlled verification actually performed

`tests/test_cplus_real_agent_paths_script.py`: **11 passed**, five existing SWIG warnings. All HTTP uses `httpx.MockTransport`; guard rows and model responses are synthetic. It validates actual request DTOs from the audited modules, explicit approval bodies, default deep→synthesis sequence, two role/phase/tool records, exact quote/report handling and 7+4 **simulated** row reconciliation. It also checks intent timeout with GET 200/404, lost job ACK with completed operation recovery, low headroom before second mode, partial terminal jobs, readonly temporary-fixture SQLite access (including no creation of a missing file), and rejection of four prohibited financial/legacy-handoff mutations.

Five representative receipts and a summary are in `results/agent-paths-fixture/`. Their simulated SDK rows and phase/model text are explicitly labelled; `actual_provider_calls=0`, actual socket requests=0, and private configuration/ledger reads=0. Ruff, Python compilation and CLI help pass. The operator has not yet run this harness against a real LLM as part of this worker's evidence. No paid diagnostic, deployment, original C contract change or root-hotspot edit was performed.
