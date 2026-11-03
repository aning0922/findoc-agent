# G4 exact saved exports v2: read-only supplement

Reviewed `data/cplus-g4-exact-exports-v2` and its saved result. Root reports
`REAL_HTTP_EXACT_SAVED_MODEL_REPORT_AND_CHART_FILES`, PASS and
`zero_new_provider_calls=true`; authenticated HTTP execution is root's evidence,
not replayed here. All **9/9** downloaded CSV/XLSX/PPTX files match their own
manifest byte length and SHA-256. Each print HTML is present; layout was not
visually inspected in this supplement.

| Saved domain | CSV rows | XLSX sheets / formulas | PPTX slides / charts |
| --- | ---: | --- | --- |
| chart_report_v1 | 10 | 3 / 0 | 6 / 1 actual total-assets annual trend |
| paired deep showcase_report_v2 | 27 evidence rows | 3 / 0 | 7 / 0 |
| paired synthesis showcase_report_v2 | 16 evidence rows | 3 / 0 | 6 / 0 |

The chart-draft receipt in `cplus-g4-finish-v2/result.json` contains ten saved
candidate points; **10/10** match a chart CSV row by metric, exact normalized
Decimal, physical page and financial review state. The PPTX's native chart object
and title establish a business chart exists; this supplement did not render its
six slides or independently inspect chart-series values. The original overview-ai
single-year export finding from `M5-g4-real-file-review.md` remains open: success
for this two-year chart draft does not retroactively add a chart to that PPTX.

Both paired source reports were found in the saved
`docs/cplus/eval/results/agent-paired-e0115-continued-v1/result.json`. Their saved
report payload SHA values independently match the exact v2 export refs. All **6/6
deep** and **2/2 synthesis** saved model interpretations are present verbatim in
CSV and XLSX overview. Deep PPTX contains all six full texts. Synthesis PPTX
contains the first 120 characters of each of its two longer interpretations;
both are explicitly marked as excerpts, so it is not a complete-text PPTX. CSV/
XLSX remain the complete-text artifact. AI content is still `ai_unreviewed`;
no human semantic or financial acceptance is inferred.

The local `finish-v2` chart receipt, when parsed and reserialized as Python JSON,
does **not** reproduce the v2 server-ref SHA. Root's retained v1 observation
attributes the earlier hash mismatch to JavaScript numeric reserialization;
v2 used server GET values and a new operation. This review independently confirms
the mismatch remains in the stored finish JSON and does not pretend it is the
server's exact canonical byte/type evidence. It does not replay the v1 UNKNOWN.

## Bounded source review of 448417d

The optional `domain/identifier/revision` filter is applied before iterating the
selected domain's matching snapshots; every retained item still goes through
`resolve` and owner/identity checks. Bad partial selections are rejected. No
obvious permission bypass was found in this source-only check. This is not a
new concurrency, authorization-fault or full-site test.

No private cookie, provider, ledger or live-port request was used. No original
failure receipt, export file or source JSON was modified. Human financial and
semantic acceptance remain pending.
