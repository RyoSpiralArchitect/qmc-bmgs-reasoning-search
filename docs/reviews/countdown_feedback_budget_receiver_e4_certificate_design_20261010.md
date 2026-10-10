# E4 certificate design: bounded local review — 2026-10-10

Scope: certificate design, actual frozen lower code and retained E4 evidence.
This is the same agent's bounded local review, not independent-agent, external
or human approval. No certifier, publisher or successor coordinator was implemented.

## Verdict

Ready for the **read-only certifier implementation/test slice**, subject to its
own review and source freeze. Not ready to issue a certificate, qualify a new
coordinator, prepare a production candidate or execute the original study.
The [design](../strategy/countdown_feedback_budget_receiver_e4_certificate_design_20261010.md)
specifies C-T01–C-T16 as requirements, not passing new tests.

The earlier E4 evidence remains valid as historical reconstruction evidence.
Current receiver admission is still false; the original replication outcomes
remain unexecuted. Neither a design review nor a regression PASS changes that.

## Hazards addressed in the design

| Priority | Concrete hazard and code evidence | Resolution |
| --- | --- | --- |
| P1 | `N.verify_saved` requires saved reconstruction_head == current HEAD. E4's saved c19db4a result cannot be reinterpreted as a run at 3a69f33 or a later commit. | Leave that guard unchanged. Pin old bytes/HEAD as history; the new certifier owns fresh work and its own operation HEAD. The complete old 23-key schema is explicitly partitioned, without a general ignore/normalize rule. |
| P1 | `B.prepare` constructs authorization.json through candidate_projection as part of publication. Reusing it would exceed certificate-only scope and still invoke the old receiver checks. | Separate certificate-only publisher; no authorization file, candidate, consume or old bridge admission call. |
| P1 | `N.reconstruct` returns detached JSON, not the retained live capture needed before effects. A wrapper that accepts this JSON or a saved PASS as a proof could skip computation/revalidation. | New source-owned ordered reconstruction retains genuine evidence/runtime/source bindings; no caller proof/object/callback interface. Projection alone is not qualification. |
| P1 | A certificate binding the hash of its future verification receipt creates circular provenance; embedding the mutable operation HEAD prevents equality across review commits. | Certificate binds fixed sources and old evidence. Later verification/publication records bind the certificate, actual frozen operation HEAD and review revision, never vice versa. |
| P1 | E4 guards cover only frozen E4/lower source, not a new certifier/publisher. | Separate complete source receipts, callable/origin checks, phase-local source/HEAD revalidation and drift tests. Publisher source is in its own publication record. |
| P1 | `N.stable_state/revalidate` calls `C.unused(REPLICATION)`. Using it unchanged for analysis after consumption makes legitimate consumed evidence unverifiable; disabling it broadly removes protection. | C1/C3 remain pre-consumption. C4 must separately own exact persisted-claim post-consumption checks; no skip-unused switch and no claim that this gap is already implemented. |
| P2 | Reviewing the proposed certificate by pre-populating issued mirrors confuses proposal and publication, or occupies names the publisher must create exclusively. | One separately named review-only proposal.json; issued bundle/mirrors remain absent until their authorized phase. |
| P2 | A correct certificate/hash can obscure the historical negative screen or inflate the 2048 replay count into source-independent evidence. | Preserve both false screen conjunctions and full summary equality. Report one source multiset per PUBLIC archive, distinct from the original sealed 64-source inputs. |
| P2 | A post-write/fsync/delivery failure might incorrectly be reported as “not published” and retried, or permanent bundle-absence checks could reject its own valid creation. | Switch from pre-creation absence to exact owned directory/prefix. Retain occupied/partial/unknown/committed effects; no cleanup, resume, adoption or alternate namespace. Mirror promotion is later documentation, not a frozen-HEAD transaction write. |

These are hazards in prospective shortcuts, not findings that the frozen strict
receiver checks are bugs. The proposal addresses their design implications;
implementation tests and actual qualification remain required.

## Inspection boundary

Read the full E4 policy/result/review and October 1 successor design; inspected
the old certificate projection/reconstruction/prepare/admit path, E4 source and
saved-result gates, current-unused checks, snapshot/ReadOnlyArchive lifetime and
exclusive descriptor mechanics. File snapshots bind their own generation and
parent identities; evidence archives bind their directory generation. A new
sibling certificate bundle must not be mistaken for modification of those
immutable evidence archives or for blanket permission to mutate the ledger.

Authenticated all three promoted E4 receipts against 3a69f33121be244c21143979be0a04fe71cdac5e;
checked their complete observation/verification linkage and frozen source bytes.
The read-only inventory preserved 375 tracked files / 80086741 bytes with full
POSIX modes, both 1027-file PUBLIC archives, original three-file seal, three
ledger rows and four absent original slots. Six current E4 chains still match.
The proposed proposal/bundle/mirror names are absent, not reserved.

This inventory uses lstat/hash and reviewed Git comparison for bounded design
evidence. It is not the proposed descriptor-bound admission, numerical replay,
proof of physical identity, hostile-host protection or an atomic filesystem lock.
No original reconstruction or old same-HEAD verifier was rerun.

## Remaining gates

The new certifier's concrete private capture lifecycle, nested closed-schema
validation, source receipt, exact whole-certificate projection and failure
accounting need implementation and tests. The publisher's complete COMMIT
schema, owned-descriptor transaction and failure/delivery tests need a later
separate closure and review. The design does not conceal these as completed.

Actual certificate proposal generation and fresh-process verification/publication
need later explicit scopes; the latter must compare all canonical certificate
bytes after repeating the complete genuine path. New PUBLIC integration and
exact-new-digest production consent remain separate. The same-implementation
fresh process is operational independence, not algorithmic independence.

Full regression results and final preservation checks are recorded in the
[task report](../countdown_feedback_budget_receiver_e4_certificate_design_20261010.md)
and operations receipt. They validate unchanged code and design packaging, not
the unimplemented C-T cases or any newly issued certificate.

Completed local regression: 1484 tests in 860.034s, zero skips, plus all remaining
repository checks; exit0 and final repository validation PASS. The final inventory
after validation is byte-identical to the saved design inventory. Documentation
checks corrected a 24-versus-23 prose count and a helper regex that omitted the
digit in historical_e4; both failed outputs are retained. No production schema,
old receipt or source was changed to obtain a PASS.
