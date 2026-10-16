# v7 explicit receiver re-attestation

This is an additive acceptance policy for the already sealed 64-task study.
It is not a device-identity repair, a new cohort, or an execution authorization.
All original protected executable files, receipts, candidate and seal remain
unchanged. The old runner continues to reject the changed physical binding.

## Fixed scope and acyclic authority

The original candidate and PUBLIC summary/COMMIT and three seal mirrors are
anchored to `b57b16ee107eddf07aa94bcf7b20763577aab3a8`. The numerical and
publication implementation remains qualified at
`91359c9327861210c03ad0bc4e267af240f4ec93`.

The order is bridge implementation commit -> original-evidence re-attestation
-> candidate/certificate review commit -> explicit exact-digest confirmation.
The bridge source receipt covers its own executable, tests and this policy;
historical source receipts do not pretend to cover those additions.

1. Check that the original fixed replication claim and output are unoccupied
   before any costly qualification, replay or recipe verification.
2. Read only exact reviewed historical bytes. Close all 1,027 original PUBLIC
   files, its authorization and consumed PUBLIC claim, and all three seal files.
   Hash every cell before any replay. Enforce no-follow, owned private directories
   and regular single-link files, size caps, closed filenames and stable snapshots.
3. Admit exactly one uniform device-number correspondence across every recorded
   path component in the original candidate and PUBLIC publication/authorization.
   Lexical paths and inode numbers must be unchanged. Bind the exact *current*
   PUBLIC/cohort/output-parent/ledger identities. This establishes a narrowly
   reviewed correspondence, not proof of a reboot cause or physical disk identity.
   Do not fabricate historical directory identities that were never recorded.
4. Independently verify unchanged historical identity authorities and runtime,
   run the original 32-trace PUBLIC baseline, replay all 1,024 original PUBLIC
   traces and 512 budget prefixes, and reconstruct the exact original receipt
   and complete saved summary. No old receipt is rewritten or relabeled.
5. Compare the seal's original generation-qualification reference with that
   reproduced PUBLIC evidence, then independently reproduce the exact original
   64-task acceptance order and rejection manifest. Do not use witnesses or
   hardness measures, search those tasks, generate a replacement cohort, or
   call the old loader with a substituted qualification callback.
6. Publish a separate closed non-authorizing certificate and candidate. An
   independent process reconstructs them from reviewed bytes. The new schema is
   deliberately rejected by the old runner. No old Admission/Inputs instance
   is fabricated and no module/global is patched in production.

## Execution and analysis boundaries

The new entry point requires reviewed candidate **and** certificate bytes,
reviewed source ancestry and explicit candidate digest. Its inputs are detached
immutable values produced only after full re-attestation. It reuses the unchanged
search, replay, reduction, durable claim and publication functions. Occupied or
uncertain claims/publications are retained; there is no resume, retry, reset or
namespace override. The original fixed study claim is the only replication slot.

Certificates bind identities of the output parent and ledger, not their mutable
mtime or permanent claim absence. Pre-consumption operations require absence;
post-consumption analysis instead requires the exact persisted claim and run
binding. Evidence directories remain immutable throughout. Any later device or
inode transition is rejected by the reviewed certificate; no automatic remount
exception is available.

Replaying original PUBLIC traces qualifies evidence reconstruction and the
unchanged numerical path. It does **not** prove a new end-to-end execution of the
bridge's orchestration. Boundary/fault tests and review are reported separately
from a real full-shape PUBLIC qualification and from replication. A candidate is
not a claim of execution or algorithmic superiority. The 64 task clusters,
1,024 cells, 512 pairs, 256 four-arm blocks, frozen thresholds and claim ceilings
are unchanged. No QMC/causal/population conclusion or locked-128 authority follows.

## Operator procedure

Use a clean checkout, a fresh empty owned mode-0700 `PYTHONPYCACHEPREFIX`, absolute
`PYTHONPATH` to `src`, and `python3 -P -B`. Do not modify the checkout during a
source-qualified operation. Each independent verification uses a fresh process
and fresh private cache. Run the full repository validator after code changes.

The bridge CLI has disjoint `--prepare`, `--verify-candidate`, `--run-replication`,
`--analyze-replication` and `--verify-replication` operations. Exact mode-specific
arguments are mandatory. Preparation never consumes a study claim. Promotion of
the three candidate-bundle files into the prescribed tracked locations is a
separate exact-byte operation. Review them at a new full commit OID before asking
for explicit candidate confirmation. Never recycle the earlier approval of the
original candidate as approval of the re-attested one.
