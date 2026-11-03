# M5 R04/G03 evaluation handoff

Business baseline: `fcefb125c7d167e6752301580748e1ec4fd3d752`. Date: 2026-11-03, Asia/Taipei. Scope is the owned evaluator, `docs/cplus/eval/results/*`, and this handoff; no business/backend/UI changes.

## Evidence boundary

`experiments/cplus/evaluate_retrieval.py` verifies the immutable public seed, materializes a new temporary runtime, and uses actual `create_runtime_app` with C+ enabled, actual cached offline BAAI/bge-m3, real Milvus Lite, and root's actual publication guard/commit hooks. The searches use the root HTTP routers through FastAPI TestClient. A test-only private-marker middleware binds the fixed evaluation headers; this is an in-process HTTP assembly test, not an actual gateway login or signed-in browser test. No null publication guard, fake embedding, mocked vector store, or private active runtime is used.

Provider model is `disabled-no-calls`; provider budget/config names are removed without inspecting their values. The SDK dummy base URL is loopback port 9. No dotenv, password, root login configuration, private allowance ledger, or original developer database is opened. All writes belong to the new disposable copy and owned result files. No human financial confirmation is performed.

M0 did not record a BGE weight revision/hash, so exact historical weight identity cannot be proven retrospectively. Current dense recheck nevertheless reproduces the original chunk order and cosine values exactly for all six frozen queries. The original PDF content SHA, source_revision, source identity fields, and selection scope hash are compared for exact equality and must match before each query.

## Six exact queries

The runner reads query bytes and source scope from `docs/cplus/evidence/M0-retrieval-before.json`; no substitute wording is used. Each HTTP search asks for top_k=5. Root's unchanged algorithm internally considers up to 20 lexical/dense candidates before returning at most five; those internal candidates are not represented as top5 results.

All page numbers below are physical PDF pages in the same Gree 2025 PDF, SHA `7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c`, source_revision `9ccf4adc9c76fc6d4fc9f81dee755b1f8b723726502ebc6a62616f1aea1f3395`, scope hash `eacf6c068e9edf5ca229b746e0f4257f48c88951408a468e673d034a702edc60`.

| Case | Exact M0 query | M0 stored dense pages | Current hybrid pages |
| --- | --- | --- | --- |
| risk-general | 2025年报主要经营风险有哪些 | 38, 98, 196, 39, 205 | 38, 39, 98, 121, 27 |
| risk-material | 年报中如何描述原材料价格波动风险 | 195, 39, 196, 98, 35 | 39, 38, 121, 10, 27 |
| risk-competition | 公司面临的市场竞争风险 | 180, 185, 150, 150, 199 | 38, 39, 27, 27, 37 |
| risk-overseas | 海外市场与汇率波动风险 | 35, 196, 39, 195, 35 | 39, 38, 121, 27, 27 |
| business | 公司主要业务和主要产品 | 10, 12, 11, 14, 24 | 10, 21, 20, 23, 124 |
| cashflow | 摘录经营活动产生的现金流量净额原文 | 7, 7 | 7, 7, 10, 126, 104 |

Current dense recheck matches all six original chunk orders with maximum cosine difference **0.0**. Current hybrid's **30/30 returned source excerpts pass an independent second call to the actual exact verifier**. This count measures source verification, not relevance, coverage, correctness of a generated answer, or human acceptance.

Applying the current C+ verifier to M0's 27 stored dense hits accepts 18 and does not admit 9: four fail current page/source gate checks and five competition-query records do not match a single current paragraph evidence record in their complete serialized form. These failures are retained per hit. They do not imply the historical PDF text was fabricated, nor are they silently dropped from the before side.

Every old and new hit has its physical page, complete text, snippet, identity and explicit score type in the JSON; `six-query-before-after.md` presents all top5 records with truncated snippets. `dense_cosine` is Milvus COSINE (nullable for lexical-only hits), `fusion_score` is rank-only RRF, and `rerank_score` adds the program's bounded topic/table heuristic. Neither latter score is cosine, a probability, or a quality metric.

## Relevance observations and historical failure

Agent-only observations: physical page 39 includes production-factor/material price, competition, overseas and currency risk disclosures; page 38 contains the start of the main-risk section after several operating-strategy paragraphs. The current risk queries put these pages early. Some lower-ranked results remain broad or tangential. The cashflow query's first page-7 hit contains administrative/shareholding material and the heading of the accounting-data section; its presence is not evidence that the requested cashflow excerpt is complete or the first hit is adequate. No human relevance labels, precision, MRR, answer accuracy, or user review are claimed; numerical metrics remain null.

The exact historical question currently returns physical pages **39, 38, 121, 27, 27**. Neither the old page-70 complete text nor the “委托理财” phrase is reproduced in current top5; this is explicitly **not reproduced**, not a claim the original failure did not happen.

The original historical wrong-class page-70 entrusted-finance table is preserved unchanged in `docs/cplus/evidence/M0-historical-risk-failure.json`. The evaluator also sends its exact original question, “请根据格力2025年报总结主要经营风险，只要原文与解释，不要计算。”, to current no-provider retrieval. This is a query diagnostic, not a rerun of the original real-model job. Its exact-text and entrusted-finance phrase reproduction flags are separately recorded; lack of a match must be reported as not reproduced, not as proof all operating-risk questions are fixed.

I additionally rendered and visually inspected original physical pages 38, 39 and 70 from the checksum-pinned public PDF; printed page numbers are 37, 38 and 69. This supports page identity and section/table identification, not human financial or semantic acceptance. The PNGs are temporary review aids at `/tmp/cplus-m5-pdf-review/`.

## Fixed 24 cases

`fixed24-execution-tiers.json` retains all 24 exact frozen questions, required tier, this worker's actual executions, separate previous-checkout evidence references/hashes, tool components available for verification, and remaining gaps. Its Markdown companion is a reviewable tier checklist. Previous root/worker artifacts are explicitly labelled read-only prior evidence and are never counted as new execution here.

Exact E01-01, E01-06 and E01-07 questions are probed through current root context/answer endpoints with provider disabled. Those probes establish only actual excerpt-tool behavior, fixed source identities, source verification and unverified financial authority. They do not execute their requested quick/deep/synthesis model modes, deep roles, or refusal semantics. HTTP 200 and intent are not full answer PASS.

Real Gree 2024/2025 collection returns **38 candidate cells per year**. Bilateral risk/business/R&D output labels all three topics `comparison_required`, with provider outcome `not_requested`. Candidate checkup returns `no_direction_divergence`, `direction_diverges`, and debt/asset change `0.178119` percentage points for its three program rules. These are actual program outputs, not human-confirmed financial conclusions. Candidate arithmetic/observations remain separate from confirmed input acceptance and model causal explanation. CP-18/20's human-confirmed axes stay human_pending; CP-19/21 and E01's real-model or paired-agent requirements remain unverified with generation disabled. CP-22 import/cache, CP-23 multiformat artifacts, and CP-24 complete real-browser flows are not re-executed by this retrieval suite.

Root's retained bounded diagnostic records `ReadTimeout` and UNKNOWN. This evaluation does not replay it, read its ledger, refund it, attribute all earlier HTTP failures to it, or stop ordinary retrieval work because of it. There is no real-model success claim in this run.

The public v1 inventory has Gree 2024/2025 and Midea 2025 READY plus a derived scan in legacy FAILED state; Midea 2024 is absent. Its missing-source-dependent question is retained as not run, pending the separately prepared new public seed. No substitute PDF, latest report, or implicit scope expansion is used.

## Reproduction and artifacts

```sh
PYTHONPATH=. .venv/bin/python experiments/cplus/evaluate_retrieval.py \
  --seed /absolute/path/to/readonly/showcase-seed-v1 \
  --output docs/cplus/eval/results/new-owned-run
```

To generate the 24-case checklist and per-hit Markdown from an existing completed receipt without rerunning retrieval/model/tool operations:

```sh
PYTHONPATH=. .venv/bin/python experiments/cplus/evaluate_retrieval.py \
  --seed /absolute/path/to/readonly/showcase-seed-v1 \
  --output docs/cplus/eval/results/v1 --summarize-existing
```

The v1 core run began before the presentation/checklist-only helper was added. Its exact executed source is preserved as `results/v1/executed-evaluator.py.txt`, matching the receipt's `script_sha256`. The final evaluator adds Markdown/checklist generation, refusal to overwrite nonempty result directories, and removes an unused import; the actual query, source, model, retrieval and tool-probe code is preserved in that executed snapshot. No completed query was replayed merely to update report formatting.

- `results/v1/retrieval-evaluation.json`: actual runtime/source/model provenance, exact six before/after, current dense recheck, exact historical-question search and fixed-case tool receipts.
- `results/v1/six-query-progress.json`: incremental six-query receipts, retained independently of final success/failure.
- `results/v1/six-query-before-after.md`: every before/after hit's page, snippet and typed scores.
- `results/v1/fixed24-execution-tiers.{json,md}`: all 24 cases with exact execution tiers and gaps.

Final verification: Ruff and Python compilation pass; all six frozen questions/source scopes match exactly, dense recheck values match M0, all 30 current excerpts exact-verify, 24 unique frozen case IDs/questions are preserved, provider/financial approvals remain zero, the executed-source snapshot hash matches the receipt, and seed integrity plus temporary-runtime cleanup are proven. The current BGE revision is `5617a9f61b028005a4858fdac845db406aefb181`.
