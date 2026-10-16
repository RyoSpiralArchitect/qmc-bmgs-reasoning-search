# Receiver successor: bounded local implementation review — 2026-10-03

Scope: the three-file D1 source closure at
`200b1f8c2dae4214c1917c32a7ff981eaf978fe9`, the actual read-only inspection,
and its documented claim ceiling. This is a single-agent local review, not an
independent-agent, external or human approval.

## Result

No unresolved actionable issue was identified within this read-only slice after
the corrections below. This is not a conclusion about an unimplemented
reconstruction, proof publication, admission, coordinator or production path.

## Findings addressed before source freeze

1. **Durability effects in the old archive reader.** `B.Archive` calls
   `S.base._observe`, which forward-syncs files and its directory. The new
   `ReadOnlyArchive` owns a no-follow, bounded, private/owned, complete-generation
   read without forwarding those effects. Tests prohibit fsync and the old reader.
   The older design inventory is consequently not described as fsync-free.
2. **Evidence drift during final source checks.** Revalidation now brackets the
   source checks with immutable-evidence/current-location reads; it retains the
   inspection-entry HEAD, rather than sampling an initial HEAD after attestation.
3. **Comparator serialization and fixture permissions.** The first captured
   focused run reported 8 errors: the canonical object parser was incorrectly
   used on a list, and positive archive fixtures lacked required mode0600.
   The list is now copied inside a canonical object and fixtures have the correct
   permissions. The dedicated missing/extra/link/generation cases continue to
   reject for the intended restrictions.
4. **Receipt overclaim surface.** The inspection has a closed envelope, exact
   source/anchor/epoch registry and explicit non-authorizing ceiling. Unknown
   fields, boolean/numeric aliases, altered source closure and reconstruction or
   execution assertions reject. Schema validation remains only a comparator;
   it does not authenticate caller-supplied observations.

## Adversarial boundaries checked

- Separate E0/E1 ownership; missing/duplicate/reordered/extra chains; exact epochs;
  all component identities and shared prefixes; no invented historical bundle.
- Reviewed COMMIT→STARTED authentication before reference access; fixed control
  paths; exact reviewed Git bytes, including self-consistently rehashed tampering.
- Archive closure, hardlinks/symlinks, bytes and same-byte generation changes;
  old PUBLIC source/review/auth/claim/fence/summary linkage.
- Complete original seal/scientific projection and generation qualifier, not
  count-only or digest-only permission to replace scientific inputs.
- No injected proof, callback, input adapter or effectful CLI; selected dependency
  replacement fails. AST inspection found no direct calls to the prohibited old
  admission/replay/search/publication/consume/fsync operations.
- Pre-consumption occupied names retained, including dangling links; separate
  exact existing-claim comparator, not perpetual claim absence for later analysis.
- Source/HEAD/current identity drift, unknown or consumed failures, output-delivery
  failure, old/general approvals, missing source entries and cross-mode bindings.

The policy explicitly maps T01–T22 and distinguishes functional implementation
from interface rejection around deferred operations. Thirty passing tests and
one genuine inspection are different evidence types. The actual observation
matched 16 reviewed anchors, 11 chains, 6 roles and both complete PUBLIC archives,
without numerical replay or any effectful operation.

## Residual limitations and unmet gates

Source/descriptor checks are process-local and non-atomic with arbitrary host
mutation. The dependency guard is not a sandbox against a caller who controls
Python globals or the interpreter. Runtime/baseline and numerical reconstruction,
current admission, exact-new-digest consent and a new coordinator are not
implemented. No mocks/static results or old PUBLIC success can qualify them.
The old entrypoint remains rejected on this receiver; it was not retried.

Fresh full repository validation at the frozen implementation exited 0: **1,370
tests passed in 836.886 seconds, zero skips**, followed by successful artifact,
provenance and CLI checks. The final repository marker was PASS. The captured
validator transcript is complete (no tool-output omission); its byte count and
SHA-256 are retained in the operations receipt. This is regression evidence,
not receiver reconstruction or scientific performance evidence.

All old bytes/modes remain preserved. No source or authority namespace was
relaxed to get a passing inspection. No experimental search, new cohort,
certificate/candidate issuance or consumed claim was introduced.
