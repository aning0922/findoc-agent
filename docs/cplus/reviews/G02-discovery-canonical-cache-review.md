# G02 independent public announcement cache review

Base: `dd8cca7`. Worktree: `findoc-discovery-canonical-cache`.

## Confirmed defect and saved evidence

Read the controller's `data/showcase-local-controller-v1/discovery-private.sqlite`
using SQLite `mode=ro`. No owner, principal, session, ticket or private candidate
identifier was copied into this review. No live browser/session, network request,
model call or runtime write was used.

The saved Chinese Haier 2025 full annual report has public announcement ID
`1225038336`. After removing per-search candidate ID/timestamps/version digest,
the code-search and pinyin-search snapshots differ only at
`security_identity.match_type`:

| Query match | Old version digest |
| --- | --- |
| code_exact | `e3bcf95402585830d7722b7fa1fdf6662fea78ca838c9c5b510fa92306029203` |
| pinyin_exact | `1c5d7721c1df6e68103e6c4bce66233c04e6a42d63a8fd7c53bbd860a15af3aa` |

Saved successful imports include a code-search cold miss, a repeated code-search
hit, and a pinyin-search cold miss. All three have PDF SHA-256
`14186f9f9b47f687c527ba14825664f3b09e51759d581636cddcc248f26e3660`.
This identifies unnecessary repeated public download, not failed import.

`CNInfoProvider.announcements` correctly keeps the selected security's match hints
in its candidate provenance. `DiscoveryService.post_search` previously hashed
the entire raw announcement into `version_digest`; the broker uses that digest
as its public cache lookup key. Thus query match strategy split one public version.

## Minimal correction and boundaries

`announcement_version_digest` copies the raw announcement and excludes only
`match_type` and `pinyin` from its nested security identity for public version
hashing. All announcement metadata and other security fields remain included.
The provider payload is retained. The separate immutable candidate digest still
covers the complete snapshot, match hints, public version and private tokens.

Read-only recomputation over both actual saved raw snapshots yields the same
new version digest:
`d061a6d0be6c2f5a5be97731a7c7ba26dea8c922acf7f56f15226049be7e41de`.
No historical receipts or public cache rows are migrated or rewritten. A new
version-key lookup can cold-download once after deployment; subsequent new
snapshots of that unchanged public report reuse the canonical entry. Existing
operation replay and old immutable candidate/ticket semantics remain intact.

Public/private boundary source audit: the broker publishes only bytes downloaded
from the authorized official URL after ticket checks and cover validation. Its
cache hit revalidates content hash and cover identity. The private binder still
runs for each separately authorized import; neither private uploads nor child
document/collection caches are consulted or inserted into this public cache.
No broker, upload route, frontend, seed or launcher code was changed.

## Verification

- Regression reproduced before the fix: code search then pinyin search produced
  `cache_hit=false` on the second import.
- After the fix, code/pinyin/Chinese-name searches preserve their different match
  hints and full candidate digests, produce one public version key, download once,
  and independently invoke the private binder three times. Bad candidate digest
  imports are rejected.
- Fourteen metadata/identity changes (including report year, language, revision,
  PDF locator/URL, publication date, security code, exchange, organization and
  support status) retain distinct version keys.
- `pytest tests/test_cplus_discovery.py tests/test_cplus_public_cache.py -q`:
  **18 passed**, five existing PyMuPDF/SWIG deprecation warnings. Existing cases
  cover generation revocation, UNKNOWN no-replay, wrong cover, private identity
  absence in public DB and official download boundaries. Ruff and diff checks pass.

Evidence level: saved real receipts plus source audit and controlled regression
tests. This is not a new live browser cache-hit observation.

Additional observation, outside this cache-key repair: `_security` orders only
by expiry. Multiple snapshots whose expiry is capped by the same short owner
lease can tie and select an earlier matching security snapshot. The new test uses
a lease longer than the 1800-second candidate TTL so each query has a distinct
expiry and exercises the intended three match strategies. This tie does not
explain the saved real cache split, whose snapshots explicitly show both matches.
