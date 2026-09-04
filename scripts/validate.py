#!/usr/bin/env python3
"""Run the repository's download-free validation surface."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEMP_PARENT_ENV = "QMC_BMGS_VALIDATION_TEMP_PARENT"


def _temporary_parent() -> Path:
    configured = os.environ.get(TEMP_PARENT_ENV)
    try:
        if configured is not None and not configured.strip():
            raise ValueError("the configured parent is empty")
        parent = (Path.home() if configured is None else Path(configured)).expanduser()
        parent = parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError("the configured parent is not a directory")
        if parent.is_relative_to(ROOT.resolve()):
            raise ValueError("the configured parent is inside the source checkout")
    except (OSError, RuntimeError, ValueError) as error:
        raise RuntimeError(
            f"Validation temporary-parent setup failed: {error}. Set "
            f"{TEMP_PARENT_ENV} to a short, quiescent, existing directory outside "
            "the source checkout. No shared-temp or symlink-alias fallback is used."
        ) from error
    return parent


def _probe_unix_socket_path(temporary_root: Path) -> None:
    # Bind only a local filesystem node, without listening or connecting. Match
    # the longest existing legacy fixture shape before running the full suite.
    try:
        with tempfile.TemporaryDirectory(
            prefix="qmc-bmgs-v2-test-", dir=temporary_root
        ) as temporary:
            socket_parent = Path(temporary) / "r1-socket"
            socket_parent.mkdir()
            socket_path = socket_parent / ".QMC-BMGS-V2R2-socket.garbage"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.bind(os.fspath(socket_path))
    except (AttributeError, NotImplementedError, OSError) as error:
        raise RuntimeError(
            f"Unix-socket validation preflight failed under {temporary_root}: "
            f"{error}. Unix-socket fixtures must be supported; set {TEMP_PARENT_ENV} "
            "to a shorter, quiescent, existing directory outside the source "
            "checkout on a filesystem supporting Unix sockets. Socket tests are "
            "not skipped, and no shared-temp or symlink-alias fallback is used."
        ) from error


def _run(command: list[str], *, temporary_root: Path, cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    environment = os.environ.copy()
    # Whole-path publication generations include temporary-root ancestors.
    # Unrelated users of the shared OS temp namespace must not perturb the
    # intended fault injection of a repository test.
    environment["TMPDIR"] = str(temporary_root)
    environment["PYTHONPATH"] = str(SRC)
    environment.setdefault("PYTHONPYCACHEPREFIX", "/tmp/qmc_bmgs_pycache")
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _validate(temporary_root: Path) -> None:
    def run(command: list[str], *, cwd: Path = ROOT) -> None:
        _run(command, temporary_root=temporary_root, cwd=cwd)

    run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "src",
            "tests",
            "scripts",
        ]
    )
    if shutil.which("ruff") is None:
        print("ruff unavailable: lint check skipped", flush=True)
    else:
        run(["ruff", "check", "."])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([sys.executable, "scripts/verify_artifacts.py"])
    run(
        [
            sys.executable,
            "-P",
            "-B",
            "scripts/audit_dense_feedback_opportunity.py",
            "--self-test",
        ]
    )

    # Catch accidental sibling-import or source-relative assumptions by invoking
    # every CLI module from outside the repository.
    outside = Path("/tmp")
    for module in (
        "qmc_bmgs.policy",
        "qmc_bmgs.anthropic_countdown",
        "qmc_bmgs.openai_countdown",
        "qmc_bmgs.benchmarks.role_lock",
        "qmc_bmgs.benchmarks.countdown",
        "qmc_bmgs.experiments.d4_noise_sweep",
        "qmc_bmgs.experiments.channel_ablation",
        "qmc_bmgs.experiments.fixed_verifier_budget",
        "qmc_bmgs.experiments.two_phase_sampler",
        "qmc_bmgs.experiments.two_phase_validation",
        "qmc_bmgs.experiments.credit_assignment",
        "qmc_bmgs.experiments.countdown_anthropic_dev",
        "qmc_bmgs.experiments.countdown_openai_dev",
        "qmc_bmgs.experiments.countdown_thompson_source_ablation",
        "qmc_bmgs.experiments.countdown_calibration_grid",
        "qmc_bmgs.experiments.countdown_track_a_substrate",
        "qmc_bmgs.experiments.countdown_track_a_search",
        "qmc_bmgs.experiments.countdown_track_a_canary_manifest",
        "qmc_bmgs.experiments.countdown_track_a_canary_runner",
        "qmc_bmgs.experiments.countdown_track_a_canary_analysis",
        "qmc_bmgs.experiments.countdown_thompson_diagnostic_runner",
        "qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis",
        "qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2",
        "qmc_bmgs.experiments.countdown_thompson_posthoc_mechanism",
        "qmc_bmgs.experiments.countdown_thompson_selection_margin",
        "qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest",
        "qmc_bmgs.experiments.countdown_thompson_dense_scale_runner",
        "qmc_bmgs.experiments.countdown_thompson_dense_scale_analysis",
    ):
        command = [sys.executable, "-m", module, "--self-test"]
        if module == "qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest":
            command.extend(["--repository-root", str(ROOT)])
        run(command, cwd=outside)
    run(
        [
            sys.executable,
            "-m",
            "qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest",
            "--verify",
            str(ROOT / "docs/preregistrations/countdown_thompson_dense_scale_v5"),
            "--repository-root",
            str(ROOT),
        ],
        cwd=outside,
    )
    print("repository validation: PASS")


def main() -> None:
    # A short private namespace avoids the busy OS temp root and preserves room
    # for legacy Unix-socket fixture names. Always use the real, resolved parent.
    with tempfile.TemporaryDirectory(
        prefix=".qv-", dir=_temporary_parent()
    ) as temporary:
        temporary_root = Path(temporary).resolve()
        _probe_unix_socket_path(temporary_root)
        _validate(temporary_root)


if __name__ == "__main__":
    main()
