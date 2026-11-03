# Final two-year business export: independent file QA

Read-only inputs: `data/cplus-final-business-native-v1/result.json`, its
`template_receipt.result`, and the downloaded cash-template CSV/XLSX/PPTX/PDF.
Root's result records `REAL_REACT_HTTP_PUBLIC_PDF_GUARDED_MODEL`, PASS with 32
checks and one newly authorized SDK call. That native execution is root's
evidence; this review did not call a provider or use a live session.

## Outcome and material AI issue

The **two-year cash template covers the requested G6 business-chart path**:
its actual PPTX has six slides and one editable total-assets trend chart for
2024/2025, based on the saved candidate points. The chart source footer identifies
2024 annual report physical page 111 and 2025 page 86; values, unit and candidate
status are visible. This does not erase the separate single-year overview-ai
finding: that earlier PPTX still has zero charts, and its original failure and
files remain unchanged.

**Do not present this saved AI interpretation as a verified financial summary.**
The original interpretation states “2024、2025年经营现金流46,383,114,754.02元、
29,369,250,570.66元” and gives parent net profit `29,003,103,411.66` then
`32,184,570,372.28`. In the ten saved candidate points the year associations are:

| Candidate metric | 2024 | 2025 |
| --- | ---: | ---: |
| Operating cash flow, CNY yuan | 29,369,250,570.66 | 46,383,114,754.02 |
| Parent net profit, CNY yuan | 32,184,570,372.28 | 29,003,103,411.66 |

The interpretation's listed order reverses the two years for both metrics.
It is preserved verbatim and labelled AI 待审阅, but the label does not make the
year/value association correct. It also refers to OCR; the selected financial
points are fast-text candidates, so that wording should not be treated as proof
of OCR provenance for them. Human semantic review is pending. No new correction,
model call, financial confirmation or rewritten receipt was performed here.

## Exact file and source checks

The original template contains **10 candidate points** and three program rules;
`provider_outcome=returned`. CSV and XLSX each have 10 financial rows. All 10
match the original points on company name/code, metric, exact normalized Decimal,
period start/end/as-of, basis, scope, currency, raw unit, document ID, source
revision, physical page and unconfirmed review state. CSV preserves decimal as
apostrophe-prefixed text; XLSX preserves exact strings. XLSX reopens with three
sheets and zero formula cells.

The PPTX reopens with one chart whose stored series is `总资产`:
`3680.3170452286`, `3913.7199981949` 亿元人民币, corresponding to original exact
values `368031704522.86`, `391371999819.49` yuan. All three program rules are
visible on slide 4; the exact saved AI interpretation is present on slide 5 and
marked 待审阅. These checks do not validate the model's semantic correctness.

| File | SHA-256 |
| --- | --- |
| CSV | `dc53b9486d34d0a9fa16ab983ec5b72224aac1642a094982057ee0149ddb4bec` |
| XLSX | `6b9a316cd22affdc07c80d2d3bb407477d77058d9df7efda2440600e2e7d0a88` |
| PPTX | `089d9dcb350e9a0ed3c17564b0385a1e5a95a3c71f8ae2b8333f16788a56c583` |
| Browser PDF | `ee9c2f3f434e63ce802f1bbca082dbfc870cca315c8fe5247d7a18772a9fdb22` |

All four match the lengths/SHA in root's result. PPTX was independently rendered
with LibreOffice Impress and `FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf`;
**all 6/6 pages** were viewed individually. Page images are retained in
`final-business-qa/slide-{1..6}.png`. No obvious clipping was observed in this
renderer; this is not Microsoft PowerPoint acceptance.

The browser PDF has **3 pages**. Only page 1 and page 3 were visually inspected,
retained as `browser-first.png` and `browser-last.png`; Chinese is visible but
the print is small and long structured JSON on the first page runs into the right
edge. Page 2 and full-document layout were not visually accepted.

Original artifacts and receipts were not modified. Review tier:
**READ_ONLY_REAL_NATIVE_ARTIFACT_AND_SAVED_RECEIPT + LOCAL_IMPRESS_RENDER**.
Zero new provider calls, no private cookie or 14540/14542 access, no human
financial approval. Financial and semantic acceptance remain `human_pending`.
