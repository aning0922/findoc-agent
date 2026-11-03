# Batch AI-plan disclosure follow-up

Reviewed root WIP over observed HEAD `705bc91c2892e3192d4f2354e9fa4cf24a04cce1`.
Actual React source SHA-256 was unchanged during the fixture:
`b66a2fbea0f2174c0796e08c574eceb6e53ed38685a8ed3e4edce1ba19c82fb9`.

**The original P1 is FIXED:** recovered AI plans now display their saved mode and
upper bound, and missing/conflicting AI metadata prevents approval. One explicitly
promised legacy pure-tools compatibility case still fails; this is not a renewed
paid-operation disclosure P1.

## Independent actual React results

Used the same isolated browser/Vite approach as the original reproduction, with
four synthetic saved-plan responses and no real backend. Temporary cache/config
and browser were cleaned up. No provider, credentials, ledger or live root ports
were used.

| Case | Expected | Observed |
| --- | --- | --- |
| Saved AI plan, four true prepared flags, upper bound 4 | Checked read-only AI control, at-most-four disclosure, original plan approval | PASS; confirmation says 最多 4 次 AI 解释 and approves the same ID/revision/hash |
| AI prepared flags but missing limits | No zero-cost fallback; approval disabled | PASS; explicit metadata-unverifiable message, no POST |
| pure_tools mode contradicts true AI prepared flags | Approval disabled | PASS; explicit metadata-unverifiable message, no POST |
| Historical pure-tools limits object without execution_mode or AI flags | Preserve legacy zero-model approval | FAIL; approval remains disabled |

Evidence is appended as `M5-batch-ui-recovery-FIXED-proof.json`; the executable
fixture is `M5-batch-ui-recovery-FIXED-fixture.cjs`. It exits nonzero while any
expected compatibility case fails. The first three cases close the prior P1;
the fourth must not be reported as passing.

Original `M5-batch-ui-recovery-proof.json` and its reproduction fixture remain
byte-for-byte identical to the earlier committed versions. No old failure record
was replaced with a success record.

## Remaining P2: historical limits object rejected

Historical plans already contain `limits={max_cells:12, parallel_cells:1,
templates:[...], provider_calls_by_service:0}`. They lack the newly added
execution_mode/max_provider_attempts and their prepared cells lack AI flags.

Current `savedPure` permits an explicit pure_tools mode or **no limits object**.
Because the historical object exists, `!plan.limits` is false and the legitimate
old pure-tools plan is incorrectly blocked. This was tested with the historical
shape, not a hypothetical future protocol.

Smallest correction: recognize the known historical no-AI plan shape even when
its legacy limits object exists. Retain rejection of true AI flags with absent
mode/upper bound and contradictory mode/flags. Re-run the same four cases; do not
change the saved plan/hash or resend preparation merely to make recovery work.

## Root native evidence, separately attributed

Read root's `data/cplus-batch-live-controls-v1/result.json`. It records tier
`REAL_CHROME_SOCKET_HTTP_PUBLIC_PDF_BGE_LIVE_CANCEL_AND_OWNED_FILE_FAULT`, PASS,
provider_calls=0 and ten checks, including cancellation of three queued tasks
while preserving the active result, one missing source/three successful tool
cells, byte-for-byte PDF restoration and read-only history without redispatch.

Those are root's saved native results, not newly executed evidence from this
follow-up. The previous seven controlled cancellation tests were not rerun here;
this task was limited to the modified recovery disclosure UI.
