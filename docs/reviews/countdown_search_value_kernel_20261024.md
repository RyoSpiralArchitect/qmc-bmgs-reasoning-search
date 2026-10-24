# Search-value kernel review, 2026-10-24

Scope: additive single-cell control/replay implementation and fixtures, following
merged PRs33 and34. This is same-agent source review and testing, not an external
or fresh independent reviewer, study result, or human execution approval.

## Findings and disposition

- The change preserves all existing source and evidence files. Four controls
  delegate to the original engine; tests compare complete inner bytes.
- The mean-off intervention changes only the mean's use in selection. It retains
  the original visit/mean/m2 updates and dense scale16 return. Constructed fixtures
  distinguish zero-mean equivalence, nonzero-mean selection change and remaining
  visit-dependent noise. It must not be described as disabling all learning.
- The new method cannot masquerade as a historical single16 trace: configuration,
  selection metadata and summary identities differ, and old replay rejects it.
  The metadata-only stage-one projection is limited to checking unchanged
  material/backups. Stage two actually executes the new policy and compares all
  bytes. Tamper tests rehash altered evidence before checking rejection.
- Proposal-internal work is reconstructed from materialized cache misses and
  cross-checked against a spy on the original heuristic. The record distinguishes
  duplicate root-action counts, uncharged internal work and audit overhead.
  This does not establish equal total compute or runtime performance.
- No generated cohort, study execution, new outcome-driven tuning, default
  promotion, C5/locked use, provider call or modification to an old attempt occurs.
  The current API is not the future sealed executable candidate.

No blocking issue was found within this implementation slice. Private-engine
integration and the metadata adapter are explicit maintenance risks covered by
the focused equivalence/replay tests; they need requalification if dependencies
change. The incomplete study harness/manifest is an unmet next gate, not claimed
complete by this PR.

## Validation snapshot

Focused validation:23 tests, zero skips, PASS; Ruff PASS. The fixtures use
previously used implementation tasks, not the prospective128-source
cohort. Complete repository validation is pending at this snapshot. A separate
completion receipt must identify the full-suite input commit and distinguish it
from any later records-only commit; hosted CI and external approval remain
separate claims.
