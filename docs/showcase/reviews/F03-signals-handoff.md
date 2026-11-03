# F03 read-only balance change signals

Base integration commit: `bbf098f6599ccb6e5d017962a0f973c4ce002b5f`. Branch: `codex/showcase-f03-signals`. Scope is `app/finance_v2/signals.py`, minimal additive API/service methods, three tests, and this handoff. Frontend/runtime/old fact contracts untouched. Root owns UI integration.

## Endpoint and UI contract

`GET /financial/extended-signals?company_id=<id>&document_id=<id>&source_revision=<64hex>`

All three parameters are required exactly once; extra/duplicate parameters return 422. Success has `Cache-Control: no-store`, `schema_version=extended-signals-v1`, explicit `source` identity, `source_status=current_valid`, `calculation_version`, `signals`, `notices`, and `limitations`. No operation UUID, persistence, provider call, financial confirmation or investment score is created by GET.

`signals` always contains entries for `total_assets`, `total_liabilities`, `debt_asset_ratio`. Every entry has `metric_key` and `status` (`available` or `missing`). Missing entries have a machine `reason`; do not render a numeric zero in place of missing.

Available assets/liabilities have `from_date`, `to_date`, `delta_decimal` (CNY_YUAN), `change_percent_decimal` (string or null), `percent_unavailable_reason`, `unit=CNY_YUAN`, and `input_refs`. Each input ref preserves metric ID, exact date, value/unit, local_operator confirmation reference, and original evidence references. Decimal strings must remain strings until formatted for display.

Available ratio entry has `from_date`, `to_date`, `from_percent_decimal`, `to_percent_decimal`, `delta_percentage_points_decimal`, `unit=PERCENTAGE_POINTS`, and four `input_refs`. Ratio values themselves are percentages; delta is **percentage points**, not percentage growth. Neutral `notices` describe asset/liability direction only and require the matched dates and valid ratio. Display dates as returned, not as inferred year labels.

Example shape (illustrative only, not a real confirmed result):

```json
{"metric_key":"total_assets","status":"available","from_date":"2025-01-01","to_date":"2025-12-31","delta_decimal":"0.03","unit":"CNY_YUAN","change_percent_decimal":"0.000000","percent_unavailable_reason":null,"input_refs":[]}
```

Real available entries always include their admitted input references; empty refs above only abbreviate the shape.

## Admission and calculation rules

Service first validates the exact current source even when there are no collected metrics. It filters stored metric records by exact company/document/source_revision, re-extracts and revalidates them using existing `_selected`, and checks source/evidence plus live receipts inside the existing attached-source read transaction. Only raw candidates backed by a current unrevoked `local_operator` receipt are projected into internal `confirmed/current_valid` input. `simulated_test` receipts, unconfirmed candidates and unsupported rows never compute. Existing analyses, client values, browser flags and other document versions are not inputs.

For each metric, exactly two admitted distinct dates are sorted by real ISO `as_of_date`. Fewer dates yield `missing/two_confirmed_dates_required`. Duplicate metric/date returns 409 `ambiguous_signal_metric_date`; more than two dates returns 409 `ambiguous_signal_date_pair`. No automatic latest-version/latest-date selection. The explicitly pinned revision selects the version; metrics from other revisions cannot join it. Unsupported extraction ambiguities stay missing rather than becoming admitted.

- Difference is later minus earlier using Decimal with input-scaled local precision.
- Percentage change is difference / earlier * 100, only when earlier > 0 and later >= 0. Zero earlier returns null plus `zero_baseline`; negative balances return null plus `negative_balance`. The arithmetic difference remains available.
- Ratio requires assets and liabilities at the same two dates, assets > 0 and liabilities >= 0. Otherwise ratio stays missing. Each liability/assets * 100 is rounded half-even to six decimals; percentage-point change is later rounded ratio minus earlier rounded ratio, six decimals.
- A same-year opening date remains that date. `2025-01-01` is never relabeled `2024-12-31`, and the interface never calls arbitrary two-date changes year-over-year.
- Source change/unavailability propagates the existing source error (representative corruption returned 409), without a historical signal fallback. UI must clear previous signals upon source selection/change or a failed refresh; server never returns old signals on failure. A read is a point-in-time response, not a continuing validity subscription.

## Verification

Three new representative tests passed: exact subtraction above float-safe range, nontrivial percentage/ratio-point values and zero/negative rules; untrusted/missing inputs and duplicate/multiple-date/source mismatch rejection; real API over synthetic PDF/temporary SQLite showing empty/candidate/simulated receipt never calculates, repeated GET changes no operation/analysis counts, query rejection, and corrupted source returns no signals.

Final check:

```sh
/tmp/findoc-m3-independent-env/bin/python -m pytest tests/test_finance_v2_signals.py tests/test_finance_v2.py -q -p no:cacheprovider -k 'not real_pdf'
```

Result: **5 passed, 1 deselected, 5 dependency deprecation warnings** (1.73s). New tests alone: 3 passed. Ruff changed Python files PASS; diff check PASS. Real-PDF opt-in check intentionally deselected; no real DB, `.env`, model or human financial approval used. Arithmetic fixtures marked `UNIT_FAKE_NOT_A_RECEIPT` are internal adapter dictionaries only; service test uses actual `simulated_test` receipts and verifies exclusion. This is synthetic implementation evidence, not human-confirmed business acceptance. Root still owns UI and final integrated verification.
