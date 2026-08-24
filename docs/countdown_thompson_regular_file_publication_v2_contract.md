# Countdown Thompson regular-file publication v2 contract

Status: implemented and verified for non-diagnostic synthetic fixtures only.
Production diagnostic execution remains disabled.

Wire revision: `v2r2`. The superseded pre-release `.qmc-bmgs-v2-` namespace is
not adopted or migrated by this revision.

## Question

Can the diagnostic publisher obtain exact attempt and artifact authority without
the portable-POSIX `mkdir` then `open/stat` interval that blocks the v1
directory protocol?

## Frozen phase-1 design

For an absolute output path `P/A`, v2 uses one flat namespace in the already
existing, non-symlink parent `P`:

```text
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.attempt.json
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.started.json
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.ready-to-commit.json
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.not-run.json
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.invalid.json
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.records.jsonl
P/.qmc-bmgs-v2r2-<sha256(lowercase ASCII basename)>.manifest.json
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
of service is safer than executing twice through a filesystem alias. A reserved
output namespace is single-use across all authorizations; a retry requires a
new reviewed output name.

`v2r2` also performs a stable descriptor-bound directory scan before ownership,
before STARTED/callback boundaries, during every terminal proof, and during
restart inspection. Any entry whose lowercase name begins the superseded
`.qmc-bmgs-v2-` prefix blocks every output in that parent, regardless of the
entry's type, suffix, or bytes. It is never adopted, renamed, removed, or
forward-synchronized. This directory-wide fence prevents an old exact-path
reservation from being overlooked through a parent or basename alias. Running
a superseded publisher concurrently is outside the transition contract: all
older publisher processes must be quiescent before a parent is used with
`v2r2`.

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
record count that the restart verifier rejects.

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
- COMMITTED means the attempt, STARTED, records, manifest, READY, and output
  commit are exact in two collective snapshots, while NOT_RUN and INVALID are
  absent. Records and manifest without that commit are non-authoritative.
- A private observation hook cannot retract an already owned NOT_RUN, INVALID,
  or COMMITTED receipt. Its exception is ignored only after the corresponding
  retained terminal descriptor exists, and the complete exact snapshot still
  runs. Any mutation made before the exception therefore remains AMBIGUOUS for
  the in-process publisher.
- A process restart may validate an exact terminal collective, but it may not
  reclaim or resume a non-terminal reservation. Before returning a recovered
  terminal, the verifier reopens every authoritative member, proves its stable
  generation across `fsync(file_fd)`, then `fsync`s the parent and repeats the
  full snapshot. Thus visible pre-barrier bytes are forward-completed rather
  than mistaken for evidence that the interrupted publisher's barrier returned.
  The authorization remains spent and a non-terminal state is AMBIGUOUS.

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
  superseded-namespace refusal, and a two-process reservation race.

The existing v1 schemas, directory publisher, analyzer, and production entry
point are unchanged. The v1 fixture publisher remains private and the real
diagnostic entry point remains fail-closed.

## Claim boundary

Observed:

- the synthetic regular-file substrate can close COMMITTED, NOT_RUN, and
  INVALID fixtures under its tests;
- injected ownership or terminal conflicts fail closed as AMBIGUOUS;
- a losing output reservation does not invoke the synthetic outcome callback.

Not established:

- authorization of the sealed 240-cell diagnostic;
- compatibility with the existing v1 analyzer, authorizations, or the
  superseded pre-release regular-file namespace;
- correctness on NFS, SMB, FUSE, or other unqualified filesystems;
- power-loss guarantees beyond the host filesystem's `fsync` contract;
- protection from a malicious kernel or root, or any untrusted process running
  under the publisher's effective UID with access to the output namespace or
  retained descriptors;
- any scientific result, direction, quality, or performance claim.

Production integration requires a separate authorization schema that binds
`publication_backend=posix_regular_files/v2r2` and
`artifact_layout=flat_commit_root/v2r2`, a production v2r2 analyzer, source/seal
closure integration, platform/filesystem qualification, and a fresh exact-head
authority review.

## Residual assumptions

- local POSIX `openat(O_EXCL)`, inode/link count, regular-file `fsync`, and
  directory `fsync` behave according to the host filesystem contract;
- for accepted ASCII basenames, any filesystem name alias has the same
  lowercase ASCII spelling; filesystems with trailing-dot/space folding, 8.3
  aliases, or other equivalence rules are unqualified;
- all superseded publisher binaries and processes are quiescent before `v2r2`
  uses a parent directory;
- inode metadata generation does not perform an undetectable ABA inside one
  collective proof interval;
- all same-UID processes with namespace access are part of the trusted computing
  base; within that boundary, interference may force AMBIGUOUS but must not
  produce a false COMMITTED result;
- exact terminal bytes can be integrity-validated after restart, but retained
  descriptor provenance ends with the publishing process, so inspection proves
  structural consistency and durability rather than creator authentication.
