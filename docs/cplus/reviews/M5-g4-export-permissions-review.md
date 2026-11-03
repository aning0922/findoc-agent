# G4 root export registration and permission review

**No reproducible P0/P1 was found in this bounded review.** No business repair is
requested on the evidence below. This is not whole-site or production acceptance.

Reviewed `45e706f` as included in independent checkout
`67ad3367e2cf13fe6b3a794b9da395b3a1f751f4`. At final comparison root HEAD was
`9455ebe33773063c2b4f1a99b00d460692a055ca`; all seven reviewed production files
matched byte-for-byte. Exact hashes and execution denominator are recorded in
`M5-g4-export-permissions-proof.json`.

## Registration and identity source audit

- `register_cplus_runtime` creates one TemplateRunService and ChartReportDraftService
  using the same statements, hybrid, identity validator, publication guard and
  synchronous commit check. It registers their routes/state before the single
  `register_exports` call. This review fixture invokes that root assembly once;
  it does not manually add duplicate G4 services or routers.
- `exports_v2/api.py` admits precisely `template_run_v1` and `chart_report_v1` in
  the shared Ref contract. `demo/policy.py` admits their explicit POST operations
  as native-operation routes. No new report list or provider is constructed.
- The shared report registry reads each leaf's immutable snapshots by both ID
  and owner. Revision is fixed to 1 and the canonical original payload SHA is
  checked before currentness can be downgraded. Display labels do not replace
  report identity or grant financial authority.
- Leaf create paths freeze selected sources, collection/cell refs and points.
  They retain source/receipt guards through the inner store COMMIT. Leaf read
  paths check owner before loading historical content and again after currentness
  checks. An old identity cannot acquire access by causing a source failure.
- Root G4 resolution rebuilds only the selected statement points, including current
  receipts, and compares them with the saved point snapshot. Changes downgrade
  display status; they do not rewrite the saved financial values or original SHA.
- Current export publication nests the root source guard, statement receipt read
  transaction and export writer transaction. Artifact GET resolves the exact
  domain/ID/revision/hash from the stored manifest, then returns immutable bytes.

## Independent executed tests: 8 / 8 passed

New file: `tests/test_cplus_g4_export_permissions.py`. Four cases are parameterized
over the two new domains, giving exactly eight executed tests:

| Case | template_run_v1 | chart_report_v1 |
| --- | --- | --- |
| Registry, original identity and stale boundaries | PASS | PASS |
| Source and receipt locks survive inner export COMMIT | PASS | PASS |
| Download re-resolves original domain; historical bytes remain identical | PASS | PASS |
| Expiry during actual file INSERT rolls back final publication | PASS | PASS |

Details observed:

1. Actual root ASGI creates a two-year cash template and a revenue chart draft.
   Shared registry lists each exact report_ref once and resolves its original
   snapshot. Wrong revision, payload hash and swapped domain are rejected.
   Old generation, expired identity and a distinct owner hash cannot resolve it.
2. Injected receipt changes and selected-cell numeric drift produce `stale`, while
   the original snapshot remains byte-identical. Old-generation identity is still
   rejected when receipt currentness is stale. These changes are controlled
   callbacks, not real human receipt creation or real financial approvals.
3. Under the actual current-export guard, a temporary export DB COMMIT completes.
   While the outer guard remains open, separate SQLite writer threads attempting
   source-company and statement-store writes both time out/roll back as blocked.
   This verifies the deployed rollback-journal mechanism, not arbitrary unsupported
   journal modes or filesystem mutation scenarios.
4. Actual CSV creation and GET succeed. After simulated receipt drift, historical
   GET returns the same bytes and ETag. Removing the exact corresponding leaf from
   app.state makes that file GET return structured 403; restoring it restores the
   same bytes. The reader does not bypass the domain resolver using file ownership
   alone.
5. A SQLite trigger expires the trusted fixture identity during INSERT into files.
   The pre-COMMIT check rejects publication; files count remains zero and the
   reserved operation remains UNKNOWN.

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest \
  tests/test_cplus_g4_export_permissions.py -q -p no:cacheprovider
```

Result: **8 passed, 5 existing PyMuPDF/SWIG warnings in 8.44s**. Ruff format/check
passes. Only this new test file and review evidence are committed; original G4
tests and root business code are untouched.

## Evidence boundaries

Tier: **UNIT_SYNTHETIC_REAL_ROOT_ASGI_TEMP_SQLITE_AND_FILES**. Generated synthetic
PDFs use the real source/statement/G4/export services and temporary SQLite. The
in-process ASGI identity marker and embedding adapter are controlled fixtures.
An empty legacy report catalog is supplied solely because the shared list also
enumerates legacy domains; it does not replace either G4 service or its store.

No real provider, credential, private budget ledger, human financial approval,
14540/14542 session, or original runtime was accessed. Root's real four-template,
chart-draft and browser-export execution remains separately owned evidence and is
not inferred from these eight tests. No new P2 product defect was established;
the absence of native/provider execution here is a declared review tier, not a
new completion requirement or permission gate.
