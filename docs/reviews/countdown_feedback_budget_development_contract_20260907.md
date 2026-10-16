# Development contract/compiler: validation and boundaries

Date: 2026-09-07. Code commit:
`af6716e408eb3d27782e591d050527f80d746864`.
Base: PR27 merge `6a375be06c3d1da0fc3618f176264ca473291355`.

## Predecessor integrity

PR27's P1 integration risk was addressed with a committed-tree ancestry guard
and a history-preserving merge. Its original and corrected producing commits
remain ancestors of the merge. The P1 comment was answered and resolved.
After merging, the saved public 192-cell summary independently reverified with
all 96 prefixes and unchanged digest
`620871116058d135567706245d04264ef6d6035e82ad53049c967cada0189026`.
No historical receipt was relabeled or rewritten.

## New validation

- 20 focused contract/compiler tests: PASS.
- `python3 -B scripts/validate.py`: PASS for the 909-test suite, compilation,
  Ruff, artifact checks, receipt ancestry, frozen design, outside-checkout CLI
  checks, and existing v5 seal verification.
- The new CLI self-test also passed separately from `/tmp`, producing the same
  contract and synthetic schedule digests as the in-checkout invocation.
- All six pinned input files are hash checked, with missing/changed files
  rejected. Tests exercise revalidation of every input, including a late failure
  at the final summary snapshot.
- All six historical/public exclusion boundaries reject both full-task and
  source-multiset overlaps. The union remains 179 full-task / 167 source identities.
- Synthetic 192-cell closure, 96 complete budget-pair mappings, and 48 ordered
  four-arm blocks passed. The mappings cover every candidate cell exactly once
  in each pairing system; these are not observed event-prefix checks.
- Rehashed missing/reordered/altered cells, pairs, blocks and authority flags
  are rejected by exact regeneration. Candidate keys remain distinct from
  future production cell keys.
- Separate read-only checks rejected all three actual stored canary,
  diagnostic and dense-scale authorization files as schedule candidates.
- `git diff --check`: PASS. Existing package source, scientific design,
  preregistrations, public fixtures/receipts, results and authorizations have no
  diff from the PR27 merge.

The initial standalone temporary-file test encountered macOS's `/var` alias.
Only the disposable test root was changed to its resolved real path; the
production reader's no-follow requirement was retained. The corrected test and
full suite passed.

The contract digest is
`555018a2734587d417c71c7523f4420c3eec4a1ac47aa2d4fa4870f5feac4dce`.
The synthetic schedule-candidate digest is
`35761709902de870b3f78e76bb0651bea99dcaaef3cc754e66b24d6e3cbbbe98`.
No runtime/source-qualified execution receipt is claimed for either candidate.

## Interpretation and next gate

This round used local code inspection and automated negative tests, not a fresh
independent reviewer. It validates this contract/compiler layer only.

No new development task definition, solution witness, proposal, perturbation
point, search record, or outcome was materialized. The new self-test uses hashes
of labelled synthetic strings. The full repository suite separately exercises
existing public/synthetic fixtures; it does not run the new v6 cohort.

Production schemas are reserved names, not implemented or qualified protocols.
The production runner, analyzer, publication path, full authority verification,
fresh cohort generation/sealing, and exact reviewed authorization candidate
remain subsequent work. `STOP_REPAIR_NO_LOCKED_128_RUN` and the consumed prior
authorization stay unchanged. No performance or causal conclusion follows.
