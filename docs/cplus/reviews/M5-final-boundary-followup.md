# M5 export permission follow-up

**Disposition: the previously reproduced export-download P1 is closed by the
reviewed repair. No new P0/P1 was found in this narrowly scoped follow-up.**

Reviewed root WIP based on `e6726c68d159550192ef07753cd81eae3aeb9525`.
During validation root committed the repair as
`47e5d233d37991e911497727a4aed42f7e34e13e`; the observed root HEAD then advanced
to `d303a4e37b11db450fe7e52d3b3d353a57b93176`. The observed `app/cplus/exports.py`
SHA-256 before and after validation was unchanged:
`7693be976d8a50898ae1fe141e6a7ef04ad90cfd5f99bd3bfed94d27c9ab5dc9`.
The reviewed root test SHA-256 was
`0c5c2658880e6783f253eb530b9c8a1ad3e945de9fb65a12e6f7dea429d2154f`.

## Source review

The injected artifact reader is now asynchronous and resolves the manifest's
exact `domain`, `id`, `revision` and `payload_sha256` before allowing bytes to be
returned. Existing domain resolution performs owner/parent/job display-access
checks before accepting historical source state. Resolution failures become
`ExportError('display_permission_denied', 403)`; the router produces a structured
denial instead of exposing saved content. Identity checks surround resolution.

The reader does not generate a new export, choose a later version, call a model
or invoke the renderer. The immutable file service continues to return the stored
bytes and ETag after its integrity check. Source staleness which the resolver
explicitly permits remains a historical read; parent permission denial is not
converted into that stale fallback.

## Executed verification

Ran root's `tests/test_cplus_export_permission.py` read-only against the actual
root module, plus an independent adaptation written in a new temporary directory.
Pytest cache and Python bytecode writes were disabled. Both cases used the actual
root export wiring, in-process ASGI HTTP requests, temporary SQLite operations,
and an actual CSV renderer. Source, parent permission and identity were controlled
fixtures; no running application session was used.

The independent case additionally injected a source guard failure and replaced
`asyncio.create_subprocess_exec` after initial export with a function that raises
if GET tries to rerender. Observed:

| Condition after successful CSV creation | Result |
| --- | --- |
| Parent display permission revoked | HTTP 403, `display_permission_denied`, no artifact body |
| Permission restored | HTTP 200, original bytes and ETag |
| Source guard reports `source_changed`, permission valid | HTTP 200, original historical bytes and ETag |
| Source stale and parent permission revoked | HTTP 403; no stale permission fallback |
| All download attempts | No renderer invocation; operation IDs/states unchanged |

**2 passed in 1.42s.** The temporary fixture was removed automatically. The
production source hash remained identical across execution. The older
`M5-export-permission-proof.py` records the pre-fix reproduction and is not a
post-fix success test; its old expectation is superseded by this follow-up and
the root regression test.

This closes the controlled root-wiring finding. It does not claim a new native
Chrome parent-deletion flow, provider call, or production acceptance. No real
ledger, credentials, provider, 14540 session, root business code or root tests
were modified. This follow-up introduces no broader gate or additional
hypothetical findings.
