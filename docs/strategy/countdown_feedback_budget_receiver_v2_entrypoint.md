# Receiver v2: reviewed entrypoint for the original replication

This additive entrypoint connects one already reviewed candidate to the unchanged
qualified coordinator. Its implementation task ends after source review, synthetic
tests and actual metadata-only preflight/check. It does not spend the study.

## Fixed identity and separate evidence classes

The only candidate digest is
`198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070`.
The exact promoted candidate is
`docs/preregistrations/countdown_feedback_budget_receiver_v2.authorization.json`,
159,005 bytes with SHA-256
`7adaeba09ffdc21f21a852ad047b1aa7e0914ec284063a3ce768d410147fbb5b`.
Its raw counterpart, preparation receipt and prior actual admission-verification
receipt remain byte-identical to the candidate evidence review
`667cc144ccb70073be8224a69b778f65107109da`.

The original `feedback_budget_confirmation_64_seed_26091301/v1` study retains
64 accepted source multisets, 1,024 cells, its sealed schedule, budgets, seeds,
output `artifacts/work/feedback-budget-replication-v7-20260913-a`, and original
fixed replication claim. No v2 replacement claim, output, candidate, cohort,
PUBLIC attempt, retry slot or caller-selected mode/path is provided.

Three evidence classes must not be conflated:

1. Synthetic boundary tests exercise mocked dispatch and adverse states.
2. Actual preflight/check attest source and reviewed saved metadata. They do not
   rerun genuine production admission or prove production execution readiness.
3. A later separately authorized run performs genuine admission again through
   the coordinator before consumption and production search. Prior admission,
   metadata checks, CLI existence and candidate integrity are not user consent.

The entrypoint source receipt covers only
`scripts/run_feedback_budget_receiver_replication.py`,
`tests/test_feedback_budget_receiver_replication_entrypoint.py`, and this policy.
It is separate from the frozen five-file coordinator closure and three-file
candidate-preparer closure. Neither is edited, replaced or requalified here.

## Freeze, preflight, review, check

First commit all three entrypoint source files. Use a fresh owned mode-0700
Python cache, absolute `PYTHONPATH` to this repository's `src`, and `python3 -P -B`
for each actual operation. Preserve source, HEAD and artifacts during operations.
Full lowercase 40-character implementation/review revisions are required.

`--preflight --implementation-revision IMPLEMENTATION` requires the frozen
implementation HEAD and unused original claim/output/summary. It authenticates
the original raw/promoted candidate, its reviewed preparation and admission
verification, saved PUBLIC evidence, source closures and output-parent binding.
It calls no admission, consume, generation or production dispatcher.

Promote the exact successful stdout receipt to
`docs/qualifications/countdown_feedback_budget_receiver_v2_entrypoint_20261001.preflight.json`
and commit the review. Run `--check --implementation-revision IMPLEMENTATION
--reviewed-revision REVIEW` in a fresh process. This rechecks reviewed source and
the exact preflight receipt, plus current unoccupied production slots. The
receipt's historic unused-claim observation does not assert current unused state
during later analysis. Both operations return metadata-only, not-authorized
statuses and zero replication search calls. Run the repository validator before
declaring implementation complete. Local review is not independent-agent or
human approval.

## Separate run, analysis and verification

Only `--run` accepts `--confirm-digest`. It requires implementation/review
revisions and the exact literal candidate digest, supplied after explicit human
confirmation of that digest. Do not populate it automatically from a candidate,
an earlier receipt or a general instruction to continue. No environment-derived
confirmation, default, abbreviation, retry or resume is supported.

The entrypoint revalidates its reviewed source, fixed evidence and parent, then
delegates exactly once to genuine `C.run(REPLICATION, fixed_path, supplied_digest,
review_revision, observer)`. The unchanged coordinator owns genuine admission,
qualified PUBLIC replay, original sealed-input reconstruction, exact candidate
revalidation, irreversible original claim consumption and exclusive publication.
The wrapper never supplies fabricated admission/inputs, patches coordinator
callbacks, consumes a claim itself or implements an alternative search loop.

Wrapper checks occur before dispatch, at progress callbacks and after return.
They do **not** add an atomic source check inside the coordinator's claim/commit
transaction or extend its qualified source closure. Source/HEAD drift during
admission or publication can therefore be detected after irreversible effects.
Preserve such effects and classify the result as failed/uncertain; no auto-retry.
Keep the checkout stable and do not edit or commit while a real run is active.

After a separately authorized run, `--analyze` replays committed evidence and
exclusively saves the fixed summary; `--verify` independently replays the saved
summary. Both require the same reviewed entrypoint/preflight, accept no digest
confirmation and perform no new replication search. They deliberately do not
require unused production slots, because the genuine original claim/output must
already exist. A valid coordinator summary is not proof of which historical
wrapper was invoked. Do not promote it as such. Neither operation authorizes
another run, a new cohort or locked-128 evaluation.

## Failure ownership and scientific ceiling

Any occupied name, including a dangling symlink, remains occupied. Never unlink,
overwrite, repair by replacement or silently adopt claim/output/summary state.
No generic wrapper error proves non-consumption: use unknown unless the genuine
coordinator supplies a known consumption outcome, or has successfully returned
from a committed run. An exception after that return reports consumed=true even
if post-dispatch source validation fails. Failed stdout delivery is delivery
uncertainty, not evidence of failed execution. Preserve every artifact and inspect
the original state before deciding any next action. There is no automatic retry.

Do not interpret metadata checks, mock commits or successful plumbing as a
scientific result. The PUBLIC negative numerical screen remains unchanged. The
original cohort is conditional on its solvability filter, not an unconditional
population sample. A future summary must retain distinct mechanical, resource
and semantic/scientific denominators. Do not change thresholds or search settings
after inspecting outcomes. Production execution requires a separate explicit
exact-digest approval; locked-128 evaluation remains unauthorized.
