# Receiver successor: read-only inspection contract

This is D1 of the [2026-10-01 design](countdown_feedback_budget_receiver_successor_design_20261001.md).
It implements a byte/provenance and fixed-epoch metadata inspection, not D2
reconstruction, current admission, or an execution coordinator. Its only CLI
operations are `--self-test` and `--inspect --implementation-revision <full OID>`.
There is no output-path, callback, proof, certificate, candidate, confirmation,
publication, claim-consumption, replay, run, analysis or retry input.

## Source ownership and operation

The exact new source closure is:

- `scripts/inspect_feedback_budget_receiver_successor.py`
- `tests/test_feedback_budget_receiver_successor_inspection.py`
- this policy, `docs/strategy/countdown_feedback_budget_receiver_successor_inspection.md`

Freeze these files in a descendant of design revision
`96890dea719b9de5f14f1a1afe7147d4951b16e0` before actual inspection. Use a new private
bytecode-cache directory, absolute repository `src` in `PYTHONPATH`, and
`python3 -P -B`. The lower source attestors require unchanged reviewed Git bytes,
source-only module origins, absent sibling bytecode caches and a clean checkout.
They check source, not runtime/baseline/replay qualification. All old qualified
files remain unchanged. Source/HEAD and captured evidence are revalidated before
return. Caller-supplied revisions must be full lowercase commit OIDs; aliases
and branch names are not acceptance inputs.

No operation creates an artifact, fsyncs a retained archive/claim, consumes a
namespace, generates tasks, runs numerical search, or calls an old admission.
JSON observations go to stdout, failures to stderr; saving/promoting an observation
is a separate documentation action. OS-managed access timestamps and ordinary
Git read-side housekeeping are not a claim of bit-for-bit disk inactivity.

Important implementation distinction: old `B.Archive` calls `_observe`, which
forward-syncs files and directories. The successor does **not** use it or the old
claim/fence inspectors. Its own `ReadOnlyArchive` calls only no-follow, bounded,
single-link file reads and closed directory-generation checks. It revalidates
bytes, identities and generations without any forward-sync call. Thus the older
design inventory's use of `B.Archive` must not be interpreted as proof that that
diagnostic was fsync-free. This correction does not rewrite its saved evidence.

## Closed metadata boundary

Sixteen fixed reviewed Git anchors authenticate the original study, complete
three-file seal, v1 three-file certificate/candidate bundle, both PUBLIC archives,
and prepared v2 candidate/evidence. Each PUBLIC reviewed COMMIT authenticates
STARTED **before** parsing or following its references. Only fixed authorization,
summary and claim paths may then be read. Complete cell schema/hash closure and
receipt/summary/authorization/source/claim/fence linkage are checked, but no
numerical result is recomputed. Historical success flags stay historical.

The 11 ordered chains have explicit owning file, authenticating Git anchor,
review revision, JSON pointer, epoch and location role. Exactly E0 device
16777233 and E1 device 16777231 may correspond directly to E2 device 16777234.
Paths, full integer component chains, unchanged inodes and shared prefixes must
match. No broad device wildcard, transitive mapping, invented historical bundle
chain, numeric/bool alias, reordered chain or additional epoch is accepted.
The bridge bundle is a current-only directory snapshot with reviewed file bytes.
The result is **metadata correspondence**, not disk identity, reboot causality,
mapping consent, receiver admission or proof of numerical reconstruction.

The entire original seal (including acceptance/rejection order) must equal its
reviewed bytes. All original candidate fields except the explicitly versioned
schema/digest, parent and connector-qualification envelope remain identical.
Input/schedule/seal references and the original generation qualifier are checked.
This is metadata preservation, not acceptance-order regeneration. The 64-source
sealed study, fixed claim and original output remain unspent. Each PUBLIC archive
has 64 task definitions from **one** source multiset, not 64 independent sources.
Negative saved results are preserved; neither hashes nor tests establish a gain.

An `inspection_shape` result is schema validation only. Even a self-consistent
fabrication cannot become admission: this module has no proof/inputs/run adapter.
Its ceiling is always `NOT_IMPLEMENTED` reconstruction and
`NOT_QUALIFIED_FOR_EXECUTION`. An actual inspection must independently capture
and authenticate the fixed files; it accepts no externally supplied receipt.

The fresh-process/source boundary is not a security sandbox against arbitrary
Python code executing in the same interpreter. A guard additionally detects
accidental substitution of selected read dependencies; it does not claim to
defeat a caller who can rewrite the guard, globals or interpreter itself.

## State boundary and rejection-test coverage

The original claim/output/v2-summary absence gate runs before source inspection
and again at the end. It is specific to this pre-consumption D1 operation, not
an invariant of a future proof. `persisted_claim` instead compares exact existing
claim bytes and mode/study linkage, without an absence test. It is used on old
PUBLIC claims here; synthetic tests exercise the corresponding replication
metadata branch. This does not implement production analysis or consumption.

Errors preserve evidence; no deletion, retry, rebind or recovery is attempted.
Known consumed/unknown state in an existing execution failure is retained.
Other failures report consumption as unknown, independently of this inspector's
`execution_dispatch_entered=false` and `new_effects_attempted=false`.

The test names map to the design matrix T01–T22. Coverage is deliberately split:

| IDs | Implemented boundary exercised | Not established by these tests |
| --- | --- | --- |
| T01–T06 | Closed epoch/owner/path/type/prefix comparator | Historical bytes were genuinely read in a synthetic fixture |
| T07–T10 | Authenticate-before-reference, strict archive reads/generations, PUBLIC linkage and Git-byte check | Numerical correctness |
| T11 | Receipt cannot claim environment/baseline/replay reconstruction; no such operation exists | Actual failure of a real reconstruction path (not implemented) |
| T12–T13 | Complete saved scientific projection and original generation reference | Acceptance-order regeneration |
| T14 | No caller proof/adapter/callback; dependency substitution rejected | Hostile interpreter isolation |
| T15 | Static/history evidence cannot assert new execution qualification | New coordinator PUBLIC run (not implemented) |
| T16 | Occupied claim/output/summary, including dangling symlinks, reject early | Concurrent consumption transaction |
| T17 | Exact persisted-claim comparator accepts owned bytes after creation without absence | Actual consumption/publication/analysis integration (not implemented) |
| T18 | Current identities, source and HEAD drift fail revalidation | Atomic prevention of effects in a future runner |
| T19 | Known consumed and unknown failure states retained, including output-delivery error | Actual partial publication recovery |
| T20 | All run/consent/publication CLI inputs rejected, including old digest | Future exact-new-digest consent gate (not implemented) |
| T21 | Exact three-file source closure; missing/additional source entries reject | Qualification of future code |
| T22 | Persisted mode/study/output/authorization binding checked | Production analysis |

Additional tests cover outside-checkout invocation, no fsync/write dependencies,
source drift, receipt authority flags and metadata-only actual-operation wiring.
Repository regression validation and actual inspection are separate receipts;
neither turns these deferred gates into passed ones. Later steps remain genuine
reconstruction, independent new evidence review, separately approved fixed PUBLIC
qualification of new integration, candidate review and exact-digest consent.
