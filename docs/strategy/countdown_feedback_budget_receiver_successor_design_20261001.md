# Current-receiver successor: bounded design — 2026-10-01

Status: **DESIGN_ONLY — NOT_REATTESTED, NOT_AUTHORIZED_TO_RUN**.

See the [result and evidence summary](../countdown_feedback_budget_receiver_successor_design_20261001.md)
and [bounded review](../reviews/countdown_feedback_budget_receiver_successor_design_20261001.md).

The user approved design and review of a current-receiver re-attestation after
the v2 metadata preflight rejected the changed output-parent binding. This
document proposes a new, separately reviewed acceptance path. It does not activate
that path, implement it, issue a certificate/candidate, reserve a new PUBLIC
attempt, or approve any digest. All old code and evidence remain unchanged.

## Decision

Use an additive, narrowly scoped successor that separates:

1. **Historical byte and numerical evidence reconstruction.** Authenticate every
   old artifact and reconstruct its original result without rewriting its
   recorded locations or pretending an old admission succeeded on this receiver.
2. **Current-receiver admission.** Explicitly compare the named historical epochs
   with fresh descriptor-bound current locations, then issue a new non-authorizing
   proof only after genuine reconstruction completes.
3. **Qualification of a new execution path.** Any successor coordinator has its
   own source closure and requires an explicitly authorized fixed PUBLIC exercise
   and independent saved-summary replay. Old v2 PUBLIC evidence cannot qualify
   code that was not part of its source receipt.
4. **Production consent.** Only a separately reviewed candidate and explicit
   confirmation of its exact digest can reach the unchanged original study claim.

The immediate proposed next implementation slice is read-only inspection and
closed proof/schema validation, with synthetic adverse-case tests. It must expose
no preparation/publication, consume, PUBLIC-run or replication-run CLI. Later
slices need their own bounded scope and review; they are not authorized here.

Do not add a general device-ID wildcard, patch old JSON, replace old candidates,
or intercept the old admission/qualification callbacks. A new wrapper around
the unchanged `C.run` cannot solve the current mismatch: that call independently
rechecks the old candidate parent, old PUBLIC locations and old receiver proof.

## Live design evidence and its limits

Baseline: `04114aee55d97b96d437ba49a9b1ef24898e9504`.
The immediately preceding entrypoint implementation is
`4d419343d6a542a132d2336456000e9c638f1cc3` and its failed preflight remains a
failure. The new design inventory is a read-only observation, not a certificate.

The inventory inspected 11 recorded location chains and 6 current directory
locations. All recorded lexical paths and inode numbers agree with the current
receiver. It hash-closed two retained PUBLIC archives, each containing 1,024 cell
files plus STARTED, RECEIPT and COMMIT: **2,054 files / 272,846,815 bytes** total.
Their exact reviewed COMMITs, saved-summary linkage, authorization/claim bytes
and the v2 fixed fence agree. All three original sealed-cohort files agree with
their reviewed mirrors; the raw three-file bridge bundle also matches its reviewed
bytes and historical candidate projection. No numerical trace replay,
acceptance-order reconstruction, fresh admission, publication or search was
performed by this inventory.

This supports preservation and a design input only. Matching paths/inodes and
bytes does not prove physical-disk identity, a reboot cause, readiness, admission
or human acceptance of a mapping. Those claims remain false or unavailable.

## Three epochs, not one global substitution

| Epoch | Recorded device | Owning evidence | Required treatment |
| --- | --- | --- | --- |
| E0: original v7 | 16777233 | Original candidate and original PUBLIC STARTED/authorization | Preserve old bytes; compare these 3 recorded chains directly with E2 |
| E1: receiver and v2 | 16777231 | v1 certificate/current-locations, v1 candidate, v2 PUBLIC and v2 production candidate | Preserve old bytes; compare these 8 recorded chains directly with E2 |
| E2: current observation | 16777234 | Fresh no-follow descriptors, scoped to this one case | Bind exact current identities; not an accepted mapping yet |

The old certificate's E0→E1 mapping remains immutable historical evidence.
The successor must independently check E0→E2 and E1→E2. It must not infer the
current correspondence merely by composing the old mapping with one observed
output-parent change. A single global `old_device -> current_device` restriction
over mixed E0/E1 records would reject valid history or invite a broad exception.

For this case, the proposed allowlist is the exact epoch pairings above. Require
closed chain labels, their owning reviewed artifacts/JSON fields, exact lexical
paths, complete component counts, plain integer device/inode pairs, unchanged
inodes, and one uniform device transition **per epoch**. Shared path prefixes
must agree both within an epoch and at the current endpoint across epochs. Missing,
duplicate, reordered/relabeled or extra chains, boolean/numeric aliases, changed
inodes, mixed transitions, symlinks, hardlinks and generation changes reject.
Any later change from E2 rejects; there is no automatic successor acceptance.

The closed chain registry is:

- E0: original replication candidate parent; original PUBLIC authorization parent;
  original PUBLIC STARTED directory.
- E1: v1 certificate `current_locations` for original PUBLIC, cohort, output
  parent and ledger; v1 candidate parent; v2 replication candidate parent;
  v2 PUBLIC authorization parent; v2 PUBLIC STARTED directory.

The old bridge bundle has no authenticated historical directory identity in its
bundle COMMIT. Bind its **current** directory and exact historical file bytes;
do not invent an E0/E1 inode chain for it. Source and ordinary mirror directories
likewise require current snapshots and reviewed bytes, not fabricated historical
locations. Future code must use the closed registry, not recursively treat every
incidental `identities` field as the same kind of persistent authority.

## Immutable roots and unchanged scientific contract

| Root | Reviewed revision / source | Why it remains authoritative |
| --- | --- | --- |
| Original candidate, original PUBLIC summary/COMMIT and seal mirrors | `b57b16ee107eddf07aa94bcf7b20763577aab3a8` | Original study/evidence definitions |
| Original numerical/publication implementation | `91359c9327861210c03ad0bc4e267af240f4ec93` | Unchanged numerical and storage functions |
| v1 receiver implementation | `951d273ccf4072b8e0557970cc71095951b843b7` | Historical source, not current acceptance |
| v1 candidate/certificate/bundle COMMIT | `bf83efbaa94af3dc9b6863a19202acffa815ad74` | Exact prior proof and E1 locations |
| v2 shared coordinator | `c0b048e401d39802c46acd70060ad9af27b0a911` | Exact code actually exercised by historical v2 PUBLIC |
| v2 PUBLIC evidence | `ba51b631d6398d0813a36614b3d27821d019162e` | Preserved v2 execution and independent verification |
| v2 production candidate/admission evidence | `667cc144ccb70073be8224a69b778f65107109da` | Exact prepared-but-unexecuted candidate and prior admission result |
| Failed entrypoint and design baseline | `04114aee55d97b96d437ba49a9b1ef24898e9504` | Current failure must remain a failure |

The study remains `feedback_budget_confirmation_64_seed_26091301/v1`, with 64
accepted source multisets, 1,024 cells, 512 budget pairs and 256 four-arm blocks.
Preserve the original contract, full task/acceptance/rejection manifests, schedule,
seed hierarchy, scale/budget values, verifier/metric definitions and thresholds.
The cohort remains conditional on the existing solvability filter. Do not claim
that examined candidates are independent source multisets or population samples.

- Input manifest: `4a969fc46e506d2fc81e0b9a45c841bb8e27f81fb7190ff73abbd72d9fe284b3`.
- Schedule: `0da39f97a3bd1e6068d33dae9658c7c3656b3a76aa8854e0a4820683b622352b`.
- Seal: `b457706230403b6c2a7ccb1bd6f5ce7ef027bf45fc5fb49995825611ada53479`.
- v2 candidate: `198f4582054184e2e476542afc1621178b3a1fbc6b82bd002b67f99c6684d070`.
- Original production output: `artifacts/work/feedback-budget-replication-v7-20260913-a`.
- Original replication claim: `artifacts/work/feedback-budget-v7-authorization-ledger/replication-548114440db6e0fa49226e28d519fbe1c0f113d5edfe76f282e7ebc29c0bfc3c.json`.

New proof/candidate envelopes may change only explicitly reviewed provenance and
current-location fields, their schema/source references and derived digests.
All scientific fields require complete canonical equality against the original
projection. This is not permission to mint that envelope now. Keep the original
generation-qualification reference: replacing it with a newer PUBLIC result
would change the sealed study. No old consumption claim is removed or replaced.

## Ordered reconstruction contract for a future implementation

1. **Cheap scope gate.** Reject occupied original replication claim/output/summary
   before expensive work. Require fixed reviewed paths, full immutable revisions,
   ancestry, fresh private cache and unchanged qualified source. Do not consume.
2. **Authenticate references before dereference.** Reviewed COMMIT bytes must
   authenticate STARTED before following its authorization or claim path. Check
   complete closed filenames and hashes for both PUBLIC archives, all three seal
   files, the v1 three-file bundle, raw/promoted candidates, summaries and exact
   spent claims/fence. Authenticate schema/domain and linkage separately from
   content hashes. Retain original bytes; no rewritten historical STARTED.
3. **Bind current locations.** Capture immutable evidence with current no-follow,
   owned/private descriptor generations. Validate the exact 11-chain registry
   and both epoch correspondences. Snapshot all current locations, including the
   current-only bundle. Treat this as an explicit case acceptance rule, not proof
   of disk identity. Revalidate before and after later computations.
4. **Reconstruct original environment.** Execute the genuine frozen source/runtime,
   lower identity-authority and 32-trace baseline checks. Metadata comparisons or
   a well-formed saved certificate are not substitutes for these computations.
5. **Replay original PUBLIC.** Use genuine fixed PUBLIC inputs and unchanged
   replay/reduction functions for every 1,024 saved cells and 512 budget prefixes.
   Reproduce the full original receipt and summary byte for byte, with historical
   metadata retained as historical. Do not call an old current-location inspector
   with forged identities, callbacks, modules or admission objects.
6. **Replay v2 PUBLIC.** Authenticate its exact old authorization, binding, claim,
   fixed fence, coordinator source and v1 proof references. Independently replay
   all 1,024 cells/512 prefixes and reproduce the complete saved receipt/summary.
   Its historical `receiver_admission` references remain old bytes. The new
   replay result must never state that current `B.admit` or `C.admit` succeeded.
7. **Reconstruct original sealed acceptance.** With the original generation
   reference, reproduce the exact acceptance/rejection order and entire seal
   through genuine original recipe checks. This is acceptance verification, not
   experimental policy search, new cohort publication, witness/hardness selection
   or a changed sample. Compare the entire input projection, not just counts.
8. **Complete new proof.** Only the successful ordered path creates its own
   detached proof/inputs value. Revalidate source, evidence, HEAD, live locations
   and unused state before any later certificate publication. Independently
   reconstruct a reviewed certificate in another fresh process. A deterministic
   expected certificate template is a comparator, never a proof that steps ran.

Steps 4–8 have not been executed for E2. The design inventory performed only a
read-only subset of steps 1–3; hashes and observed correspondences are not admission.

Historical summary reconstruction needs its own explicit, reviewed projection
that takes authenticated historical metadata and freshly replayed numerical
results. It must not instantiate a fake old `Transport`, `Proof`, `Admitted` or
`Inputs`, pass an old certificate as a qualification callback, or assign to old
module globals. Reuse lower pure numerical functions and genuine PUBLIC loaders;
define the successor's own admission types and provenance. Do not alter any old
protected file to let historical current-location checks accept E2.

## Proposed proof boundary and source ownership

The successor verifier must own a closed source receipt for every added executable,
test and acceptance policy, separately chaining the unchanged historical sources.
A future coordinator must also own its own source closure; the current entrypoint
source receipt cannot cover either addition. Exact filenames and schemas must be
fixed at implementation freeze, before any actual generation or attempt approval.
No source digest, new revision, certificate digest or attempt is allocated here.

A proposed non-authorizing receiver certificate must include: closed schema/status;
the original study/claim identity; exact historical anchor byte references and
review revisions; successor implementation/source digest; separate historical
epoch correspondences; exact current location chains; complete reconstruction
receipt references/counts; the original sealed-input/schedule digests; and explicit
false execution-authority/locked-128 flags with zero experimental search calls.
Missing or unknown required fields reject; unknown physical identity/reboot cause
must not be converted to an affirmative claim. Independent verification must
compare the entire expected canonical certificate, not merely its self-digest.

PUBLIC records describe 64 task definitions from one source multiset. Their
1,024 rows are not 64 independent sources, and a negative numerical screen is not
erased by a new receiver proof. Keep mechanical integrity, resource accounting,
semantic quality, historical replay and new execution as separate denominators.

## State and effect ownership

| State | Evidence required to leave it | Effects allowed by that separately approved phase |
| --- | --- | --- |
| D0: design reviewed (this task) | Explicit implementation scope | Documentation and read-only observations only |
| D1: verifier implementation reviewed | Source freeze, negative tests, actual-operation scope | Read-only implementation/tests; no certificate from mocks |
| D2: new receiver evidence reconstructed | Exact certificate review and fresh-process reconstruction | One separately authorized exclusive proof publication; no search/candidate consent |
| D3: successor coordinator qualified | Reviewed source, explicitly approved fixed PUBLIC attempt, actual run plus independently verified summary | Only that new PUBLIC attempt; old spent fences remain spent |
| D4: production candidate reviewed | Full candidate/admission verification and explicit exact-digest human approval | Candidate metadata only; original study remains unspent |
| D5: original study consumed/committed | Authentic persisted claim/output plus independent analysis | One original study; no replacement claim, retry or new cohort |

This table is a proposed ordering, not a set of approved operations. D0 does not
skip D1–D4, and a later failure never automatically returns an effectful state
to an unspent state. New publication paths and the new PUBLIC attempt identity
must be fixed and reviewed before their authorization. No such path is created
or reserved here. Preserve the original replication output and claim exactly.

The unchanged coordinator cannot admit E2 because it calls strict old receiver
admission and the old PUBLIC inspector. Do not call it with substituted globals
or fake admissions. A new admission/execution integration is new code even if
its numerical loop is unchanged. Historical replay qualifies reconstruction,
not this integration. D3 therefore requires separate full-shape PUBLIC evidence;
it is neither optional nor already supplied by the old successful PUBLIC run.

Freeze source and HEAD during each qualified operation. The successor's genuine
proof revalidation belongs in admission and its own publication checks, not only
in an outer progress callback. Revalidate before consumption and before/after
publication, and preserve partial/uncertain effects. Checks around system calls
do not make arbitrary source changes atomic with the filesystem transaction.
Do not promise that detected drift can undo a consumed claim.

Bind evidence directory bytes and generations as immutable. Bind output-parent
and ledger **identity chains**, not permanent absence, parent mtime or forever-
unchanged ledger membership. The baseline three spent ledger records remain
byte-identical; only exact separately approved step-specific claim/fence names
may be added. Before consumption, require the original study slot absent. After
consumption, require the exact persisted owned claim and authenticated binding.
A proof that requires perpetual claim absence cannot support valid analysis.

On any mismatch, missing anchor, source/HEAD drift, uncertain publication or
occupied slot: stop and retain evidence. A known committed run remains consumed
even when later validation or result delivery fails. Unknown consumption stays
unknown. Never unlink, replace, adopt, resume or retry automatically, and never
change a digest or output namespace to reopen the original study or PUBLIC fence.

## Planned adverse-case matrix (specified, not implemented or passed)

| ID | Case | Required behavior |
| --- | --- | --- |
| T01 | Exact closed E0/E1 evidence and current E2 paths/inodes | Metadata correspondence may be established only; no proof before full reconstruction |
| T02 | E0 and E1 incorrectly merged into one old-device group | Reject; epoch ownership is explicit |
| T03 | Only output parent matches; other recorded chain is missing/changed | Reject before replay |
| T04 | Changed inode, inconsistent shared prefix, mixed current devices | Reject; no wildcard or transitive shortcut |
| T05 | Unknown epoch/chain, duplicate label, boolean or numeric alias | Reject closed-schema/type mismatch |
| T06 | Historically unrecorded bundle identity filled from current state | Reject fabricated provenance |
| T07 | STARTED tampered to redirect an authorization/claim path | Reject its anchored hash before accessing the named target |
| T08 | Missing/extra archive file, hardlink/symlink, changed bytes or generation | Reject before numerical replay |
| T09 | v2 PUBLIC claim/fence, source, review or authorization linkage differs | Reject even if cell numbers look correct |
| T10 | Self-consistent rehashed but unreviewed historical certificate/candidate | Reject reviewed-byte mismatch |
| T11 | Full hash closure passes, but environment/baseline/replay differs | No certificate or successful reconstruction receipt |
| T12 | v2 replay passes, but original generation qualification is replaced | Reject; preserve original sealed identity |
| T13 | Task/acceptance/rejection order, budget, seed, schedule or threshold changes | Reject complete scientific-projection mismatch |
| T14 | Forged old admission/inputs, caller-provided proof callback or global patch | Reject interface/origin/source boundary; never enter effects |
| T15 | Static/mocked tests or historical PUBLIC replay offered as new coordinator qualification | Remain NOT_QUALIFIED_FOR_EXECUTION |
| T16 | Original claim/output/summary already occupied, including dangling symlink | Stop before costly admission; preserve name |
| T17 | Expected authorized claim creation after pre-consumption checks | Post-consumption verification uses exact claim, not an absence invariant |
| T18 | E2 device/inode, source or HEAD changes during reconstruction/run | Stop; retain any effects; no automatic re-attestation or retry |
| T19 | Partial claim/publication or failed result delivery | Unknown/consumed outcome preserved; no countermanding NOT_RUN |
| T20 | PUBLIC approval, old digest approval or general “continue” used for production | Reject; require the new exact production candidate digest |
| T21 | New source file omitted from successor source receipt | Reject source-closure gap |
| T22 | Later analysis opens persisted replication rather than PUBLIC binding | Enforce exact mode/study/claim; no cross-mode reinterpretation |

The unchanged repository tests are a regression check only. None of T01–T22 is
claimed as an implemented successor test here. Implementation review must link
each row to concrete tests and genuine paths, and document any remaining gaps.

## Rejected shortcuts and remaining gates

- Editing device numbers or recomputing hashes inside old receipts destroys the
  historical anchor and does not produce genuine current admission.
- Disabling the wrapper's parent check leaves the coordinator, old PUBLIC
  inspector and old receiver proof checks failing independently.
- Copying old PUBLIC rows into a new output is replay, not a new full-path run.
- Passing old data structures off as currently admitted objects bypasses the
  exact verifier that is being designed.
- Keeping a new code path under the old source digest misstates qualification.
- Disk UUID, boot time, same inode, a mount command or a filename cannot by itself
  replace the reviewed, bounded evidence acceptance rule. No disk operations are
  proposed in this task.

Remaining gates are implementation and adversarial tests; genuine reconstruction
and independently reviewed current-receiver evidence; new coordinator qualification;
candidate review; and explicit exact-digest production consent. The design permits
planning these gates, not silently executing them. Locked-128 evaluation, causal
claims, population inference and QMC superiority remain outside scope.

## Code paths grounding the design

- `scripts/feedback_budget_replication_reattest.py`: `mapping`, `current_locations`,
  `inspect_transport`, `verify_original_public`, `verify_original_seal`,
  `certificate_projection`, `reconstruct`, `candidate_projection`, `admit`.
- `scripts/feedback_budget_receiver_execution.py`: `receiver_admit`, `admit`,
  `analyze`, `qualified_public`, `run`, and its separate five-file `SOURCE_FILES`.
- `scripts/feedback_budget_replication_execution_storage.py`: `claim_path`,
  `frozen_binding`, `inspect`, `inspect_claim` and exclusive publication mechanics.
- `scripts/feedback_budget_receiver_attempt.py`: fixed fence derivation,
  consumption and exact persisted-payload linkage.
- `scripts/run_feedback_budget_receiver_replication.py`: unchanged reviewed
  preflight/dispatch gates; its failure must not be relabeled as a PASS.
