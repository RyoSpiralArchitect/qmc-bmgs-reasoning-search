# Current-receiver successor: bounded local design review — 2026-10-01

Scope: design and review only, based on the actual code and read-only retained
evidence. This is a single-agent review, not an independent-agent, external or
human approval. No project instructions were hidden, no production source was
edited, and no proposed successor behavior was executed.

## Verdict and ceiling

The proposal is coherent enough for a **bounded read-only implementation slice**.
It is not an implemented verifier, accepted current-receiver mapping, successful
re-attestation, new orchestration qualification, candidate or execution authority.
The original v2 preflight remains failed and the original study remains unspent.

The first implementation slice should contain fixed historical inspection,
epoch/chain schema and provenance validation, source-bound read-only interfaces
and synthetic rejection tests. No certificate/candidate publisher, consumption
or experimental dispatcher should be exposed in that slice. The later actual
reconstruction and effectful phases need explicit, separate scope.

## Design hazards found and addressed

| Priority | Hazard | Evidence and design resolution |
| --- | --- | --- |
| P1 | Parent-only remapping leaves old admission and PUBLIC checks failing | `C.admit` checks its parent, calls `qualified_public`, then genuine `B.admit`; `S.inspect` compares recorded publication identities. Use a separately owned successor, not a wrapper/global patch. |
| P1 | Treating all history as one old device either rejects valid history or admits a broad exception | Inventory found 3 E0 chains and 8 E1 chains. The original certificate records E0→E1. Check E0→E2 and E1→E2 independently with closed ownership and shared-prefix constraints. |
| P1 | Valid hashes or a certificate projection could be mistaken for genuine current proof | `B.certificate_projection` explicitly says metadata is not proof; `B.reconstruct` performs environment, replay and original acceptance verification. New proof must likewise arise only from the complete real path, never fake old objects/callbacks. |
| P1 | Reusing v2's PUBLIC success for newly added execution code misstates qualification | v2's five-file source closure does not contain a successor. Require a separately scoped full PUBLIC run and independent saved-summary verification for any new coordinator. |
| P1 | Replacing the original generation reference silently changes the study | `B.verify_original_seal` compares the complete original seal, admission context and generation qualification. Preserve that reference, all 64 accepted sources and the complete schedule/acceptance/rejection order. |
| P1 | Permanent unused-claim or immutable-ledger-membership checks make post-consumption verification impossible | `C.analyze` and storage inspect the persisted exact claim. Separate immutable old records and directory identities from expected step-specific ledger additions; pre-consumption absence is not a permanent certificate invariant. |
| P2 | Inferring unrecorded historical bundle identities invents provenance | The old three-file bundle COMMIT binds bytes, not a historical directory chain. Use a current-only bundle snapshot and exact reviewed bytes; no fabricated E0/E1 identity. |
| P2 | A live inventory could accidentally become an activation or re-attestation receipt | Inventory has an explicit design-only status, false mapping/authority flags, zero experimental search and no numerical replay. New candidate/certificate/publication paths are not allocated by this proposal. |

These are hazards in proposed approaches, not claims that the old strict checks
are bugs. Their continued rejection of E2 is correct under their frozen policies.
The design addresses them, but only implementation and actual qualification can
establish that a successor enforces them.

## Adversarial pass over the proposed contract

Reviewed the positive path against missing chains, mixed device epochs, changed
inodes/prefixes, historical reference redirection, missing/extra archive files,
tampered claims/fence, rehashed unreviewed artifacts, old-object injection,
partial replay, changed generation references, changed scientific projections,
source-closure omissions, occupied slots and uncertain post-consumption effects.
The design specifies T01–T22 to cover these cases. They are **planned tests**, not
implemented or passing successor tests. No claim of independent implementation
or resistance to a malicious host/process is made by this static review.

The source-qualified runtime must preserve source/HEAD and live evidence for the
whole operation. Revalidation around publication cannot make arbitrary Git/source
changes atomic with filesystem consumption; unknown/consumed effects must survive
failure. This limitation is explicit rather than hidden by a wrapper progress hook.

## Read-only evidence inspection

Two inventory passes were performed. The second adds exact raw v1 bundle closure,
its deterministic historical candidate projection and final current-directory
revalidation. The first source/output is retained locally; neither pass performed
numerical replay, fresh admission, certificate/candidate publication or any study
search. This was not a retry of the failed production entrypoint/preflight.

The final pass authenticated 12 reviewed JSON anchors, 11 recorded location
chains, both 1,027-file PUBLIC archives, the original three-file cohort and raw
three-file bridge bundle, and all three prior ledger records. STARTED hashes were
checked against reviewed COMMITs before following authorization/claim references.
The v2 fence was checked using its exact deterministic expected payload, without
calling a consume path. Immutable snapshots/archives were revalidated after reads.

Observed archival correspondence is 16777233→16777234 for E0 and
16777231→16777234 for E1. The prior 16777233→16777231 certificate is untouched.
Paths and inode numbers match. This does not prove the same physical disk, explain
why the device number changed, accept the mapping, or grant execution permission.

No unresolved design issue was identified within this bounded scope. Remaining
implementation and actual-evidence gates are deliberate, documented and unmet.
Regression-validation and packaging results are recorded separately in the
operations receipt; no previous PASS is reused as a new successor result.

Fresh full repository validation at baseline
`04114aee55d97b96d437ba49a9b1ef24898e9504` exited 0: 1,340 tests in 823.850
seconds, zero skips, plus compile, lint, artifact/provenance and CLI checks.
The final preservation observation found all 341 old tracked files byte- and
mode-identical and all original production slots absent. This validates the
unchanged implementation only; it does not execute the proposed successor matrix.

Packaging identified a tool-output truncation of 7,542 middle tokens in the
captured validator log. The final unittest summary, repository PASS and exit 0
were delivered and retained. The operations record marks this capture as partial;
it does not claim an intact per-test transcript or reconstruct omitted text.
