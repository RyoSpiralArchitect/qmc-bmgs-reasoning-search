# Allocation recovery result-package review

## Scope and chain

The original allocation experiment was approved at candidate3221d5f and
plan digest `d88244d33e61f83bf878e77e3827ae3633ca6db08adb7f846a64631310f361e9`.
It completed at operation35f3b1b:6,144 cells,10,240 branches,256 source clusters
and8 fixed seeds. The original run, plan, all56 source references, raw COMMIT,
cells and interrupted analysis fence remain byte-identical. The original
analysis completion/exit/progress and host restart trigger remain UNKNOWN.

Ryō delegated recovery-candidate selection and execution. This is recorded as
`delegated_candidate_selection`, not a fabricated personal approval of a
digest not yet presented. Candidate91e6460 added five files, without changing
the old480. Recovery manifest digest is
`26ed891bd45ac89577335029b01aec6bfacc38a483a69709a468b0a933fc780b`.
It freezes11,995 historical files,26 directory memberships and8 absences.

The first recovery qualification exited1 before tests because its temporary
AF_UNIX path was too long. Its records remain intact. Ryō explicitly approved
one separately recorded environment-only retry. With the short temporary
parent, candidate91e6460 passed1,775 tests in940.396s, skip0, exit0, and
`repository validation: PASS`; postflight passed with empty errors. This was
not another candidate, an unrecorded retry, or a scientific experiment.
The [qualification completion receipt](../qualifications/countdown_feedback_allocation_recovery_20261024.validation.json)
closes the candidate-time pending gate without editing that old snapshot.

## Completed recovery and arithmetic review

Recovery ran once from2026-10-23T17:18:15.752851Z to17:47:55.220187Z, exit0,
postflight PASS, no errors, equal before/after invariants. It started from cell
zero in a new slot and private runtime, not from unknown old progress. All
10,240 branches replayed byte-identically,6,144 branch prefixes and2,048 blocks
were checked, and the whole original reduction was reproduced. The captured
stdout equals the new6,489,859-byte summary, SHA-256
`56cc30618bd2ab1897f4ec6f1e677caf10fce631ae65d213d56a2cb5fa25d9ad`.
Summary digest is `c7bb6ba14b13fbaa480dba71ab40953724fc029fe0fc237ea2c9ce16dae40c76`.

Separate saved-evidence review checked all process/input/intent/start/helper/
manifest/log references,485 tracked Git bytes, the old480 invariant, all11,995
historical files/26 memberships/8 absences, predecessor failure and approval
references, and qualification receipt. Original C5/production slots remain
absent, as do the old analysis process receipt and old summary.

The detailed cache maximum3 is distinct from measured peak RSS435,879,936
bytes; no claim of constant total memory or proven reboot causation follows.

A stdlib-only arithmetic implementation re-read the authenticated raw events,
reconstructed every terminal/readout/error/work field, checked all saved
prefixes and allocations, and reproduced the full reduction including source/
seed strata, leave-one-out, exact rational source variance and fixed decision
rule. It exited0 with empty errors. It uses the prior observation's event
checker but does not import the experimental engine/reducer. This is not an
independent reviewer or extra replay. The observed primary is−17/2,048,
readout `NO_PRACTICAL_UPLIFT_SIGNAL`; all negative/secondary results, null winner
and scientific decision, fixed denominators and model caveats are retained.

## Result-package qualification

Completed: one full repository validation ran on result-package commit
`b01f3770a1065b23c8fa4a0c7e7b352107770517`, from
2026-10-23T18:12:23.483268Z to18:31:27.974513Z. The actual logs report
1,775 tests in974.056s, OK, zero skips, exit0, and final
`repository validation: PASS`. Postflight passed with empty errors and equal
before/after invariants. The short temporary parent and fresh private runtime
were preserved; the suite was not restarted.

The [result-validation completion receipt](../qualifications/countdown_feedback_allocation_recovery_20261024.result-validation.json)
records a separate read-only audit of all process/input/intent/start/helper/log
hashes,498 tracked Git bytes,12,036 protected files (including11,995 historical
files),32 directory memberships,8 absences,56 original source references and
10 same-byte raw/mirror pairs. The prior485 candidate files and480 original
files remain unchanged. Original analysis completion and restart cause remain
UNKNOWN; old completion records are still absent. The audit is not another
suite, scientific replay, experiment or independent-reviewer endorsement.

The subsequent completion commit changes only this pending section and adds
that receipt. It is a records-only commit, not another full-suite run. The
operations record's pending state remains a time-of-capture snapshot. Its
result-review reference resolves against this review's Git bytes at the tested
`b01f3770a1065b23c8fa4a0c7e7b352107770517` commit, not the later live file;
the operations record was not rewritten to match the completion edit.

Hosted checks and external review are separate. No CI approval, merge, new
experiment, C5/locked evaluation, provider execution or default promotion is
claimed. New allocation ideas remain proposals requiring a fresh plan.

## Artifacts

- [Observation and negative-result analysis](../observations/countdown_feedback_allocation_recovery_20261024.md)
- [Reproducible arithmetic check](../observations/countdown_feedback_allocation_recovery_20261024.py)
- [Operation chain and all capture references](../qualifications/countdown_feedback_allocation_recovery_20261024.execution.json)
- [Original interruption](../qualifications/countdown_feedback_allocation_recovery_20261024.interruption.json)
- [Preserved first qualification failure](../qualifications/countdown_feedback_allocation_recovery_20261024.qualification-failure.json)
- [Recovered summary](../qualifications/countdown_feedback_allocation_recovery_20261024.summary.json)
- [Full arithmetic diagnostics](../qualifications/countdown_feedback_allocation_recovery_20261024.diagnostics.json)
