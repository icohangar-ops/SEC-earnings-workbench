"""SEC EDGAR client (stdlib only).

EDGAR has no API key; SEC requires a User-Agent header that identifies the
caller (per their fair-access policy). The client reads ``EDGAR_USER_AGENT``
from the environment if set, falling back to a generic identifier — set this
to ``"<name> <email>"`` for production use.

Endpoints wrapped:
    - company_tickers           Ticker → CIK lookup (one big JSON)
    - submissions               Filing history per company
    - recent_filings            Filtered, ordered slice of submissions
    - company_facts             XBRL company facts (financial concept time series)
    - full_text_search          EDGAR EFTS search
    - fetch_document            Raw HTML/text body of a filing document
    - extract_text              Strip HTML to plain text (stdlib only)

Rate limit: SEC allows 10 req/s. Caching (24h on disk) is the primary defense.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from cme.research.data.cache import DiskCache


class EdgarError(RuntimeError):
    """Raised on non-recoverable EDGAR errors."""


# SEC fair-access policy requires a User-Agent with contact info (name +
# email). Override with EDGAR_USER_AGENT for production use; this default is
# sufficient for low-volume identification only.
_DEFAULT_USER_AGENT = "sec-earnings-workbench zan-maker contact@example.com"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


@dataclass
class FilingRef:
    """Lightweight reference to a single EDGAR filing."""

    cik: int
    accession_no: str  # 18-char with dashes, e.g. 0000320193-24-000123
    form: str  # 10-K, 10-Q, 8-K, DEF 14A, etc.
    filing_date: str  # YYYY-MM-DD
    report_date: str  # YYYY-MM-DD (period of report; may equal filing_date)
    primary_document: str  # filename of the primary document
    is_xbrl: bool = False

    @property
    def accession_no_dashless(self) -> str:
        return self.accession_no.replace("-", "")

    @property
    def index_url(self) -> str:
        return f"{_ARCHIVES_BASE}/{self.cik}/{self.accession_no_dashless}/index.json"

    @property
    def primary_doc_url(self) -> str:
        return f"{_ARCHIVES_BASE}/{self.cik}/{self.accession_no_dashless}/{self.primary_document}"

    def citation(self) -> str:
        return f"[{self.form} filed {self.filing_date}, accession {self.accession_no}]"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "cik": self.cik,
            "accession_no": self.accession_no,
            "form": self.form,
            "filing_date": self.filing_date,
            "report_date": self.report_date,
            "primary_document": self.primary_document,
            "primary_doc_url": self.primary_doc_url,
        }


class _TextExtractor(HTMLParser):
    """Stdlib HTML→text stripper. Drops <script>/<style>, collapses whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        return re.sub(r"\s+", " ", raw).strip()


@dataclass
class EdgarClient:
    """Stdlib EDGAR client with on-disk caching."""

    user_agent: Optional[str] = None
    cache: DiskCache = field(default_factory=DiskCache)
    timeout_seconds: float = 30.0
    _ticker_index: Optional[Dict[str, Dict[str, Any]]] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.user_agent:
            self.user_agent = os.environ.get("EDGAR_USER_AGENT") or _DEFAULT_USER_AGENT

    @property
    def is_live(self) -> bool:
        """EDGAR is keyless, but tests / offline runs can opt out.

        Setting ``EDGAR_DISABLED=1`` in the environment makes the client behave
        like AV / FRED with no key — the workbench degrades gracefully and the
        rest of the pipeline keeps running.
        """
        return os.environ.get("EDGAR_DISABLED", "").strip().lower() not in {"1", "true", "yes"}

    # --- Low-level HTTP ----------------------------------------------------

    def _request(self, url: str, *, accept: str = "application/json") -> str:
        cache_key = f"edgar:{accept}:{url}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent or _DEFAULT_USER_AGENT,
                "Accept": accept,
                "Accept-Encoding": "gzip, deflate",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_bytes = resp.read()
                encoding = resp.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    import gzip

                    raw_bytes = gzip.decompress(raw_bytes)
                elif encoding == "deflate":
                    import zlib

                    raw_bytes = zlib.decompress(raw_bytes)
                raw = raw_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise EdgarError(f"EDGAR HTTP {exc.code} for {url}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EdgarError(f"EDGAR request failed for {url}: {exc}") from exc
        self.cache.set(cache_key, raw)
        return raw

    def _request_json(self, url: str) -> Any:
        raw = self._request(url, accept="application/json")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EdgarError(f"EDGAR returned non-JSON: {raw[:200]}") from exc

    # --- Ticker / CIK ------------------------------------------------------

    def _load_ticker_index(self) -> Dict[str, Dict[str, Any]]:
        if self._ticker_index is not None:
            return self._ticker_index
        data = self._request_json(_TICKERS_URL)
        # company_tickers.json is a dict-of-dicts keyed by row number.
        index: Dict[str, Dict[str, Any]] = {}
        for row in data.values():
            ticker = str(row.get("ticker", "")).upper()
            if not ticker:
                continue
            index[ticker] = {
                "cik": int(row.get("cik_str", 0)),
                "name": row.get("title", ""),
                "ticker": ticker,
            }
        self._ticker_index = index
        return index

    def cik_for(self, ticker: str) -> Optional[int]:
        idx = self._load_ticker_index()
        row = idx.get(ticker.upper())
        return row["cik"] if row else None

    def company_name_for(self, ticker: str) -> Optional[str]:
        idx = self._load_ticker_index()
        row = idx.get(ticker.upper())
        return row["name"] if row else None

    # --- Submissions / filings --------------------------------------------

    def submissions(self, ticker: str) -> Optional[Dict[str, Any]]:
        cik = self.cik_for(ticker)
        if cik is None:
            return None
        return self._request_json(_SUBMISSIONS_URL.format(cik=cik))

    def recent_filings(
        self,
        ticker: str,
        *,
        forms: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[FilingRef]:
        """Most recent filings for ``ticker`` (newest first), optionally
        filtered to specific form types (e.g. ``["10-K", "10-Q", "8-K"]``)."""
        sub = self.submissions(ticker)
        if not sub:
            return []
        cik = self.cik_for(ticker)
        recent = (sub.get("filings") or {}).get("recent") or {}
        accession = recent.get("accessionNumber") or []
        forms_arr = recent.get("form") or []
        filing_date = recent.get("filingDate") or []
        report_date = recent.get("reportDate") or []
        primary_doc = recent.get("primaryDocument") or []
        is_xbrl = recent.get("isXBRL") or [0] * len(accession)
        wanted = {f.upper() for f in forms} if forms else None
        out: List[FilingRef] = []
        for i, acc in enumerate(accession):
            form = (forms_arr[i] if i < len(forms_arr) else "").upper()
            if wanted and form not in wanted:
                continue
            out.append(
                FilingRef(
                    cik=cik or 0,
                    accession_no=acc,
                    form=form,
                    filing_date=filing_date[i] if i < len(filing_date) else "",
                    report_date=report_date[i] if i < len(report_date) else "",
                    primary_document=primary_doc[i] if i < len(primary_doc) else "",
                    is_xbrl=bool(is_xbrl[i]) if i < len(is_xbrl) else False,
                )
            )
            if len(out) >= limit:
                break
        return out

    def latest_filing(self, ticker: str, form: str) -> Optional[FilingRef]:
        results = self.recent_filings(ticker, forms=[form], limit=1)
        return results[0] if results else None

    def eight_ks_since_last_periodic(self, ticker: str) -> List[FilingRef]:
        """8-Ks filed after the most recent 10-Q (or 10-K if no 10-Q is later).
        This implements the DiligenceAgent's '8-K sweep' rule."""
        latest_10q = self.latest_filing(ticker, "10-Q")
        latest_10k = self.latest_filing(ticker, "10-K")
        anchors = [f for f in (latest_10q, latest_10k) if f is not None]
        if not anchors:
            return []
        anchor_date = max(f.filing_date for f in anchors)
        eight_ks = self.recent_filings(ticker, forms=["8-K"], limit=40)
        return [f for f in eight_ks if f.filing_date > anchor_date]

    # --- Company facts (XBRL) ---------------------------------------------

    def company_facts(self, ticker: str) -> Optional[Dict[str, Any]]:
        cik = self.cik_for(ticker)
        if cik is None:
            return None
        return self._request_json(_COMPANY_FACTS_URL.format(cik=cik))

    # --- Full-text search --------------------------------------------------

    def full_text_search(
        self,
        query: str,
        *,
        ciks: Optional[List[int]] = None,
        forms: Optional[List[str]] = None,
        date_range: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        params: Dict[str, str] = {"q": query}
        if ciks:
            params["ciks"] = ",".join(f"{c:010d}" for c in ciks)
        if forms:
            params["forms"] = ",".join(forms)
        if date_range:
            params["dateRange"] = date_range
        url = f"{_FULL_TEXT_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        return self._request_json(url)

    # --- Document fetch + extract -----------------------------------------

    def fetch_document(self, url: str) -> str:
        """Fetch a filing document (HTML or text) and return the body."""
        return self._request(url, accept="text/html, text/plain")

    @staticmethod
    def extract_text(html: str) -> str:
        parser = _TextExtractor()
        try:
            parser.feed(html)
        except Exception:
            # Some filings have malformed markup; bail and return what we got.
            pass
        return parser.text()

    @staticmethod
    def extract_section(text: str, section_name: str, *, max_chars: int = 12000) -> str:
        """Best-effort extract of a 10-K item section (e.g. 'Item 1A. Risk Factors').

        Looks for the next ``Item`` after the named section as the terminator.
        Filings vary widely; this is a coarse cut intended for human review,
        not programmatic parsing of every line.
        """
        if not text:
            return ""
        pattern = re.compile(
            rf"(?is)\b{re.escape(section_name)}\b(.*?)(\bItem\s+\d+[A-Z]?\.\s)",
        )
        m = pattern.search(text)
        if not m:
            return ""
        body = m.group(1).strip()
        if len(body) > max_chars:
            body = body[:max_chars] + "…"
        return body
