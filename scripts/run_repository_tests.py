#!/usr/bin/env python3
"""Full discovery, with an explicit verified mirror for path-bound legacy tests.

This changes only where unchanged historical tests read their unchanged source
and fixtures. It does not relocate receipts, patch admission, or execute studies.
All other tests run in the candidate checkout. No test may disappear or skip.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_ROOT_ENV = "QMC_BMGS_HISTORICAL_TEST_ROOT"
GUIDE_PROFILE_ENV = "QMC_BMGS_HISTORICAL_TEST_GUIDES"
GUIDE_PROFILE = "published-guides-20261103"
BASE = "2fc168157f9d4adc039f6a330d65e0361b31bb15"
# The eight historical modules do not read these three narrative guides.
# Keep the original strict mirror unchanged unless this closed profile is
# requested. Accept only whole guide sets from these immutable public trees.
GUIDES = ("README.md", "docs/algorithm.md", "docs/engineering_north_star.md")
GUIDE_REVISIONS = (
    BASE,
    "0b0381bfc861673a8555c4a6169c24c4f239e91c",  # main after PR37
    "4967660e03cbcef680022b7e17629af8931bab74",  # public bilingual guide
)
RESULT = "docs/qualifications/countdown_feedback_diversity_development_20261022.result-validation.json"
ORIGINAL = "docs/preregistrations/countdown_thompson_feedback_budget_v7_execution_authorization_candidate.json"
LEGACY_MODULES = frozenset(
    "test_feedback_budget_" + suffix
    for suffix in (
        "receiver_e3_environment",
        "receiver_e3_public_replay",
        "receiver_e4",
        "receiver_e4_certificate",
        "receiver_e4_publisher",
        "receiver_replication_entrypoint",
        "receiver_successor_inspection",
        "replication_reattest",
    )
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def regular(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "relative file required")
    full = root / path
    require(full.resolve(strict=True) == full, "fixture aliases are forbidden")
    require(stat.S_ISREG(full.lstat().st_mode), "regular fixture required")
    return full.read_bytes()


def verified_file(root, reference):
    raw = regular(root, reference["path"])
    require(
        len(raw) == reference["byte_count"]
        and hashlib.sha256(raw).hexdigest() == reference["sha256"],
        f"historical fixture bytes differ: {reference['path']}",
    )
    if "mode" in reference:
        require(
            stat.S_IMODE((root / reference["path"]).stat().st_mode)
            == reference["mode"],
            f"historical fixture mode differs: {reference['path']}",
        )
    return raw


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify_tree(candidate, historical, entries, *, guide_sets=None):
    """Both copies must equal the immutable merge tree, not just each other."""
    if guide_sets is not None:
        require(set(GUIDES) <= {row[3] for row in entries}, "incomplete guide set")
        for root in (candidate, historical):
            observed = tuple(git_blob(regular(root, path)) for path in GUIDES)
            require(observed in guide_sets, "unreviewed narrative guide set")
    for mode, kind, oid, path in entries:
        require(
            kind == "blob" and mode in {"100644", "100755"}, "regular Git blob required"
        )
        for root in (candidate, historical):
            # The validation entry point is the sole parent-file implementation
            # change. It is not imported by any of the eight historical modules.
            if root == candidate and path == "scripts/validate.py":
                continue
            if guide_sets is not None and path in GUIDES:
                # All three actual files in this checkout were verified jointly.
                continue
            raw = regular(root, path)
            require(
                git_blob(raw) == oid,
                f"frozen source or evidence differs: {root / path}",
            )


def verified_mirror(candidate, configured):
    historical = Path(configured)
    require(
        historical.is_absolute() and historical.resolve(strict=True) == historical,
        "historical root must be an exact absolute directory without aliases",
    )
    raw_tree = subprocess.check_output(["git", "ls-tree", "-rz", BASE], cwd=candidate)
    entries = []
    for row in raw_tree.rstrip(b"\0").split(b"\0"):
        header, name = row.decode().split("\t", 1)
        entries.append((*header.split(), name))
    profile = os.environ.get(GUIDE_PROFILE_ENV)
    require(profile in (None, GUIDE_PROFILE), "unknown historical guide profile")
    guide_sets = None
    if profile == GUIDE_PROFILE:
        guide_sets = {
            tuple(
                subprocess.check_output(
                    ["git", "rev-parse", "--verify", f"{revision}:{path}"],
                    cwd=candidate, text=True,
                ).strip()
                for path in GUIDES
            )
            for revision in GUIDE_REVISIONS
        }
    verify_tree(candidate, historical, entries, guide_sets=guide_sets)
    # This path is historical evidence, not a user-selectable admission root.
    original = json.loads(regular(candidate, ORIGINAL))
    require(
        Path(original["output_path"]).parents[2] == historical,
        "configured root differs from the frozen historical location",
    )
    result = json.loads(regular(candidate, RESULT))
    inputs = json.loads(verified_file(historical, result["inputs"]))
    for reference in inputs["protected"]:
        verified_file(historical, reference)
    for directory, expected in inputs["membership"].items():
        actual = sorted(
            str(p.relative_to(historical)) for p in (historical / directory).iterdir()
        )
        require(actual == expected, f"historical membership differs: {directory}")
    for path in inputs["absent"]:
        require(
            not os.path.lexists(historical / path), f"historical slot occupied: {path}"
        )
    return historical, len(entries), len(inputs["protected"])


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def replace_legacy(suite, historical, selected=LEGACY_MODULES):
    original = list(cases(suite))
    replacements = {}
    loader = unittest.TestLoader()
    for name in sorted(selected):
        spec = importlib.util.spec_from_file_location(
            name, historical / "tests" / f"{name}.py"
        )
        require(spec is not None and spec.loader is not None, "test module missing")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        replacements.update(
            {test.id(): test for test in cases(loader.loadTestsFromModule(module))}
        )
    require(not loader.errors, "historical test collection failed")
    expected = [test.id() for test in original if test.id().split(".")[0] in selected]
    require(
        Counter(expected) == Counter(replacements.keys()),
        "historical test identity/count differs",
    )
    result = unittest.TestSuite(replacements.get(test.id(), test) for test in original)
    require(
        Counter(test.id() for test in cases(result))
        == Counter(test.id() for test in original),
        "full test identity/count differs",
    )
    return result


def main():
    # Match `python -m unittest discover`: a few existing tests import the
    # repository's scripts namespace. This entry point is invoked with -P, so
    # declare that trusted candidate root explicitly instead of relying on cwd.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    configured = os.environ.get(HISTORICAL_ROOT_ENV)
    require(
        configured is not None or GUIDE_PROFILE_ENV not in os.environ,
        "a guide profile requires the authenticated historical root",
    )
    mirror = verified_mirror(ROOT, configured) if configured is not None else None
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"))
    require(not loader.errors, "candidate test collection failed")
    if mirror:
        historical, tracked, protected = mirror
        suite = replace_legacy(suite, historical)
        guides = os.environ.get(GUIDE_PROFILE_ENV, "original guides")
        print(
            f"Verified historical mirror: {historical}; {tracked} tracked entries ({guides}), "
            f"{protected} protected artifacts, {len(LEGACY_MODULES)} unchanged test modules",
            flush=True,
        )
    print(f"Complete collection: {suite.countTestCases()} tests", flush=True)
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        if mirror:
            require(
                verified_mirror(ROOT, configured) == mirror, "historical mirror changed"
            )
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
