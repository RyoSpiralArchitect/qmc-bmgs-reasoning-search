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
