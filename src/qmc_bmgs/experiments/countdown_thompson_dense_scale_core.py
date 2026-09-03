"""Outcome-blind identities and exact cell execution for the dense-scale lane.

No public function in this module grants production authority. The runner owns
the reviewed-authorization and STARTED barriers; the analyzer independently
replays the complete collective before performing any scientific reduction.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import os
import platform
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from qmc_bmgs.benchmarks.countdown import CountdownTask
from qmc_bmgs.experiments import countdown_thompson_dense_scale_manifest as manifest
from qmc_bmgs.experiments import (
    countdown_thompson_regular_file_publication_v2 as storage,
)
from qmc_bmgs.substrate.budget import TRACK_A_WORK_AXES, TrackAWorkBudget
from qmc_bmgs.substrate.countdown_search import (
    TrackABudgetProfile,
    TrackAMethodSpec,
    build_search_run_identity,
    project_track_a_anchor_equivalence_trace,
    replay_countdown_track_a_search_bytes,
    run_countdown_track_a_search,
    search_runtime_metadata,
)
from qmc_bmgs.substrate.perturbations import perturbation_runtime_metadata
from qmc_bmgs.substrate.proposals import TrackAProposalSpec
from qmc_bmgs.substrate.trace import canonical_json, sha256_json, strict_json_loads


BUNDLE_ID = "countdown_thompson_dense_scale_12_seed_26082601/v1"
AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-dense-scale-execution-authorization/v1"
)
AUTHORIZATION_SCOPE = "one_exact_complete_384_cell_dense_scale_development_run"
EXECUTION_MODE = "authorized_dense_scale_development"
FIXTURE_BUNDLE_ID = "countdown_thompson_dense_scale_nondiagnostic_full_shape_384/v1"
FIXTURE_AUTHORIZATION_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-dense-scale-nondiagnostic-full-shape-"
    "execution-authorization/v1"
)
FIXTURE_AUTHORIZATION_SCOPE = (
    "one_exact_nondiagnostic_dense_scale_full_shape_384_cell_fixture"
)
FIXTURE_EXECUTION_MODE = "nondiagnostic_dense_scale_full_shape_fixture"
FIXTURE_DESIGN_DIGEST = (
    "2c7b2831a59872560e0310339ea21b7a6cc84ff513eba30f204562b980518d0c"
)
FIXTURE_SCHEDULE_DIGEST = (
    "d68dd802e683ebcf81f3ce78c3fb297e8c1ecf8ed9059ae1cc869d25845d9d1e"
)
RECORD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-run-record/v1"
FIXTURE_RECORD_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-dense-scale-nondiagnostic-full-shape-run-record/v1"
)
FIXTURE_STEM = "qmc-bmgs-countdown-thompson-dense-scale-nondiagnostic-full-shape"
CLAIM_BOUNDARY = "one development run only; no confirmation, superiority, QMC, or locked-128 authority"
FIXTURE_CLAIM_BOUNDARY = (
    "public fixture plumbing only; no development result or scientific decision"
)
EXPECTED_CELL_COUNT = 384
SCALE_ORDER = (0, 1, 2, 4, 8, 16, 32, 64)
EXPLORATION_SEEDS = (7168, 7169, 7170, 7171)
PREREGISTRATION_MERGE_REVISION = "03818e81d27e67488524ed3cb8f7eadcd32becdd"
CONTRACT_MERGE_REVISION = "3e486c6c196ff6a296e5692555a8e3a885713b18"
FROZEN_AUTHORITY = {
    "analysis_manifest_digest": "07303c90974612e9ac20fc285718170385dc9e13de5abb929a2038c2ebf70b02",
    "anchor_qualification_digest": "2b79d8c052aeef0a39209b41e0de5ff1c09a7b4b69234e7434b39da79bc7ca92",
    "budget_manifest_digest": "c41e5a817c261cd88281c52b8367ecca4f208b8f9e8fed0b6624deb84547e062",
    "bundle_id": BUNDLE_ID,
    "cell_count": EXPECTED_CELL_COUNT,
    "dense_scale_seal_digest": "49f820692aa4f3551ca5634bdc89efe225fe05d1dc8acb8e814f231f3eea222f",
    "method_manifest_digest": "66195d7888efaf588f4eb050a7c9272a8159b5550e786afe1432f9e5df2beebd",
    "preregistration_file_sha256": "bc68216a2f3e4809fd65914cd7a663d9d8f4ff74c3299de5e1ac36a04eecb547",
    "proposal_manifest_digest": "f9f0d84d7e8ae1cb344efc7d56a9db0adc038929658ef9a81259cf52fe3364f5",
    "runtime_binding_digest": "bfd7429ab09aa64365efccedec3da99082a93e6c54ab8f2d8b79cb98099504e2",
    "schedule_digest": "ea488a273282acecd7e4113ebc123daf4651b0b04f9d4e1f36264b7d4644aebd",
}
PUBLIC_CONTRACT_RELATIVE_PATH = (
    "src/qmc_bmgs/data/countdown_thompson_dense_scale_public_contract_v1.json"
)
PUBLIC_CONTRACT_SHA256 = (
    "0d4962c53c9559385c224b68b5713e675c29692c19d1dda20f85726b0fc2de6f"
)
BUILD_SCHEMA_VERSION = "qmc-bmgs-countdown-thompson-dense-scale-source-build/v1"
RUNTIME_SCHEMA_VERSION = (
    "qmc-bmgs-countdown-thompson-dense-scale-runtime-qualification/v1"
)

# A fixed conservative superset, not a discovery-based allowlist. Historical
# implementations remain byte-identical; loaded package modules outside this
# set are refused. Public data is protected by the same Git/source-byte gate.
_PACKAGE_PATHS = (
    "__init__.py",
    "anthropic_countdown.py",
    "openai_countdown.py",
    "policy.py",
    "countdown_scoring.py",
    "records.py",
    "benchmarks/__init__.py",
    "benchmarks/countdown.py",
    "benchmarks/role_lock.py",
    "data/__init__.py",
    "experiments/__init__.py",
    "experiments/channel_ablation.py",
    "experiments/countdown_anthropic_dev.py",
    "experiments/countdown_calibration_adversarial_audit.py",
    "experiments/countdown_calibration_grid.py",
    "experiments/countdown_openai_dev.py",
    "experiments/countdown_thompson_dense_scale_manifest.py",
    "experiments/countdown_thompson_dense_scale_core.py",
    "experiments/countdown_thompson_dense_scale_publication.py",
    "experiments/countdown_thompson_dense_scale_runner.py",
    "experiments/countdown_thompson_dense_scale_analysis.py",
    "experiments/countdown_thompson_diagnostic_analysis.py",
    "experiments/countdown_thompson_diagnostic_manifest.py",
    "experiments/countdown_thompson_diagnostic_runner.py",
    "experiments/countdown_thompson_posthoc_mechanism.py",
    "experiments/countdown_thompson_regular_file_publication_v2.py",
    "experiments/countdown_thompson_selection_margin.py",
    "experiments/countdown_thompson_source_ablation.py",
    "experiments/countdown_track_a_canary_analysis.py",
    "experiments/countdown_track_a_canary_manifest.py",
    "experiments/countdown_track_a_canary_runner.py",
    "experiments/countdown_track_a_search.py",
    "experiments/countdown_track_a_substrate.py",
    "experiments/credit_assignment.py",
    "experiments/d4_noise_sweep.py",
    "experiments/fixed_verifier_budget.py",
    "experiments/two_phase_sampler.py",
    "experiments/two_phase_validation.py",
    "substrate/__init__.py",
    "substrate/budget.py",
    "substrate/countdown_search.py",
    "substrate/perturbations.py",
    "substrate/proposals.py",
    "substrate/trace.py",
)
PROTECTED_SOURCE_PATHS = tuple(
    sorted(
        tuple("src/qmc_bmgs/" + path for path in _PACKAGE_PATHS)
        + (PUBLIC_CONTRACT_RELATIVE_PATH,)
    )
)
SEARCH_SOURCE_PATHS = tuple(str(path) for path in manifest._SOURCE_BINDING_PATHS)
RECORD_FIELDS = {
    "budget_evidence",
    "cell_id",
    "cell_key",
    "deterministic_digest",
    "provider_calls",
    "replay",
    "run_binding_digest",
    "schema_version",
    "search_record",
    "search_run_identity_digest",
    "search_trace_byte_count",
    "search_trace_sha256",
    "source_multiset_fingerprint",
}


class DenseScaleExecutionError(ValueError):
    """A dense-scale input or exact execution invariant failed closed."""


def canonical_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_canonical(raw: bytes) -> dict[str, Any]:
    try:
        parsed = strict_json_loads(raw.decode("utf-8"))
        if type(parsed) is not dict or canonical_bytes(parsed) != raw:
            raise DenseScaleExecutionError("expected one canonical JSON object")
        return parsed
    except (UnicodeError, TypeError, ValueError, RecursionError) as error:
        raise DenseScaleExecutionError("invalid canonical JSON object") from error


def with_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "deterministic_digest" in payload:
        raise DenseScaleExecutionError("digest already exists")
    snapshot = parse_canonical(canonical_bytes(dict(payload)))
    snapshot["deterministic_digest"] = sha256_json(snapshot)
    return snapshot


def require_sha256(value: object, label: str = "digest") -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise DenseScaleExecutionError(f"{label} must be lowercase SHA-256")
    return value


def require_digest(payload: object, fields: set[str] | None = None) -> dict[str, Any]:
    if type(payload) is not dict or (fields is not None and set(payload) != fields):
        raise DenseScaleExecutionError("closed object field set drifted")
    value = require_sha256(payload.get("deterministic_digest"))
    if (
        sha256_json({k: v for k, v in payload.items() if k != "deterministic_digest"})
        != value
    ):
        raise DenseScaleExecutionError("object digest drifted")
    return payload


def _generation(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    raw: bytes = field(repr=False)
    generation: tuple[int, ...]
    parent_identities: tuple[tuple[int, int], ...]
    byte_cap: int

    @classmethod
    def capture(
        cls, path: Path | str, *, byte_cap: int = 8 * 1024 * 1024
    ) -> FileSnapshot:
        path = Path(path).absolute()
        if ".." in path.parts:
            raise DenseScaleExecutionError(
                "snapshot path may not contain parent traversal"
            )
        parent_fd = file_fd = -1
        result = None
        failure = None
        try:
            parent_fd, parents = storage._walk_absolute_directory_nofollow(path.parent)
            before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > byte_cap
            ):
                raise DenseScaleExecutionError(
                    "snapshot must be one bounded non-linked regular file"
                )
            file_fd = os.open(
                path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            opened = os.fstat(file_fd)
            if _generation(opened) != _generation(before):
                raise DenseScaleExecutionError("snapshot changed during open")
            chunks = []
            total = 0
            while True:
                block = os.read(file_fd, min(1024 * 1024, byte_cap + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > byte_cap:
                    raise DenseScaleExecutionError("snapshot exceeds byte cap")
                chunks.append(block)
            raw = b"".join(chunks)
            after = os.fstat(file_fd)
            lexical = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            check_fd, check_parents = storage._walk_absolute_directory_nofollow(
                path.parent
            )
            try:
                if (
                    parents != check_parents
                    or _generation(after) != _generation(before)
                    or _generation(lexical) != _generation(before)
                    or len(raw) != after.st_size
                ):
                    raise DenseScaleExecutionError("snapshot identity or bytes changed")
            finally:
                os.close(check_fd)
            result = cls(path, raw, _generation(after), parents, byte_cap)
        except (OSError, ValueError, storage.RegularFilePublicationV2Error) as error:
            failure = error
        finally:
            for descriptor in (file_fd, parent_fd):
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError as error:
                        failure = failure or error
        if failure is not None or result is None:
            raise DenseScaleExecutionError(
                f"cannot attest stable regular file: {path.name}"
            ) from failure
        return result

    def revalidate(self) -> None:
        other = FileSnapshot.capture(self.path, byte_cap=self.byte_cap)
        if other != self:
            raise DenseScaleExecutionError("immutable input identity changed")


def public_contract() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / Path(PUBLIC_CONTRACT_RELATIVE_PATH).name
    )
    raw = FileSnapshot.capture(path).raw
    if sha256_bytes(raw) != PUBLIC_CONTRACT_SHA256:
        raise DenseScaleExecutionError("public contract source bytes drifted")
    payload = strict_json_loads(raw.decode("utf-8"))
    if type(payload) is not dict or set(payload) != {
        "analysis",
        "budget",
        "proposal",
        "methods",
        "runtime_binding",
        "schema_version",
    }:
        raise DenseScaleExecutionError("public contract shape drifted")
    for key in ("analysis", "budget", "proposal", "methods", "runtime_binding"):
        require_digest(payload[key])
    return payload


def anchor_qualification() -> dict[str, Any]:
    result = public_contract()["analysis"]["anchor_equivalence"]["qualification"]
    require_digest(result)
    if (
        result["deterministic_digest"]
        != FROZEN_AUTHORITY["anchor_qualification_digest"]
    ):
        raise DenseScaleExecutionError("public qualification identity drifted")
    return result


def _profile(row: dict[str, Any]) -> TrackABudgetProfile:
    profile = TrackABudgetProfile(
        profile_id=row["profile_id"],
        primary_axis=row["primary_axis"],
        budget=TrackAWorkBudget(**row["budget"]),
        schema_version=row["schema_version"],
    )
    if canonical_bytes(profile.to_dict()) != canonical_bytes(row):
        raise DenseScaleExecutionError("budget typed reconstruction drifted")
    return profile


def reproduce_anchor_qualification() -> dict[str, Any]:
    expected = anchor_qualification()
    task = CountdownTask((1, 2, 3, 4, 5, 6), 720)
    proposal = TrackAProposalSpec("greedy_rollout_target_error/v1")
    profile = _profile(expected["budget_profile"])
    for receipt in expected["receipts"]:
        source = receipt["source"]
        binary = receipt["anchor_label"] == "binary_terminal_anchor"
        authority = (
            TrackAMethodSpec.dimension_normalized_thompson(source)
            if binary
            else TrackAMethodSpec.dimension_normalized_dense_thompson(source)
        )
        scaled = TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
            source, 0 if binary else 1
        )
        projections = []
        for label, method in (("authority", authority), ("scaled", scaled)):
            if canonical_bytes(method.to_dict()) != canonical_bytes(
                receipt[f"{label}_method_spec"]
            ):
                raise DenseScaleExecutionError(
                    "qualification method reconstruction drifted"
                )
            result = run_countdown_track_a_search(
                task,
                proposal=proposal,
                method=method,
                budget_profile=profile,
                exploration_seed=7168,
            )
            replayed = replay_countdown_track_a_search_bytes(
                result.canonical_bytes,
                task=task,
                proposal=proposal,
                method=method,
                budget_profile=profile,
                exploration_seed=7168,
                expected_run_identity_digest=result.run_identity_digest,
            )
            if (
                replayed != result.canonical_bytes
                or sha256_bytes(replayed) != receipt[f"expected_{label}_trace_sha256"]
            ):
                raise DenseScaleExecutionError(
                    "public qualification trace/replay mismatch"
                )
            projection = project_track_a_anchor_equivalence_trace(
                replayed, method=method
            )
            if sha256_json(projection) != receipt["expected_common_projection_digest"]:
                raise DenseScaleExecutionError(
                    "public qualification projection mismatch"
                )
            projections.append(canonical_bytes(projection))
        if projections[0] != projections[1]:
            raise DenseScaleExecutionError("public anchor projections differ")
    return expected


def runtime_qualification() -> dict[str, Any]:
    expected = public_contract()["runtime_binding"]
    search = search_runtime_metadata()
    iid = perturbation_runtime_metadata("iid")
    sobol = perturbation_runtime_metadata("sobol")
    if (
        sha256_json(search) != expected["search_runtime"]["digest"]
        or sha256_json(iid) != expected["iid_runtime"]["digest"]
    ):
        raise DenseScaleExecutionError("sealed search/IID runtime is not reproduced")
    return with_digest(
        {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "search_runtime": search,
            "iid_runtime": iid,
            "sobol_runtime": sobol,
            "host": {
                "architecture": platform.machine(),
                "node": platform.node(),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            },
            "provider_calls": 0,
        }
    )


def git_bytes(root: Path | str, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", os.fspath(root), *args], check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise DenseScaleExecutionError("Git authority check failed") from error


def require_git_oid(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 40
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise DenseScaleExecutionError("revision must be a full lowercase commit OID")
    return value


def git_head(root: Path | str) -> str:
    return require_git_oid(git_bytes(root, "rev-parse", "HEAD").decode("ascii").strip())


def require_ancestor(
    root: Path | str, ancestor: str, descendant: str, *, strict: bool = False
) -> None:
    for oid in (ancestor, descendant):
        require_git_oid(oid)
        if git_bytes(root, "cat-file", "-t", oid) != b"commit\n":
            raise DenseScaleExecutionError("revision must identify a commit, not a tag")
    if strict and ancestor == descendant:
        raise DenseScaleExecutionError("revision must strictly descend from authority")
    git_bytes(root, "merge-base", "--is-ancestor", ancestor, descendant)


def runtime_import_policy() -> tuple[dict[str, Any], Path]:
    prefix = sys.pycache_prefix
    if (
        not sys.flags.safe_path
        or not sys.dont_write_bytecode
        or type(prefix) is not str
    ):
        raise DenseScaleExecutionError(
            "source-only startup requires -P -B and a fresh cache prefix"
        )
    path = Path(prefix)
    try:
        metadata = path.lstat()
        if (
            not path.is_absolute()
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
            or tuple(path.iterdir())
        ):
            raise DenseScaleExecutionError(
                "cache namespace must be fresh, empty, owned, mode0700"
            )
    except OSError as error:
        raise DenseScaleExecutionError("cache namespace cannot be verified") from error
    return (
        {
            "bytecode_cache_prefix_empty": True,
            "bytecode_cache_prefix_mode": "0700",
            "bytecode_cache_prefix_owner": "effective_user",
            "bytecode_writes_disabled": True,
            "import_safe_path": True,
            "loader_policy": "exact_source_file_loader_no_cache/v1",
        },
        path.resolve(strict=True),
    )


def _regular_git_blob(root: Path, revision: str, relative: str) -> bytes:
    entry = git_bytes(root, "ls-tree", "-z", revision, "--", relative)
    if (
        not entry.startswith(b"100644 blob ")
        or entry.count(b"\x00") != 1
        or not entry.endswith(b"\t" + relative.encode("utf-8") + b"\x00")
    ):
        raise DenseScaleExecutionError(
            "protected source must be one non-executable Git blob"
        )
    return git_bytes(root, "show", f"{revision}:{relative}")


def verify_historical_source_receipts(
    root: Path | str, revision: str, receipts: object
) -> None:
    """Validate an untrusted historical revision against externally reviewed bytes.

    This does not qualify the analyzer's current imports; source_attestation is
    independently required for that. Callers also close authorization ancestry.
    """
    root = Path(root)
    require_git_oid(revision)
    if git_bytes(root, "cat-file", "-t", revision) != b"commit\n":
        raise DenseScaleExecutionError("historical execution revision is not a commit")
    if type(receipts) is not dict or set(receipts) != set(PROTECTED_SOURCE_PATHS):
        raise DenseScaleExecutionError("historical source receipt set is not closed")
    for relative in PROTECTED_SOURCE_PATHS:
        raw = _regular_git_blob(root, revision, relative)
        expected = {"byte_count": len(raw), "sha256": sha256_bytes(raw)}
        if canonical_bytes(receipts[relative]) != canonical_bytes(expected):
            raise DenseScaleExecutionError(
                "historical execution source receipt mismatch"
            )


def source_attestation(
    root: Path | str, authorized_revision: str | None = None
) -> dict[str, Any]:
    root = Path(root).absolute()
    if Path(git_bytes(root, "rev-parse", "--show-toplevel").decode().strip()) != root:
        raise DenseScaleExecutionError(
            "repository root must be the exact checkout root"
        )
    policy, cache = runtime_import_policy()
    if git_bytes(root, "status", "--porcelain", "--untracked-files=all"):
        raise DenseScaleExecutionError("source checkout must be clean")
    head = git_head(root)
    approved = authorized_revision or head
    require_ancestor(root, CONTRACT_MERGE_REVISION, approved)
    require_ancestor(root, approved, head)
    snapshots = {}
    receipts = {}
    for relative in PROTECTED_SOURCE_PATHS:
        snapshot = FileSnapshot.capture(root / relative)
        if snapshot.raw != _regular_git_blob(
            root, head, relative
        ) or snapshot.raw != _regular_git_blob(root, approved, relative):
            raise DenseScaleExecutionError(
                f"protected source differs from reviewed Git: {relative}"
            )
        snapshots[relative] = snapshot
        receipts[relative] = {
            "byte_count": len(snapshot.raw),
            "sha256": sha256_bytes(snapshot.raw),
        }
    for row in public_contract()["runtime_binding"]["source_files"]:
        if receipts[row["path"]] != {
            "byte_count": row["byte_count"],
            "sha256": row["sha256"],
        }:
            raise DenseScaleExecutionError("sealed search source bytes may not change")
    allowed = {}
    for path in _PACKAGE_PATHS:
        suffix = path.removesuffix(".py").replace("/", ".")
        module_name = (
            "qmc_bmgs"
            if suffix == "__init__"
            else "qmc_bmgs." + suffix.removesuffix(".__init__")
        )
        allowed[module_name] = (root / "src" / "qmc_bmgs" / path).resolve()
    loaded_modules = list(sys.modules.items())
    for name, module in loaded_modules:
        spec = getattr(module, "__spec__", None)
        spec_name = getattr(spec, "name", "")
        if not (
            name == "qmc_bmgs"
            or name.startswith("qmc_bmgs.")
            or (name == "__main__" and spec_name.startswith("qmc_bmgs."))
        ):
            continue
        origin = getattr(spec, "origin", None)
        file = getattr(module, "__file__", None)
        cached = getattr(module, "__cached__", None)
        expected_name = spec_name if name == "__main__" else name
        try:
            if (
                type(origin) is not str
                or type(file) is not str
                or type(cached) is not str
                or type(getattr(spec, "loader", None))
                is not importlib.machinery.SourceFileLoader
                or expected_name not in allowed
                or spec_name != expected_name
                or Path(origin).resolve(strict=True) != allowed[expected_name]
                or Path(origin).resolve() != Path(file).resolve()
                or not Path(cached).is_absolute()
                or not Path(cached).resolve().is_relative_to(cache)
                or os.path.lexists(cached)
            ):
                raise DenseScaleExecutionError(
                    f"protected import origin/cache drifted: {name}"
                )
        except OSError as error:
            raise DenseScaleExecutionError(
                "protected import cannot be attested"
            ) from error
    for snapshot in snapshots.values():
        snapshot.revalidate()
    if (
        git_head(root) != head
        or git_bytes(root, "status", "--porcelain", "--untracked-files=all")
        or runtime_import_policy()[0] != policy
    ):
        raise DenseScaleExecutionError("source checkout changed during attestation")
    return with_digest(
        {
            "schema_version": BUILD_SCHEMA_VERSION,
            "runner_revision": approved,
            "source_files": receipts,
            "runtime_import_policy": policy,
            "search_build_digest": sha256_json(
                {p: receipts[p] for p in SEARCH_SOURCE_PATHS}
            ),
        }
    )


@dataclass(frozen=True)
class DenseExecutionCell:
    _key_raw: bytes = field(repr=False)

    @property
    def key(self) -> dict[str, Any]:
        return parse_canonical(self._key_raw)

    @property
    def cell_id(self) -> str:
        return sha256_json(self.key)

    @property
    def task_fingerprint(self) -> str:
        return self.key["task_fingerprint"]

    @property
    def exploration_seed(self) -> int:
        return self.key["exploration_seed"]

    @property
    def terminal_value_scale(self) -> int:
        return self.key["terminal_value_scale"]

    @property
    def method_label(self) -> str:
        return self.key["method_label"]

    def to_dict(self) -> dict[str, Any]:
        return {"cell_id": self.cell_id, "cell_key": self.key}


@dataclass(frozen=True)
class FrozenDenseInputs:
    _raw: bytes = field(repr=False)
    fixture: bool
    _files: tuple[FileSnapshot, ...] = field(default=(), repr=False)
    _bundle_directory_generation: tuple[int, ...] | None = field(
        default=None, repr=False
    )

    @property
    def payload(self) -> dict[str, Any]:
        return parse_canonical(self._raw)

    @property
    def bundle_id(self) -> str:
        return self.payload["bundle_id"]

    @property
    def cells(self) -> tuple[DenseExecutionCell, ...]:
        return tuple(
            DenseExecutionCell(canonical_bytes(row["cell_key"]))
            for row in self.schedule
        )

    @property
    def schedule(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.payload["execution_matrix"]["schedule"])

    @property
    def schedule_digest(self) -> str:
        return self.payload["execution_matrix"]["schedule_digest"]

    @property
    def seal_digest(self) -> str | None:
        return None if self.fixture else self.payload["deterministic_digest"]

    @property
    def design_digest(self) -> str:
        return self.payload["deterministic_digest"]

    @property
    def tasks(self) -> dict[str, CountdownTask]:
        tasks = {}
        for row in self.payload["cohort"]["tasks"]:
            task = CountdownTask(tuple(row["inputs"]), row["target"])
            if canonical_bytes(task.to_dict()) != canonical_bytes(row):
                raise DenseScaleExecutionError("task typed reconstruction drifted")
            tasks[task.task_fingerprint] = task
        return tasks

    @property
    def task_sources(self) -> dict[str, str]:
        return {
            key: task.source_multiset_fingerprint for key, task in self.tasks.items()
        }

    @property
    def proposal(self) -> TrackAProposalSpec:
        row = self.payload["proposal"]["spec"]
        spec = TrackAProposalSpec(row["policy_id"])
        if canonical_bytes(spec.to_dict()) != canonical_bytes(row):
            raise DenseScaleExecutionError("proposal typed reconstruction drifted")
        return spec

    @property
    def budget(self) -> TrackABudgetProfile:
        return _profile(self.payload["budget"]["profile"]["spec"])

    @property
    def methods(self) -> dict[str, TrackAMethodSpec]:
        result = {}
        for row in self.payload["methods"]["methods"]:
            spec = TrackAMethodSpec.dimension_normalized_scaled_dense_thompson(
                "iid", row["terminal_value_scale"]
            )
            if canonical_bytes(spec.to_dict()) != canonical_bytes(row["spec"]):
                raise DenseScaleExecutionError(
                    "only the exact v5 IID scale family is executable"
                )
            result[row["label"]] = spec
        return result

    def revalidate(self) -> None:
        for snapshot in self._files:
            snapshot.revalidate()
        if self._bundle_directory_generation is not None:
            if (
                _closed_bundle_generation(self._files[0].path.parent)
                != self._bundle_directory_generation
            ):
                raise DenseScaleExecutionError(
                    "sealed bundle directory generation changed"
                )
        if self.fixture and self._raw != public_fixture_inputs()._raw:
            raise DenseScaleExecutionError("public fixture design drifted")


def public_fixture_inputs() -> FrozenDenseInputs:
    public = public_contract()
    tasks = [
        CountdownTask((1, 2, 3, 4, 5, 6), target).to_dict() for target in range(1, 13)
    ]
    cohort = with_digest({"schema_version": FIXTURE_STEM + "-tasks/v1", "tasks": tasks})
    methods = dict(public["methods"])
    methods.pop("deterministic_digest")
    methods["schema_version"] = FIXTURE_STEM + "-methods/v1"
    methods = with_digest(methods)
    schedule = []
    for task in tasks:
        for row in methods["methods"]:
            for seed in EXPLORATION_SEEDS:
                key = {
                    "budget_profile_id": "score256",
                    "budget_profile_spec_digest": public["budget"]["profile"][
                        "spec_digest"
                    ],
                    "bundle_id": FIXTURE_BUNDLE_ID,
                    "exploration_seed": seed,
                    "method_label": row["label"],
                    "method_manifest_digest": methods["deterministic_digest"],
                    "method_spec_digest": row["spec_digest"],
                    "proposal_label": "heuristic",
                    "proposal_spec_digest": public["proposal"]["spec_digest"],
                    "schema_version": FIXTURE_STEM + "-cell-key/v1",
                    "task_fingerprint": task["task_fingerprint"],
                    "task_manifest_digest": cohort["deterministic_digest"],
                    "terminal_value_scale": row["terminal_value_scale"],
                }
                schedule.append({"cell_id": sha256_json(key), "cell_key": key})
    payload = with_digest(
        {
            "schema_version": FIXTURE_STEM + "-design/v1",
            "bundle_id": FIXTURE_BUNDLE_ID,
            "execution_mode": FIXTURE_EXECUTION_MODE,
            "claim_boundary": FIXTURE_CLAIM_BOUNDARY,
            "cohort": cohort,
            "methods": methods,
            "proposal": public["proposal"],
            "budget": public["budget"],
            "analysis": public["analysis"],
            "runtime_binding": public["runtime_binding"],
            "execution_matrix": {
                "cell_count": EXPECTED_CELL_COUNT,
                "schedule": schedule,
                "schedule_digest": sha256_json(schedule),
                "scale_order": list(SCALE_ORDER),
                "exploration_seeds": list(EXPLORATION_SEEDS),
            },
        }
    )
    if (
        payload["deterministic_digest"] != FIXTURE_DESIGN_DIGEST
        or payload["execution_matrix"]["schedule_digest"] != FIXTURE_SCHEDULE_DIGEST
    ):
        raise DenseScaleExecutionError("fixed public fixture design/schedule drifted")
    return FrozenDenseInputs(canonical_bytes(payload), True)


def _closed_bundle_generation(path: Path) -> tuple[int, ...]:
    descriptor = -1
    try:
        descriptor, _ = storage._walk_absolute_directory_nofollow(path)
        before = _generation(os.fstat(descriptor))
        if set(os.listdir(descriptor)) != {manifest.BUNDLE_FILENAME}:
            raise DenseScaleExecutionError("sealed bundle directory is not closed")
        after = _generation(os.fstat(descriptor))
        if before != after:
            raise DenseScaleExecutionError(
                "sealed bundle directory changed during observation"
            )
        return after
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_production_inputs(path: Path | str, root: Path | str) -> FrozenDenseInputs:
    path = Path(path).absolute()
    directory_generation = _closed_bundle_generation(path)
    snapshot = FileSnapshot.capture(path / manifest.BUNDLE_FILENAME)
    if sha256_bytes(snapshot.raw) != FROZEN_AUTHORITY["preregistration_file_sha256"]:
        raise DenseScaleExecutionError("sealed preregistration bytes differ")
    verified = manifest.verify_countdown_thompson_dense_scale_bundle(
        path, repository_root=Path(root)
    )
    payload = verified.payload
    if canonical_bytes(payload) != snapshot.raw:
        raise DenseScaleExecutionError("verified bundle snapshot differs")
    observed = {
        "analysis_manifest_digest": payload["analysis"]["deterministic_digest"],
        "anchor_qualification_digest": payload["analysis"]["anchor_equivalence"][
            "qualification"
        ]["deterministic_digest"],
        "budget_manifest_digest": payload["budget"]["deterministic_digest"],
        "bundle_id": payload["bundle_id"],
        "cell_count": len(verified.cells),
        "dense_scale_seal_digest": verified.seal_digest,
        "method_manifest_digest": payload["methods"]["deterministic_digest"],
        "preregistration_file_sha256": sha256_bytes(snapshot.raw),
        "proposal_manifest_digest": payload["proposal"]["deterministic_digest"],
        "runtime_binding_digest": payload["runtime_binding"]["deterministic_digest"],
        "schedule_digest": payload["execution_matrix"]["schedule_digest"],
    }
    if canonical_bytes(observed) != canonical_bytes(FROZEN_AUTHORITY):
        raise DenseScaleExecutionError("frozen dense-scale authority drifted")
    if (
        payload["analysis"]["anchor_equivalence"]["qualification"]
        != anchor_qualification()
    ):
        raise DenseScaleExecutionError("public and sealed qualification disagree")
    snapshot.revalidate()
    if _closed_bundle_generation(path) != directory_generation:
        raise DenseScaleExecutionError(
            "sealed bundle directory changed during verification"
        )
    return FrozenDenseInputs(snapshot.raw, False, (snapshot,), directory_generation)


def _cell_arguments(
    inputs: FrozenDenseInputs, cell: DenseExecutionCell
) -> dict[str, Any]:
    if type(inputs) is not FrozenDenseInputs or type(cell) is not DenseExecutionCell:
        raise DenseScaleExecutionError("exact immutable input types are required")
    key = cell.key
    if cell.to_dict() not in inputs.schedule:
        raise DenseScaleExecutionError("cell is outside the exact frozen schedule")
    task, proposal, method, budget = (
        inputs.tasks[cell.task_fingerprint],
        inputs.proposal,
        inputs.methods[cell.method_label],
        inputs.budget,
    )
    expected = {
        "task_fingerprint": task.task_fingerprint,
        "proposal_spec_digest": sha256_json(proposal.to_dict()),
        "method_spec_digest": sha256_json(method.to_dict()),
        "budget_profile_spec_digest": sha256_json(budget.to_dict()),
        "method_manifest_digest": inputs.payload["methods"]["deterministic_digest"],
        "bundle_id": inputs.bundle_id,
    }
    if any(
        canonical_bytes(key.get(k)) != canonical_bytes(v) for k, v in expected.items()
    ):
        raise DenseScaleExecutionError("cell component identities do not close")
    return {
        "task": task,
        "proposal": proposal,
        "method": method,
        "budget_profile": budget,
        "exploration_seed": cell.exploration_seed,
    }


def _budget_evidence(
    trace: dict[str, Any], profile: TrackABudgetProfile
) -> dict[str, Any]:
    if trace["events"][-1]["kind"] != "search_finished":
        raise DenseScaleExecutionError("trace has no final search summary")
    summary = trace["events"][-1]["payload"]["summary"]
    ledger = trace["ledger_snapshot"]
    primary = profile.primary_axis
    remaining, usage = ledger["remaining"], ledger["usage"]
    limits = profile.to_dict()["budget"]
    if (
        summary["budget_valid"] is not True
        or set(remaining) != set(TRACK_A_WORK_AXES)
        or set(usage) != set(TRACK_A_WORK_AXES)
        or any(
            type(usage[a]) is not int
            or type(remaining[a]) is not int
            or usage[a] < 0
            or remaining[a] != limits[a] - usage[a]
            or remaining[a] < 0
            for a in TRACK_A_WORK_AXES
        )
        or any(remaining[a] <= 0 for a in TRACK_A_WORK_AXES if a != primary)
        or any(a != primary for a in summary["stop_blocked_axes"])
    ):
        raise DenseScaleExecutionError(
            "budget invalid or non-primary guard bound/exhausted"
        )
    return {
        "blocked_axes": summary["stop_blocked_axes"],
        "budget_valid": True,
        "non_primary_headroom": {
            a: remaining[a] for a in TRACK_A_WORK_AXES if a != primary
        },
        "primary_axis": primary,
        "primary_headroom": remaining[primary],
        "profile_spec": profile.to_dict(),
        "remaining": remaining,
        "stop_reason": summary["stop_reason"],
        "usage": usage,
    }


def _validate_binding(inputs: FrozenDenseInputs, binding: dict[str, Any]) -> None:
    require_digest(binding)
    payload = inputs.payload
    expected = {
        "bundle_id": inputs.bundle_id,
        "execution_mode": FIXTURE_EXECUTION_MODE if inputs.fixture else EXECUTION_MODE,
        "schedule_digest": inputs.schedule_digest,
        "dense_scale_seal_digest": inputs.seal_digest,
        "fixture_design_digest": inputs.design_digest if inputs.fixture else None,
        "preregistration_file_sha256": None
        if inputs.fixture
        else FROZEN_AUTHORITY["preregistration_file_sha256"],
        "analysis_manifest_digest": payload["analysis"]["deterministic_digest"],
        "anchor_qualification_digest": FROZEN_AUTHORITY["anchor_qualification_digest"],
        "method_manifest_digest": payload["methods"]["deterministic_digest"],
        "budget_manifest_digest": payload["budget"]["deterministic_digest"],
        "proposal_manifest_digest": payload["proposal"]["deterministic_digest"],
        "runtime_binding_digest": payload["runtime_binding"]["deterministic_digest"],
    }
    if any(
        canonical_bytes(binding.get(k)) != canonical_bytes(v)
        for k, v in expected.items()
    ):
        raise DenseScaleExecutionError(
            "run binding does not match the frozen input domain"
        )


def _record_payload(
    inputs: FrozenDenseInputs,
    cell: DenseExecutionCell,
    trace: dict[str, Any],
    binding: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    _validate_binding(inputs, binding)
    raw = canonical_bytes(trace)
    return with_digest(
        {
            "schema_version": FIXTURE_RECORD_SCHEMA_VERSION
            if inputs.fixture
            else RECORD_SCHEMA_VERSION,
            "cell_id": cell.cell_id,
            "cell_key": cell.key,
            "source_multiset_fingerprint": arguments[
                "task"
            ].source_multiset_fingerprint,
            "run_binding_digest": binding["deterministic_digest"],
            "search_record": trace,
            "search_run_identity_digest": sha256_json(
                build_search_run_identity(**arguments)
            ),
            "search_trace_byte_count": len(raw),
            "search_trace_sha256": sha256_bytes(raw),
            "budget_evidence": _budget_evidence(trace, arguments["budget_profile"]),
            "provider_calls": 0,
            "replay": {
                "stage1_generative": "PASS",
                "stage2_byte_identical": "PASS",
                "replayed_sha256": sha256_bytes(raw),
            },
        }
    )


def build_record(
    inputs: FrozenDenseInputs, cell: DenseExecutionCell, binding: dict[str, Any]
) -> dict[str, Any]:
    """Execute once; callers must already own their domain's durable STARTED."""
    _validate_binding(inputs, binding)
    arguments = _cell_arguments(inputs, cell)
    result = run_countdown_track_a_search(**arguments)
    replayed = replay_countdown_track_a_search_bytes(
        result.canonical_bytes,
        **arguments,
        expected_run_identity_digest=result.run_identity_digest,
    )
    if replayed != result.canonical_bytes:
        raise DenseScaleExecutionError("fresh cell replay differs")
    return _record_payload(inputs, cell, parse_canonical(replayed), binding, arguments)


def verify_record(
    inputs: FrozenDenseInputs,
    cell: DenseExecutionCell,
    row: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    _validate_binding(inputs, binding)
    require_digest(row, RECORD_FIELDS)
    arguments = _cell_arguments(inputs, cell)
    expected_id = sha256_json(build_search_run_identity(**arguments))
    raw = canonical_bytes(row["search_record"])
    if (
        row["schema_version"]
        != (FIXTURE_RECORD_SCHEMA_VERSION if inputs.fixture else RECORD_SCHEMA_VERSION)
        or canonical_bytes({"cell_id": row["cell_id"], "cell_key": row["cell_key"]})
        != canonical_bytes(cell.to_dict())
        or row["search_run_identity_digest"] != expected_id
        or type(row["provider_calls"]) is not int
        or row["provider_calls"] != 0
    ):
        raise DenseScaleExecutionError(
            "run record domain/cell/provider identity drifted"
        )
    replayed = replay_countdown_track_a_search_bytes(
        raw, **arguments, expected_run_identity_digest=expected_id
    )
    expected = _record_payload(
        inputs, cell, parse_canonical(replayed), binding, arguments
    )
    if canonical_bytes(row) != canonical_bytes(expected):
        raise DenseScaleExecutionError(
            "run record does not exact-match independent replay and accounting"
        )
    return parse_canonical(replayed)
