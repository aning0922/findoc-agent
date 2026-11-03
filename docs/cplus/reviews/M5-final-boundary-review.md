# M5 final independent boundary review

Review base: `07d05b0` in independent worktree `findoc-m5-final-boundary-review`.
The production retrieval diff and its focused tests from `35a1922` were temporarily
applied for validation, then removed from this review branch. Root advanced to
`51b791e` during review; its export wiring is unchanged from the reviewed base.
Root's uncommitted frontend/docs, later experiment expansion and future commits
are not implicitly covered. This handoff changes only review documentation and
a controlled reproduction script.

## Finding: P1 — exported files bypass current parent display permission

**Trigger:** an authorized user exports a `research_answer_v1` linked to a parent
conversation; the parent's display permission is subsequently denied while the
same lease/owner remains valid; the user requests the already-created CSV/XLSX/PPTX.

**Evidence:** `app/cplus/exports.py:63-68` checks
`conversations.selection(parent_conversation_id, ...)` before allowing a new
research-answer export. However, its injected download `reader` at lines 134-136
only calls `validate(identity)` and returns true. `app/exports_v2/service.py:238-264`
correctly filters by export owner and invokes that reader, but therefore never
receives the domain-specific permission denial. Unchanged bytes and a valid lease
do not establish continuing permission to display the linked resource. The
existing M4 contract explicitly requires the per-GET trusted display-permission
check; immutable storage should not remove that check.

**Controlled reproduction:** `M5-export-permission-proof.py` uses the actual root
`register_exports` wiring, actual ExportService/renderer and a temporary SQLite/CSV
artifact, with injected source/identity/permission fixtures. It first exports and
reads a synthetic research answer, switches the parent permission callback to
raise 403, verifies that a fresh export is denied, then observes that the existing
file still returns identical bytes. Output:

```text
REPRODUCED: new export rejects revoked parent display permission; existing file returns identical bytes
```

Run from repository root:

```sh
PYTHONPATH=. python docs/cplus/reviews/M5-export-permission-proof.py
```

This is a reproduced root-wiring authorization gap with controlled permission
revocation, not a new real-browser parent-deletion test. The real conversation
repository has a deletion/tombstone path which denies selection; that complete
deletion-to-download route was source-audited but not executed here. No cross-owner
or cross-generation disclosure was reproduced.

**Smallest repair:** inject an async, read-only, domain-specific display-permission
checker for artifact GET, using the saved report_ref and original parent/job
association. Keep the exact stored artifact bytes/ETag; do not rerender, invoke
models, select latest, or turn source staleness alone into a permission failure.
Apply equivalent checks for linked `showcase_report_v2` job/parent access. Add a
root-wiring regression for permission revocation after successful export.

No additional reproduced P0/P1 was found in the bounded checks below. This P1 is
an existing local export authorization contract, not a new production gate.

## Retrieval integration and publication

The proposed change ranks the same candidate set before calling the original
verifier, then attempts candidates in deterministic score/evidence-ID order until
top_k are admitted or candidates are exhausted. It does not truncate to top_k
before rejection/backfill. Each admitted item still invokes fresh source/page
verification. Original context validation, post-provider evidence verification,
source/memory publication guard, and synchronous pre-COMMIT identity check remain.
Legacy dense cosine admission remains distinct from hybrid scores.

Focused tests cover rejected leading candidates, all rejected candidates, original
page gate, changed current source, actual temporary SQLite writer blocking, WAL
rejection, and lease expiry inside the final result insertion rolling back while
preserving UNKNOWN. Root assembly OCR replacement/history and source/artifact/
memory lock tests also passed. This validates mechanism invariants using fixtures;
it does not establish new live BGE latency or real-model answer quality.

## Existing 5 CNY allowance and disabled models

Source audit: C+ launcher requires an explicit existing shared ledger for enabled
providers; same-git canonical location, regular private file, cap exactly `5`,
and exclusion from seed/reset paths are checked. Runtime assembly repeats shared
ledger admission before provider construction. Reservation is committed before
the physical request, includes all existing reservations, forces SDK retries to
zero, and retains the full reservation on timeout/missing usage. Reopening does
not reset it. Usage accounting is conservative reservation, not observed billing.

Tests use new temporary fake ledgers only. Restart/exhaustion, immutable allowance,
same-repository reuse, symlink/hardlink/mode rejection and forbidden-reset-root
checks passed. No actual ledger, credentials, dotenv or account balance was read.
The retained documentation reports four physical C+ ReadTimeout/UNKNOWN attempts;
this review does not independently reconcile their cost or refund/replay them.

The normal disabled launcher supplies a dummy loopback endpoint and no budget
configuration. C+ root passes `None` provider callbacks to retrieval, annual diff
and checkup explanation when model is `disabled-no-calls`; batch uses those tools.
Root assembly tests produced `provider_unconfigured`/`unconfigured` and retained
real evidence fields with no AI interpretation. This is not a claim that every
legacy endpoint has a dedicated disabled response; legacy model paths were not
executed, and no provider-health or authenticated POST claim is made.

## Seed, artifacts and evidence truthfulness

Read-only verification of the actual root v3 seed passed: manifest
`d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d`,
42 listed payloads, all 43 bundle files including manifest hashed successfully.
The financial display artifact contains five series/ten points,
`financial_authority=false`, `human_approvals=0`. The GET route verifies manifest
and candidate hashes, source revision/content/parser/company/basis/page bounds,
and removes points from unavailable/stale series. These remain preset unconfirmed
candidates; no human financial acceptance is inferred.

Read saved root results in `data/cplus-interview-a-cold/result.json` and
`data/cplus-interview-a-cache/result.json`: the former records completed/READY with
cache_hit=false, the latter completed/READY with cache_hit=true and the same public
PDF SHA. Their tier is REAL_REACT_HTTP_PUBLIC_PDF_BGE_V3_SEED. This review checks
the saved receipts; the new-generation Chrome/socket/BGE execution is root's
evidence, not an independent browser replay. No 14540 session was used.

Actual `data/cplus-export-v3/real-peer.{csv,xlsx,pptx}` byte lengths and SHA-256
match its result.json. XLSX ZIP/XML has three worksheets and zero formula nodes;
PPTX has six slides. Print PDF SHA-256 independently observed:
`f069c8b30c2a421682d7c39007b42a285676aed25051ba118e5d2a4df213cf6b`.
This review did not render the new files or inspect every printed page. The older
M4 21-page PDF review is a different artifact and must not be applied to v3.
The point-memory result preserves a 2024 comparative period from the 2025 filing,
unconfirmed authority and sourced excerpts; it is not a model-success receipt.

## Executed validation and residual observations

With the proposed retrieval patch applied, ran:

```sh
python -m pytest tests/test_cplus_retrieval_verify_budget.py \
  tests/test_cplus_publication_fixes.py tests/test_cplus_shared_budget.py \
  tests/test_provider_budget.py tests/test_cplus_exports.py \
  tests/test_cplus_ocr_context.py tests/test_cplus_m3_integration_review.py -q
```

**26 passed**, five existing PyMuPDF/SWIG warnings. The separate export permission
reproduction also completed. New provider calls, human financial approvals and
real runtime mutations: zero. Only temporary fixtures and this review's files
were written.

- Documentation P2: `KNOWN_ISSUES.md` still describes M0 in progress and the M1
  publication defects as active, while those guards are fixed and exercised here.
  Update the status when folding the current handoff into root documentation.
- Unreproduced limits: no claim of provider availability, actual billed balance,
  all-format visual perfection, real-browser parent revocation, or complete legacy
  disabled-path coverage. These are evidence limits, not new P0/P1 findings.
