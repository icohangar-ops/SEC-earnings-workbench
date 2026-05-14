"""Cache backend for external API responses.

Supports two backends:
  - DiskCache: on-disk JSON files (default, no DB required)
  - CockroachCache: distributed CockroachDB cache (set USE_COCKROACHDB=true)

Both implement the same get/set interface so they are interchangeable.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


def _default_cache_root() -> Path:
    return Path(os.environ.get("RESEARCH_CACHE_DIR", Path.home() / ".cache" / "research-workbench"))


# ---------------------------------------------------------------------------
# Disk Cache (original — no DB required)
# ---------------------------------------------------------------------------

@dataclass
class DiskCache:
    """Minimal key-value cache with TTL in seconds. Writes JSON files."""

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


# ---------------------------------------------------------------------------
# CockroachDB Cache (distributed, ACID, multi-region)
# ---------------------------------------------------------------------------

@dataclass
class CockroachCache:
    """Distributed cache backed by CockroachDB.

    Drop-in replacement for DiskCache. Requires USE_COCKROACHDB=true
    and the db/cockroachdb_layer to be configured.
    """

    ttl_seconds: int = 24 * 3600

    def get(self, key: str) -> Optional[Any]:
        try:
            from cme.db.cockroachdb_layer import get_session, ResearchCacheRepository
            session = get_session()
            try:
                result = ResearchCacheRepository.get(session, key)
                return result
            finally:
                session.close()
        except Exception:
            # Graceful fallback — if CockroachDB is unreachable, return None
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            from cme.db.cockroachdb_layer import get_session, ResearchCacheRepository
            session = get_session()
            try:
                ResearchCacheRepository.set(session, key, value, self.ttl_seconds)
                session.commit()
            finally:
                session.close()
        except Exception:
            # Graceful fallback — if CockroachDB is unreachable, silently skip
            pass


# ---------------------------------------------------------------------------
# Factory — picks the right cache based on env
# ---------------------------------------------------------------------------

def get_cache() -> Any:
    """Return the appropriate cache backend based on configuration.

    Set USE_COCKROACHDB=true to use CockroachDB, otherwise falls back
    to the on-disk JSON cache.
    """
    if os.getenv("USE_COCKROACHDB", "false").lower() in ("true", "1", "yes"):
        return CockroachCache()
    return DiskCache()
