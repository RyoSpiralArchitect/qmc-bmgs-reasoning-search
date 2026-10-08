# Receiver E3: bounded local review — 2026-10-08

Scope: the three-file fixed-case E3 source closure at
`85f90035cdfa57f75393500cae72b2aba1e96e96`, one genuine environment
reconstruction, retained evidence, and the claim ceiling. This is a single-agent
local design/implementation review, not independent-agent, external or human
source approval.

## Result

No unresolved actionable issue was identified in this bounded slice.
This does not review or qualify an unimplemented PUBLIC replay projection,
complete receiver proof, certificate publication or execution integration.

## Corrections and diagnostic failures retained

1. **Final source-change window.** The first implementation checked HEAD before
   immutable evidence reads. Added clean-checkout and HEAD checks after those
   reads too, plus a rejection test for changes inside that interval. This detects
   observed drift; it is not an atomic sandbox against arbitrary concurrent writers.
2. **Static/failure overclaim surface.** Static output now says NOT_PERFORMED,
   rejected operations FAILED_INCOMPLETE, and only successful actual output says
   PARTIAL_ENVIRONMENT_ONLY. Environment interruption preserves unknown completed
   extent. After the whole environment comparison succeeds, later revalidation or
   output-delivery failure preserves 32 completed baseline traces but no admission.
3. **Test-edit error.** Adding metadata-closure tests accidentally moved an
   environment-fixture assertion loop into the next method. Ruff and an interim
   33-test run caught undefined `env` / NameError. Moved the unchanged assertions
   back; final 33 focused tests passed in 10.203s. The initial 31-test pass and
   intermediate failure transcript remain stored, as does the old E2 30-test pass.
4. **Post-operation digest diagnostic.** The first standalone receipt checker
   hashed the object payload with a trailing newline. The repository uses a
   newline for JSON file bytes, but not for the object-digest payload. Reading
   `core.with_digest` and `substrate.trace.sha256_json` resolved that diagnostic
   mistake. The corrected checker verified canonical bytes, the object digest,
   new source references and the entire saved environment. The successful actual
   operation and its observation bytes were never changed or rerun.

## Boundaries inspected and tested

- E0/E1 registry order, exact owning artifact/JSON fields, and direct comparisons
  to E3; E2's six observational chains checked independently, not transitively.
- Exact current endpoint32, fixed prior endpoint34, full paths/components, plain
  integer types, inodes, shared prefixes and closed roles; the old E2 comparator
  still rejects E3. No old source, globals, receipts or acceptance rules changed.
- Exact reviewed E2 bytes and fixed hash/length before parsing; old source
  linkage and the fixed 16-anchor metadata/PUBLIC archive closure remain genuine.
- All fresh historical-source, anchor, archive and sealed-metadata observations
  compared to the pinned E2 observation, in addition to current live file reads.
- Actual `R.environment(B.ORIGINAL_SOURCE)` called once after metadata/identity
  gates, every environment field compared to the authenticated original, and
  source/runtime/evidence/HEAD/unused slots checked again before return.
- No fake old Transport/Proof/Inputs/Admitted object, qualification callback,
  alternate path/device/consent CLI, forward-fsync archive reader, consume,
  publication, new PUBLIC or production dispatch.
- Known consumed versus unknown state, interrupted numerical work, late failure,
  dependency substitution, whole-environment mismatches, source closure and
  outside-checkout CLI behavior covered by the 33 synthetic tests.

The actual observation separately matched all 17 direct chains, both complete
retained PUBLIC archives and the complete original environment. It genuinely
recomputed the 32-trace matrix and matched its full baseline analysis. Unit tests
and static self-test are not the source of that numerical claim.

Full repository validation at the frozen implementation passed: 1,403 tests in
905.427s, zero skips, plus compile/lint/artifact/provenance/CLI checks; exit0 and
`repository validation: PASS`. The original 353 tracked files and full file modes
are unchanged. Genuine reconstruction, synthetic tests and local regression
validation remain different evidence categories.

## Residual limits

The selected-callable guard is not security against a hostile interpreter.
Filesystem/source checks are observations across intervals, not an atomic lock
against arbitrary writers. Matching paths/inodes/devices is this reviewed case's
metadata condition, not physical-disk identity or reboot causality.

The two retained PUBLIC archives have not been numerically replayed here; their
old success flags remain historical. The original 64-source acceptance order has
not been reconstructed. Current receiver admission, full D2 proof, certificate/
candidate issuance and new coordinator qualification remain unmet. No numerical
quality, causal, population or exploration-performance claim follows.

Next: explicit historical summary projections, genuine full PUBLIC replays,
exact sealed acceptance reconstruction, independent full-result verification;
then separately scoped proof publication/new integration qualification/candidate
review and exact-new-digest consent. No review conclusion here waives those gates.
