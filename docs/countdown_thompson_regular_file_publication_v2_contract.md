# Countdown Thompson regular-file publication v2 contract

Status: implemented and verified for non-diagnostic synthetic fixtures only.
Production diagnostic execution remains disabled.

## Question

Can the diagnostic publisher obtain exact attempt and artifact authority without
the portable-POSIX `mkdir` then `open/stat` interval that blocks the v1
directory protocol?

## Frozen phase-1 design

For an absolute output path `P/A`, v2 uses one flat namespace in the already
existing, non-symlink parent `P`:

```text
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.attempt.json
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.started.json
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.ready-to-commit.json
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.not-run.json
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.invalid.json
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.records.jsonl
P/.qmc-bmgs-v2-<sha256(lowercase ASCII basename)>.manifest.json
P/A                                                     # commit receipt, last
```

The output basename must be ASCII. The attempt name depends on a conservative
lowercase digest of that basename within its pinned parent, not the
authorization digest. The exact lexical output path retains a separate
provenance digest. Case-only and parent-path aliases that reach the same
directory therefore contend on the same sidecar reservation, while Unicode
filename-equivalence rules cannot create an unmodelled alias because non-ASCII
basenames are refused before parent access. This deliberately over-collapses
case variants on case-sensitive filesystems: denial of service is safer than
executing twice through a filesystem alias. A reserved output namespace is
single-use across all authorizations; a retry requires a new reviewed output
name.

Every protocol file is created directly at its final name with:

```text
openat(parent_fd, name,
       O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
       0600)
```

The descriptor returned by that successful call is the only in-process
ownership evidence. Matching bytes at a pre-existing name are never adopted.
The descriptor is retained through terminal proof.

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
  runs. Any mutation made before the exception therefore remains AMBIGUOUS.
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
  crashes before each terminal barrier, case-insensitive output aliases, and a
  two-process reservation race.

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
- compatibility with the existing v1 analyzer or authorizations;
- correctness on NFS, SMB, FUSE, or other unqualified filesystems;
- power-loss guarantees beyond the host filesystem's `fsync` contract;
- protection from a malicious kernel, root, or a same-UID process that already
  holds writable descriptors;
- any scientific result, direction, quality, or performance claim.

Production integration requires a separate authorization schema that binds
`publication_backend=posix_regular_files/v2` and
`artifact_layout=flat_commit_root/v2`, a production v2 analyzer, source/seal
closure integration, platform/filesystem qualification, and a fresh exact-head
authority review.

## Residual assumptions

- local POSIX `openat(O_EXCL)`, inode/link count, regular-file `fsync`, and
  directory `fsync` behave according to the host filesystem contract;
- inode metadata generation does not perform an undetectable ABA inside one
  collective proof interval;
- denial of service is allowed: interference may force AMBIGUOUS, but must not
  produce a false COMMITTED result;
- exact terminal bytes can be integrity-validated after restart, but retained
  descriptor provenance ends with the publishing process.
