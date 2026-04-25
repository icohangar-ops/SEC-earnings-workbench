"""Structured research briefs — the input to a Research Workbench session.

Three task types map onto the three source prompts:

    - CompanyBrief         → ``Company research`` prompt (business model strategist)
    - SECDeepDiveBrief     → ``SEC filing deep research`` prompt (10-K/10-Q deep dive)
    - InitiationBrief      → ``Top stock research`` prompt (initiation of coverage)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ResearchTaskType(str, Enum):
    COMPANY_RESEARCH = "company_research"
    SEC_DEEP_DIVE = "sec_deep_dive"
    INITIATION = "initiation"


@dataclass
class ResearchBrief:
    """Common fields for any research task."""

    title: str
    company: str
    ticker: str
    problem: str
    # Optional context provided by the requester.
    industry: str = ""
    requestor: str = "corp_dev"
    high_stakes: bool = True
    origin_system: str = "Claude"
    origin_model: str = "GPT-5.4"
    partner_system: str = "Partner"
    partner_model: str = "GPT-5-equivalent"
    decision_id: Optional[str] = None
    investment_thesis_seed: str = ""
    peers: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)


@dataclass
class CompanyBrief(ResearchBrief):
    """Business-model deep dive (sections 1–11 of the company-research prompt)."""

    task_type: ResearchTaskType = ResearchTaskType.COMPANY_RESEARCH
    revenue_streams_hint: List[str] = field(default_factory=list)
    customer_segments_hint: List[str] = field(default_factory=list)
    geography_hint: List[str] = field(default_factory=list)


@dataclass
class SECDeepDiveBrief(ResearchBrief):
    """SEC filing deep-research task (10-K, 10-Q, 8-K, DEF 14A scan)."""

    task_type: ResearchTaskType = ResearchTaskType.SEC_DEEP_DIVE
    filings_in_scope: List[str] = field(
        default_factory=lambda: ["10-K", "10-Q", "8-K", "DEF 14A"]
    )
    red_flag_focus: List[str] = field(default_factory=list)
    fiscal_years_back: int = 3


@dataclass
class InitiationBrief(ResearchBrief):
    """Initiation of Coverage report task (GS-style 8-section report)."""

    task_type: ResearchTaskType = ResearchTaskType.INITIATION
    rating_seed: str = "Buy"  # Buy / Hold / Sell preliminary lean
    target_price_usd: Optional[float] = None
    valuation_method_preference: str = "EV/EBITDA"  # or P/E, EV/Sales, sum-of-parts
    forecast_years: int = 3
    key_drivers_hint: List[str] = field(default_factory=list)
