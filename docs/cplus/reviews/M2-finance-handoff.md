# M2 Finance v3 first usable slice

Base `3c737327198a55b72d02490a981b5259cd164ffa`; branch `codex/cplus-statements-v3`. Additive new modules only. This is a collection/review/receipt/trend candidate for root integration, not complete F01–F06 acceptance or human financial sign-off.

## Root wiring

```python
from app.financial_statements_v3 import StatementService, create_statement_router
from app.company_profile import ProfileService, create_profile_router
from app.checkup import CheckupService, create_checkup_router
statements = StatementService(runtime_root, source_service, company_service)
app.include_router(create_statement_router(statements, owner_authorizer=authorize_extended_finance))
app.include_router(create_profile_router(ProfileService(statements)))
app.include_router(create_checkup_router(CheckupService(statements)))
```

Existing OwnerAuthorization is actually in `app.finance_v2.service`, not contracts (PORTS_V1 location typo). Router authorizer is required for confirmations/revocations; missing fails403. Root must register those two writes with owner=True plus native_operation, remaining new writes native_operation; apply existing generation/private identity fencing. No runtime/demo/UI/old finance/migration files modified here.

Routes follow API_V1 exact names under `/cplus`: POST financial/collections; GET financial/collections/{id}; GET companies/{id}/statements; POST financial/reviews; POST financial/confirmations; POST financial/confirmations/{id}/revoke; GET financial/operations/{id}; POST financial/trend-projections; GET companies/{id}/profile; POST checkups; GET checkups/{id}. Strict input rejects unknown fields/client amounts; operation UUID/body digest conflict, UNKNOWN not replayed.

collection response has `id=collection_id`, source, immutable `cells`, collection payload_sha256. Cell schema statement-cell-v3 includes revision1/payload hash, complete source identity/content hash/parser, metadata_hash including company snapshot, disclosure version, raw/normalized Decimal string + units/currency, scope/basis, `time={kind:instant,as_of_date}` or `{kind:duration,period_start,period_end,period_type:annual}`, row/page/word bbox evidence and separate extraction/financial/transcription axes. TypeAdapter in models validates mutually exclusive time fields/date order. Source must be legacy READY/current/cover matches; OCR is not admitted.

review request `cell_refs=[{cell_id,cell_revision,payload_sha256}]`; result has review_id/review_sha256 and frozen cells. Confirm takes exactly operation_id, review_id, review_sha256, confirmed=true. Receipt stores server actor, time, exact cell hashes; revocation is independent immutable event. Final source guard runs in attached rollback-journal transaction and company snapshot is checked. Owner deadline is rechecked inside tx just before actual COMMIT, in addition to service entry. WAL fails closed. Records have UPDATE/DELETE abort triggers and SHA checks. Old v1/v2 fact tables are not touched.

Trend requests: operation_id, collection_refs, metric_keys, candidate_view defaultfalse. collection_refs supports UUID strings (all cells) **or explicit `{collection_id,cell_ids:[...]}` selections**. This optional shape is needed for two reports containing the same comparative financial period; no automatic latest. API_V1 froze the field name but not its element shape. Root can use the object selection to choose exact current-year rows per report. Repeated company/metric/time across selected cells is rejected even if values agree. candidate_view=false returns only current source + unrevoked local_operator receipt points; candidate_view=true includes unconfirmed candidates with explicit status, not a financial grant. `changes` includes exact delta, explicit from/to time, positive-base percent or reason, formula version and input IDs. No point filling. Cached projection replay revalidates sources and its original receipts; revoked projection is not regranted.

GET collection/list returns immutable historical cells with a separate current source_status; UI must not treat the saved `extraction_status=candidate` or historical values as current confirmation. Profile is deliberately minimal: company + collection/source inventory and empty selected KPI array; it does not choose latest versions or generate text. Root can use trends to fill explicitly selected KPIs. It is not the finished company360 dashboard.

Checkup returns three deterministic rules: income/profit direction divergence, cash/profit direction divergence, debt/asset ratio percentage-point change. Missing/incomparable/nonpositive base gives insufficient. candidate_view explicitly labels candidate_observation; confirmed mode requires admitted cells. It neither assigns investment scores nor attributes causes. Explanation requests currently fail `guarded_explanation_not_connected` even if a callback was supplied; this optional feature is deferred to root's shared guarded-provider integration. Stored checkup reads are historical snapshots and separately recheck source status. They are not a new current financial approval.

## Actual public extraction proof

Read only the two Gree PDFs referenced by M0-statement-page-map, without opening seed/development DB. Physical rows/columns are extracted using PyMuPDF word geometry, exact consolidated statement heading (including explicit continuation), matching dated/年度 columns, CNY unit, whole cell decimal and exact row labels. Parent/note tables without exact headings do not qualify. Actual results: **38 candidate cells per PDF**, all three statements, all unconfirmed. Core current-year values:

| metric | Gree 2025 | Gree 2024 |
|---|---:|---:|
| revenue | 170447058533.57 | 189163654064.64 |
| net_profit_parent | 29003103411.66 | 32184570372.28 |
| operating_cash_flow | 46383114754.02 | 29369250570.66 |
| total_assets | 391371999819.49 | 368031704522.86 |
| total_liabilities | 241580719144.79 | 226518009574.89 |

2025 assets/liabilities comparisons preserve **2025-01-01**; 2024 preserve **2024-01-01**, not inferred previous December. Profit/cash columns preserve annual2025/2024 and2024/2023 respectively. Public proof `M2-finance-public-candidates.json` contains original row words, bbox, physical page, time and exact Decimal; PDF hashes are checked. Direct proof uses synthetic adapter identity in the test and explicitly does **not** assert a current runtime source_revision/receipt. Exported public proof strips those synthetic adapter IDs. It is REAL_PUBLIC_PDF_CANDIDATES, not runtime admission or financial confirmation.

## Tests and remaining limits

Three representative groups:

1. Synthetic temp SQLite/fast source: collect/review; absent owner refusal; explicitly simulated owner receipt, current trend; revocation removes confirmed points; candidate opt-in; ambiguity refusal; corrupted PDF invalidates source/projections; API unknown amount rejected; invalid time union rejected.
2. Synthetic owner expiration at final source guard rolls back receipt and leaves original operation UNKNOWN; no retry.
3. Explicit readonly two-public-PDF extraction, exact five core amounts per report, all three statements, preserved opening dates and zero financial approvals.

```sh
CPLUS_PUBLIC_PAGE_MAP=docs/cplus/evidence/M0-statement-page-map.json \
  /Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python \
  -m pytest tests/test_cplus_statements.py -q -p no:cacheprovider
```

Final run 3 PASS (2.52s), 5 dependency deprecation warnings. Earlier initial run failed because SQLite attached URI lacked uri=True; fixed, retained here rather than claiming first-pass success. Without env public test skips. Ruff and diff check pass. Human financial approvals=0; paid calls=0; no .env/secret/budget DB read. Simulated actor/receipts exist only in temporary synthetic fixture; no actual PDF data is signed.

Finite support: first release recognizes consolidated annual fast-text exact row labels/two explicit columns and supported CNY units, not arbitrary quarterly/parent/complex merged/negative-parentheses tables. A missing/ambiguous row is omitted or unsupported; UI must not fill zero. Cell coverage list is not proof all statement lines are extracted. No interpolation across missing years or silent disclosure selection. Full real runtime route integration, source/deadline concurrency audit, proper chart UI, fullcompany360 enrichment, optional model explanations and human review positive still await root/next slice. This handoff delivers backend usable slice promptly rather than waiting for UI.
