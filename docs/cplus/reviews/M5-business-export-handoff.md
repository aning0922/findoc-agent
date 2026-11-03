# M5 business export leaf handoff / ADR supplement

Base `e510876`. Business edits are limited to `app/exports_v2/projection.py`,
`render.py`, `service.py` and their dedicated tests. Root's resolver/router,
frontend, runtime, seed and provider code are not changed.

## Resolver contract

Root supplies an optional `resolved.display_companies` mapping:

```json
{"company-id":{"name":"真实registry名称","security_code":"000651","exchange":"SZSE"}}
```

These are display labels read at export time, not financial authority. Projection
uses them for `company_name`, `company_code`, `exchange` and retains the original
report_ref ID/revision/payload SHA. It does not infer a company from a title.
Old snapshots without mapping remain readable; missing labels are not invented.

The service deep-copies the initial mapping, re-resolves after rendering and
compares it along with snapshot/status. Any label drift leaves operation UNKNOWN
without publishing files. The immutable manifest records `projection_version`
`business-v2`, `display_companies`, and its canonical SHA-256. Existing request
`export_profile_version=research-v1` and manifest schema remain compatible.
GET still returns stored bytes; it does not render again or update frozen labels.

Financial rows now include flat `period_kind`, `as_of_date`, `period_start`,
`period_end`, `physical_page`, `physical_pages`, `authority`, `source_link` and
`generated_at`. A single page is emitted only if evidence identifies one unique
page; all pages and full original evidence remain available. Raw/normalized
Decimal strings, original units, basis/scope/currency and financial_review survive.
Generated timestamp is consistent between file data and the service manifest.

Evidence rows flatten SourceRef identity/year/page and carry company labels.
Annual topics' saved explanations appear in evidence/overview/PPTX with their
references and AI review status. Checkup `rule_id/observation` rows are recognized;
three rule cards, missing observations and already-saved model findings render.
No absent explanation, checkup source or financial value is synthesized.

## Business visuals

- Peer snapshots: a saved comparable single metric across two/three companies is
  rendered as an editable actual-amount chart; period, basis/scope, units and
  candidate/confirmed status are visible. CNY_YUAN chart axes use 亿元人民币;
  exact original decimals remain in labels and tables. This is display scaling,
  not a newly approved financial calculation.
- Same-company annual values can form a trend only with matching basis/scope/
  currency/unit, unique periods and aligned period shapes. Quarter/full-year
  mixes, unknown basis and unavailable source pages do not produce charts.
- No comparable financial series: annual snapshots show three bilateral topics,
  then the saved AI explanations; no citation-count graph substitutes for business
  values. AI-cited evidence IDs are preferred within the already-saved topic scope.
- Source-year/page footers and complete source notes bind each page. Long original
  text is visibly marked as an excerpt; linebreaks are collapsed for slide layout,
  while complete source strings remain in CSV/XLSX. No new provider call occurs.
- XLSX keeps three sheets and exact string values. Business columns are visible;
  technical columns remain in expandable groups. Long evidence is split into
  numbered `excerpt_part` rows without dropping text; CSV retains full entries.

## Verification and actual artifacts

Ruff passes. Dedicated export tests: **9 passed**. Cases include label drift during
render, exact period/page/Decimal projection, incompatible chart rejection,
quarter-versus-annual rejection, native financial chart values, actual annual
explanation inclusion, checkup rules/missing values, saved findings, immutable GET,
permission rejection, and rollback before final publication.

Local outputs: `/Users/aipuli/.codex/worktrees/findoc-business-exports/data/business-export-qa/`.
No original root artifact was overwritten. Existing public saved snapshots used:

| Sample | Original result | Original payload SHA |
| --- | --- | --- |
| Peer | `e584cb8f-c464-4d80-b820-246fbe2bf3ea` | `e5498bef7ec866c632076ebba3431dd58b9154668e8945e9d8b014249df37c1c` |
| Annual | `f5c7b0eb-7a22-46d2-8cf9-c805f4515db9` | `23dbafc0d08f8ab22af96a07382ec0077445e3a6a232d47f332bfbaa2c031106` |

Peer payload was read by its explicit ID from the existing public validation
runtime's peer store; labels were read from its registry for those exact companies.
Annual payload comes from the saved `annual-after-projection-fix.json` real-provider
receipt, with three existing explanations. No model was called for this work.
Both are rendered as **historical/stale local snapshots**; no live source-current
or real authenticated root export claim is made by this independent renderer run.

Actual peer CSV has ten rows with names/codes/pages and unconfirmed authority.
Annual CSV contains all three exact saved explanation strings. Both XLSX files
reopen with three sheets and zero formula cells. Peer PPTX has six slides and one
actual total-assets amount chart; annual PPTX has seven slides and bilateral
topics/AI explanations, without invented financial charts.

LibreOffice Impress opened and rendered both PPTX files. All thirteen final slides
were individually inspected; an initial multiline clipping issue was corrected,
then affected slides rerendered. PNGs for every page are in
`business-export-qa/peer-{1..6}.png` and `annual-{1..7}.png`. Calc opened both XLSX;
first-page views of all three sheets were inspected. This is not Microsoft
PowerPoint/Excel desktop acceptance or an assertion of every Calc print page's
layout. Explicit system fontconfig was used for Chinese rendering.

`business-export-qa/proof.json` records artifact paths, report identities, hashes
and all screenshot hashes. Primary PPTX SHA-256 values:

- Peer: `a0291c594d7ac468efb689b27986b4e341238b86de03f7dfab81754d35ea3361`
- Annual: `541110072540d3c6c12a184f6e75ffa65de57b43bddb9efb3d71607526fa6878`

Root integration next step: supply the real registry mapping through the resolver,
then exercise the authenticated export route with the current saved business
results. Existing body/ref SHA and authority must remain unchanged. Human semantic
and financial review remain pending; retained real-model explanation is not a
semantic acceptance claim. No root ports, credentials or private ledger were used.
