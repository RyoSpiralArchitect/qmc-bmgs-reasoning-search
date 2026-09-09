# Development-path public qualification: validation and limits

Date: 2026-09-10. Producing executable:
`117c9a98d6ab562cb087d8124df138f71922fa58`.
This extends PR28; PR28 remains open for review, not automatically merged.

## Executed and independently checked

The new public adapter executed the already excluded twelve tasks, four seeds,
two scales and two budgets. It stored all 192 cells in an exclusive local POSIX
publication, replayed the complete matrix, checked all 96 exact budget prefixes,
and reduced mechanism, errors and exact success in the frozen order.

Separate `--analyze-public` and `--verify-public` processes independently loaded
the same closed publication, reproduced the 32-trace baseline and all 192 search
records, recomputed the reductions, and produced/verified identical summary
bytes. Each process used a fresh private empty bytecode-prefix directory outside
the checkout. The new source, unchanged protected search package and frozen
CPython 3.13.13/arm64 CPU binary64 runtime were rechecked around analysis.

| Receipt | Digest / quantity |
|---|---|
| New public manifest digest | `29a9693a061ee6ac17bb2b7d6af362cceb85fd56568e2ea2ad13654c87f5bf6e` |
| Durable COMMIT digest | `3a523784181002e0dbe563aa8b1d583177eff9f757e0d1f43bc21e7d4401c5aa` |
| Execution receipt digest | `5821af32531db61bc238e540cb5349a88d47e5449da627fdec12d206c77b20f8` |
| Independent summary digest | `16788fa259223e5b6c41e931cc7176b3c9acf90345cbbb4f73218d6ab816163e` |
| Independent summary file SHA-256 | `9f1e216d2b24949e645e82e17f7244e56c8cd71d43bf42e2e69fbc66657afac2` |
| Independent summary bytes | 735906 |
| Publication closure | 195 files / 25254972 bytes |
| Replayed cells / exact budget prefixes | 192 / 96 |
| Four-arm blocks / task rows / success-pattern rows | 48 / 12 / 16 |

The local immutable publication is
`artifacts/work/feedback-budget-development-path-v6-20260910`; its separate
summary has the same name plus `.summary.json`. The COMMIT and complete summary
are tracked under `docs/qualifications/countdown_feedback_budget_v6_development_path_20260910.*.json`,
byte-identical to their local originals. The ancestry guard now also protects
this producing commit; a history-preserving merge is required.

All **192 search trace SHA-256 values match** PR27's corrected, independently
verified public full-shape summary. Only the new-domain outer records/bindings
and new ordered reductions differ. The 96 completion pairs remain 87 instances
of 2→4 and nine of 2→5 terminals. No search implementation, numerical method,
old outcome, authorization or frozen design was changed.

The reducer retains the public mechanism coverage (17 already-low divergences,
19 newly-high divergences, 12 no-divergence blocks) and all null/adverse cells.
This is **pipeline coverage on one source multiset**, not twelve independent
development sources or evidence of amplification. The public numerical screen
is false and `scientific_decision` remains null; it does not issue either a
development STOP or a development signal. No v6 development task was generated
or executed, and there were zero provider calls.

## Automated negatives and local inspection

Full `python3 -B scripts/validate.py` passed at receipt/ancestry commit
`afbf718f1b1fa392d440a36eb9261f63182c4b4d`: **953 tests in 518.817 seconds**
(the unit-test duration), followed by compilation/Ruff, artifact and ancestry
checks, all outside-checkout CLI self-tests and the existing v5 seal verification.
All 44 new-path tests and the earlier 20 contract/compiler tests passed; no tests
were skipped. The producing executable was unchanged. A further independent
verify from this receipt-bearing descendant also returned the identical
`16788fa...` summary digest. These are local checks, not a hosted CI or independent
review approval.

The focused checks cover immutable/strict public input reconstruction, complete
cell binding, rehashed last-cell identity/trace corruption, old384 rejection,
full-payload prefixes, outcome-redacted views, exact finite arithmetic, all seven
forbidden success patterns, unsupported or concentrated rescues, missingness,
no-overwrite storage, durable partial failure, non-countermanding commit
uncertainty, symlink/hardlink rejection, and late directory-entry injection after
the independent analyzer's last reduction.

The original 43 focused tests passed together after correcting test-fixture
mistakes: a charge mutation had selected an initially uncharged event, two tests
expected the wrong exception base class, and an injected post-fsync hook error
was correctly reconciled by the existing storage primitive. The final uncertainty
test instead injects failure at postcommit closure. The corrected fixtures do
not relax production validation. A further explicit old384 rejection test passed
separately. Input-object immutability and disabled CLI option abbreviation were
also fixed before the producing executable was committed and qualified.

This is local code inspection plus automated adversarial tests and separate
analyzer processes, **not a fresh independent code review**. The qualification
does not cover production authorization, real development tasks, remote storage,
reboots/power loss or hostile same-user behavior. See the
[implementation boundary and commands](../countdown_feedback_budget_development_path.md).

## Remaining gate

The shared computational path is public-qualified, but production cohort/seal
and exact authorization admission are not implemented. Review this patch and
qualification before implementing/qualifying that layer, then generate/seal the
frozen excluded cohort and review an exact authorization candidate. Permission
for a complete development experiment remains a separate gate. New executable
bytes require fresh qualification. The old `STOP_REPAIR_NO_LOCKED_128_RUN`,
consumed authorization and locked-128 boundary remain unchanged.
