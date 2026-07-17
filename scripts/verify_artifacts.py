#!/usr/bin/env python3
"""Verify promoted artifact bytes, record counts, and strict JSON parsing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_record_digest(record: dict[str, Any]) -> str:
    canonical = json.loads(json.dumps(record))
    canonical.get("usage", {}).pop("wall_time_s", None)
    canonical.pop("deterministic_digest", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def verify_manifest(path: Path) -> dict[str, Any]:
    manifest = _strict_json(path)
    if manifest.get("schema_version") != "qmc-bmgs-artifact-manifest/v1":
        raise AssertionError(f"unsupported manifest schema: {path}")

    directory = path.parent
    for name, expected in manifest["files"].items():
        artifact = directory / name
        if not artifact.is_file():
            raise AssertionError(f"missing artifact: {artifact}")
        if artifact.stat().st_size != int(expected["bytes"]):
            raise AssertionError(f"byte-size mismatch: {artifact}")
        if _sha256(artifact) != expected["sha256"]:
            raise AssertionError(f"SHA-256 mismatch: {artifact}")

        if artifact.suffix == ".jsonl":
            records = 0
            with artifact.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line, parse_constant=_reject_constant)
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise AssertionError(
                            f"invalid strict JSON at {artifact}:{line_number}"
                        ) from exc
                    records += 1
                    digest = record.get("deterministic_digest")
                    if digest is not None and digest != _canonical_record_digest(
                        record
                    ):
                        raise AssertionError(
                            f"record digest mismatch at {artifact}:{line_number}"
                        )
            if records != int(expected["records"]):
                raise AssertionError(f"record-count mismatch: {artifact}")
        elif artifact.suffix == ".json":
            payload = _strict_json(artifact)
            quality = payload.get("data_quality")
            if quality is not None and quality.get("status") != "PASS":
                raise AssertionError(f"summary validation is not PASS: {artifact}")
    return manifest


def main() -> None:
    manifests = sorted((ROOT / "artifacts").rglob("manifest.json"))
    if not manifests:
        raise SystemExit("no artifact manifests found")
    verified = [verify_manifest(path) for path in manifests]
    print(
        "artifact verification: PASS",
        {item["artifact_id"]: item["files"]["records.jsonl"]["records"] for item in verified},
    )


if __name__ == "__main__":
    main()
