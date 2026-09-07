# PR27 P1: preserve receipt ancestry

The [P1 review comment](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/27#discussion_r3940781928)
identifies an important integration constraint: squashing evidence-bearing
commits loses the ancestry required by source attestation, even if every final
file is byte-identical. Regenerating a receipt before another squash would not
remove that constraint.

The reported sibling relationship is not present in the actual PR history.
Local Git and GitHub's commit API both give `d63980cf715788d0e8062afb9ceb58bb6fef1dc0`
as the direct parent of the reviewed `9ce996f5f8e6a4d19dd635b0135b8560b5bdaedc`.
It is also an ancestor of the later `d1d2c2d9da741a8440415fc176fea561a6aaf548`.
The comment's `5820cdb5` object was unavailable both locally and through the
repository's commit API; its origin is unknown.

The resolution is to preserve the producing commits with a normal merge and
add a download-free committed-tree ancestry guard to repository validation.
Real disposable Git graphs cover a valid descendant and merge commit, an
identical-tree squash, a sibling, a missing object, malformed/noncommit OIDs,
inconsistent nested revisions, missing/nonregular receipts, and shallow history.

No historical receipt, trace, protected search/qualification executable, frozen
design, STOP decision, or authorization is changed. The guard checks retrieval
and ancestry only. Existing source/runtime attestation and independent replay
remain mandatory for operational verification.

## Validation

At correction `8ac7c2bb9562c2b30960f20145de0f21ebf95629`:

- The 13 ancestry regression tests passed; repository validation passed all
  **889 tests** (`Ran 889 tests in 434.734s`), Ruff, artifact checks, outside-root
  CLI self-tests, and the existing v5 seal verification.
- The guard passed on GitHub's candidate merge
  `25d2dcca5292a99223b1a0d60ad4598aea0fcdd8` as well as the PR head.
- Independent verification of the corrected 32-trace receipt passed, retaining
  digest `3ccc94562e01dea7a733e31b7bfa855c28416a3f180d5096b89adf0bedea9d3c`.
- Independent saved-summary verification of all 192 public cells and 96 budget
  prefixes passed, retaining digest
  `620871116058d135567706245d04264ef6d6035e82ad53049c967cada0189026`.
- Tracked historical evidence hashes and protected executable bytes are
  unchanged. No v6 development task was generated or executed.
