# G02 curated financial candidate seed handoff

Delivered a new immutable `showcase-cplus-seed-v3`, adding only the manifest-bound
`cplus-financial-candidates.json` display artifact to the fixed v2 seed. The helper
and CLI are independent of dashboard routes and application assembly.

## Artifacts and identities

- Seed directory: `/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/showcase-cplus-seed-v3`
- Manifest SHA-256: `d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d`
- Bundle: `/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/findoc-showcase-cplus-seed-v3.tar.gz`
- Bundle SHA-256: `c45d3cb8ec6ffb0d6ff411fe34fdffc9639fc49ad9e1615ed979a1d8dd10355e`
- Parent v2 manifest SHA-256: `287d939e8d72aba2092a4fae00f10ecab0711258a86f11f453dd760febe49459`
- Machine-readable verification: `docs/cplus/reviews/G02-curated-financial-proof.json`.

The immutable seed contains 42 manifest-listed payload files. All 41 original v2
payloads retain their exact SHA-256, including SQLite databases, vectors and
archive files. The SQLite and vector manifest specifications are unchanged.
The archive's 43 regular files, including its manifest, were streamed and hashed
against the manifest. No archive extraction was required.

The v1 seed was reverified against manifest
`efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4`.
The v2 bundle still hashes to
`8852d191adfe74b1f4700f499919dd3b05e0e92e840d53bc6a6eecaa015fed3b`.

## Candidate contract and source checks

The artifact has schema `cplus-curated-financial-series-v1`,
`data_origin=preset_candidate`, `financial_authority=false`, `human_approvals=0`,
and the parent manifest SHA. There are five series and ten points, with no missing
metrics. The company display field is `company_name` alongside `company_id`.
Every point retains period, exact normalized/raw decimal strings, raw unit,
document ID, source revision, content SHA, parser version, physical page and
`financial_review=unconfirmed`.

The helper materialized v2 into a private temporary runtime, read the two fixed
Gree disclosures through `DocumentSourceService.source` and `.file`, then used the
existing v3 extractor. It froze the original v2 files into v3, rather than copying
the temporary runtime's service-initialized databases. No financial-service
receipt, confirmation or collection was written. No document upload, BGE/model
initialization, download, paid call or human approval occurred.

Only a unique current-report full-year or year-end cell is eligible. Duplicate,
missing, unsupported, nonfinite, incomparable or already-confirmed candidates
are excluded with explicit missing reasons. Grouping preserves company, metric,
PRC_GAAP basis, consolidated scope, CNY currency and CNY_YUAN normalized unit.
Annual durations and year-end instants are selected explicitly; there is no
automatic latest/comparative choice or derived growth calculation.

| Metric | 2024 physical page | 2025 physical page | Period |
| --- | ---: | ---: | --- |
| revenue | 113 | 88 | Report-year full year |
| net_profit_parent | 113 | 88 | Report-year full year |
| operating_cash_flow | 114 | 89 | Report-year full year |
| total_assets | 111 | 86 | Report-year December 31 |
| total_liabilities | 112 | 87 | Report-year December 31 |

For all ten points, the exact amount word and its bounding box were checked
against the actual PDF physical page, the page explicitly contained 人民币元,
and the raw decimal matched the printed amount with commas removed. These are
programmatic source checks, not human financial acceptance or browser evidence.
The proof JSON records the actual printed labels, amounts, units and boxes.

## Invocation and validation

```sh
python -m experiments.cplus.curate_financial_seed \
  /absolute/path/to/showcase-cplus-seed-v2 \
  /absolute/path/to/a-new-showcase-cplus-seed-v3 \
  --bundle /absolute/path/to/a-new-showcase-cplus-seed-v3.tar.gz \
  --proof-json /absolute/path/to/a-new-proof.json
```

The parent manifest is pinned in code. Existing destination seed, archive and
proof paths are refused; the original seeds are never overwritten. The final
archive verifier was also run read-only against the actual generated bundle.

Validation completed: Ruff format/check; two focused pytest tests for unique
current-year selection and archive payload/manifest hash rejection; actual CLI
generation; read-only seed, parent and archive verification. Pytest reported the
existing five PyMuPDF/SWIG deprecation warnings.

Root integration should serve this separately as preset unconfirmed observations,
preserve source-currentness checks and make its candidate status visible in chart
UI. GET routing, chart rendering, browser verification and product/release
acceptance remain with the controlling integration task.
