# Saved real-agent report export QA and new domain contract

Follow-up to `50fd623`. Leaf changes remain in projection/render and dedicated
tests; root `exports.py`, API Literal and runtime assembly are not edited.

## Added domain mappings

| Domain | Payload schema | ID field | Revision |
| --- | --- | --- | --- |
| `chart_report_v1` | `chart-report-v1` | `report_id` | Saved revision; absent means immutable revision 1 |
| `template_run_v1` | `template-run-v1` | `run_id` | Immutable revision 1 |

`financial_points` is projected through the same Decimal/period/source rules;
`selected_sources` supplies exact source metadata; `topics`, `checkup_rules`,
`findings`, `interpretation` retain their existing saved-result meanings.
Template checkup rules render even when financial chart data is also present.
No new model or financial calculation is introduced. Root must still add these
domains to Ref Literal and resolver/registry assembly before HTTP export is enabled.

## Real saved report inputs

Read only `docs/cplus/eval/results/agent-paths-real-v2/result.json` from the root
integration checkout. Extracted **saved_report**, without adding the GET-only
currentness/history decorations from report_revision, to retain the canonical
saved-payload SHA. Input-file SHA is recorded in `agent-export-qa/proof.json`.

| Case | Original report | Saved payload SHA | Existing model interpretations |
| --- | --- | --- | ---: |
| E01-06 deep | `cca24d35-15a4-4c19-82a7-e6588bbddd70`, revision 1 | `c47fdd2a86ab9015f10dfc9d4e25147123f41816245b29a34d28f6c30439c0e2` | 6 |
| E01-01 synthesis | `be8e51f6-23f4-40b1-8c4a-1efe088ee732`, revision 1 | `5cc318b879ded3188f47f5eb740b67baf7979727b813d140ee3d43547371c3bd` | 2 |

These independent QA outputs are labelled historical/stale, because no live
source-currentness route was called. No registry was read for this follow-up:
display_companies was not fabricated, so source footers show the saved document
identifier, year and page. Root-supplied registry labels continue to use the
previously verified display_companies contract.

Deep now uses two AI pages so all six actual saved interpretations are retained;
synthesis retains both saved interpretations. The latter explicitly reports
insufficient cash-flow evidence; export preserves that limitation and does not
turn the real provider execution into a successful factual answer claim.
Nested showcase snapshot limitations are now also projected/rendered.

Original-source findings and model interpretations appear on separately labelled
pages. Source excerpts are visibly limited, with shown/total counts and full
content retained in the saved report. Presentation text folds whitespace only.
The first render exposed overflow in a three-finding page; it was corrected to
two explicitly counted original-source excerpts, then rendered and checked again.

## Actual artifacts and verification

Outputs are under
`/Users/aipuli/.codex/worktrees/findoc-business-exports/data/business-export-agent-qa/`.

- `deep.pptx`: seven slides, SHA-256
  `3d038f5fd07e33205f576c065ab29c7194ffdde81337e16e8663cef795a8344e`.
- `synthesis.pptx`: six slides, SHA-256
  `e43b88db363242070a95a9ff4991d31d97a9863dacf626943768743c01339f3c`.

Both files were opened/rendered with LibreOffice Impress using explicit Chinese
fontconfig. All thirteen slides were individually inspected; PNGs and hashes
are committed under `agent-export-qa/`. Reopening native PPTX confirmed every one
of the 6/2 original model texts and both saved limitations is present (whitespace
normalized only), and no financial chart was invented from textual evidence.

Ruff passes; dedicated export tests **12 passed**. Added checks cover both domain
schema/ID/revision contracts and template-run checkup rendering. This is projection/
renderer acceptance for new domains, not an assertion that root's new HTTP assembly
has already been exercised. Existing source/authority/ref SHA protections remain.

This work made **zero provider calls**, zero financial approvals, and used neither
14540 nor 14542. It is local rendering of already-saved REAL_LLM evidence, not a
new model execution or human semantic endorsement. No original receipt/artifact
was altered, and no private ledger or credential file was opened.
