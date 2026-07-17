"""Stable serialization helpers shared by benchmarks and experiments."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_record_digest(record: dict[str, Any]) -> str:
    """Hash deterministic run content while excluding measured wall time."""
    canonical = json.loads(json.dumps(record))
    canonical.get("usage", {}).pop("wall_time_s", None)
    canonical.pop("deterministic_digest", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
