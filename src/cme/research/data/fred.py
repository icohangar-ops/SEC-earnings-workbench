"""FRED (Federal Reserve Economic Data) client — stdlib only.

Used for macro context: policy rates, yield curve, inflation, broad market
indices. The workbench attaches a small panel of FRED series to every research
session so valuation discussions cite real macro state.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from cme.research.data.cache import DiskCache


class FredError(RuntimeError):
    """Raised on non-recoverable FRED errors."""


_BASE_URL = "https://api.stlouisfed.org/fred"


# Default macro panel — small, generally relevant for any equity research call.
DEFAULT_MACRO_PANEL: Dict[str, str] = {
    "DGS10": "10-Year Treasury Yield",
    "DGS2": "2-Year Treasury Yield",
    "DFF": "Federal Funds Effective Rate",
    "T10Y2Y": "10Y-2Y Yield Spread",
    "CPIAUCSL": "CPI All Urban Consumers (SA)",
    "UNRATE": "Unemployment Rate",
}


@dataclass
class FredClient:
    """Lightweight FRED client with on-disk caching."""

    api_key: Optional[str] = None
    cache: DiskCache = field(default_factory=DiskCache)
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("FRED_API_KEY")

    @property
    def is_live(self) -> bool:
        return bool(self.api_key)

    def _request(self, endpoint: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        params = {**params, "api_key": self.api_key, "file_type": "json"}
        cache_key = f"fred:{endpoint}:" + urllib.parse.urlencode(sorted(params.items()))
        cache_key_safe = cache_key.replace(self.api_key, "<KEY>")
        cached = self.cache.get(cache_key_safe)
        if cached is not None:
            return cached
        url = f"{_BASE_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise FredError(f"FRED request failed: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FredError(f"FRED returned non-JSON: {raw[:200]}") from exc
        if "error_message" in data:
            raise FredError(f"FRED error: {data['error_message']}")
        self.cache.set(cache_key_safe, data)
        return data

    def series(self, series_id: str) -> Optional[Dict[str, Any]]:
        """Series metadata for a FRED series ID."""
        data = self._request("series", {"series_id": series_id})
        if data is None:
            return None
        seriess = data.get("seriess") or []
        return seriess[0] if seriess else None

    def latest_observation(self, series_id: str) -> Optional[Dict[str, Any]]:
        """Most recent non-empty observation for a series. Returns
        ``{"date": ..., "value": ...}`` or ``None``."""
        data = self._request(
            "series/observations",
            {"series_id": series_id, "sort_order": "desc", "limit": "5"},
        )
        if data is None:
            return None
        for obs in data.get("observations", []):
            value = obs.get("value")
            if value not in (None, ".", ""):
                return {"date": obs.get("date"), "value": value}
        return None

    def macro_panel(self, panel: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
        """Pull the latest observation for each series in ``panel``. Returns a
        dict keyed by series_id with ``{"label", "date", "value"}`` entries.
        Series that fail or return no key produce ``{"label", "error"}``."""
        target = panel or DEFAULT_MACRO_PANEL
        out: Dict[str, Dict[str, Any]] = {}
        for series_id, label in target.items():
            entry: Dict[str, Any] = {"label": label}
            try:
                obs = self.latest_observation(series_id)
            except FredError as exc:
                entry["error"] = str(exc)
                out[series_id] = entry
                continue
            if obs is None:
                entry["error"] = "no observation"
            else:
                entry.update(obs)
            out[series_id] = entry
        return out
