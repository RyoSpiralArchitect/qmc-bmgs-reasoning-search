"""Real disposable Git DAGs exercise provenance-preserving and squash merges."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "feedback_budget_provenance_tested",
    ROOT / "scripts/check_feedback_budget_provenance.py",
)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class FeedbackBudgetProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="qmc-ancestry-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Provenance test")
        self.git("config", "user.email", "provenance@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.base = self.commit("base")
        self.producing = self.commit("producing executable")
        self.write_receipts(self.producing)
        self.published = self.commit("publish receipts")

    def git(self, *args):
        return (
            subprocess.check_output(
                ["git", "-C", str(self.root), *args], stderr=subprocess.PIPE
            )
            .decode()
            .strip()
        )

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def write_receipts(self, producing):
        for relative, paths in gate.RECEIPTS.items():
            receipt = {}
            for path in paths:
                value = receipt
                for key in path[:-1]:
                    value = value.setdefault(key, {})
                value[path[-1]] = producing
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(receipt), encoding="utf-8")

    def test_real_repository_receipts_retain_their_producing_ancestors(self):
        result = gate.verify(ROOT)
        self.assertEqual(result["status"], "PUBLIC_RECEIPT_ANCESTRY_PASS")
        self.assertEqual(len(result["receipts"]), 5)
        self.assertFalse(result["trace_replay_performed"])
        self.assertFalse(result["development_execution_authorized"])

    def test_normal_published_descendant_passes(self):
        self.assertEqual(gate.verify(self.root)["checked_revision"], self.published)

    def test_merge_commit_preserves_producing_revision(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        merge = self.git(
            "commit-tree", tree, "-p", self.base, "-p", self.published, "-m", "merge"
        )
        self.assertEqual(gate.verify(self.root, merge)["checked_revision"], merge)

    def test_identical_tree_squash_fails_even_when_producing_object_exists(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        squash = self.git("commit-tree", tree, "-p", self.base, "-m", "squash")
        self.assertEqual(self.git("rev-parse", squash + "^{tree}"), tree)
        with self.assertRaisesRegex(gate.ProvenanceError, "not an ancestor"):
            gate.verify(self.root, squash)

    def test_sibling_revision_is_not_accepted(self):
        tree = self.git("rev-parse", "HEAD^{tree}")
        sibling = self.git("commit-tree", tree, "-p", self.base, "-m", "sibling")
        self.write_receipts(sibling)
        self.commit("sibling receipts")
        with self.assertRaisesRegex(gate.ProvenanceError, "not an ancestor"):
            gate.verify(self.root)

    def test_missing_producing_object_fails(self):
        self.write_receipts("0" * 40)
        self.commit("missing revision")
        with self.assertRaisesRegex(gate.ProvenanceError, "Git ancestry check failed"):
            gate.verify(self.root)

    def test_short_oid_ref_and_non_string_fail(self):
        for invalid in (self.producing[:8], "HEAD", "--help", 42, None):
            with self.subTest(invalid=invalid):
                self.write_receipts(invalid)
                self.commit("invalid revision")
                with self.assertRaisesRegex(gate.ProvenanceError, "full lowercase"):
                    gate.verify(self.root)

    def test_noncommit_object_fails(self):
        self.write_receipts(self.git("rev-parse", "HEAD^{tree}"))
        self.commit("tree instead of commit")
        with self.assertRaisesRegex(gate.ProvenanceError, "identify a commit"):
            gate.verify(self.root)

    def test_nested_revision_disagreement_fails(self):
        target = self.root / next(iter(gate.RECEIPTS))
        receipt = json.loads(target.read_text())
        receipt["source"]["package_source"]["runner_revision"] = self.base
        target.write_text(json.dumps(receipt), encoding="utf-8")
        self.commit("inconsistent revisions")
        with self.assertRaisesRegex(gate.ProvenanceError, "revisions disagree"):
            gate.verify(self.root)

    def test_missing_nested_revision_fails(self):
        target = self.root / next(iter(gate.RECEIPTS))
        target.write_text("{}", encoding="utf-8")
        self.commit("missing fields")
        with self.assertRaisesRegex(gate.ProvenanceError, "missing revision field"):
            gate.verify(self.root)

    def test_missing_receipt_is_not_silently_skipped(self):
        (self.root / next(iter(gate.RECEIPTS))).unlink()
        self.commit("missing receipt")
        with self.assertRaisesRegex(gate.ProvenanceError, "missing or non-regular"):
            gate.verify(self.root)

    def test_symlink_receipt_fails(self):
        target = self.root / next(iter(gate.RECEIPTS))
        target.unlink()
        target.symlink_to("unrelated.json")
        self.commit("symlink receipt")
        with self.assertRaisesRegex(gate.ProvenanceError, "missing or non-regular"):
            gate.verify(self.root)

    def test_shallow_clone_fails_with_retrieval_guidance(self):
        destination = Path(self.temporary.name) / "shallow"
        subprocess.run(
            ["git", "clone", "-q", "--depth=1", self.root.as_uri(), str(destination)],
            check=True,
            capture_output=True,
        )
        with self.assertRaisesRegex(gate.ProvenanceError, "complete Git history"):
            gate.verify(destination)


if __name__ == "__main__":
    unittest.main()
