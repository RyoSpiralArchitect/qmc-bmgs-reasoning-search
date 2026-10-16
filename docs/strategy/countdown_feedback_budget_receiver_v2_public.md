# v7 receiver coordinator v2 — fixed PUBLIC full-path qualification

This is one additive PUBLIC-only qualification of a new shared execution and
analysis coordinator. It is not authorization to execute the sealed 64-task
replication study. Historical artifacts, the v1 receiver bridge, both historical
candidate generations, and all existing consumption claims remain unchanged.

## Scope, source closure and authority order

The new coordinator is `scripts/feedback_budget_receiver_execution.py`; the
fixed-attempt helper is `scripts/feedback_budget_receiver_attempt.py`. Their
namespace is the v1 receiver domain followed by `/coordinator/v2`:

`qmc-bmgs-countdown-thompson-feedback-budget-confirmation/v1/receiver-reattestation/v1/coordinator/v2`.

The new source receipt covers exactly these additions:

- `scripts/feedback_budget_receiver_execution.py`
- `scripts/feedback_budget_receiver_attempt.py`
- `tests/test_feedback_budget_receiver_execution.py`
- `tests/test_feedback_budget_receiver_attempt.py`
- `docs/strategy/countdown_feedback_budget_receiver_v2_public.md`

It separately chains the unchanged v1 bridge attestation at
`951d273ccf4072b8e0557970cc71095951b843b7`. The preserved v1 candidate,
certificate and bundle COMMIT are reviewed bytes at
`bf83efbaa94af3dc9b6863a19202acffa815ad74`. Those receipts do not pretend to
cover the added coordinator. The historical numerical/publication implementation
and original evidence anchors remain those already verified by v1.

The order is new implementation commit -> source-bound PUBLIC candidate ->
candidate review commit -> fixed-attempt PUBLIC execution -> independent analysis
and saved-summary verification -> reviewed qualification evidence. No receipt
depends on a future artifact or grants itself execution authority. Exact reviewed
candidate bytes, source ancestry and the explicit candidate digest are required
at execution; candidate preparation and integrity verification do not consume
either a PUBLIC or replication claim.

## One fixed PUBLIC attempt

The sole attempt identity is `receiver_public_full_path_20260922_a/v1`.
Its repository-relative paths are fixed:

- Output: `artifacts/work/feedback-budget-v7-receiver-public-20260922-a`
- Raw authorization: `artifacts/work/feedback-budget-v7-receiver-public-20260922-a.authorization.json`
- Saved summary: `artifacts/work/feedback-budget-v7-receiver-public-20260922-a.summary.json`

There are no caller-selected output, attempt, ledger or retry namespaces. Before
any execution consumption, reject occupied or uncertain attempt/output state.
The additional fixed fence is inside the existing
`artifacts/work/feedback-budget-v7-authorization-ledger` and is named
`receiver-public-{digest}.json`, where `digest` is SHA-256 of canonical JSON for
`[new_domain, attempt_identity]`. This uses the project's JSON-digest convention
(no trailing newline), not the full serialized-file hash.

Consume and durably verify that fence **before** calling the unchanged
`S.consume` for the PUBLIC authorization. Its fixed identity prevents a changed
candidate digest from reviving this attempt. The fence and the ensuing PUBLIC
claim must bind the exact reviewed authorization and execution identities;
analysis validates their linkage. The original spent PUBLIC claim is neither
reused nor changed. A new PUBLIC authorization claim is additional evidence for
this explicitly separate qualification, not a reset of a previous study.

The fence's `owner_nonce` is a deterministic correlation label derived from the
domain, attempt, authorization digest and reviewed/execution commits, not a secret
capability. Inspection reconstructs its complete expected bytes from those pinned
references. Exclusive file creation and held descriptors provide ownership.

An occupied fence, failed second consumption, partial output or uncertain
publication is retained. There is no automatic retry, resume, adoption,
regeneration under a different name, deletion or replenishment. A successfully
completed operation whose result cannot be delivered is reported as delivery
uncertain, not as an unexecuted operation. Diagnose and preserve evidence instead
of rerunning scientific work.

## Authentic admission and shared execution

The coordinator independently invokes genuine v1 admission for the preserved
candidate/certificate and reconstructs the original evidence and sealed metadata.
That step does not search the sealed tasks or transfer execution authority from
the old candidate. It neither fabricates an old Admission/Inputs instance nor
patches a module, global, loader or qualification callback.

The PUBLIC adapter then obtains the authentic fixed PUBLIC input object from the
unchanged PUBLIC loader. Only detached, internally verified immutable admissions
enter the coordinator. Caller-supplied dictionaries or bindings alone are not
admission. Exact source/runtime, file content, current directory identities and
reviewed bytes are checked at admission and revalidated across publication.

One shared coordinator performs consumption linkage, run binding, ordered search
record generation, durable full-matrix publication, closed-file inspection,
all-cell replay, reduction, summary publication and independent verification.
It reuses unchanged numerical and storage functions. PUBLIC execution must
actually generate and save its new records; replaying the old PUBLIC archive,
copying old rows or a mocked execution is not this qualification.

Analysis first authenticates the persisted run and exact spent claims, then
reconstructs admission and replays every saved trace. It compares the complete
receipt, and a fresh process reproduces the complete saved summary byte for byte.
Reusable PUBLIC qualification verification must not require permanent absence of
the replication claim: later post-consumption replication analysis must still be
able to verify its PUBLIC reference. Pre-consumption checks and post-consumption
exact-claim checks are different gates.

## Frozen numerical shape and claim ceiling

The existing PUBLIC definitions, seeds, scales and budgets are unchanged:

- 64 task definitions drawn from **one** source multiset;
- 4 seeds (`8192` through `8195`), scales `0` and `16`, budgets `256` and `512`;
- 1,024 cells, 512 exact budget-prefix pairs, and 256 four-arm blocks.

These are not 64 independent source multisets or 256 independent tasks. All
identity and budget checks precede replay; the existing outcome-ordered reducer
and fixed comparisons remain unchanged. The previously reported PUBLIC
numerical screen was false and remains historical evidence; do not tune inputs,
thresholds or interpretation to replace that result.

PUBLIC results retain `replication_cells_executed = 0`,
`replication_execution_authorized = false`,
`locked_128_evaluation_authorized = false`, and `scientific_decision = null`.
No provider calls, sealed-task search, replacement cohort, witness/hardness
selection, causal claim, population inference or QMC superiority follows.

A successful run qualifies the **shared coordinator and PUBLIC adapter actually
exercised**. It does not establish that v1 `B.run` was executed or that the v2
production adapter has been exercised at runtime. Static review, negative tests,
authentic v1 admission verification and actual PUBLIC execution are separate
evidence categories.

## Closed future production boundary

A closed internal production adapter is included in the source closure now so
later use need not silently change the qualified shared coordinator. This task
exposes no production execution CLI and does not create, confirm or execute a v2
production candidate. PUBLIC authorization cannot select the production adapter.

Any later v2 production envelope must bind the exact new source, the independently
verified and reviewed PUBLIC qualification, and authentic v1 admission of the
preserved candidate/certificate. It requires its own reviewed bytes and explicit
exact-digest execution confirmation. Neither the old candidate approval nor a
PUBLIC PASS authorizes that execution. The same original fixed replication claim
and fixed production output remain authoritative; they must never be reset or
replaced with a v2-specific replication slot.

## Operator procedure and completion evidence

Use a clean checkout, absolute `PYTHONPATH` to `src`, a fresh empty owned mode-0700
`PYTHONPYCACHEPREFIX`, and `python3 -P -B`. Keep source and reviewed artifacts
unchanged throughout each qualified operation. Each independent verification
uses a fresh process and fresh private cache. Run the repository validator after
code changes, and keep boundary/fault tests distinct from the actual PUBLIC run.

Record exact implementation/review commits, source and candidate digests, the
fixed fence and PUBLIC claim, the closed publication COMMIT, analysis receipt,
saved-summary hash and independent verification result. Preserve failures and
negative outcomes. Before and after this PUBLIC-only task, check that the original
replication claim and production output remain absent; these are task-scope
observations, not permanent invariants in reusable qualification evidence.
