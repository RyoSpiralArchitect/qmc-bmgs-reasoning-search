# E4 read-only certificate proposal verifier

Status: **C1 IMPLEMENTATION WITH PERSISTENT-IDENTITY FIX — NOT AN ISSUED
CERTIFICATE OR EXECUTION AUTHORITY**.

This acceptance policy belongs to the same frozen three-file closure as
`scripts/feedback_budget_receiver_e4_certificate.py` and
`tests/test_feedback_budget_receiver_e4_certificate.py`. The design revision is
`0aeb46b039c1d1b46874f7b43c3a655d03b2eff9`; the unchanged E4 reconstruction is
`c19db4a7994eeb5f33c610cdee3ebc0c72e2a004`, source digest
`52deaa2df32b9b03786bd6afeaedb885146a68ddc7de9d0a195f5462275f2456`.
The [certificate-only design](countdown_feedback_budget_receiver_e4_certificate_design_20261010.md)
remains the C0 scope and later C2–C5 gate specification. The 2026-10-14 correction
below supersedes its cross-boot device-number comparison and proposal schema,
not the original study, numerical implementation, claim slots or consent scope.

## 2026-10-14 identity correction (same study, not a new E5 experiment)

The previous orchestrator treated `st_dev=16777234` as persistent receiver
identity. On 2026-10-14 every protected path had `st_dev=16777229`, unchanged
inodes and byte-identical retained evidence. macOS boot time was 2026-10-12
23:03:57 JST, after the 2026-10-10 observation. The current value equals the
device node's `st_rdev` for `/dev/disk3s5`. BSD device identifiers are allocated
in an attachment/mount context, not permanent disk identities. Apple's
`diskutil(8)` IDENTIFIERS section explicitly directs software to use UUIDs
across attachment/reboot changes. Apple distinguishes a nonpersistent
[volume identifier](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumeidentifier)
from a persistent
[volume UUID](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumeuuidstring).
The application bug is the cross-boot equality requirement. A reboot occurred
between observations, but historical UUIDs and kernel allocation logs were not
retained; do not claim proof of the exact allocator event or physical continuity.

The corrected certifier separates two scopes:

- Persistent receiver: fixed paths, every component's inode, and source-pinned
  volume UUIDs. The root component's current APFS system snapshot UUID is
  `C026C959-2B1E-4273-ADF5-64BE3D5D8ADF`; all remaining components of the six
  fixed paths reside on Data UUID `5CF14066-7B07-4A1D-8F3F-0A1806A1A4E7`.
  These are a new 2026-10-14 baseline, NOT invented historical E4 UUIDs.
- One running operation: actual full `(st_dev, st_ino)` chains and persistent
  bindings must remain exactly unchanged. Source, HEAD, all evidence snapshots,
  private/no-follow descriptor checks, unused claims, runtime, complete archived
  content and all numerical reconstructions remain mandatory.

UUIDs are read with Darwin `fgetattrlist(ATTR_VOL_INFO | ATTR_VOL_UUID)` from
held no-follow descriptors, not guessed from device names or accepted from a
caller. Every shared prefix must agree. Missing/zero/truncated UUID, unsupported
platform, different UUID, changed path/inode, or mid-operation device change
rejects. Root and Data have different UUIDs despite sharing the observed
`st_dev`; one UUID for the whole chain would be incorrect. An OS snapshot change
or a real move to a different volume intentionally requires a new review.

The frozen E4/E3/E2 sources and historical records remain byte-identical. No
constant is monkeypatched and no live stat record is normalized to an old device
number. After current UUID and historical path/inode correspondence checks,
the frozen **pure historical mapping** is reconstructed from authenticated old
identities and compared whole. It is named `historical_location_correspondence`
in the v2 proposal. Separate `receiver_identity` binds the current persistent
UUID/path/inode projection and explicitly says historical UUID continuity is
unproven. Actual operation-local device numbers appear only in the detached
operation/verification receipt, so a later boot need not change proposal bytes.
This is neither new experiment data nor receiver admission or execution authority.

## Authority boundary

C1 implements read-only operations and synthetic adverse-case tests. Approval
to implement is **not approval to perform actual numerical reconstruction**.
There is no publisher, old-bridge prepare wrapper, admission, candidate, PUBLIC
allocator, claim consumer, dispatcher, consent override, recovery or resume API.
No dependency source or original evidence is modified.

Three objects remain distinct: pinned historical records; a private live capture
created only after the complete genuine ordered path; and detached certificate
bytes. Hashing, parsing, comparing a template, or loading a saved PASS cannot
create a registered capture. Even a registered capture is not execution authority.
No public constructor takes receipts, callbacks, mappings or legacy proof types.
The capture retains actual source, runtime, evidence snapshots, location chains
and genuine PUBLIC inputs, and rechecks them when asked for an operation receipt.
Detached bytes have no perpetual-current-state promise. This is an API boundary,
not protection against a malicious interpreter, host or privileged monkeypatching.

Only one reconstruction attempt is allowed per process/module instance. A failure
requires stopping, retaining evidence and a separate decision about a fresh
process; there is no automatic retry. CLI verification is launched in a new
process with the same frozen implementation; it is not an algorithmically
independent verifier. Importing the library does not authorize computation.
Actual attestation/reconstruction retains the frozen lower runtime's required
`-P -B`, absolute `PYTHONPATH` to this checkout's `src`, and a private empty
`PYTHONPYCACHEPREFIX` outside the checkout. Static self-test does not qualify that
runtime or require actual source attestation; it only checks the bound callables
and static registries.

## Exact ordered computation

1. Check original unspent study slots, source closure, current HEAD and the six
   fixed receiver location chains with the persistent-identity correction above.
   Read the three fixed E4 historical records
   against review `3a69f33121be244c21143979be0a04fe71cdac5e`; check their complete
   pinned bytes before parsing any of them. Caller-selected paths are unsupported.
2. Authenticate the existing lower metadata/archives and all 23 direct historical
   chains: 3 original-v7, 8 receiver-20260921, 6 E2 and 6 E3. Epoch ownership stays
   separate even when device numbers recur; no physical continuity or reboot
   cause is inferred. The historical 23-key record retains its 16 comparison / 7
   immutable-envelope partition: the location comparison is explicitly historical,
   while current persistent and operation-local identities are checked separately.
   Its c19db4a HEAD and device identities are never rewritten.
3. Obtain the genuine original five-field environment, including the 32-trace
   baseline. Compare the entire environment with E3 and E4. Load genuine fixed
   PUBLIC inputs, not sealed production inputs or supplied admission objects.
4. Independently replay each of the two retained PUBLIC archives: 1024 traces
   and 512 full-event budget-prefix comparisons each; compare complete receipt
   and summary bytes through the frozen E4 implementation. Both historic screens
   remain false and each PUBLIC source denominator remains one multiset.
5. Use the fresh original-v7 generation reference and call the genuine original
   cohort generator once. Reproduce full order, 102 attempts / 64 accepted /
   38 rejected, full three-file seal and 1109241-byte input projection. This
   exhaustive solvability work is not replication-policy search.
6. Compare all 16 fields (including the rebuilt historical mapping) in full against the pinned E4
   record. Revalidate new and frozen source, runtime, current operation HEAD,
   original unspent slots, real snapshots and location chains before and after
   expensive stages and at completion. Only then register the private capture.

The new source attestation binds its three complete files and chains the frozen
E4 source. Callable/origin guards include the new orchestrator and the old helper
entry points it uses. Later review/document commits may descend from the same
implementation revision if protected source and evidence stay byte-identical.
HEAD must remain unchanged during each operation. The old E4 same-HEAD verifier
is neither called nor relaxed.

## Certificate and verification contracts

The deterministic proposal has thirteen top-level fields. Relative to C0,
`location_correspondence` becomes `historical_location_correspondence` and
`receiver_identity` is added, under the explicitly revised domain suffix
`/receiver-e4-certificate/v2/certificate`. `case.device` is explicitly renamed
`case.historical_device`. All other inherited structures stay
unchanged. It uses compact sorted ASCII JSON with
one final newline; the content digest excludes itself and the newline. Duplicate
keys, nonfinite values, noncanonical encodings, bool/float aliases for counts,
missing/extra fields and self-consistently rehashed deviations all reject.
Whole canonical equality against the source-owned pinned projection closes the
entire inherited schema, not just selected success fields. That comparator is a
rejection filter, not a proof of reconstruction.

Certificate projection preserves the original study, generation reference,
input/schedule/seal digests, output/summary/global claim paths and planned
64/1024/512/256 denominators. Its eleven claim-ceiling fields are false or plain
integer zero. Publication state and current operation HEAD are not certificate
fields. Actual current device numbers are operation-local receipt fields, not
persistent certificate fields. Historical source/verification records stay historical, including their
original meanings and negative scientific results.

`--reconstruct --implementation-revision <full-OID>` returns bare canonical
proposal bytes on stdout; the detached operation receipt goes to stderr after
stdout is flushed. It may later be retained, with separate C2 approval, only as
the proposed fixed comparison record
`docs/qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.proposal.json`.
The certifier itself writes no files or namespaces.

`--verify-proposal --implementation-revision <full-OID>
--reviewed-proposal-revision <full-OID>` authenticates that one fixed path against
the supplied immutable descendant review before parsing it, rejects any template
deviation, repeats the entire genuine path, and compares **all certificate bytes**.
It then revalidates both the proposal snapshot and live capture before returning
a detached receipt. A stale caller-provided verification receipt cannot replace
this computation. The receipt records the current operation HEAD, complete source,
reviewed target, full completed work, same-implementation fresh-process method
and false authority; it is not embedded in the certificate (no hash cycle).

`--self-test` is static and works outside the checkout. It performs no baseline,
PUBLIC or cohort computation. No CLI path/device/output/consent/execution or
abbreviated-mode overrides are accepted. All result delivery is explicit:
partial/failed stdout is unknown; a later stderr failure retains the fact of
completed stdout flush, never certificate issuance. Completed work counters are
retained on downstream failure; entered-but-unfinished numerical counts remain
unknown, not zero. Failure does not assert original claim absence or consume it.

## Test evidence and explicit unimplemented boundaries

The new tests exercise fixed historical authentication, typed whole-template
comparison (including every nested object's extra-field rejection), private
capture registration, callable guards, source/HEAD drift, ordered genuine-helper
dispatch through explicitly MOCK fixtures, partial/completed work accounting,
fixed reviewed proposal comparison and delivery failures. The unchanged E4 tests
cover direct mapping ownership, real lower replay/summary wiring and full seal
comparison. These tests do not count as an actual certifier reconstruction.
Persistent-identity regressions additionally cover changed boot-local numbers,
wrong/missing volume UUIDs, path/inode/type/role drift, drift during capture or an
operation, descriptor cleanup, unchanged historical metadata and detached live
identity receipts. Mocked reboots are not an observed physical reboot test.

| Design case | C1 coverage / limitation |
| --- | --- |
| C-T01 | Saved PASS/template cannot register capture; failed real-helper wiring rejects |
| C-T02 | Exact full 23-chain projection, epoch/owner/order mutations; frozen E4 mapping tests |
| C-T03 | All three historical byte pins before parsing; fixed reviewed proposal before comparison |
| C-T04 | Closed whole schema, nested extensions, aliases, duplicate/nonfinite/noncanonical JSON |
| C-T05 | Ordered one baseline, two separate PUBLIC calls, original reference, one cohort, 16 whole comparisons; MOCK only |
| C-T06 | Own/old callable, origin, source and operation-HEAD checks; final capture drift |
| C-T07 | Complete template and reconstructed proposal bytes, not selected fields |
| C-T08 | Ancestor-bound source/review versus protected-byte drift; old same-HEAD source unchanged |
| C-T09 | No supplied proof/receipt/callback API; future publisher consumption NOT IMPLEMENTED |
| C-T10 | No filesystem publication calls; exclusive bundle/partial publication tests NOT IMPLEMENTED |
| C-T11 | All false/zero ceilings; no issued-state field, candidate or execution API |
| C-T12 | Detached receipt cannot replace fresh full proposal verification/live revalidation |
| C-T13 | Historical verification references only; no certificate/future-verifier hash cycle |
| C-T14 | Original unused pre-consumption invariant retained; post-consumption C4 analysis NOT IMPLEMENTED |
| C-T15 | Negative screens and original generation/study/global-claim identity retained |
| C-T16 | No production/consent/path override; future new candidate and exact-digest consent remain separate |

Do not interpret this table as completed C3 publication or C4/C5 integration.
Later C3 needs its own source-owned publisher, exact proposal review, explicit
certificate-only scope and fresh live reconstruction immediately before one
exclusive bundle. C4 separately needs a new qualified coordinator and approved
fixed PUBLIC attempt. C5 needs a reviewed new candidate and exact-new-digest
production consent; the original study claim and output remain unchanged.
