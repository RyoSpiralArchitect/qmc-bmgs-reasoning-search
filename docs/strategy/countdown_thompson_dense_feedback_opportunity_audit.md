# Dense-scale feedback opportunity and observed conversion audit

Date fixed: 2026-09-04. This is a post-outcome, exploratory audit, not a new
preregistration. The existing scale-16 result and terminal-count distribution
were already known when these additional reductions were fixed.

## Scope and evidence boundary

Use only the existing 384-cell dense-scale artifact, its six lifecycle files,
the exact PR #23 authorization, and the canonical PR #24 summary. Preserve all
336 positive-scale / scale-zero pairs in the original order and the original
`STOP_REPAIR_NO_LOCKED_128_RUN` decision. No new task, scale, seed, proposal,
budget, provider call, search execution, alternative continuation, or outcome
retry is permitted.

The audit is a standalone standard-library tool. It changes no frozen package
source. It must pin external input bytes to the recorded SHA-256 anchors,
check canonical JSON / JSONL, reconstruct event hash chains and accepted
hard-work charges, and cross-check trace outcomes and pair coordinates against
the already replay-closed summary. It does not itself rerun generative search
or stage-two replay. Historical replay PASS and this audit's byte/ledger /
reduction checks must remain separately labelled.

Frozen anchors:

- observation merge: `1ffe31668e4642e95ec0fbadd1b4f52a287e1dad`;
- authorization merge: `f13e3a5d08333f94e44eeeb921e2dfe253cc72e8`;
- authorization SHA-256:
  `c043085cccaec720a782d9297599e35b72a8cb9ca015fa98d800923c4eec92dd`;
- raw JSONL SHA-256:
  `50d671822a94d0c43c75087ea3edbcb7264977e32e95efd78ddb0fdbc482478e`;
- summary SHA-256:
  `76e181de21f7efbd4eb826f5dff181d7e13a1daf5c0da2e926b76f305b2fc651`;
- summary deterministic digest:
  `b7886df480ad0047d781673119b24482711a89ff46929066152a1c9c18d7e1e7`.

All six raw file names, sizes, and hashes are fixed in the PR #24 evidence
inventory; they cannot be replaced by a caller-supplied expected digest.

## Definitions fixed before additional raw reductions

1. Reconstruct seven-axis usage from the contiguous event `charge` receipts.
   Each accepted receipt contributes once; events without a receipt contribute
   zero. Check the final usage against the ledger and record budget evidence.
   A rejected stop charge is not accepted work and must not be added.
2. Use the original summary's first action-divergence coordinate and check both
   actual selection events, action indices, states, and full score vectors.
   Do not pair decisions after that first divergence.
3. At divergence, report both traces' remaining budget immediately before the
   selection's accepted charge and immediately after it. This is not the
   first uncharged proposal-material event of its batch.
4. Find the earliest differing applied backup value on the recorded common
   prefix. Count completed terminals strictly after that backup, separately
   for baseline and scaled traces. No such backup is `null`, not zero exposure.
5. Count completed terminals after the divergent selection by event order,
   using explicit trajectory IDs. The diverged trajectory is complete only
   if its own terminal event appears afterward. Never infer trajectory IDs
   from terminal-vector length or observation index. Record remaining completed
   opportunities in bins `0`, `1`, and `2+`; retain nondivergent pairs separately.
6. The common-prefix minimum error uses all verified terminals before the
   divergence, and must agree on both sides. The observed suffix uses all
   verified terminals after it. Report `no_completed_terminal`,
   `no_prefix_terminal`, `exact_hit`, `improved_nonexact`, `tied`, or `worse`.
   A suffix exact hit is not automatically a new cell success: preserve the
   separate original whole-cell new/lost-success indicators.
7. Report whole-cell minimum-error wins/ties/losses versus scale zero for every
   pair and cross-tab them by scaled post-divergence opportunity bin. Keep
   the full 48-pair denominator per scale, with explicit `no_divergence`.
8. At the shared first-divergence surface, retain preceding backup support,
   baseline and scaled selected actions, and exact-rational score margins and
   scaled-winner displacement obtained from the stored binary64 values.
   These are descriptive local scores, not a posterior-probability claim.
9. Count distinct task/seed pairs and distinct tasks as well as scale-pair
   entries; the same rescue at scales 16/32/64 is not three independent rescues.
   Report each trace's actual stop reason, blocked axes, uncharged attempted
   step, and final remaining budget without inferring an unobserved continuation.

## Publication and interpretation

Require a clean committed audit source, safe-path/no-bytecode startup, exact
source and design bytes, and read-only descriptor snapshots of all inputs.
Publish a new canonical audit receipt outside raw / source / preregistration
with exclusive creation and file/directory durability checks. Never overwrite
an existing destination. An uncertain publication retains its slot and must
not be called a valid published receipt. This is a local quiescent POSIX
operation, not hostile same-UID, kernel, reboot, NFS/SMB/FUSE, or transient
source replacement protection.

Opportunity bins are post-intervention quantities. Cross-tabulations are
descriptive: they cannot establish that insufficient budget caused failure,
that extra budget would rescue a cell, or that terminal closeness predicts
future solvability. The purpose is to prioritize one later repair-development
hypothesis. Any new outcome-bearing experiment still requires a separately
frozen design and authorization; the original STOP result grants no
confirmation or locked-128 authority.
