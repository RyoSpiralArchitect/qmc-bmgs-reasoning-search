# E4 receiver certificate design and review — 2026-10-10

Status: **DESIGN_ONLY — NO_CERTIFICATE_ISSUED**.

The certificate-only design and bounded local review are recorded. It packages
original-input and historical PUBLIC reconstruction evidence without creating
a production candidate or conveying execution permission. No new certifier,
publisher or coordinator was implemented in this task.

## Decisions

- Keep immutable historical E4 receipts, private live evidence captures and
  detached certificate bytes as three distinct objects. Only genuine fresh
  reconstruction may produce a live capture; a saved PASS cannot replace it.
- Leave E4's historical same-HEAD verifier unchanged. New operation HEADs are
  bound in separate verification/publication receipts; old c19db4a evidence is
  not relabeled as newly computed.
- Use a certificate-only bundle with certificate, verification and COMMIT,
  never an authorization candidate. The old bridge's prepare path is unsuitable
  because it creates a candidate too.
- Keep the original study/input/schedule/generation reference and both negative
  PUBLIC screens. New coordinator qualification and exact-digest production
  consent remain separate gates.
- Separate pre-consumption absence from later exact persisted-claim verification.
  The current E4 verifier is deliberately not a post-consumption analysis path.

The proposed schema has 12 top-level fields; the old observation's complete
23-key schema is partitioned into 16 fresh-equality fields and 7 immutable
historical-envelope fields. Strict nested schemas, complete canonical equality,
source ownership and partial/unknown publication effects are specified.
C-T01–C-T16 are **planned adverse cases**, not implemented or passing new tests.

[Detailed design](strategy/countdown_feedback_budget_receiver_e4_certificate_design_20261010.md)
and [bounded local review](reviews/countdown_feedback_budget_receiver_e4_certificate_design_20261010.md).

## Current read-only evidence

Baseline: `3a69f33121be244c21143979be0a04fe71cdac5e`.
All three E4 observation/verification/operations files match their complete
reviewed Git bytes; the observation and verification refer to the same c19db4a
source and 215556-byte canonical result. This checks saved evidence linkage;
the expensive reconstruction was **not rerun** here.

The six current E4 location chains still match device16777234. All 375 prior
tracked files / 80086741 bytes and full POSIX modes are preserved. Both retained
PUBLIC archives preserve 2054 files / 272846815 bytes, and both saved numerical
screens remain false. The original three-file cohort seal and three spent ledger
records are unchanged. Original output, claim, receiver-v2 summary and the old
failed entrypoint's success-receipt slot remain absent.

All five proposed proposal/bundle/mirror names are absent and **not reserved**.
No new PUBLIC attempt identity or production candidate digest was allocated.
The inventory is lstat/hash plus reviewed Git comparison, not numerical evidence
or a new descriptor-bound admission.

[Read-only inventory](qualifications/countdown_feedback_budget_receiver_e4_certificate_design_20261010.inventory.json).
Inventory digest:
`0fe57bcec2ea0a9c5237c65eeb0a0e3f3ccce67cf844a0b28fdc4dfcab6de13f`.

## Validation and limitations

Full local regression validation passed: **1484 tests in 860.034s, zero skips**,
plus compile, lint, artifact/provenance and outside-checkout CLI checks; final
`repository validation: PASS`, exit0. Launch observed at 2026-10-10 07:35:25 UTC;
completion observed at 07:52:57 UTC. The unchanged implementation was tested at
baseline 3a69f33121be244c21143979be0a04fe71cdac5e while new design-only documents
were prepared. This is local validation, not CI or new certifier qualification.

The complete retained log has 302486 bytes, SHA-256
`26502236ade2da8e30d0bb2c753276e215fd61cae93354709915781fcd482700`.
The final post-validation read-only inventory reproduced all inventory bytes
exactly, including protected-file modes and absent original/proposed slots.
[Operations and log references](qualifications/countdown_feedback_budget_receiver_e4_certificate_design_20261010.operations.json).

The first documentation consistency check found a prose counting error:
the old observation has 23 keys, not the draft's 24. The listed sets already
matched all fields without overlap (16 + 7). Corrected only the new design and
review prose; the failed assertion output is retained locally.
A later helper check initially omitted digits from its field-name pattern and
missed historical_e4; corrected the checker, not the certificate's 12-field
schema. That failed output is also retained. The corrected documentation check
passes the 23-key partition, 12 proposed fields, 16 planned cases and local links.

Regression fixtures include real PUBLIC kernel search/replay under synthetic
test bindings. Zero actual-study operation counts do not mean zero computation;
these fixtures are not a source-qualified new PUBLIC attempt or the original
64-source replication study.

Review is bounded same-agent review, not independent-agent/external review or CI.
Regression validation of unchanged code cannot qualify the proposed certifier
or publisher. No original numerical reconstruction, certificate/candidate
issuance, new PUBLIC exercise, replication-policy search, production cell,
locked-128 evaluation, push, PR or merge occurs in this task.

## Next gate

Implement and test the source-owned **read-only certificate verifier**.
After its source freeze/review, separately scope actual certificate proposal
reconstruction. Exact proposal review, a separately reviewed publisher and
fresh-process whole-certificate reconstruction precede exclusive certificate-only
publication. Only then proceed to the separately approved fixed new PUBLIC
integration qualification; production still needs its own exact-new-digest consent.
