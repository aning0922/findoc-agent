# M3 P1 fixes: independent targeted verification

Verified on 2026-11-03 (Asia/Taipei), fixed business baseline **`b2b73d508206d8a1213b9efefe421cfd2c94f7f0`**. Review branch: `codex/cplus-m3-fixes-verification`.

**All four original P1 findings pass this targeted verification.** This closes the reproduced assembly defects at this baseline, within the synthetic SQLite and intercepted-API React evidence described below. It is not an overall M3, real-provider, production, financial, or human acceptance result.

The original `ee836e6` reproduction, three strict xfails, their `--runxfail` failures, and the original React period-loss result remain in `docs/cplus/reviews/M3-integration-review.md`; that report was not edited or replaced. Root's pre-existing fixes to the Python assertions are part of `b2b73d5`. This review executes those assertions and strengthens them with additional independent integration checks.

## Results

| Original P1 | Executed verification | Result |
| --- | --- | --- |
| Nested memory generation check self-locks inside root publication fence | Root-mounted peer and checkup-explanation adapters read the same generation while the actual original memory publication guard holds its SHARED lock. SQLite tracing sees no `BEGIN IMMEDIATE` during these reads and sees explicit rollbacks. A subsequent committed generation change is rejected. Actual root HTTP peer POST and checkup-explanation POST both complete using real disposable SQLite stores. | PASS; no self-lock reproduced |
| Fast evidence favorite includes OCR-only page fields | Actual root-mounted original memory router still rejects the old malformed shape with HTTP 422; corrected payload succeeds with HTTP 200 and its original operation can be read. Actual React favorite sends the fast evidence ID and null artifact/page/line fields. | PASS; backend contract retained |
| OCR historical GET claims current after active artifact replacement | Actual root HTTP creates OCR enrollment/build/context/answer, then activates a different artifact. Executing an answer with the old context returns 409 `artifact_changed`; context and answer GET return historical snapshots with `current_source_status=stale_or_unavailable`. All stored object rows and operation count remain unchanged by GET. Actual React fetches the answer GET after POST and renders the historical warning. | PASS; active-only execution and read projection both verified |
| Chart comparative period is lost | Actual root HTTP resolves a cell from a **2031 report / 2030 comparative instant**, persists exact focus in context and answer, and rejects changed time or a non-selected focus source. Actual React clicks a **2025 report / 2024 comparative duration** point, obtains focus via GET, sends the exact full focus and same source in contexts POST, and keeps the actual 2024 period in the question. Missing cell ID, revision, or hash each blocks before focus GET or any POST. | PASS; report year does not replace actual financial period |

## Python evidence

Executed:

```sh
.venv/bin/pytest -q -rx \
  tests/test_cplus_m3_integration_review.py \
  tests/test_cplus_financial_focus.py \
  tests/test_cplus_memory_view.py
```

Result: **8 passed**, no skipped or xfailed cases, with five existing SWIG deprecation warnings. Six cases are in the independently owned integration review file; the other two are the root-added focus and memory-view tests. Terminal output is also retained locally at `/tmp/cplus-m3-fixes-python-verification.log`.

The independent integration file now verifies:

1. Current OCR answer GET succeeds for the original owner/expiry; expired recovery is HTTP 403. After active artifact replacement, the old context cannot execute, both history projections are stale, and GET does not change persisted objects or create operations.
2. Fast favorite's old malformed body remains rejected; its corrected body is accepted by the original memory router mounted alongside actual root routes.
3. Independent writer threads cannot commit source/company, active-artifact, or memory-generation changes during the inner retrieval transaction's before-COMMIT hook. A tampered complete quote tail is rejected with 409 `exact_evidence_unverified`.
4. Both root-injected memory adapters read generation under the actual publication fence without write escalation, and reject an outdated generation after an external commit.
5. Actual root focus GET recovers the 2030 cell from a 2031 report; context POST and answer POST retain exact cell/time/source and `financial_authority=false`. Mutated time is rejected with 409 `focus_cell_changed`; an unselected focus source is rejected with 409 `focus_source_changed`.
6. Actual root HTTP peer comparison and checkup explanation complete across the real SQLite stores. The checkup has a real program-generated candidate observation, explanation outcome is `unconfigured`, and financial authority remains false.

These are synthetic fixtures: generated PDFs, fake OCR engine, fake embeddings/index callback, and an explicitly empty fake dense adapter. `register_cplus_runtime` and its real routers, source checks, statement extraction, memory service, publication guard, and SQLite transactions run unchanged. A test-only middleware supplies the private marker for fixed test headers; this is not a real gateway/session authentication test. No private developer runtime or original database is used.

## React evidence

Executed using Node 24 and installed local Google Chrome, in a fresh Playwright browser context:

```sh
node tests/cplus_m3_draft_review.cjs
```

Result:

```text
PASS: actual React chart 2025 report/2024 period keeps exact server focus, source and question; fast favorite and historical GET refresh pass; 3 missing-cell metadata cases block before POST.
```

This replaces the owned script's fixed-baseline failure assertion with a positive regression. The test mounts **actual `CPlusCompanyEntry` and `CPlusCompany360`**, selects the comparative revenue cell, requests a candidate projection, clicks the actual SVG point, follows the actual entry component's session draft/navigation into **actual `DocumentResearchPanel`**, and reads the resulting DOM and intercepted requests. It does not manufacture the positive draft directly.

The captured sequence is:

```text
chart selection → candidate trend projection → SVG point click
→ entry's sessionStorage draft and /conversations navigation
→ research-source GET → financial/cells/{cell_id}/research-focus GET
→ contexts POST → answers POST → answers/{answer_id} GET → favorite POST
```

The focus GET uses `revision=1` and the exact payload hash. The contexts body contains the complete mock server focus unchanged, including `cell_id`, `cell_revision`, `payload_sha256`, `metric_key=revenue`, normalized value/unit, `financial_authority=false`, exact selected `source_ref`, and:

```json
{
  "report_year": 2025,
  "time": {
    "kind": "duration",
    "period_start": "2024-01-01",
    "period_end": "2024-12-31"
  }
}
```

Here `report_year` is in `focus.source_ref` and `time` is in `focus`; the JSON above is only a compact projection for readability. Both draft and final answer question retain `2024-01-01 至 2024-12-31`. The textarea visibly includes the server-resolved actual period. The answer POST binds the returned context ID/revision/hash; the answer focus is recovered through that context, rather than sent as browser authority in the answer request.

After the answer POST, exactly one answer GET supplies a stale projection, and the React historical warning appears. The actual fast favorite body retains the evidence ID/source revision and sends `artifact_id`, `physical_page`, and `source_line_index` as null. Each of three isolated negative cases removes one required cell metadata field from the actual generated draft and observes the explicit blocking message, no context action, zero focus GETs, and zero POSTs.

Full intercepted request evidence is locally retained at `/tmp/cplus-m3-fixes-ui-verification.json`; the previous `/tmp/cplus-m3-draft-review.json` is not overwritten. This is **UI_MOCK_ACTUAL_REACT** evidence: all `/api/**` calls are intercepted; external requests are blocked; page errors and attempted external requests are both empty. It proves the actual React request/navigation/display contract, not that a live browser backend persisted this mock focus. The separate Python root HTTP test supplies server persistence and rejection evidence.

## Scope, limitations, and verification hygiene

- Only `tests/test_cplus_m3_integration_review.py`, `tests/cplus_m3_draft_review.cjs`, and this new document were changed. No root or business implementation was edited; no push was performed.
- Model is `disabled-no-calls` in Python. React uses intercepted APIs only. Provider calls, financial confirmations, private config/ledger reads, and paid spend are all zero. Original root-reported provider UNKNOWN receipts are neither retried nor reclassified by this review.
- Vite is owned by the script, loopback-only, launched with `FINDOC_E2E_DISABLE_ENV_FILES=1` and a minimal environment; its browser and process are closed in `finally`. Existing user browser profiles are not opened.
- Fixture development initially exposed a missing pytest import, a missing empty-dense adapter, and a Python object-aliasing error in a negative request (mutating focus also mutated the selected source). Those harness errors were corrected before the final passing run; none is presented as a new application defect. The negative source test now independently copies the selected source.
- Python Ruff, JavaScript syntax check, and `git diff --check` pass. No broad build, live model, native OCR, full gateway authentication, full race sweep, author review, or deployment was run.
- Requested Sol High switch could not be performed through the available tools; this report does not label this chat or its evidence as a Sol High run.
