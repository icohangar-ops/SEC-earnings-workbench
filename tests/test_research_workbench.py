"""Smoke tests for the Research Workbench. Runs without API keys (graceful
degradation): the workbench should still produce all three artifact types and
land a valid lock state."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Force agents to run without external data — strip env keys for the test.
os.environ.pop("ALPHAVANTAGE_API_KEY", None)
os.environ.pop("FRED_API_KEY", None)
os.environ["EDGAR_DISABLED"] = "1"  # avoid network calls to SEC EDGAR in tests

from cme.chp.models import SessionStatus  # noqa: E402
from cme.research import (  # noqa: E402
    CompanyBrief,
    InitiationBrief,
    ResearchTaskType,
    ResearchWorkbench,
    SECDeepDiveBrief,
)
from demo import DiligenceAgent, FundamentalsAgent, MarketsAgent  # noqa: E402


def _bench() -> ResearchWorkbench:
    return ResearchWorkbench(agents=[FundamentalsAgent(), DiligenceAgent(), MarketsAgent()])


def test_company_research_runs_and_locks():
    bench = _bench()
    brief = CompanyBrief(
        title="AAPL business model",
        company="Apple Inc.",
        ticker="AAPL",
        problem="Map AAPL business model and revenue drivers from primary sources.",
        peers=["MSFT", "GOOGL"],
        revenue_streams_hint=["iPhone", "Services"],
    )
    rep = bench.run(brief)
    assert rep.brief.task_type == ResearchTaskType.COMPANY_RESEARCH
    assert rep.case.status in {SessionStatus.PROVISIONAL_LOCK, SessionStatus.EXPLORING}
    assert rep.artifact.title.startswith("Business Model Memo")
    assert "ALPHAVANTAGE_API_KEY not set" in " ".join(rep.data_warnings)
    assert "FRED_API_KEY not set" in " ".join(rep.data_warnings)
    rendered = rep.render()
    assert "Audit Trail" in rendered
    assert "Initial CHP Packet" in rendered
    # EDGAR is disabled in tests — the warning must surface and the artifact
    # must still emit a "Recent SEC Filings" section with the DATA NEEDED marker.
    assert any("EDGAR_DISABLED" in w for w in rep.data_warnings)
    headings = [s["heading"] for s in rep.artifact.sections]
    assert any("Recent SEC Filings" in h for h in headings)


def test_sec_deep_dive_runs_and_locks():
    bench = _bench()
    brief = SECDeepDiveBrief(
        title="NVDA SEC scan",
        company="NVIDIA Corp.",
        ticker="NVDA",
        problem="Surface red flags from NVDA filings.",
        red_flag_focus=["customer concentration"],
    )
    rep = bench.run(brief)
    assert rep.brief.task_type == ResearchTaskType.SEC_DEEP_DIVE
    assert rep.artifact.title.startswith("SEC Deep-Dive Memo")
    # The memo must contain the SEC-prompt section names verbatim.
    headings = [s["heading"] for s in rep.artifact.sections]
    assert any("Red Flag" in h for h in headings)
    assert any("Governance" in h for h in headings)
    assert any("Forward-Looking" in h for h in headings)


def test_initiation_runs_and_renders_target_upside():
    bench = _bench()
    brief = InitiationBrief(
        title="MSFT initiation",
        company="Microsoft Corp.",
        ticker="MSFT",
        problem="Initiate coverage with rating + target.",
        peers=["GOOGL", "AMZN"],
        rating_seed="Buy",
        target_price_usd=520.0,
        valuation_method_preference="EV/EBITDA",
        forecast_years=3,
    )
    rep = bench.run(brief)
    assert rep.brief.task_type == ResearchTaskType.INITIATION
    assert rep.artifact.title.startswith("Initiation of Coverage")
    md = rep.artifact.render()
    assert "Target price: 520.0" in md
    assert "Buy" in md


def test_audit_trail_per_claim_provenance():
    bench = _bench()
    brief = CompanyBrief(
        title="GOOGL business model",
        company="Alphabet Inc.",
        ticker="GOOGL",
        problem="Map GOOGL business model.",
    )
    rep = bench.run(brief)
    # One audit entry per expansion step + one recommendation per agent.
    by_agent = {}
    for e in rep.audit.entries:
        by_agent.setdefault(e.agent, 0)
        by_agent[e.agent] += 1
    # 3 agents × (>=6 expansion steps + 1 recommendation) = >=21 entries
    assert sum(by_agent.values()) >= 21
    assert set(by_agent.keys()) == {"fundamentals", "diligence", "markets"}


class _StubEdgarClient:
    """Deterministic stand-in for EdgarClient — no network calls, no cache.

    Returns the same handful of synthetic filings for every ticker so the test
    can assert that EDGAR data flows end-to-end (context → artifact → audit).
    """

    is_live = True

    def __init__(self) -> None:
        from cme.research.data import FilingRef  # noqa: WPS433

        self._latest_10k = FilingRef(
            cik=320193,
            accession_no="0000320193-25-000079",
            form="10-K",
            filing_date="2025-10-31",
            report_date="2025-09-27",
            primary_document="aapl-20250927.htm",
            is_xbrl=True,
        )
        self._latest_10q = FilingRef(
            cik=320193,
            accession_no="0000320193-25-000045",
            form="10-Q",
            filing_date="2025-08-01",
            report_date="2025-06-28",
            primary_document="aapl-20250628.htm",
            is_xbrl=True,
        )
        self._eight_ks = [
            FilingRef(
                cik=320193,
                accession_no="0000320193-26-000001",
                form="8-K",
                filing_date="2026-04-20",
                report_date="2026-04-20",
                primary_document="aapl-20260420.htm",
                is_xbrl=False,
            ),
            FilingRef(
                cik=320193,
                accession_no="0000320193-26-000002",
                form="8-K",
                filing_date="2026-02-24",
                report_date="2026-02-24",
                primary_document="aapl-20260224.htm",
                is_xbrl=False,
            ),
        ]

    def cik_for(self, ticker: str):
        return 320193

    def company_name_for(self, ticker: str):
        return "STUB INC."

    def recent_filings(self, ticker, *, forms=None, limit=10):
        all_filings = [self._latest_10k, self._latest_10q] + self._eight_ks
        if forms:
            wanted = {f.upper() for f in forms}
            all_filings = [f for f in all_filings if f.form in wanted]
        return all_filings[:limit]

    def latest_filing(self, ticker, form):
        if form.upper() == "10-K":
            return self._latest_10k
        if form.upper() == "10-Q":
            return self._latest_10q
        return None

    def eight_ks_since_last_periodic(self, ticker):
        return list(self._eight_ks)


def test_edgar_filings_flow_into_artifact_and_audit():
    """EDGAR data must surface in the artifact, the audit trail's external
    sources block, and the data-warnings list (none in live mode)."""
    from cme.research.data import EdgarClient  # noqa: WPS433

    bench = ResearchWorkbench(
        agents=[FundamentalsAgent(), DiligenceAgent(), MarketsAgent()],
        edgar=_StubEdgarClient(),  # type: ignore[arg-type]
    )
    brief = SECDeepDiveBrief(
        title="AAPL SEC scan",
        company="Apple Inc.",
        ticker="AAPL",
        problem="Surface red flags from AAPL filings.",
    )
    rep = bench.run(brief)

    # Artifact: filings must show up as a primary-sources section with citations.
    md = rep.artifact.render()
    assert "0000320193-25-000079" in md  # latest 10-K accession
    assert "Latest 10-K: filed 2025-10-31" in md
    assert "8-Ks since latest periodic" in md
    # Audit trail: EDGAR ingestion summary in External Grounding Sources.
    audit_md = rep.audit.render()
    assert "SEC EDGAR" in audit_md
    assert "filings ingested" in audit_md
    # Report-level access: report.edgar_filings populated.
    assert len(rep.edgar_filings) >= 2
    # Diligence agent must reference real filing dates from shared context.
    diligence_turn = next(t for t in rep.turns if t.agent == "diligence")
    expansion_text = " ".join(s.content for s in diligence_turn.trace.expansion)
    assert "2025-10-31" in expansion_text or "0000320193" in expansion_text
    # No EDGAR warning when live.
    assert not any("EDGAR_DISABLED" in w for w in rep.data_warnings)
    # Sanity: the real EdgarClient should still be importable.
    assert EdgarClient is not None


def test_lock_progression_via_validator():
    bench = _bench()
    brief = CompanyBrief(
        title="META business model",
        company="Meta Platforms Inc.",
        ticker="META",
        problem="Map META business model.",
        peers=["GOOGL", "SNAP"],
    )
    rep = bench.run(brief)
    if rep.case.status == SessionStatus.PROVISIONAL_LOCK:
        case = bench.lock(
            rep.case.decision_id,
            validator="fresh_instance",
            item="Memo v1",
            rationale="Coheres; sources cited.",
        )
        assert case.status == SessionStatus.LOCKED
