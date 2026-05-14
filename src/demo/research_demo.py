"""End-to-end Research Workbench demo running all three task types."""
from __future__ import annotations

from cme.research import (
    CompanyBrief,
    InitiationBrief,
    ResearchWorkbench,
    SECDeepDiveBrief,
)
from demo import DiligenceAgent, FundamentalsAgent, MarketsAgent


def main() -> None:
    bench = ResearchWorkbench(
        agents=[FundamentalsAgent(), DiligenceAgent(), MarketsAgent()],
    )

    company = CompanyBrief(
        title="AAPL business model deep dive",
        company="Apple Inc.",
        ticker="AAPL",
        problem="Map the AAPL business model and revenue drivers from primary sources.",
        industry="Consumer Electronics / Services",
        peers=["MSFT", "GOOGL", "AMZN"],
        revenue_streams_hint=["iPhone", "Services", "Wearables", "Mac", "iPad"],
        customer_segments_hint=["Consumer", "Enterprise", "Education"],
        geography_hint=["Americas", "Europe", "Greater China"],
    )
    rep1 = bench.run(company)
    print("=" * 80)
    print(rep1.render())

    sec = SECDeepDiveBrief(
        title="NVDA SEC filing scan",
        company="NVIDIA Corp.",
        ticker="NVDA",
        problem="Surface red flags and earnings-quality signals from NVDA SEC filings.",
        industry="Semiconductors",
        peers=["AMD", "AVGO", "INTC"],
        red_flag_focus=["customer concentration", "inventory build", "SBC % revenue"],
        fiscal_years_back=3,
    )
    rep2 = bench.run(sec)
    print("=" * 80)
    print(rep2.render())

    init = InitiationBrief(
        title="MSFT initiation of coverage",
        company="Microsoft Corp.",
        ticker="MSFT",
        problem="Initiate coverage on MSFT with a 12-month rating and target.",
        industry="Software / Cloud",
        peers=["GOOGL", "AMZN", "ORCL"],
        rating_seed="Buy",
        target_price_usd=520.0,
        valuation_method_preference="EV/EBITDA",
        forecast_years=3,
        key_drivers_hint=["Azure ARR growth", "Copilot attach rate", "Op margin"],
        investment_thesis_seed="Cloud + AI attach with sustained operating-margin tailwind",
    )
    rep3 = bench.run(init)
    print("=" * 80)
    print(rep3.render())


if __name__ == "__main__":
    main()
