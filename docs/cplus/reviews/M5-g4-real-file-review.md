# G4 real overview export: independent reading QA

Read-only source: root `data/cplus-g4-live-v1/overview-ai.{csv,xlsx,pptx,pdf}`
and `result.json`, specifically `template_runs[0].receipt.result`. The overall
result remains **FAIL** due to a later chart-script selector; the saved export
is evidence for the earlier completed template/export steps only. No record or
original artifact was changed.

## Finding: required business chart absent

The saved template contains five real 2025 candidate financial points. The actual
PPTX has six slides and **zero chart objects**; slide 2 says no suitable financial
series and does not show a finance chart. This does not satisfy the requested
actual finance business chart in this export, even though the file opens and
other business exports may contain charts. A truthful single-period chart or
clearly labelled other supported visualization can use the saved points; retain
metric, period, unit and unconfirmed status, and never fabricate an extra year.

The independent review does not edit code. This is a concrete file-level gap,
not a claim that all report domains lack charts.

## Actual file checks

- The original receipt contains five candidate metrics: total assets, liabilities,
  revenue, parent net profit and operating cash flow. All five CSV and XLSX rows
  match the receipt on metric, basis, scope, currency, raw unit, review state,
  document/source revision, period, physical page and normalized Decimal.
- Company is 珠海格力电器股份有限公司, code `000651` in all rows. CSV prefixes
  exact decimal text with an apostrophe for spreadsheet safety; XLSX retains the
  exact original decimal strings. Three workbook sheets reopen; formula cells: 0.
- PPTX reopens: six slides, no chart. The actual saved AI interpretation is
  present verbatim and labelled 待审阅. It says its available excerpts lack complete
  financial data; the saved template separately contains candidate financial
  points. Its OCR wording and substantive claims remain human semantic review,
  not a confirmed assessment of the fast-source excerpts.
- Inspected **all six** existing Impress-rendered PNG pages individually with the
  supplied CJK font configuration. Text is readable and no obvious clipping was
  observed. Contact sheet: `M5-g4-overview-contact.png`. This is visual evidence
  for the supplied renderer/environment, not universal client compatibility.
- Browser-produced PDF is a separate eight-page artifact. Its SHA is recorded
  below; this review did **not** inspect its pages and makes no PDF layout claim.

| File | SHA-256 |
| --- | --- |
| CSV | `5dae84a656dc716ac458a975de39a9eae9dc2bdb6fc42e7c14be66bd5ee5873b` |
| XLSX | `8bb6bb748688bc5f653f759ca1ebda6b2ca3d636d3b87731c696005533f44090` |
| PPTX | `d430f707a7f19558dbc418f1028748069b0765af219f939220d4f5dd2862df7d` |
| Browser PDF | `e460b364e4b2c4b22b4f0e750bc5e5790d105ae354f44f1138869bb96f368a8b` |

`data/cplus-g4-finish-v2` existed at inspection but contained no exported sample
files; its result was FAIL with intermediate chart-draft checks. It is not counted
as chart/export acceptance and no waiting or rerun was performed.

Tier: **READ_ONLY_REAL_TEMPLATE_RECEIPT_AND_DOWNLOADED_FILES**, with six-slide
visual review. Human financial confirmation and semantic acceptance remain
`human_pending`. Zero new provider calls, no live-port access, and no real PDF,
database or credential is included in this commit.
