"""External data clients for the research workbench.

Two providers are wired in:
    - AlphaVantage (company fundamentals + earnings + quotes + news sentiment)
    - FRED         (Federal Reserve Economic Data — macro context series)

Both clients degrade gracefully if no API key is set: they return ``None`` and
the calling agent emits a ``DATA NEEDED`` claim instead of fabricating numbers.
A 24-hour on-disk cache lives under ``~/.cache/research-workbench/`` so reruns
do not burn quota.
"""

from cme.research.data.alphavantage import AlphaVantageClient, AlphaVantageError
from cme.research.data.cache import DiskCache
from cme.research.data.fred import FredClient, FredError

__all__ = [
    "AlphaVantageClient",
    "AlphaVantageError",
    "DiskCache",
    "FredClient",
    "FredError",
]
