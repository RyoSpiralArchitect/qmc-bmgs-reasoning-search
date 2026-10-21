# Qualification portability revision

The original failed qualification and unchanged-main reproduction are retained
in their original files. Complete discovery there was 1,744 tests; failed
legacy class setups prevented 179 methods from running, leaving the reported
1,565. The historical inputs exist at the canonical local checkout. No other
computer or fabricated fixture is needed.

The user authorized a small portability remedy with regression tests and a new
freeze. `scripts/validate.py` now invokes a discovery wrapper. Its explicit
`QMC_BMGS_HISTORICAL_TEST_ROOT` option selects only the canonical root in the
old authorization. Before importing its eight historical test modules, the
wrapper checks the original 470-file PR30 tree and candidate equality for 469
unchanged files, including every historical test, production module and saved
document. The sole exception is the candidate validation entry point, which
is not imported by those historical modules. It remains required to match
the old Git blob in the mirror.

The prior tracked result-qualification receipt authenticates the inventory,
which authenticates all 5,329 protected files, directory memberships and absent
slots. No old receipt is relocated or rehashed. The eight unchanged modules
run the same 328 tests on byte-identical source at their recorded paths. All
remaining tests use the isolated candidate. Test identities and multiplicities
must match complete discovery; all failures and skips remain failures. The
mirror is authenticated again afterward, including when the test runner raises.
Original production admission, source attestation, path, inode, device and
digest assertions remain unchanged.

Eight new regression tests cover frozen-tree equality even when both copies
drift together, the narrow validator exception, path aliases and traversal,
protected byte/length/mode changes, missing or extra test identities, test
failure/skip propagation and post-exception revalidation. They passed locally.
The full expected count is now 1,752 = 1,718 + 26 + 8, with no allowed skips.
The authenticated eight-module reproduction passed all 328 tests in 78.453
seconds with zero failures, errors or skips; mirror checks passed afterward.

The initial plan stays at its exact original filename and bytes. A separate v2
plan binds the qualification revision; allocation policies, generation recipe,
fresh seeds, source exclusions, 64 clusters, 1,536 cells, 2,560 branches, seven
caps and analysis are unchanged. This is an operator review, not an independent
review. Full qualification of the committed v2 candidate is still required.
No fresh cohort generation or allocation study has happened. After successful
qualification the new exact candidate and v2 digest require human authorization
for one run and one separate-process complete analysis. PR #31 is not approved
for merge.
