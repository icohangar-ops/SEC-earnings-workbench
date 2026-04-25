"""Tiny on-disk JSON cache for external API responses."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _default_cache_root() -> Path:
    return Path(os.environ.get("RESEARCH_CACHE_DIR", Path.home() / ".cache" / "research-workbench"))


@dataclass
class DiskCache:
    """Minimal key→value cache with TTL in seconds. Writes JSON files."""

    root: Path = None  # type: ignore[assignment]
    ttl_seconds: int = 24 * 3600

    def __post_init__(self) -> None:
        if self.root is None:
            self.root = _default_cache_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.root / f"{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - payload.get("ts", 0) > self.ttl_seconds:
            return None
        return payload.get("value")

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        path.write_text(json.dumps({"ts": time.time(), "key": key, "value": value}))
