#!/usr/bin/env python3
"""One fixed E4 certificate-only publication, requiring separate issuance approval.

Implementation/self-test approval is NOT issuance approval. No supplied proof,
callback, output path, retry, mirror writer, candidate or execution dispatcher.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import stat
import sys
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/feedback_budget_receiver_e4_publisher.py"
TEST = "tests/test_feedback_budget_receiver_e4_publisher.py"
POLICY = "docs/strategy/countdown_feedback_budget_receiver_e4_publisher.md"
SOURCE_FILES = (SCRIPT, TEST, POLICY)
CERTIFIER_SCRIPT = "scripts/feedback_budget_receiver_e4_certificate.py"
CERTIFIER_REVISION = "23ac0587a1a519cfb85711ffdcc4b28c3ce41a47"
CERTIFIER_DIGEST = "4535836b9321da18e703a457356b5ff939cf8393414ddfa6ac845d2ec01f7f70"
PROPOSAL_REVISION = "d9809393352e533374eff3df742b7aa5c41e3ccb"
REVIEW_REVISION = "d3f088c324f59db433dc8e9fc9a4c194d2e17fe1"
SPEC = importlib.util.spec_from_file_location(
    "publisher_e4_frozen_certifier", ROOT / CERTIFIER_SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
K = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = K
SPEC.loader.exec_module(K)
N, V, C, R, S, core = K.N, K.V, K.C, K.R, K.S, K.core
M = S.mechanics
canonical, parse, require, digested, sha, exact = (
    K.canonical,
    K.parse,
    K.require,
    K.digested,
    K.sha,
    K.exact,
)
DOMAIN = S.DOMAIN + "/receiver-e4-certificate-publication/v1"
SCOPE = "ONE_FIXED_E4_CERTIFICATE_ONLY_NO_EXECUTION_AUTHORITY"
BUNDLE = ROOT / "artifacts/work/feedback-budget-receiver-e4-certificate-20261010-a"
NAMES = ("certificate.json", "verification.json", "COMMIT.json")
MIRRORS = tuple(
    ROOT
    / (
        "docs/qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010."
        + suffix
        + ".json"
    )
    for suffix in ("certificate", "verification", "commit")
)
REVIEW_PREFIX = "docs/qualifications/countdown_feedback_budget_receiver_e4_proposal_review_20261015."
# Every byte pin is checked BEFORE any historical JSON is parsed. A historical
# review result is a comparator, never a live reconstruction capability.
PINS = MappingProxyType(
    {
        K.PROPOSAL: (
            PROPOSAL_REVISION,
            226656,
            "129c3baa318eebb6eb88a6b124e84d681d1bd7f6b43596bc179908277e887c79",
        ),
        REVIEW_PREFIX + "verification.json": (
            REVIEW_REVISION,
            12500,
            "285e94e63abbc325a8d8176848ac3663ecfa238a7096c3e27631694c5eec0824",
        ),
        REVIEW_PREFIX + "operations.json": (
            REVIEW_REVISION,
            13464,
            "a33e28129c6b4e680869a87e8e8239a5c9a6b5bfa9e8daaaf99e000e49283dd5",
        ),
        "docs/reviews/countdown_feedback_budget_receiver_e4_proposal_review_20261015.md": (
            REVIEW_REVISION,
            7923,
            "fea7311251fc819e1b97273abfabf96f1fdad3d8e602df287a6c491a61e2eeeb",
        ),
    }
)
MAX_BYTES = 8 << 20
_STARTED = False


def closed_source(files):
    require(SOURCE_FILES == (SCRIPT, TEST, POLICY), "publisher source registry differs")
    require(
        type(files) is dict and set(files) == set(SOURCE_FILES),
        "exact publisher three-file closure required",
    )


def attest(revision):
    revision, head = R.oid(revision), core.git_head(ROOT)
    core.require_ancestor(ROOT, REVIEW_REVISION, revision)
    core.require_ancestor(ROOT, revision, head)
    require(Path(__file__).resolve() == ROOT / SCRIPT, "publisher origin differs")
    R.public._origin(K, CERTIFIER_SCRIPT)
    certifier = K.attest(CERTIFIER_REVISION)
    require(
        certifier["deterministic_digest"] == CERTIFIER_DIGEST,
        "frozen certifier differs",
    )
    files, snapshots = {}, []
    for relative in SOURCE_FILES:
        item = R.snapshot_file(ROOT / relative)
        R.reviewed_file(item, revision)
        files[relative] = dict(byte_count=len(item.raw), sha256=sha(item.raw))
        snapshots.append(item)
    closed_source(files)
    for item in snapshots:
        item.revalidate()
    require(core.git_head(ROOT) == head, "HEAD changed during publisher attestation")
    return digested(
        dict(
            schema_version=DOMAIN + "/source",
            implementation_revision=revision,
            proposal_review_revision=REVIEW_REVISION,
            files=files,
            certifier=certifier,
        )
    )


def _authenticate(evidence, source):
    items = {}
    for path, (revision, size, checksum) in PINS.items():
        item = evidence.file(ROOT / path)
        R.reviewed_file(item, revision)
        require(
            len(item.raw) == size and sha(item.raw) == checksum,
            "pinned proposal/review bytes differ: " + path,
        )
        items[path] = item
    evidence.revalidate()
    old = K.historical(evidence, source["certifier"]["frozen_reconstruction"])
    K._compare_certificate(
        items[K.PROPOSAL].raw,
        K._projection(
            old,
            source["certifier"],
            dict(original_public=False, receiver_v2_public=False),
        ),
    )
    verification = parse(items[REVIEW_PREFIX + "verification.json"].raw)
    core.require_digest(verification)
    exact(
        verification["reviewed_proposal"],
        dict(
            path=K.PROPOSAL,
            reviewed_revision=PROPOSAL_REVISION,
            **N.reference(items[K.PROPOSAL].raw),
        ),
        "reviewed proposal target differs",
    )
    exact(
        verification["implementation_source"],
        source["certifier"],
        "review certifier differs",
    )
    require(
        verification["certificate_issued"] is False, "proposal review is not issuance"
    )
    return items[K.PROPOSAL]


def _mirrors_absent():
    for path in MIRRORS:
        parent = M._PinnedParent.open(path.parent)
        try:
            parent.assert_path()
            M._assert_name_absent(parent, path.name)  # includes dangling symlinks
            parent.assert_path()
        finally:
            parent.close()


def _generation(parent, names):
    parent.assert_path()
    observed = os.fstat(parent.descriptor)
    require(
        stat.S_ISDIR(observed.st_mode)
        and stat.S_IMODE(observed.st_mode) == 0o700
        and observed.st_uid == os.geteuid(),
        "bundle must be private and owned",
    )
    before = M._parent_generation(parent)
    require(
        set(os.listdir(parent.descriptor)) == set(names),
        "exact owned filename prefix required",
    )
    entries = M._reserved_generation(parent, names)
    require(
        M._parent_generation(parent) == before,
        "bundle generation changed while observed",
    )
    parent.assert_path()
    return before, entries


def initial_effects():
    return dict(
        mkdir="NOT_ATTEMPTED",
        creation_parent_fsync="NOT_ATTEMPTED",
        creation_directory_fsync="NOT_ATTEMPTED",
        terminal_directory_fsync="NOT_ATTEMPTED",
        final_observation="NOT_ATTEMPTED",
        files={
            name: dict(
                exclusive_open="NOT_ATTEMPTED",
                write="NOT_ATTEMPTED",
                file_fsync="NOT_ATTEMPTED",
                directory_fsync="NOT_ATTEMPTED",
            )
            for name in NAMES
        },
    )


class PublicationFailure(Exception):
    def __init__(self, cause, phase, work, effects):
        super().__init__(str(cause))
        self.cause, self.phase = cause, phase
        self.work, self.effects = parse(canonical(work)), parse(canonical(effects))


class _Transaction:
    """Internal owned transaction; never accepted as a public input or proof."""

    def __init__(self):
        self.phase = "scope_and_source"
        self.work, self.effects = N.initial_work(), initial_effects()
        self.head = self.source = self.evidence = self.saved = self.capture = None
        self.outer = self.inner = None
        self.outer_generation = self.generation = None
        self.owned = []

    def prepare(self, revision):
        self.head = core.git_head(ROOT)
        self.source = attest(revision)
        self.evidence = V.Evidence()
        self.saved = _authenticate(self.evidence, self.source)
        self.outer = M._PinnedParent.open(BUNDLE.parent)
        self.outer_generation = M._parent_generation(self.outer)
        self.check()
        self.phase = "fresh_complete_reconstruction"
        self.capture = K.reconstruct(CERTIFIER_REVISION)
        state = K._state(
            self.capture
        )  # registered genuine type, not a structural receipt
        self.work = parse(state.work_raw)
        require(state.head == self.head, "reconstruction HEAD differs")
        exact(
            state.source,
            self.source["certifier"],
            "reconstructed certifier source differs",
        )
        require(
            self.capture.certificate_raw == self.saved.raw,
            "entire reconstructed certificate differs from proposal",
        )
        exact(
            dict(
                path=str(self.outer.path),
                identities=[list(x) for x in self.outer.component_identities],
            ),
            state.locations["live_locations"]["output_parent"],
            "publisher parent differs from reconstructed receiver",
        )
        self.phase = "final_live_prepublication_check"
        self.check()

    def storage(self):
        self.outer.assert_path()
        require(
            M._parent_generation(self.outer) == self.outer_generation,
            "output parent generation changed",
        )
        if self.inner is None:
            M._assert_name_absent(self.outer, BUNDLE.name)
            return
        self.inner.assert_path()
        require(
            self.inner.component_identities[:-1] == self.outer.component_identities,
            "owned directory parent changed",
        )
        names = NAMES[: len(self.owned)]
        require(
            tuple(item.name for item in self.owned) == names,
            "owned write order differs",
        )
        require(
            _generation(self.inner, names) == self.generation,
            "owned bundle generation changed",
        )
        for item in self.owned:
            M._assert_owned_exact(self.inner, item)
        require(
            _generation(self.inner, names) == self.generation,
            "owned bundle changed during readback",
        )

    def check(self):
        _guard()
        require(core.git_head(ROOT) == self.head, "publisher operation HEAD changed")
        exact(
            attest(self.source["implementation_revision"]),
            self.source,
            "publisher source changed",
        )
        require(
            not core.git_bytes(ROOT, "status", "--porcelain", "--untracked-files=all"),
            "publisher checkout must stay clean",
        )
        self.evidence.revalidate()
        if self.capture is not None:
            K._state(self.capture)
            self.capture.revalidate()
            require(
                self.capture.certificate_raw == self.saved.raw,
                "live certificate bytes changed",
            )
        C.unused(S.REPLICATION)
        _mirrors_absent()
        self.storage()
        self.evidence.revalidate()
        exact(
            attest(self.source["implementation_revision"]),
            self.source,
            "publisher source changed during live check",
        )
        require(
            not core.git_bytes(ROOT, "status", "--porcelain", "--untracked-files=all"),
            "publisher checkout must stay clean after live check",
        )
        self.storage()
        require(core.git_head(ROOT) == self.head, "publisher operation HEAD changed")
        _guard()

    def create_directory(self):
        self.phase = "exclusive_bundle_creation"
        self.check()
        self.effects["mkdir"] = "UNKNOWN_PARTIAL_OR_COMPLETE"
        os.mkdir(BUNDLE.name, 0o700, dir_fd=self.outer.descriptor)
        self.effects["mkdir"] = "COMPLETE"
        observed = os.stat(
            BUNDLE.name, dir_fd=self.outer.descriptor, follow_symlinks=False
        )
        require(stat.S_ISDIR(observed.st_mode), "created bundle is not a directory")
        self.inner = M._PinnedParent.open(BUNDLE)
        require(
            M._directory_identity(observed) == self.inner.component_identities[-1],
            "created bundle identity changed",
        )
        require(
            self.inner.component_identities[:-1] == self.outer.component_identities,
            "created bundle parent changed",
        )
        self.outer_generation = M._parent_generation(self.outer)
        self.generation = _generation(self.inner, ())
        self.check()
        self.sync(self.outer, self.effects, "creation_parent_fsync")
        self.sync(self.inner, self.effects, "creation_directory_fsync")

    def sync(self, parent, effects, key):
        self.check()
        effects[key] = "UNKNOWN_PARTIAL_OR_COMPLETE"
        parent.fsync()  # one barrier only; no reconciliation/retry on error
        effects[key] = "COMPLETE"
        self.check()

    def create_file(self, name, raw):
        require(
            len(self.owned) < 3 and name == NAMES[len(self.owned)],
            "fixed next filename required",
        )
        require(
            type(raw) is bytes and len(raw) <= MAX_BYTES,
            "bounded canonical payload required",
        )
        core.require_digest(parse(raw))
        self.phase = "exclusive_" + name
        self.check()
        effects = self.effects["files"][name]
        effects["exclusive_open"] = "UNKNOWN_PARTIAL_OR_COMPLETE"
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=self.inner.descriptor,
        )
        effects["exclusive_open"] = "COMPLETE"
        item = M._OwnedRegularFile(name, descriptor, b"")
        self.owned.append(item)  # retain descriptor even if initial observation fails
        observed = os.fstat(descriptor)
        item.identity, item.signature = (
            M._directory_identity(observed),
            M._stable_file_signature(observed),
        )
        # Enforces single link, exact 0600, uid, empty bytes, retained fd/name identity.
        M._assert_owned_exact(self.inner, item)
        previous = self.generation
        self.generation = _generation(self.inner, NAMES[: len(self.owned)])
        require(
            all(entry in self.generation[1] for entry in previous[1]),
            "prior prefix changed during exclusive open",
        )
        self.check()
        effects["write"] = "UNKNOWN_PARTIAL_OR_COMPLETE"
        M._write_all(descriptor, raw)
        effects["write"] = "COMPLETE"
        item.expected = raw
        item.signature = M._stable_file_signature(os.fstat(descriptor))
        M._assert_owned_exact(self.inner, item)
        previous = self.generation
        self.generation = _generation(self.inner, NAMES[: len(self.owned)])
        require(
            self.generation[0] == previous[0], "directory changed during file write"
        )
        require(
            all(
                entry in self.generation[1] for entry in previous[1] if entry[0] != name
            ),
            "other file changed during write",
        )
        self.check()
        effects["file_fsync"] = "UNKNOWN_PARTIAL_OR_COMPLETE"
        os.fsync(descriptor)
        effects["file_fsync"] = "COMPLETE"
        self.check()
        self.sync(self.inner, effects, "directory_fsync")

    def location(self):
        self.storage()
        state = K._state(self.capture)
        parent = state.locations["persistent_locations"]["output_parent"]
        volume_uuid = K._volume_uuid(self.inner.descriptor)
        require(
            volume_uuid == parent["components"][-1]["volume_uuid"],
            "bundle volume differs",
        )
        result = dict(
            path=str(BUNDLE),
            live_component_identities=[
                list(x) for x in self.inner.component_identities
            ],
            persistent_components=parent["components"]
            + [
                dict(
                    volume_uuid=volume_uuid,
                    inode=self.inner.component_identities[-1][1],
                )
            ],
        )
        self.storage()
        return result

    def close(self):
        for item in reversed(self.owned):
            item.close()
        if self.inner is not None:
            self.inner.close()
        if self.outer is not None:
            self.outer.close()


def _verification(transaction):
    transaction.check()
    operation = K.operation_receipt(transaction.capture)
    return digested(
        dict(
            schema_version=DOMAIN + "/verification",
            status="WHOLE_RECONSTRUCTED_PROPOSAL_BYTE_IDENTICAL_BEFORE_ISSUANCE",
            scope=SCOPE,
            operation_head=transaction.head,
            publisher_source=transaction.source,
            certifier_source=operation["implementation_source"],
            receiver_identity=operation["receiver_identity"],
            reviewed_proposal=dict(
                path=K.PROPOSAL,
                reviewed_revision=PROPOSAL_REVISION,
                **N.reference(transaction.saved.raw),
            ),
            proposal_review_revision=REVIEW_REVISION,
            proposal_review_records={
                path: dict(reviewed_revision=revision, byte_count=size, sha256=checksum)
                for path, (revision, size, checksum) in PINS.items()
                if path != K.PROPOSAL
            },
            independently_reconstructed_certificate=N.reference(
                transaction.capture.certificate_raw
            ),
            complete_canonical_certificate_byte_identical=True,
            verification_method=K.METHOD,
            algorithmically_independent_implementation=False,
            work=transaction.work,
            original_study_slot_absent_at_verification=True,
            certificate_issued_at_verification=False,
            claim_ceiling=K.ceiling(),
        )
    )


def _commit(transaction, verification_raw):
    transaction.check()
    return digested(
        dict(
            schema_version=DOMAIN + "/commit",
            status="CERTIFICATE_ONLY_BUNDLE_COMMIT",
            scope=SCOPE,
            operation_head=transaction.head,
            publisher_source=transaction.source,
            certifier_source=transaction.source["certifier"],
            reviewed_proposal_revision=PROPOSAL_REVISION,
            proposal_review_revision=REVIEW_REVISION,
            bundle_location=transaction.location(),
            payloads={
                "certificate.json": N.reference(transaction.capture.certificate_raw),
                "verification.json": N.reference(verification_raw),
            },
            publication_order=list(NAMES),
            claim_ceiling=K.ceiling(),
        )
    )


def issue(implementation_revision, *, scope):
    """Only a full immutable revision and explicit certificate-only scope enter."""
    global _STARTED
    transaction = _Transaction()
    try:
        _guard()
        require(
            type(scope) is str and scope == SCOPE,
            "explicit certificate-only scope required",
        )
        require(
            type(implementation_revision) is str,
            "full implementation revision required; no proof input",
        )
        require(
            not _STARTED and not K._RECONSTRUCTION_STARTED and not K._LIVE,
            "fresh process required; no adoption, retry or resume",
        )
        _STARTED = True
        implementation_revision = R.oid(implementation_revision)
        M._require_posix_capabilities()
        transaction.prepare(implementation_revision)
        verification_raw = canonical(_verification(transaction))
        transaction.create_directory()
        transaction.create_file("certificate.json", transaction.capture.certificate_raw)
        transaction.create_file("verification.json", verification_raw)
        commit_raw = canonical(_commit(transaction, verification_raw))
        transaction.create_file("COMMIT.json", commit_raw)
        transaction.phase = "terminal_durability_and_owned_observation"
        transaction.sync(
            transaction.inner, transaction.effects, "terminal_directory_fsync"
        )
        transaction.effects["final_observation"] = "UNKNOWN_PARTIAL_OR_COMPLETE"
        transaction.check()
        transaction.effects["final_observation"] = "COMPLETE"
        return digested(
            dict(
                schema_version=DOMAIN + "/operation",
                status="CERTIFICATE_ONLY_BUNDLE_ISSUED",
                scope=SCOPE,
                operation_head=transaction.head,
                publisher_source=transaction.source,
                bundle_path=str(BUNDLE),
                certificate=N.reference(transaction.capture.certificate_raw),
                verification=N.reference(verification_raw),
                commit=N.reference(commit_raw),
                effects=transaction.effects,
                work=transaction.work,
                certificate_issued=True,
                promoted_mirrors_written=False,
                execution_dispatch_entered=False,
                claim_ceiling=K.ceiling(),
            )
        )
    except (Exception, KeyboardInterrupt) as error:
        if isinstance(error, K.CertificateFailure):
            transaction.work = error.work
        raise PublicationFailure(
            error, transaction.phase, transaction.work, transaction.effects
        ) from error
    finally:
        transaction.close()  # close only: never unlink, rename, adopt or retry


def failure_receipt(error, completed=None, delivery="NOT_ATTEMPTED"):
    effects = (
        error.effects
        if isinstance(error, PublicationFailure)
        else (completed["effects"] if completed else initial_effects())
    )
    commit = effects["files"]["COMMIT.json"]
    return digested(
        dict(
            schema_version=DOMAIN + "/failure",
            status="PUBLICATION_REJECTED_OR_PARTIAL_OR_DELIVERY_UNCERTAIN",
            phase=error.phase
            if isinstance(error, PublicationFailure)
            else "result_delivery",
            reason=str(error),
            scope=SCOPE,
            effects=effects,
            work=error.work
            if isinstance(error, PublicationFailure)
            else (completed["work"] if completed else None),
            certificate_issued=True
            if completed
            else (False if commit["exclusive_open"] == "NOT_ATTEMPTED" else None),
            durable_commit_barriers_completed=all(
                commit[key] == "COMPLETE"
                for key in ("write", "file_fsync", "directory_fsync")
            ),
            result_delivery=delivery,
            completed_operation=completed,
            retain_all_created_entries=True,
            automatic_retry_allowed=False,
            promoted_mirrors_written=False,
            execution_dispatch_entered=False,
            authorization_consumed=None,
            claim_ceiling=K.ceiling(),
        )
    )


def _guard():
    K._guard()
    require(
        M._PinnedParent.open.__func__ is _OPEN_PARENT,
        "publisher directory opener substituted",
    )
    for module, name, expected in _DEPENDENCIES:
        require(
            getattr(module, name) is expected, "publisher callable substituted: " + name
        )


def self_test():
    _guard()
    closed_source(dict.fromkeys(SOURCE_FILES))
    require(
        NAMES == ("certificate.json", "verification.json", "COMMIT.json"),
        "certificate-only prefix differs",
    )
    return digested(
        dict(
            schema_version=DOMAIN + "/self-test",
            status="STATIC_SELF_TEST_ONLY",
            work=N.initial_work(),
            filesystem_effects_attempted=False,
            certificate_issued=False,
            claim_ceiling=K.ceiling(),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--issue-certificate-only", action="store_true")
    parser.add_argument("--implementation-revision")
    args = parser.parse_args()
    if args.self_test and args.implementation_revision is not None:
        parser.error("self-test takes no revision")
    if args.issue_certificate_only and args.implementation_revision is None:
        parser.error("immutable publisher implementation revision required")
    completed, delivery = None, "NOT_ATTEMPTED"
    try:
        result = (
            self_test()
            if args.self_test
            else issue(args.implementation_revision, scope=SCOPE)
        )
        if not args.self_test:
            completed = result
        raw = canonical(result)
        delivery = "UNKNOWN_PARTIAL_OR_COMPLETE"
        require(sys.stdout.buffer.write(raw) == len(raw), "short result write")
        sys.stdout.buffer.flush()
        delivery = "COMPLETE_STDOUT_FLUSH"
    except (Exception, KeyboardInterrupt) as error:
        sys.stderr.buffer.write(canonical(failure_receipt(error, completed, delivery)))
        sys.stderr.buffer.flush()
        raise SystemExit(1) from error


_OPEN_PARENT = M._PinnedParent.open.__func__
_DEPENDENCIES = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            K,
            (
                "_guard",
                "attest",
                "historical",
                "_projection",
                "_compare_certificate",
                "reconstruct",
                "_state",
                "operation_receipt",
                "_volume_uuid",
                "ceiling",
            ),
        ),
        (V, ("Evidence",)),
        (V.Evidence, ("file", "revalidate")),
        (N, ("reference", "initial_work")),
        (R, ("snapshot_file", "reviewed_file", "oid")),
        (C, ("unused",)),
        (core, ("git_head", "git_bytes", "require_ancestor", "require_digest")),
        (
            M,
            (
                "_PinnedParent",
                "_OwnedRegularFile",
                "_assert_owned_exact",
                "_assert_name_absent",
                "_parent_generation",
                "_reserved_generation",
                "_write_all",
                "_read_exact_pread",
                "_walk_absolute_directory_nofollow",
                "_close_best_effort",
                "_stable_file_signature",
                "_directory_identity",
                "_require_posix_capabilities",
            ),
        ),
        (M._PinnedParent, ("assert_path", "fsync", "close")),
        (M._OwnedRegularFile, ("close",)),
        (
            _Transaction,
            (
                "__init__",
                "prepare",
                "storage",
                "check",
                "create_directory",
                "sync",
                "create_file",
                "location",
                "close",
            ),
        ),
        (
            sys.modules[__name__],
            (
                "closed_source",
                "attest",
                "_authenticate",
                "_mirrors_absent",
                "_generation",
                "initial_effects",
                "_Transaction",
                "_verification",
                "_commit",
                "issue",
                "canonical",
                "parse",
                "require",
                "digested",
                "sha",
                "exact",
            ),
        ),
    )
    for name in names
)


if __name__ == "__main__":
    main()
