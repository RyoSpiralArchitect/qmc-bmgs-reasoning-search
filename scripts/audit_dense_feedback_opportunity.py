#!/usr/bin/env python3
"""Hash-bound, standard-library-only post-hoc audit; never executes search."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any


OBSERVATION_REVISION = "1ffe31668e4642e95ec0fbadd1b4f52a287e1dad"
SCRIPT = "scripts/audit_dense_feedback_opportunity.py"
DESIGN = "docs/strategy/countdown_thompson_dense_feedback_opportunity_audit.md"
DESIGN_SHA = "7265de03d226ec7b3461a3ce4e1ae2f0d247cc296aab3ae529514d7f87f97435"
RESULTS = "docs/results/countdown_thompson_dense_scale_v5"
SUMMARY_SHA = "76e181de21f7efbd4eb826f5dff181d7e13a1daf5c0da2e926b76f305b2fc651"
EVIDENCE_SHA = "2184bc16dce93138c6c16b32c3a93680acf8d4f574fb4a243f263204ada1f28b"
AUTH = "docs/preregistrations/countdown_thompson_dense_scale_v5_execution_authorization.json"
AUTH_SHA = "c043085cccaec720a782d9297599e35b72a8cb9ca015fa98d800923c4eec92dd"
PREFIX = (
    ".qmc-bmgs-v2r3-5b2a9bde73406fbe19b2f415221f240aeba8ff2ed67d9eac25c39abdefb27495"
)
RAW = {
    "attempt": (
        PREFIX + ".attempt.json",
        2174,
        "b45c7b513b6191564cc955925a0a2ab9d001264773067da8199ec3dc605d16bc",
    ),
    "started": (
        PREFIX + ".started.json",
        999,
        "b3f7225677abd76c0dd239b06e79ec39409c780ade9a47b0261229fc3847f959",
    ),
    "records_jsonl": (
        PREFIX + ".records.jsonl",
        42248633,
        "50d671822a94d0c43c75087ea3edbcb7264977e32e95efd78ddb0fdbc482478e",
    ),
    "collective_manifest": (
        PREFIX + ".manifest.json",
        76847,
        "1653a8568fe669c5b5464e7b9bc5b8666be6da6b4428cd9fc4b221de0c48354c",
    ),
    "ready_to_commit": (
        PREFIX + ".ready-to-commit.json",
        1291,
        "a65906f6e939b8ef42cf8504e3df4115303fd73d64e020b427b7f6f561197414",
    ),
    "commit": (
        "dense-scale-v5.commit.json",
        1984,
        "70d6ab1266d45ec666bf0b1ccb1785b019ffaebc938848ea863a7501b515a6a7",
    ),
}
SCALES = (0, 1, 2, 4, 8, 16, 32, 64)
SEEDS = (7168, 7169, 7170, 7171)
AXES = (
    "proposal_state_evaluations",
    "proposal_action_scores",
    "legal_action_scores",
    "generated_perturbation_coordinates",
    "edge_selections",
    "transitions",
    "verifier_calls",
)
STOP = "STOP_REPAIR_NO_LOCKED_128_RUN"


class AuditError(ValueError):
    pass


class PublicationUncertain(AuditError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise AuditError(message)


def canonical(value: Any, *, newline: bool = False) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8") + (b"\n" if newline else b"")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value: Any) -> str:
    return sha(canonical(value))


def with_digest(value: dict) -> dict:
    return {**value, "deterministic_digest": digest(value)}


def verify_digest(value: dict, field: str = "deterministic_digest") -> None:
    require(
        value[field] == digest({k: v for k, v in value.items() if k != field}),
        "digest mismatch",
    )


def parse_json(raw: bytes) -> Any:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise AuditError("non-finite JSON: " + value)

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    # Re-serialization also rejects overflowing numeric literals such as 1e999.
    canonical(result)
    return result


def strict_json(raw: bytes) -> Any:
    result = parse_json(raw)
    require(canonical(result, newline=True) == raw, "noncanonical JSON bytes")
    return result


def integer(value: Any) -> int:
    require(type(value) is int and value >= 0, "expected nonnegative plain integer")
    return value


def vector(value: dict) -> dict:
    require(
        type(value) is dict and set(value) == set(AXES), "work-axis closure mismatch"
    )
    return {a: integer(value[a]) for a in AXES}


def rational(value: Fraction) -> dict:
    return {"numerator": value.numerator, "denominator": value.denominator}


def finite(value: Any) -> Fraction:
    require(
        type(value) is float and math.isfinite(value), "expected finite binary64 score"
    )
    return Fraction.from_float(value)


def identity(s: os.stat_result) -> tuple:
    return (
        s.st_dev,
        s.st_ino,
        s.st_mode,
        s.st_nlink,
        s.st_size,
        s.st_mtime_ns,
        s.st_ctime_ns,
    )


def open_directory(path: Path) -> tuple[int, tuple]:
    require(
        path.is_absolute() and os.path.normpath(str(path)) == str(path),
        "noncanonical absolute directory",
    )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    chain = []
    try:
        s = os.fstat(fd)
        chain.append((s.st_dev, s.st_ino))
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            s = os.fstat(fd)
            chain.append((s.st_dev, s.st_ino))
        return fd, tuple(chain)
    except BaseException:
        os.close(fd)
        raise


@dataclass(frozen=True)
class Snapshot:
    path: Path
    raw: bytes
    generation: tuple
    parent_chain: tuple

    def revalidate(self) -> None:
        other = snapshot(
            self.path, expected_sha=sha(self.raw), expected_size=len(self.raw)
        )
        require(
            other.generation == self.generation
            and other.parent_chain == self.parent_chain,
            "input identity/generation changed",
        )


def snapshot(
    path: Path, *, expected_sha: str | None = None, expected_size: int | None = None
) -> Snapshot:
    parent, chain = open_directory(path.parent)
    fd = -1
    try:
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        before = os.fstat(fd)
        require(
            stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            "input must be a singly linked regular file",
        )
        require(0 < before.st_size <= (48 << 20), "input size bound")
        require(
            expected_size is None or before.st_size == expected_size,
            "input byte count differs",
        )
        chunks = []
        remaining = before.st_size
        while remaining:
            part = os.read(fd, min(1 << 20, remaining))
            require(bool(part), "short input read")
            chunks.append(part)
            remaining -= len(part)
        require(os.read(fd, 1) == b"", "input grew while reading")
        raw = b"".join(chunks)
        require(
            expected_sha is None or sha(raw) == expected_sha,
            "frozen input SHA-256 mismatch",
        )
        require(
            identity(before)
            == identity(os.fstat(fd))
            == identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
            "input changed during descriptor read",
        )
        check, current_chain = open_directory(path.parent)
        os.close(check)
        require(current_chain == chain, "input parent identity changed")
        return Snapshot(path, raw, identity(before), chain)
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(parent)


def scan_trace(trace: dict) -> dict:
    """Reclose stored hashes and charges; not a search replay."""
    verify_digest(trace)
    limits = vector(trace["ledger_snapshot"]["limits"])
    usage = dict.fromkeys(AXES, 0)
    previous, charge_index = "0" * 64, 0
    selections, terminals, backups = {}, [], {}
    for i, event in enumerate(trace["events"]):
        require(
            integer(event["index"]) == i and event["previous_event_digest"] == previous,
            "event chain order",
        )
        verify_digest(event, "event_digest")
        previous = event["event_digest"]
        before = dict(usage)
        charge = event["charge"]
        if charge is not None:
            require(integer(charge["charge_index"]) == charge_index, "charge order")
            delta, after = vector(charge["delta"]), vector(charge["usage_after"])
            require(any(delta.values()), "empty accepted charge")
            require(
                after == {a: usage[a] + delta[a] for a in AXES},
                "charge arithmetic mismatch",
            )
            require(
                all(after[a] <= limits[a] for a in AXES), "accepted work exceeds budget"
            )
            usage, charge_index = after, charge_index + 1
        item = {
            "event_index": i,
            "payload": event["payload"],
            "remaining_before_step_charge": {a: limits[a] - before[a] for a in AXES},
            "remaining_after_step_charge": {a: limits[a] - usage[a] for a in AXES},
        }
        p = event["payload"]
        if event["kind"] == "selection_committed":
            require(charge is not None, "selection must own its accepted step charge")
            coord = (integer(p["trajectory_index"]), integer(p["depth"]))
            require(coord not in selections, "duplicate selection coordinate")
            selections[coord] = item
        elif event["kind"] == "terminal_verified":
            require(
                charge is not None
                and charge["delta"] == {a: int(a == "verifier_calls") for a in AXES},
                "terminal must own verifier-only charge",
            )
            verification = p["verification"]
            require(
                type(verification["final_value"]) is int
                and type(verification["target"]) is int,
                "terminal arithmetic type",
            )
            error = abs(verification["final_value"] - verification["target"])
            require(
                integer(p["observation_index"]) == len(terminals),
                "terminal observation order",
            )
            require(
                type(verification["success"]) is bool
                and verification["success"] == (error == 0),
                "terminal success/error mismatch",
            )
            terminals.append(
                {
                    "event_index": i,
                    "trajectory_index": integer(p["trajectory_index"]),
                    "error": error,
                }
            )
        elif event["kind"] == "trajectory_backed_up":
            trajectory = integer(p["trajectory_index"])
            require(
                charge is None
                and trajectory not in backups
                and terminals
                and terminals[-1]["trajectory_index"] == trajectory
                and terminals[-1]["event_index"] == i - 1,
                "backup/terminal alignment",
            )
            finite(p["terminal_value"])
            backups[trajectory] = item
    require(
        integer(trace["event_count"]) == len(trace["events"])
        and trace["final_event_digest"] == previous,
        "trace final chain",
    )
    require(
        integer(trace["ledger_snapshot"]["charge_count"]) == charge_index,
        "final charge count",
    )
    require(usage == vector(trace["ledger_snapshot"]["usage"]), "final ledger usage")
    remaining = {a: limits[a] - usage[a] for a in AXES}
    require(
        remaining == vector(trace["ledger_snapshot"]["remaining"]),
        "final ledger remaining",
    )
    exhausted = [a for a in AXES if remaining[a] == 0]
    require(
        trace["ledger_snapshot"]["exhausted_axes"] == exhausted, "exhausted axes differ"
    )
    require(
        terminals
        and len(terminals) == len(backups)
        and len({t["trajectory_index"] for t in terminals}) == len(terminals),
        "terminal/backup closure",
    )
    require(trace["events"][-1]["kind"] == "search_finished", "missing search end")
    stop = trace["events"][-1]["payload"]["summary"]
    require(
        vector(stop["ledger_usage"]) == usage
        and integer(stop["terminal_count"]) == len(terminals),
        "search summary closure",
    )
    attempted = vector(stop["stop_attempted_charge"])
    blocked = [a for a in AXES if attempted[a] > remaining[a]]
    require(
        stop["stop_reason"] == "primary_budget_blocked"
        and stop["stop_blocked_axes"] == blocked
        and blocked == ["legal_action_scores"],
        "unexpected/unclosed binding stop",
    )
    return {
        "selections": selections,
        "terminals": terminals,
        "backups": backups,
        "limits": limits,
        "stop": {
            "stop_reason": stop["stop_reason"],
            "blocked_axes": blocked,
            "exhausted_axes": exhausted,
            "global_incomplete_trajectory_count": integer(
                stop["incomplete_trajectory_count"]
            ),
            "uncharged_attempted_step": attempted,
            "final_remaining": remaining,
            "accepted_usage": usage,
            "completed_terminal_count": len(terminals),
        },
    }


def opportunity(view: dict, index: int) -> dict:
    after = [t for t in view["terminals"] if t["event_index"] > index]
    return {
        "completed_terminal_count": len(after),
        "bin": "2+" if len(after) >= 2 else str(len(after)),
        "terminal_trajectory_ids": [t["trajectory_index"] for t in after],
    }


def suffix_outcome(prefix: list[int], suffix: list[int]) -> dict:
    first, later = min(prefix) if prefix else None, min(suffix) if suffix else None
    category = (
        "no_completed_terminal"
        if later is None
        else "no_prefix_terminal"
        if first is None
        else "exact_hit"
        if later == 0
        else "improved_nonexact"
        if later < first
        else "tied"
        if later == first
        else "worse"
    )
    return {
        "common_prefix_minimum_error": first,
        "observed_suffix_minimum_error": later,
        "category": category,
        "cumulative_best_gain": None
        if first is None or later is None
        else first - min(first, later),
    }


def pair_row(pair: dict, baseline: dict, scaled: dict) -> dict:
    base_errors = [t["error"] for t in baseline["terminals"]]
    scaled_errors = [t["error"] for t in scaled["terminals"]]
    base_min, scaled_min = min(base_errors), min(scaled_errors)
    result = {
        k: pair[k]
        for k in (
            "task_fingerprint",
            "exploration_seed",
            "positive_scale",
            "baseline_cell_id",
            "scaled_cell_id",
        )
    }
    result.update(
        {
            "first_divergence": pair["first_action_divergence"],
            "feedback_informed": pair["feedback_informed"],
            "mechanism_stop_reason": pair["stop_reason"],
            "final_minimum_error_baseline": base_min,
            "final_minimum_error_scaled": scaled_min,
            "final_minimum_error_comparison": "win"
            if scaled_min < base_min
            else "loss"
            if scaled_min > base_min
            else "tie",
            "new_exact_success": base_min > 0 and scaled_min == 0,
            "lost_exact_success": base_min == 0 and scaled_min > 0,
            "baseline_stop": baseline["stop"],
            "scaled_stop": scaled["stop"],
            "first_scale_dependent_backup": None,
            "divergence_window": None,
        }
    )
    support = pair["shared_prefix_backup_values"]
    result["shared_prefix_backup_values"] = support
    for row in support:
        trajectory = row["trajectory_index"]
        for view, label in ((baseline, "baseline"), (scaled, "scaled")):
            require(
                canonical(view["backups"][trajectory]["payload"]["terminal_value"])
                == canonical(row[label + "_applied_value"]),
                "shared backup value differs from frozen mechanism",
            )
    different = [
        row
        for row in support
        if finite(row["baseline_applied_value"]) != finite(row["scaled_applied_value"])
    ]
    if different:
        first = different[0]
        t = first["trajectory_index"]
        result["first_scale_dependent_backup"] = {
            **first,
            "baseline_opportunity": opportunity(
                baseline, baseline["backups"][t]["event_index"]
            ),
            "scaled_opportunity": opportunity(
                scaled, scaled["backups"][t]["event_index"]
            ),
        }
    div = pair["first_action_divergence"]
    if div is None:
        result["opportunity_bin"] = "no_divergence"
        return result
    require(
        pair["feedback_informed"] is bool(different),
        "feedback flag differs from stored support",
    )
    coord = (div["trajectory_index"], div["depth"])
    selected = [baseline["selections"][coord], scaled["selections"][coord]]
    prefixes, windows = [], []
    for view, selected_event, label in zip(
        (baseline, scaled), selected, ("baseline", "scaled")
    ):
        p, i = selected_event["payload"], selected_event["event_index"]
        require(
            p["action_index"] == div[label + "_action_index"]
            and canonical(p["action"]) == canonical(div[label + "_action"])
            and canonical(p["state"]) == canonical(div["state"])
            and canonical(p["selection_values"]) == canonical(div[label + "_scores"]),
            "divergence/raw coordinate mismatch",
        )
        scores = [finite(x) for x in p["selection_values"]]
        require(
            max(range(len(scores)), key=lambda k: (scores[k], -k)) == p["action_index"],
            "selected score is not stable argmax",
        )
        prefix = [t for t in view["terminals"] if t["event_index"] < i]
        suffix = [t for t in view["terminals"] if t["event_index"] > i]
        prefixes.append([(t["trajectory_index"], t["error"]) for t in prefix])
        require(
            all(
                view["backups"][r["trajectory_index"]]["event_index"] < i
                for r in support
            ),
            "backup is not prior to divergence",
        )
        windows.append(
            {
                "remaining_before_step_charge": selected_event[
                    "remaining_before_step_charge"
                ],
                "remaining_after_step_charge": selected_event[
                    "remaining_after_step_charge"
                ],
                "opportunity": opportunity(view, i),
                "diverged_trajectory_completed": any(
                    t["trajectory_index"] == coord[0] for t in suffix
                ),
                "observed_conversion": suffix_outcome(
                    [t["error"] for t in prefix], [t["error"] for t in suffix]
                ),
            }
        )
    require(prefixes[0] == prefixes[1], "common prefix terminal outcomes differ")
    a, b = div["baseline_action_index"], div["scaled_action_index"]
    require(a != b, "not an action divergence")
    bs, ss = (
        [finite(x) for x in div["baseline_scores"]],
        [finite(x) for x in div["scaled_scores"]],
    )
    result["divergence_window"] = {
        "baseline": windows[0],
        "scaled": windows[1],
        "baseline_selected_over_scaled_action_margin": rational(bs[a] - bs[b]),
        "scaled_selected_over_baseline_action_margin": rational(ss[b] - ss[a]),
        "scaled_winner_score_displacement": rational(ss[b] - bs[b]),
    }
    result["opportunity_bin"] = windows[1]["opportunity"]["bin"]
    return result


def reduce_pairs(rows: list[dict]) -> list[dict]:
    result = []
    for scale in SCALES[1:]:
        group = [row for row in rows if row["positive_scale"] == scale]
        require(len(group) == 48, "all 48 pairs must be retained at every scale")
        crossed = []
        for bucket in ("no_divergence", "0", "1", "2+"):
            selected = [row for row in group if row["opportunity_bin"] == bucket]
            comparisons = Counter(
                row["final_minimum_error_comparison"] for row in selected
            )
            crossed.append(
                {
                    "opportunity_bin": bucket,
                    "pair_count": len(selected),
                    **{name: comparisons[name] for name in ("win", "tie", "loss")},
                }
            )
        divergent = [row for row in group if row["divergence_window"] is not None]
        conversions = Counter(
            row["divergence_window"]["scaled"]["observed_conversion"]["category"]
            for row in divergent
        )
        new = [row for row in group if row["new_exact_success"]]
        result.append(
            {
                "scale": scale,
                "pair_count": 48,
                "divergent_pair_count": len(divergent),
                "divergent_unique_task_count": len(
                    {r["task_fingerprint"] for r in divergent}
                ),
                "incomplete_diverged_trajectory_count": sum(
                    not r["divergence_window"]["scaled"][
                        "diverged_trajectory_completed"
                    ]
                    for r in divergent
                ),
                "scaled_suffix_conversion_counts": {
                    name: conversions[name]
                    for name in (
                        "no_completed_terminal",
                        "no_prefix_terminal",
                        "exact_hit",
                        "improved_nonexact",
                        "tied",
                        "worse",
                    )
                },
                "opportunity_by_final_error_comparison": crossed,
                "new_exact_success_count": len(new),
                "lost_exact_success_count": sum(r["lost_exact_success"] for r in group),
                "new_exact_unique_task_count": len(
                    {r["task_fingerprint"] for r in new}
                ),
            }
        )
    return result


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    )


def cache_identity() -> tuple:
    require(sys.flags.safe_path and sys.dont_write_bytecode, "audit requires -P -B")
    cache = Path(sys.pycache_prefix or "")
    require(cache.is_absolute(), "fresh cache prefix required")
    s = cache.lstat()
    require(
        stat.S_ISDIR(s.st_mode)
        and stat.S_IMODE(s.st_mode) == 0o700
        and s.st_uid == os.geteuid()
        and not list(cache.iterdir()),
        "cache must be empty, owned and mode0700",
    )
    fd, chain = open_directory(cache)
    try:
        require(
            identity(s) == identity(os.fstat(fd)), "cache changed during inspection"
        )
        return identity(s), chain
    finally:
        os.close(fd)


def source_snapshots(root: Path) -> tuple[str, list[Snapshot]]:
    cache_identity()
    require(
        not git(root, "status", "--porcelain", "--untracked-files=all"),
        "audit checkout must be clean",
    )
    require(
        git(root, "rev-parse", "--show-toplevel").decode().strip() == str(root),
        "exact repository root required",
    )
    head = git(root, "rev-parse", "HEAD").decode().strip()
    git(root, "merge-base", "--is-ancestor", OBSERVATION_REVISION, head)
    require(
        Path(__file__).resolve() == root / SCRIPT,
        "audit entrypoint differs from source checkout",
    )
    sources = []
    for relative in (SCRIPT, DESIGN):
        require(
            git(root, "ls-tree", "HEAD", "--", relative).startswith(b"100644 blob "),
            "audit source must be regular tracked blob",
        )
        item = snapshot(root / relative)
        require(
            item.raw == git(root, "show", "HEAD:" + relative),
            "audit source differs from Git",
        )
        sources.append(item)
    require(sha(sources[1].raw) == DESIGN_SHA, "fixed audit definitions changed")
    return head, sources


def build_audit(root: Path, raw_parent: Path) -> tuple[dict, Any]:
    head, snapshots = source_snapshots(root)
    cache = cache_identity()

    def read(
        path: Path, expected_sha: str, size: int | None = None, *, compact: bool = True
    ) -> Any:
        item = snapshot(path, expected_sha=expected_sha, expected_size=size)
        snapshots.append(item)
        return strict_json(item.raw) if compact else parse_json(item.raw)

    summary = read(root / RESULTS / "summary.json", SUMMARY_SHA, 438777)
    # The original inventory is pretty JSON; its exact bytes remain pinned.
    evidence = read(root / RESULTS / "evidence.json", EVIDENCE_SHA, compact=False)
    auth = read(root / AUTH, AUTH_SHA, 20421)
    require(
        summary["decision"] == STOP and summary["integrity"] == "PASS",
        "original result boundary changed",
    )
    require(
        summary["authorization_digest"] == auth["deterministic_digest"],
        "summary authorization differs",
    )
    verify_digest(summary)
    verify_digest(summary["mechanism"])
    raw = None
    for role, (name, size, expected) in RAW.items():
        row = next(r for r in evidence["raw_files"] if r["role"] == role)
        require(
            row["sha256"] == expected and row["byte_count"] == size,
            "raw inventory drift",
        )
        item = snapshot(raw_parent / name, expected_sha=expected, expected_size=size)
        snapshots.append(item)
        if role == "records_jsonl":
            raw = item.raw
        else:
            strict_json(item.raw)
    assert raw is not None
    frames = [strict_json(line + b"\n") for line in raw.splitlines()]
    require(len(frames) == 384, "expected exactly 384 raw frames")
    order = summary["task_seed_order"]
    require(
        len(order) == 48 and summary["scale_order"] == list(SCALES),
        "summary matrix closure",
    )
    tasks = [row["task_fingerprint"] for row in order[::4]]
    require(
        len(set(tasks)) == 12
        and order
        == [
            {"task_fingerprint": task, "exploration_seed": seed}
            for task in tasks
            for seed in SEEDS
        ],
        "task/seed order drift",
    )
    keys = [(task, scale, seed) for task in tasks for scale in SCALES for seed in SEEDS]
    views, cell_ids = {}, {}
    for index, (frame, key) in enumerate(zip(frames, keys)):
        require(
            integer(frame["record_index"]) == index
            and frame["artifact_kind"] == "countdown_thompson_dense_scale_run_v2r3"
            and frame["schema_version"]
            == "qmc-bmgs-countdown-thompson-dense-scale-record-frame/v2r3",
            "raw frame order/domain",
        )
        record = frame["payload"]
        require(
            record["schema_version"]
            == "qmc-bmgs-countdown-thompson-dense-scale-run-record/v1",
            "record domain",
        )
        verify_digest(record)
        ck = record["cell_key"]
        require(
            (ck["task_fingerprint"], ck["terminal_value_scale"], ck["exploration_seed"])
            == key
            and record["cell_id"] == digest(ck)
            and type(record["provider_calls"]) is int
            and record["provider_calls"] == 0,
            "record identity/provider mismatch",
        )
        trace = record["search_record"]
        trace_raw = canonical(trace, newline=True)
        require(
            sha(trace_raw) == record["search_trace_sha256"]
            and len(trace_raw) == record["search_trace_byte_count"],
            "record trace byte mismatch",
        )
        view = scan_trace(trace)
        require(
            record["budget_evidence"]["usage"] == view["stop"]["accepted_usage"],
            "record work differs",
        )
        position = order.index({"task_fingerprint": key[0], "exploration_seed": key[2]})
        original = summary["per_scale"][SCALES.index(key[1])]
        errors = [t["error"] for t in view["terminals"]]
        values = [
            view["backups"][t["trajectory_index"]]["payload"]["terminal_value"]
            for t in view["terminals"]
        ]
        require(
            errors == original["terminal_absolute_error_vectors"][position]
            and canonical(values)
            == canonical(original["terminal_value_vectors"][position])
            and min(errors)
            == original["minimum_terminal_absolute_error_vector"][position]
            and (min(errors) == 0) == original["success_vector"][position],
            "raw outcomes differ from replay-closed summary",
        )
        views[key], cell_ids[key] = view, record["cell_id"]
    pairs = summary["mechanism"]["ordered_pair_rows"]
    require(len(pairs) == 336, "expected exactly 336 mechanism pairs")
    rows = []
    for pair, key in zip(
        pairs,
        [
            (task, scale, seed)
            for scale in SCALES[1:]
            for task in tasks
            for seed in SEEDS
        ],
    ):
        task, scale, seed = key
        require(
            (pair["task_fingerprint"], pair["positive_scale"], pair["exploration_seed"])
            == key
            and pair["baseline_cell_id"] == cell_ids[task, 0, seed]
            and pair["scaled_cell_id"] == cell_ids[key],
            "frozen pair identity differs",
        )
        rows.append(pair_row(pair, views[task, 0, seed], views[key]))
    new = [r for r in rows if r["new_exact_success"]]
    receipt = with_digest(
        {
            "schema_version": "qmc-bmgs-dense-feedback-opportunity-audit/v1",
            "audit_status": "PASS",
            "original_handoff": STOP,
            "audit_checks": [
                "pinned_input_bytes",
                "canonical_frames_and_traces",
                "event_hash_chains",
                "seven_axis_charge_arithmetic",
                "frozen_summary_crosscheck",
                "posthoc_reductions",
            ],
            "historical_replay": "PR24 summary reports all-cell two-stage replay PASS; this audit does not rerun it",
            "search_executions_this_audit": 0,
            "generative_replays_this_audit": 0,
            "provider_calls": 0,
            "source_revision": head,
            "source_files": {
                str(s.path.relative_to(root)): {
                    "sha256": sha(s.raw),
                    "byte_count": len(s.raw),
                }
                for s in snapshots[:2]
            },
            "input_files": [
                {"path": str(s.path), "sha256": sha(s.raw), "byte_count": len(s.raw)}
                for s in snapshots[2:]
            ],
            "cell_count": 384,
            "pair_count": 336,
            "scale_order": list(SCALES),
            "per_scale": reduce_pairs(rows),
            "ordered_pair_rows": rows,
            "new_exact_scale_pair_entries": len(new),
            "new_exact_distinct_task_seed_pairs": len(
                {(r["task_fingerprint"], r["exploration_seed"]) for r in new}
            ),
            "new_exact_distinct_tasks": len({r["task_fingerprint"] for r in new}),
            "claim_boundary": "Post-hoc descriptive opportunity/conversion only; no budget counterfactual, causal mediator estimate, confirmation, retry, superiority, QMC or locked-128 authority.",
        }
    )

    def revalidate() -> None:
        require(cache_identity() == cache, "cache epoch changed")
        require(
            git(root, "rev-parse", "HEAD").decode().strip() == head
            and not git(root, "status", "--porcelain", "--untracked-files=all"),
            "source epoch changed",
        )
        for item in snapshots:
            item.revalidate()

    revalidate()
    return receipt, revalidate


def output_location(path: Path, protected_roots: tuple[Path, ...]) -> None:
    # Inode ancestry also rejects case aliases on a case-insensitive filesystem.
    parent, chain = open_directory(path.parent)
    os.close(parent)
    for root in protected_roots:
        fd, protected_chain = open_directory(root)
        os.close(fd)
        require(
            protected_chain[-1] not in chain, "output must be outside source/raw/cache"
        )


def publish(path: Path, raw: bytes, revalidate: Any) -> None:
    parent, chain = open_directory(path.parent)
    fd = -1
    created = False
    try:
        revalidate()
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
        created = True
        for offset in range(0, len(raw), 1 << 20):
            chunk = raw[offset : offset + (1 << 20)]
            while chunk:
                count = os.write(fd, chunk)
                require(count > 0, "short audit write")
                chunk = chunk[count:]
        os.fsync(fd)
        os.fsync(parent)
        before = identity(os.fstat(fd))
        require(
            stat.S_ISREG(before[2]) and before[3] == 1 and before[4] == len(raw),
            "audit output identity",
        )
        revalidate()
        require(
            before
            == identity(os.fstat(fd))
            == identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
            "audit output changed",
        )
        check, current_chain = open_directory(path.parent)
        os.close(check)
        require(current_chain == chain, "audit output parent changed")
        output = snapshot(path, expected_sha=sha(raw), expected_size=len(raw))
        require(
            output.generation == before and output.parent_chain == chain,
            "audit output readback differs",
        )
        closing, fd = fd, -1
        os.close(closing)
        closing, parent = parent, -1
        os.close(closing)
    except BaseException as error:
        if created:
            raise PublicationUncertain(
                "audit publication uncertain; retain occupied slot"
            ) from error
        raise
    finally:
        closing_errors = []
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as error:
                closing_errors.append(error)
        if parent >= 0:
            try:
                os.close(parent)
            except OSError as error:
                closing_errors.append(error)
        if closing_errors:
            raise PublicationUncertain(
                "descriptor close uncertain; retain occupied slot"
            ) from closing_errors[0]


def self_test() -> dict:
    require(
        suffix_outcome([9], [])["category"] == "no_completed_terminal",
        "empty suffix self-test",
    )
    require(
        suffix_outcome([9], [10])["cumulative_best_gain"] == 0,
        "worse suffix is not cumulative degradation",
    )
    require(
        rational(finite(0.5) - finite(0.25)) == {"numerator": 1, "denominator": 4},
        "exact binary64 subtraction",
    )
    return {
        "status": "PASS",
        "search_executions": 0,
        "scope": "pure synthetic helper checks",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--raw-parent", type=Path)
    parser.add_argument("--output", type=Path)
    try:
        args = parser.parse_args(argv)
        if args.self_test:
            require(
                all(
                    v is None
                    for v in (args.repository_root, args.raw_parent, args.output)
                ),
                "self-test accepts no operational arguments",
            )
            result = self_test()
        else:
            require(
                all(
                    v is not None
                    for v in (args.repository_root, args.raw_parent, args.output)
                ),
                "explicit root/raw-parent/output required",
            )
            root = args.repository_root.resolve(strict=True)
            raw_parent, output = args.raw_parent, args.output
            require(
                raw_parent.is_absolute() and output.is_absolute(),
                "absolute artifact paths required",
            )
            protected = (root, raw_parent, Path(sys.pycache_prefix or ""))
            output_location(output, protected)
            receipt, revalidate = build_audit(root, raw_parent)

            def before_publication() -> None:
                output_location(output, protected)
                revalidate()

            publish(output, canonical(receipt, newline=True), before_publication)
            result = {
                "status": "AUDIT_WRITTEN",
                "path": str(output),
                "deterministic_digest": receipt["deterministic_digest"],
                "sha256": sha(canonical(receipt, newline=True)),
                "pair_count": 336,
                "original_handoff": STOP,
            }
        print(canonical(result).decode())
        return 0
    except Exception as error:
        print(
            canonical(
                {
                    "status": "PUBLICATION_STATE_UNCERTAIN"
                    if isinstance(error, PublicationUncertain)
                    else "INVALID_AUDIT",
                    "reason": str(error),
                }
            ).decode()
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
