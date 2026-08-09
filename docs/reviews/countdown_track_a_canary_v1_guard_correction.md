# Countdown Track A canary v1 guard correction

## Decision

The version-one canary seal is retained unchanged but is not executable. It was
superseded by version two before any of its 936 sealed search cells was opened.
This is an outcome-blind budget-envelope correction, not a method or task
change.

## Pre-outcome reproducer

The source-disjoint non-canary fixture uses Countdown `(1,2,3,4,5,6)->720`,
task fingerprint
`5e520a1fff11e557075c5e72ae5a68376e4bdc5e2778fe4191b2c2a1cce698e6`,
the heuristic proposal, candidate IID Thompson, and exploration seed `7168`.
That fingerprint is absent from the sealed 12-task cohort.

With the version-one score256 limits, accepted work reached 227 legal-action
scores and 227 perturbation coordinates. The next state had 53 legal actions.
The atomic next-step preflight therefore saw:

```text
legal remaining       = 256 - 227 = 29
coordinate remaining  = 257 - 227 = 30
attempted vector width = 53
blocked axes           = legal_action_scores, generated_perturbation_coordinates
budget_valid           = false
```

The canonical reproducer trace SHA-256 was
`14de780153b4f50e16baf09c949904773a4ae1ed76f4c241a3a9d05b24b59094`.
This trace is test-derived and is not persisted as a canary result.

## Corrected structural envelope

The primary limit remains exactly 256 accepted legal-action scores. A complete
next action vector has at most 60 entries, so a non-primary coordinate guard
must admit `256 + 60 = 316`. Proposal scores use 317 to retain one strict unit
after the same structural maximum. Proposal-state evaluations use 87: at most
85 accepted selections, one possible next cache miss, and one strict unit.
The remaining score256 guards and the entire verifier8 profile are unchanged.

The same non-canary fixture under the corrected envelope stops only on
`legal_action_scores`, reports `primary_budget_blocked`, and keeps
`budget_valid=true`. Its canonical regression trace SHA-256 was
`6df057f51423cfcf99c5b852308613bfb05ab47f107df1f5caf84461e567b0f6`.

## Identity and claim boundary

Version one remains at
`docs/preregistrations/countdown_track_a_canary_v1/` with aggregate seal
digest
`6d3d6249141bc74e827ca0fcdf860656e5f0885d043607b80b5d9919edc30b78`.
Version two is separately materialized and sealed. Its changed budget digest
propagates through every cell identity, schedule digest, preregistration, and
aggregate seal. No version-one outcome is reused, translated, or compared.

This correction supports only the statement that the intended primary-only
stopping contract is structurally executable. It is not evidence that any
search method succeeds, that one method is stronger, or that IID and Sobol
differ.
