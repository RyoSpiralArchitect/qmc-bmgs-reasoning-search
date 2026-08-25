# Countdown Thompson regular-file publication v2 contract

Status: production wire, verifier, runner, and analyzer integrated and verified
on a distinct 240-cell nondiagnostic full-shaped fixture. No production
authorization candidate or diagnostic outcome exists at this revision.

Wire revision: `v2r3`. The superseded `.qmc-bmgs-v2-` and
`.qmc-bmgs-v2r2-` namespaces are not adopted or migrated by this revision.

## Question

Can the diagnostic publisher obtain exact attempt and artifact authority without
the portable-POSIX `mkdir` then `open/stat` interval that blocks the v1
directory protocol?

## Frozen phase-1 design

For an absolute output path `P/A`, v2 uses one flat namespace in the already
existing, non-symlink parent `P`:

```text
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.attempt.json
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.started.json
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.ready-to-commit.json
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.not-run.json
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.invalid.json
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.records.jsonl
P/.qmc-bmgs-v2r3-<sha256(lowercase ASCII basename)>.manifest.json
P/A                                                     # commit receipt, last
```

The output basename must be ASCII and its lowercase spelling may not begin
`.qmc-bmgs-`; that namespace is permanently reserved for protocol authority
files. Before constructing a `Path`, the raw text must be absolute and exactly
equal to its `normpath` spelling; trailing separators, `/.`, `/./`, `..`, and
duplicate separators are refused before parent access or callback execution.
The complete text path must also be representable by the host filesystem
encoding. Round-tripping POSIX `surrogateescape` parent components are not
rejected by this text precheck and proceed to filesystem lookup; the host
filesystem may still refuse unsupported byte sequences. Other unencodable text
is refused before parent access.
The attempt name depends on a conservative lowercase digest of the basename
within its pinned parent, not the authorization digest. The exact lexical output
path retains a separate provenance digest. Case-only and parent-path aliases
that reach the same directory therefore contend on the same sidecar
reservation, while commit names cannot alias another output's internal
sidecar. Unicode filename-equivalence rules cannot create an unmodelled output
alias because non-ASCII basenames are refused before parent access. This
deliberately over-collapses case variants on case-sensitive filesystems: denial
of service is safer than executing twice through a filesystem alias. Within one
bound parent directory object, a reserved output namespace is single-use across
all authorizations; a retry requires a new reviewed output name.

The publisher and inspector also require an external, canonical parent binding:

```json
{
  "binding_scope": "same_host_same_filesystem_identity_epoch",
  "component_identities": [
    {"st_dev": 1, "st_ino": 2}
  ],
  "deterministic_digest": "lowercase SHA-256 over the other fields",
  "output_parent_path": "/exact/normalized/parent",
  "schema_version": "qmc-bmgs-posix-output-parent-binding/v1"
}
```

`component_identities` is the root-to-leaf sequence obtained by two matching
component-wise `O_NOFOLLOW` walks. Identity integers are exact, nonnegative, and
limited to 256 bits. Booleans, subclasses, oversized identities, non-canonical
fields, path mismatch, and digest mismatch are rejected as NOT_RUN before
filesystem access. The planning-only helper may snapshot this object, but an
execution publisher must receive it from an authorization reviewed and stored
outside `P`; execution must never regenerate its expected value from the live
parent. Production authorization must hash the exact binding bytes into its own
authorization digest.

After pinning `P`, the publisher and inspector compare every component identity
with that external chain. Missing, replaced, or otherwise mismatching live
parents are `AMBIGUOUS`, including when the replacement directory is empty: the
reviewed authorization may already have been consumed in a displaced directory.
The full binding is stored in ATTEMPT, and its digest is chained through every
phase receipt, MANIFEST, and COMMIT. Restart inspection revalidates the embedded
binding's exact field types and own digest, then compares its canonical bytes to
the external reviewed binding; language-level numeric equality cannot substitute
different persisted bytes. The output reservation name intentionally remains
basename-global within the bound parent and does not include the binding digest;
a caller cannot choose a different binding to obtain a second sidecar basename
within the same directory object. A freshly captured binding for a replacement
directory is different authorization material. The synthetic API does not itself
prove that its opaque authorization digest commits to the binding, so production
integration must enforce that closure.

`v2r3` also performs a stable descriptor-bound directory scan before ownership,
before STARTED/callback boundaries, during every terminal proof, and during
restart inspection. Any entry whose lowercase name begins the superseded
`.qmc-bmgs-v2-` or `.qmc-bmgs-v2r2-` prefix blocks every output in that parent,
regardless of the entry's type, suffix, case, or bytes. It is never adopted,
renamed, removed, or forward-synchronized. This directory-wide fence prevents
an old exact-path reservation from being overlooked through a parent or
basename alias. Running a superseded publisher concurrently is outside the
transition contract: all older publisher processes must be quiescent before a
parent is used with `v2r3`.

Every protocol file is created directly at its final name with:

```text
openat(parent_fd, name,
       O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
       0600)
```

The descriptor returned by that successful call is the only in-process
ownership evidence. Matching bytes at a pre-existing name are never adopted.
The descriptor is retained through terminal proof. The generated owner nonce
is checked against the same exact lowercase-hex predicate used by the restart
verifier before the attempt name is opened.

For each file, v2 requires:

1. initial `fstat`: regular file, size zero, one link, current effective UID,
   and no group/world permission;
2. `fchmod(file_fd, 0600)` followed by a repeated exact identity, owner, and
   mode check, so restrictive caller `umask` cannot make a terminal unreadable;
3. complete writes, including short-write handling;
4. capture of the exact stable file generation immediately before
   `fsync(file_fd)`, followed by proof that the generation immediately after
   the call is identical;
5. `fsync(parent_fd)`;
6. proof that the post-barrier file is still that pre/post-`fsync` generation;
7. exact descriptor read-back plus descriptor/name inode, owner, exact `0600`
   mode, link-count, byte, and stable metadata equality;
8. lexical parent identity revalidation.

Normal and recovery control flow never renames, replaces, unlinks, quarantines,
reclaims, or cleans an authority name. Foreign files, directories, FIFOs,
sockets, hardlinks, and symlinks are retained.

The synthetic callback must return an exact built-in `list` or `tuple`. Before
any record is serialized, the producer takes a private bounded membership
snapshot of at most the configured limit plus one, validates the snapshot's
own count, and never rereads the caller-owned outer collection. Each selected
plain-dict record is then detached through canonical JSON and strict parsing.
Thus reentrant or concurrent outer-list growth cannot make the producer emit a
record count that the restart verifier rejects. Serialized bytes are counted
incrementally: the first frame that would exceed the aggregate limit is rejected
immediately, and no later record is traversed or serialized. The aggregate cap
therefore bounds accepted/persisted record bytes and stops further caller data
consumption; it is not a bound on the temporary computation required to
canonicalize one individual caller-supplied record.

The production callback is a separate API and must return one exact
`DiagnosticPublicationBatchV2`: exactly 240 canonical digest-bearing record
payloads plus one digest-bearing run manifest. The substrate wraps each payload
in an indexed production record frame, recomputes the payload-only JSONL digest,
and requires the run manifest to close over the authorization, ATTEMPT, STARTED,
output path/binding, ordered cell IDs, ordered record digests, and exact byte
receipt. The outer collective manifest embeds that run manifest. READY closes
the sidecars, and the output-path commit receipt closes READY, both sidecars,
and the nested run-manifest digest. The independent verifier regenerates these
objects, performs two stable generation snapshots with forward durability
barriers, and exposes only immutable byte snapshots for COMMITTED.

The initial reviewed-binding preflight requires the entire reserved namespace
to be absent. After the publisher durably owns ATTEMPT, callback-time input
rechecks use a distinct parent-binding revalidation that permits publisher-owned
ATTEMPT/STARTED names but grants no authority over them. The publisher alone
retains and reproves their descriptors, exact bytes, and collective state.
Reusing the empty-namespace preflight after ATTEMPT would consume every valid
attempt as NOT_RUN and is forbidden by the public full-shaped integration test.

## State machine

```text
UNRESERVED
  -> PRE_OUTCOME
  -> STARTED
  -> READY_TO_COMMIT
  -> COMMITTED

PRE_OUTCOME failure before STARTED ownership -> NOT_RUN
STARTED failure before commit ownership      -> INVALID
unprovable identity/bytes/barrier/conflict    -> AMBIGUOUS
```

Monotonic boundaries:

- Once `open(O_EXCL)` returns a STARTED descriptor, NOT_RUN is forbidden. An
  exact STARTED receipt must be forward-completed or the state is AMBIGUOUS.
- Once `open(O_EXCL)` returns the output commit descriptor, INVALID is
  forbidden. An exact commit must be forward-completed or the state is
  AMBIGUOUS.
- A valid reviewed binding followed by an unavailable or different live parent
  is AMBIGUOUS even before ATTEMPT ownership. It is never interpreted as a fresh
  UNRESERVED namespace. This prevents a displaced `P1` and empty replacement
  `P2` from each invoking the callback under the same reviewed binding.
- COMMITTED means the attempt, STARTED, records, manifest, READY, and output
  commit are exact in two collective snapshots, while NOT_RUN and INVALID are
  absent. Records and manifest without that commit are non-authoritative.
- The private `after_file_fsync`, `after_parent_fsync`, and
  `after_file_durable` observers are non-authoritative after a file descriptor
  has been exclusively created. Their exception triggers a full reconciliation
  of that retained descriptor: file and parent barriers, generation, bytes,
  name, mode, ownership, and lexical parent are re-proved. If this succeeds,
  publication may continue even when the file is ATTEMPT, STARTED, records,
  MANIFEST, or READY. Mutation by the observer makes reconciliation fail closed.
- A private observation hook also cannot retract an already owned NOT_RUN,
  INVALID, or COMMITTED receipt. The complete terminal snapshot still runs, and
  mutation made by the observer remains AMBIGUOUS for the in-process publisher.
- A process restart may validate an exact terminal collective, but it may not
  reclaim or resume a non-terminal reservation. Before returning a recovered
  terminal, the verifier reopens every authoritative member, proves its stable
  generation across `fsync(file_fd)`, then `fsync`s the parent and repeats the
  full snapshot. Thus visible pre-barrier bytes are forward-completed rather
  than mistaken for evidence that the interrupted publisher's barrier returned.
  The authorization remains spent and a non-terminal state is AMBIGUOUS. If the
  original directory object is restored at the reviewed lexical path within the
  same identity epoch, its exact terminal collective can again be inspected;
  an empty replacement cannot be used for recovery or retry.

## Implemented evidence

The phase-1 module provides:

- a synthetic-only publisher whose outcome callback is invoked only after the
  exact STARTED boundary;
- a byte- and namespace-nonmutating terminal verifier that forward-syncs exact
  terminal files and their parent before returning recovered authority;
- a `--self-test` CLI with no `--plan` or `--run` surface;
- adversarial regressions for reservation races, first-stat substitution,
  restrictive `umask`, permission widening, foreign entry types, short writes,
  barrier order, post-`fsync` generation changes, hardlinks, same-inode
  mutation, byte-identical name replacement, terminal-hook failure and
  mutation, conflicting terminal receipts, READY-backed INVALID closure,
  verifier producer-image bounds, descriptor cleanup, parent pivot, subprocess
  crashes before each terminal barrier, case-insensitive output aliases,
  commit/sidecar overlap, raw-path normalization aliases, path-like exception
  status impersonation, filesystem-encoding boundaries, generated-nonce format,
  non-finite persisted JSON, caller-owned record-container reentrancy, pinned
  parent observation faults, pure and mutating post-barrier terminal observers,
  nonterminal durable-observer reconciliation, incremental record-byte refusal,
  parent-binding schema/digest/path/type/magnitude tampering, persisted
  self-reported binding mismatch, superseded v2 and v2r2 namespace refusal
  across all entry types and case, original-parent restore, sequential parent
  replacement replay, a two-process reservation race, and a two-process
  D1-to-D2 replacement race whose total callback count is at most one under the
  same binding. A separate negative regression retains the wider failure: the
  same opaque authorization digest plus a freshly captured D2 binding can invoke
  the callback a second time.

The legacy v1 directory publisher and analyzer remain present only as
compatibility code. Production planning emits authorization v2 material for
this layout. The public diagnostic entry point now accepts only that strict
reviewed schema and calls a distinct production v2r3 publisher; the synthetic
wire cannot be relabeled as production.

## Claim boundary

Observed:

- the synthetic regular-file substrate can close COMMITTED, NOT_RUN, and
  INVALID fixtures under its tests;
- injected ownership or terminal conflicts fail closed as AMBIGUOUS;
- a losing output reservation does not invoke the synthetic outcome callback;
- for one externally frozen parent identity chain on the tested local POSIX
  filesystem, replacing the lexical parent does not allow a second invocation
  to cross the callback boundary; the replacement inspector returns AMBIGUOUS,
  not UNRESERVED;
- the broader hypothesis is false for this synthetic API: if a caller retains
  the same opaque authorization digest but supplies a freshly captured binding
  for the replacement parent, the callback can run a second time.
- authorization v2 binds `publication_backend`, `artifact_layout`, the exact
  lexical output path and digest, the complete canonical parent binding and
  digest, and explicit environment-review requirements into one top-level
  digest;
- planning captures the parent binding once, revalidates that exact object
  around source and sealed-bundle reads, and attests this substrate's source
  bytes;
- the strict reviewed loader freezes authorization bytes before output access,
  never calls the planning capture helper, and reports a replaced parent as
  `PUBLICATION_STATE_AMBIGUOUS` rather than recapturing an empty namespace.
- the production wire closes an exact 240-frame collective, nested run manifest,
  READY receipt, and commit receipt, and its independent verifier returns only
  immutable-byte snapshots after two stable generations;
- a fixed-design 240-cell nondiagnostic fixture uses the same production
  publisher, runner action, record schema, and replay validator; its distinct
  authorization schema is rejected by the production loader.

Not established:

- creation, separate review, or merge of an actual 240-cell authorization
  candidate;
- authorization or execution of the sealed 240-cell diagnostic;
- qualification of an actual target host/filesystem identity epoch; the schema
  binds exact review requirements, but this implementation PR creates no target
  candidate;
- compatibility with the existing v1 analyzer, authorizations, or the
  superseded pre-release regular-file namespace;
- correctness on NFS, SMB, FUSE, or other unqualified filesystems;
- power-loss guarantees beyond the host filesystem's `fsync` contract;
- at-most-once authority across reboot, filesystem re-creation, inode/device ABA,
  another host, or another mount namespace; those require a separate stable
  external spent-authorization ledger rather than this inode binding;
- protection from a malicious kernel or root, or any untrusted process running
  under the publisher's effective UID with access to the output namespace or
  retained descriptors;
- any scientific result, direction, quality, or performance claim.

Production execution still requires qualification of the actual
platform/filesystem/identity epoch during a separate authorization review and a
fresh exact-head authority review of this integration. The planning capture
helper remains planning-only; only the strict reviewed loader may supply
expected binding bytes to production execution.

## Residual assumptions

- local POSIX `openat(O_EXCL)`, inode/link count, regular-file `fsync`, and
  directory `fsync` behave according to the host filesystem contract;
- for accepted ASCII basenames, any filesystem name alias has the same
  lowercase ASCII spelling; filesystems with trailing-dot/space folding, 8.3
  aliases, or other equivalence rules are unqualified;
- all superseded publisher binaries and processes are quiescent before `v2r3`
  uses a parent directory;
- the parent binding is valid only for the same host, filesystem identity epoch,
  and mount interpretation in which it was reviewed; device/inode reuse and
  undetectable ABA do not preserve authority;
- all same-UID processes with namespace access are part of the trusted computing
  base. Such a process can create exact expected bytes at an `O_EXCL` name, and
  restart inspection may accept that structurally exact collective. The owner
  nonce closes byte identity but is not creator authentication or provenance;
- exact terminal bytes can be integrity-validated after restart, but retained
  descriptor provenance ends with the publishing process, so inspection proves
  structural consistency and durability rather than creator authentication.
