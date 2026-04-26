"""External data clients for the research workbench.

Three providers are wired in:
    - AlphaVantage   (company fundamentals, earnings, quotes, news sentiment)
    - FRED           (Federal Reserve Economic Data — macro context series)
    - SEC EDGAR      (filing history, full-text search, document text)

All three clients degrade gracefully if their key (or, for EDGAR, a User-Agent
override) is missing. AV/FRED return ``None`` when no key is set; EDGAR is
keyless but its calls can be skipped entirely if the workbench is configured
without an EdgarClient.

A 24-hour on-disk cache lives under ``~/.cache/research-workbench/`` so reruns
do not burn quota.
"""

from cme.research.data.alphavantage import AlphaVantageClient, AlphaVantageError
from cme.research.data.cache import DiskCache
from cme.research.data.edgar import EdgarClient, EdgarError, FilingRef
from cme.research.data.fred import FredClient, FredError

__all__ = [
    "AlphaVantageClient",
    "AlphaVantageError",
    "DiskCache",
    "EdgarClient",
    "EdgarError",
    "FilingRef",
    "FredClient",
    "FredError",
]
