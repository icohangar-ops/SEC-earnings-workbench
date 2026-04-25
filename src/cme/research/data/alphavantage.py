"""AlphaVantage REST client (stdlib only) covering the endpoints the workbench
relies on for fundamentals, earnings, quotes, and news sentiment.

AlphaVantage free tier limits requests; the disk cache (24h default) is the
primary defense. If ``ALPHAVANTAGE_API_KEY`` is not set, every method returns
``None`` so the calling agent can emit a ``DATA NEEDED`` claim.
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


class AlphaVantageError(RuntimeError):
    """Raised on non-recoverable AlphaVantage errors."""


_BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class AlphaVantageClient:
    """Lightweight AlphaVantage client with on-disk caching.

    Endpoints wrapped:
      - OVERVIEW            company snapshot (sector, market cap, ratios)
      - INCOME_STATEMENT    annual + quarterly income statements
      - BALANCE_SHEET       annual + quarterly balance sheets
      - CASH_FLOW           annual + quarterly cash flow statements
      - EARNINGS            EPS history + estimates + surprises
      - GLOBAL_QUOTE        latest price quote
      - NEWS_SENTIMENT      ticker-tagged news with sentiment scores
    """

    api_key: Optional[str] = None
    cache: DiskCache = field(default_factory=DiskCache)
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("ALPHAVANTAGE_API_KEY")

    @property
    def is_live(self) -> bool:
        return bool(self.api_key)

    def _request(self, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        params = {**params, "apikey": self.api_key}
        cache_key = "av:" + urllib.parse.urlencode(sorted(params.items()))
        # Don't cache against api key — strip it from the cache key.
        cache_key_safe = cache_key.replace(self.api_key, "<KEY>")
        cached = self.cache.get(cache_key_safe)
        if cached is not None:
            return cached
        url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AlphaVantageError(f"AlphaVantage request failed: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AlphaVantageError(f"AlphaVantage returned non-JSON: {raw[:200]}") from exc
        if isinstance(data, dict) and "Note" in data and len(data) == 1:
            # Rate-limited — surface as a soft failure, do not cache.
            raise AlphaVantageError(f"AlphaVantage rate limited: {data['Note']}")
        if isinstance(data, dict) and "Error Message" in data:
            raise AlphaVantageError(f"AlphaVantage error: {data['Error Message']}")
        self.cache.set(cache_key_safe, data)
        return data

    def overview(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._request({"function": "OVERVIEW", "symbol": ticker})

    def income_statement(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._request({"function": "INCOME_STATEMENT", "symbol": ticker})

    def balance_sheet(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._request({"function": "BALANCE_SHEET", "symbol": ticker})

    def cash_flow(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._request({"function": "CASH_FLOW", "symbol": ticker})

    def earnings(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._request({"function": "EARNINGS", "symbol": ticker})

    def global_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self._request({"function": "GLOBAL_QUOTE", "symbol": ticker})

    def news_sentiment(self, ticker: str, limit: int = 20) -> Optional[Dict[str, Any]]:
        return self._request(
            {"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": str(limit)}
        )
