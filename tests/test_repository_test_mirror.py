"""The optional mirror must preserve every test and the exact historical bytes."""

from contextlib import contextmanager
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repository_tests_tested", ROOT / "scripts/run_repository_tests.py"
)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class HistoricalMirrorTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            candidate, historical = root / "candidate", root / "historical"
            for path in (candidate, historical):
                (path / "scripts").mkdir(parents=True)
                (path / "scripts/source.py").write_bytes(b"unchanged\n")
                (path / "scripts/validate.py").write_bytes(b"old validator\n")
            entries = []
            for name in ("source.py", "validate.py"):
                raw = (candidate / "scripts" / name).read_bytes()
                oid = hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest()
                entries.append(("100644", "blob", oid, f"scripts/{name}"))
            yield candidate, historical, entries

    def test_both_copies_must_equal_frozen_git_blobs(self):
        with self.fixture() as (candidate, historical, entries):
            M.verify_tree(candidate, historical, entries)
            for root in (candidate, historical):
                (root / "scripts/source.py").write_bytes(b"same drift in both copies\n")
            with self.assertRaisesRegex(ValueError, "frozen source"):
                M.verify_tree(candidate, historical, entries)

    def test_only_candidate_validation_entrypoint_may_differ(self):
        with self.fixture() as (candidate, historical, entries):
            (candidate / "scripts/validate.py").write_bytes(b"explicit wrapper\n")
            M.verify_tree(candidate, historical, entries)
            (historical / "scripts/validate.py").write_bytes(b"historical drift\n")
            with self.assertRaisesRegex(ValueError, "frozen source"):
                M.verify_tree(candidate, historical, entries)

    def test_alias_escape_and_nonregular_fixtures_rejected(self):
        with self.fixture() as (candidate, _, __):
            (candidate / "alias").symlink_to(candidate / "scripts")
            for name in (
                "alias/source.py",
                "../historical/scripts/source.py",
                str(candidate / "scripts/source.py"),
                "scripts",
            ):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    M.regular(candidate, name)

    def test_protected_bytes_length_and_mode_are_bound(self):
        with self.fixture() as (candidate, _, __):
            ref = dict(
                path="scripts/source.py",
                byte_count=10,
                sha256=hashlib.sha256(b"unchanged\n").hexdigest(),
                mode=0o644,
            )
            self.assertEqual(M.verified_file(candidate, ref), b"unchanged\n")
            for key, value in (
                ("byte_count", 11),
                ("sha256", "0" * 64),
                ("mode", 0o600),
            ):
                with (
                    self.subTest(key=key),
                    self.assertRaisesRegex(ValueError, "historical fixture"),
                ):
                    M.verified_file(candidate, {**ref, key: value})

    def mirror_suite(self, root, extra=""):
        (root / "tests").mkdir()
        path = root / "tests/fixture_legacy.py"
        path.write_text(
            "import unittest\nclass Example(unittest.TestCase):\n    def test_one(self): pass\n"
            + extra
        )
        spec = importlib.util.spec_from_file_location("fixture_legacy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return unittest.TestLoader().loadTestsFromModule(module)

    def test_replacement_retains_entire_test_identity_multiset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original = self.mirror_suite(root)
            suite = M.replace_legacy(original, root, {"fixture_legacy"})
            self.assertEqual(
                [t.id() for t in M.cases(suite)], [t.id() for t in M.cases(original)]
            )
            self.assertIsNot(next(M.cases(suite)), next(M.cases(original)))

    def test_missing_or_extra_test_never_silently_replaces_collection(self):
        for suffix in ("    def test_two(self): pass\n", ""):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                original = self.mirror_suite(root)
                path = root / "tests/fixture_legacy.py"
                path.write_text(
                    path.read_text() + suffix if suffix else "import unittest\n"
                )
                with self.assertRaisesRegex(ValueError, "identity/count"):
                    M.replace_legacy(original, root, {"fixture_legacy"})

    def test_suite_failures_and_skips_remain_nonzero(self):
        for success, skipped in (
            (False, []),
            (True, [("test", "unavailable")]),
            (True, []),
        ):
            with (
                patch.dict(M.os.environ, {}, clear=True),
                patch.object(
                    M.unittest.TestLoader, "discover", return_value=unittest.TestSuite()
                ),
                patch.object(
                    M.unittest.TextTestRunner,
                    "run",
                    return_value=SimpleNamespace(
                        wasSuccessful=lambda: success, skipped=skipped
                    ),
                ),
                patch("sys.stdout", new=io.StringIO()),
            ):
                self.assertEqual(M.main(), 0 if success and not skipped else 1)

    def test_mirror_reverified_even_when_runner_raises(self):
        with (
            patch.dict(M.os.environ, {M.HISTORICAL_ROOT_ENV: "/fixture"}),
            patch.object(
                M, "verified_mirror", return_value=(Path("/fixture"), 470, 5329)
            ) as verify,
            patch.object(M, "replace_legacy", side_effect=lambda suite, root: suite),
            patch.object(
                M.unittest.TestLoader, "discover", return_value=unittest.TestSuite()
            ),
            patch.object(
                M.unittest.TextTestRunner,
                "run",
                side_effect=RuntimeError("interrupted"),
            ),
            patch("sys.stdout", new=io.StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                M.main()
            self.assertEqual(verify.call_count, 2)
