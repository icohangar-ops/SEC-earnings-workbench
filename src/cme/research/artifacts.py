"""Research artifact templates produced by a Workbench session.

Three artifact shapes, one per task type:

    - BusinessModelMemo   → company-research prompt structure (sections 1–11)
    - SECDeepDiveMemo     → SEC deep-research prompt structure (6 sections + summary)
    - InitiationOfCoverage → GS-style IoC structure (8 sections + appendix)

All artifacts share the ``ResearchArtifact`` interface: ``render() -> str``
markdown, plus structural fields the audit trail can index.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cme.agent import TurnResult
from cme.chp.models import DecisionCase, SessionStatus
from cme.research.briefs import CompanyBrief, InitiationBrief, SECDeepDiveBrief
from cme.research.data import FilingRef


@dataclass
class ResearchArtifact:
    title: str
    decision_id: str
    lock_state: str
    bottom_line: str = ""
    sections: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"# {self.title}",
            f"_decision_id: `{self.decision_id}`  ·  lock_state: **{self.lock_state}**_",
            "",
        ]
        if self.bottom_line:
            lines.append("## Bottom Line")
            lines.append(self.bottom_line)
            lines.append("")
        for s in self.sections:
            lines.append(f"## {s['heading']}")
            for item in s.get("bullets", []):
                lines.append(f"- {item}")
            if s.get("table"):
                lines.append("")
                lines.append(s["table"])
            if s.get("body"):
                lines.append("")
                lines.append(s["body"])
            lines.append("")
        if self.sources:
            lines.append("## Primary Sources")
            for src in self.sources:
                lines.append(f"- {src}")
        return "\n".join(lines).rstrip() + "\n"


@dataclass
class BusinessModelMemo(ResearchArtifact):
    pass


@dataclass
class SECDeepDiveMemo(ResearchArtifact):
    pass


@dataclass
class InitiationOfCoverage(ResearchArtifact):
    pass


# --- Builders ---------------------------------------------------------------


def _by_agent(turns: List[TurnResult]) -> Dict[str, TurnResult]:
    return {t.agent: t for t in turns}


def _lock_state(case: DecisionCase) -> str:
    return case.status.value if isinstance(case.status, SessionStatus) else str(case.status)


def _agent_bullets(turn: Optional[TurnResult]) -> List[str]:
    if not turn:
        return ["(agent did not run)"]
    bullets: List[str] = [f"Recommendation: {turn.trace.recommendation}"]
    if turn.trace.what_would_change:
        bullets.append(f"Would change if: {turn.trace.what_would_change}")
    bullets.append(f"Confidence: {turn.trace.confidence.value}")
    if turn.deltas_applied:
        bullets.append(f"Playbook deltas: {len(turn.deltas_applied)}")
    return bullets


def _fmt_money(raw: Any) -> str:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return "Not disclosed"
    if v >= 1_000_000_000_000:
        return f"${v / 1_000_000_000_000:.2f}T"
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    return f"${v:,.0f}"


def _fmt_pct(raw: Any) -> str:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return "Not disclosed"
    return f"{v * 100:.1f}%"


def _overview_bullets(overview: Optional[Dict[str, Any]]) -> List[str]:
    if not overview:
        return ["DATA NEEDED — AlphaVantage OVERVIEW not available."]
    fy = overview.get("LatestQuarter") or "n/a"
    return [
        f"Sector / Industry: {overview.get('Sector', 'n/a')} / {overview.get('Industry', 'n/a')} [AV OVERVIEW, {fy}]",
        f"Market cap: {_fmt_money(overview.get('MarketCapitalization'))} [AV OVERVIEW, {fy}]",
        f"P/E: {overview.get('PERatio', 'Not disclosed')}  ·  Fwd P/E: {overview.get('ForwardPE', 'Not disclosed')} [AV OVERVIEW, {fy}]",
        f"Profit margin: {_fmt_pct(overview.get('ProfitMargin'))}  ·  Op margin (TTM): {_fmt_pct(overview.get('OperatingMarginTTM'))} [AV OVERVIEW, {fy}]",
        f"Revenue (TTM): {_fmt_money(overview.get('RevenueTTM'))}  ·  EPS (TTM): {overview.get('EPS', 'n/a')} [AV OVERVIEW, {fy}]",
        f"Beta: {overview.get('Beta', 'n/a')}  ·  52w range: {overview.get('52WeekLow', 'n/a')}–{overview.get('52WeekHigh', 'n/a')} [AV OVERVIEW, {fy}]",
    ]


def _macro_bullets(macro: Optional[Dict[str, Dict[str, Any]]]) -> List[str]:
    if not macro:
        return ["DATA NEEDED — FRED macro panel not available."]
    out: List[str] = []
    for sid, entry in macro.items():
        label = entry.get("label", sid)
        if "value" in entry:
            out.append(f"{label} ({sid}): {entry['value']} [FRED, {entry.get('date', 'n/a')}]")
        else:
            out.append(f"{label} ({sid}): {entry.get('error', 'n/a')}")
    return out


def _earnings_bullets(earnings: Optional[Dict[str, Any]]) -> List[str]:
    if not earnings:
        return ["DATA NEEDED — AlphaVantage EARNINGS not available."]
    quarterly = earnings.get("quarterlyEarnings") or []
    if not quarterly:
        return ["AV EARNINGS returned no quarterly history."]
    rows = quarterly[:6]
    out: List[str] = []
    for row in rows:
        date = row.get("fiscalDateEnding", "n/a")
        rep = row.get("reportedEPS", "n/a")
        est = row.get("estimatedEPS", "n/a")
        sur = row.get("surprisePercentage", "n/a")
        out.append(f"FY end {date}: EPS reported {rep} vs est {est} (surprise {sur}%) [AV EARNINGS]")
    return out


def _income_summary_bullets(income: Optional[Dict[str, Any]]) -> List[str]:
    if not income:
        return ["DATA NEEDED — AlphaVantage INCOME_STATEMENT not available."]
    annual = income.get("annualReports") or []
    if not annual:
        return ["AV INCOME_STATEMENT returned no annual history."]
    out: List[str] = []
    for row in annual[:3]:
        date = row.get("fiscalDateEnding", "n/a")
        rev = _fmt_money(row.get("totalRevenue"))
        gp = _fmt_money(row.get("grossProfit"))
        ebit = _fmt_money(row.get("operatingIncome"))
        ni = _fmt_money(row.get("netIncome"))
        out.append(
            f"FY {date}: Revenue {rev}  ·  Gross profit {gp}  ·  EBIT {ebit}  ·  NI {ni} [AV INCOME_STATEMENT]"
        )
    return out


def _filings_bullets(
    filings: Optional[List[FilingRef]],
    *,
    eight_k_sweep: Optional[List[FilingRef]] = None,
    latest_10k: Optional[FilingRef] = None,
    latest_10q: Optional[FilingRef] = None,
    limit: int = 8,
) -> List[str]:
    """Render a 'Recent SEC Filings' bullet block from EdgarClient output.

    Always returns at least one bullet so the section is auditable: when
    nothing was pulled (offline / unknown ticker), we emit a 'DATA NEEDED'
    marker matching the AV/FRED degradation pattern.
    """
    if not filings:
        return ["DATA NEEDED — SEC EDGAR filings not pulled (offline or unknown ticker)."]
    out: List[str] = []
    if latest_10k is not None:
        out.append(
            f"Latest 10-K: filed {latest_10k.filing_date} (period {latest_10k.report_date}) "
            f"— accession {latest_10k.accession_no} [SEC EDGAR]"
        )
    if latest_10q is not None:
        out.append(
            f"Latest 10-Q: filed {latest_10q.filing_date} (period {latest_10q.report_date}) "
            f"— accession {latest_10q.accession_no} [SEC EDGAR]"
        )
    if eight_k_sweep:
        dates = ", ".join(f.filing_date for f in eight_k_sweep[:5])
        out.append(
            f"8-Ks since latest periodic ({len(eight_k_sweep)}): {dates} [SEC EDGAR]"
        )
    elif eight_k_sweep is not None:
        out.append("8-Ks since latest periodic: none — clean material-event slate.")
    # Then a chronological tail of the recent filings (skipping ones we
    # already named explicitly).
    named_accessions = {
        f.accession_no
        for f in (latest_10k, latest_10q)
        if f is not None
    }
    extras = [f for f in filings if f.accession_no not in named_accessions]
    for f in extras[:limit]:
        out.append(
            f"{f.form}: filed {f.filing_date} — accession {f.accession_no} [SEC EDGAR]"
        )
    return out


def _peer_table(overview: Optional[Dict[str, Any]], peers: List[str]) -> str:
    if not peers:
        return ""
    head = "| Ticker | Note | EV/Rev (latest) | P/E (latest) | Source |"
    sep = "| --- | --- | --- | --- | --- |"
    rows = [head, sep]
    for p in peers:
        rows.append(f"| {p} | peer of {overview.get('Symbol', '?') if overview else '?'} | DATA NEEDED | DATA NEEDED | AV OVERVIEW (per-ticker) |")
    return "\n".join(rows)


def build_business_model_memo(
    *,
    brief: CompanyBrief,
    case: DecisionCase,
    turns: List[TurnResult],
    overview: Optional[Dict[str, Any]] = None,
    income: Optional[Dict[str, Any]] = None,
    earnings: Optional[Dict[str, Any]] = None,
    macro: Optional[Dict[str, Dict[str, Any]]] = None,
    edgar_filings: Optional[List[FilingRef]] = None,
    eight_k_sweep: Optional[List[FilingRef]] = None,
    latest_10k: Optional[FilingRef] = None,
    latest_10q: Optional[FilingRef] = None,
) -> BusinessModelMemo:
    by_agent = _by_agent(turns)
    fundamentals = by_agent.get("fundamentals")
    diligence = by_agent.get("diligence")
    markets = by_agent.get("markets")

    overview_section = {"heading": "1. Snapshot (AlphaVantage)", "bullets": _overview_bullets(overview)}
    bizmodel_section = {
        "heading": "2. Business Model Map",
        "bullets": _agent_bullets(fundamentals)
        + (
            [f"Revenue stream hint: {s}" for s in brief.revenue_streams_hint]
            if brief.revenue_streams_hint
            else []
        ),
    }
    income_section = {
        "heading": "3. Three-Year Income Trajectory",
        "bullets": _income_summary_bullets(income),
    }
    drivers_section = {
        "heading": "4. Revenue Drivers",
        "bullets": [f"Driver: {s}" for s in brief.revenue_streams_hint]
        + ["See Fundamentals agent recommendation for the assembled driver equations."],
    }
    unit_econ_section = {
        "heading": "5. Unit Economics",
        "bullets": _agent_bullets(fundamentals),
    }
    segments_section = {
        "heading": "6. Customer Segments & GTM",
        "bullets": [f"Segment hint: {s}" for s in brief.customer_segments_hint] or ["Segments not pre-specified — see Fundamentals view."],
    }
    geo_section = {
        "heading": "7. Geography & Regulatory Context",
        "bullets": [f"Region hint: {g}" for g in brief.geography_hint] or ["Regions not pre-specified."],
    }
    earnings_section = {
        "heading": "8. KPIs to Watch (Earnings Cadence)",
        "bullets": _earnings_bullets(earnings),
    }
    peer_section = {
        "heading": "9. Peer Snapshot",
        "bullets": [f"Peer set: {', '.join(brief.peers) or 'none provided'}"],
        "table": _peer_table(overview, brief.peers),
    }
    risks_section = {
        "heading": "10. Risks & Sensitivities",
        "bullets": _agent_bullets(diligence),
    }
    triggers_section = {
        "heading": "11. What Would Change the Thesis",
        "bullets": _agent_bullets(markets),
    }
    macro_section = {"heading": "Macro Backdrop (FRED)", "bullets": _macro_bullets(macro)}
    filings_section = {
        "heading": "Primary Sources — Recent SEC Filings (EDGAR)",
        "bullets": _filings_bullets(
            edgar_filings,
            eight_k_sweep=eight_k_sweep,
            latest_10k=latest_10k,
            latest_10q=latest_10q,
        ),
    }
    lock_section = {
        "heading": "Lock Status",
        "bullets": [
            f"Foundation score: {case.foundation_score}",
            f"Status: {_lock_state(case)}",
            "Lock advances to LOCKED only after third-party validation (CHP).",
        ],
    }

    bottom = (
        f"{brief.company} ({brief.ticker}) — business-model deep dive. "
        f"Foundation score {case.foundation_score} from CHP attack. "
        f"Lock state: {_lock_state(case)}. Key vulnerability: "
        f"{case.dossier.structural_vulnerabilities[0] if case.dossier and case.dossier.structural_vulnerabilities else 'see audit trail.'}"
    )

    return BusinessModelMemo(
        title=f"Business Model Memo — {brief.company} ({brief.ticker})",
        decision_id=case.decision_id,
        lock_state=_lock_state(case),
        bottom_line=bottom,
        sections=[
            overview_section,
            bizmodel_section,
            income_section,
            drivers_section,
            unit_econ_section,
            segments_section,
            geo_section,
            earnings_section,
            peer_section,
            risks_section,
            triggers_section,
            macro_section,
            filings_section,
            lock_section,
        ],
        sources=[
            "AlphaVantage OVERVIEW / INCOME_STATEMENT / EARNINGS",
            "FRED macro series (rates, yield curve, CPI, unemployment)",
            "SEC EDGAR — recent 10-K / 10-Q / 8-K / DEF 14A (citations in Recent SEC Filings)",
        ],
    )


def build_sec_deep_dive_memo(
    *,
    brief: SECDeepDiveBrief,
    case: DecisionCase,
    turns: List[TurnResult],
    overview: Optional[Dict[str, Any]] = None,
    income: Optional[Dict[str, Any]] = None,
    cash_flow: Optional[Dict[str, Any]] = None,
    earnings: Optional[Dict[str, Any]] = None,
    macro: Optional[Dict[str, Dict[str, Any]]] = None,
    edgar_filings: Optional[List[FilingRef]] = None,
    eight_k_sweep: Optional[List[FilingRef]] = None,
    latest_10k: Optional[FilingRef] = None,
    latest_10q: Optional[FilingRef] = None,
) -> SECDeepDiveMemo:
    by_agent = _by_agent(turns)
    fundamentals = by_agent.get("fundamentals")
    diligence = by_agent.get("diligence")
    markets = by_agent.get("markets")

    fcf_ni_bullets: List[str] = []
    if cash_flow and income:
        cf_annual = cash_flow.get("annualReports") or []
        is_annual = income.get("annualReports") or []
        for cf, isr in list(zip(cf_annual, is_annual))[:3]:
            date = cf.get("fiscalDateEnding", "n/a")
            ocf = _fmt_money(cf.get("operatingCashflow"))
            capex = _fmt_money(cf.get("capitalExpenditures"))
            ni = _fmt_money(isr.get("netIncome"))
            fcf_ni_bullets.append(
                f"FY {date}: OCF {ocf}  ·  CapEx {capex}  ·  NI {ni} [AV CASH_FLOW + INCOME_STATEMENT]"
            )
    if not fcf_ni_bullets:
        fcf_ni_bullets = ["DATA NEEDED — AV CASH_FLOW or INCOME_STATEMENT missing."]

    snapshot_section = {"heading": "Snapshot", "bullets": _overview_bullets(overview)}
    filings_section = {
        "heading": "0. Primary Filings in Scope (EDGAR)",
        "bullets": _filings_bullets(
            edgar_filings,
            eight_k_sweep=eight_k_sweep,
            latest_10k=latest_10k,
            latest_10q=latest_10q,
            limit=12,
        ),
    }
    biz_section = {
        "heading": "1. Business Model & Moat",
        "bullets": _agent_bullets(fundamentals),
    }
    health_section = {
        "heading": "2. Financial Health",
        "bullets": _income_summary_bullets(income) + fcf_ni_bullets,
    }
    redflag_bullets = _agent_bullets(diligence) + (
        [f"Focus: {f}" for f in brief.red_flag_focus] if brief.red_flag_focus else []
    )
    if eight_k_sweep:
        redflag_bullets.append(
            f"8-K sweep since latest periodic surfaced {len(eight_k_sweep)} material-event "
            f"filings — review {', '.join(f.filing_date for f in eight_k_sweep[:3])} for "
            "Item 1.01 / 2.02 / 5.02 / 8.01 disclosures [SEC EDGAR]"
        )
    elif eight_k_sweep is not None:
        redflag_bullets.append(
            "8-K sweep since latest periodic: empty — no fresh material-event disclosures "
            "to qualify the periodic-filing read."
        )
    redflag_section = {
        "heading": "3. Red Flag Scan",
        "bullets": redflag_bullets,
    }
    governance_section = {
        "heading": "4. Management & Governance",
        "bullets": [
            "Executive comp structure: SEE DEF 14A — alignment to TSR vs revenue triggers",
            "Insider ownership %: SEE DEF 14A — >5% holders + officer beneficial",
            "Board composition / independence: SEE DEF 14A",
            "Activist positions (13D/13G): SEE EDGAR full-text search",
            "(See Diligence agent for synthesized read.)",
        ],
    }
    forward_section = {
        "heading": "5. Forward-Looking Signals",
        "bullets": _earnings_bullets(earnings) + _agent_bullets(markets),
    }
    valuation_section = {
        "heading": "6. Valuation Inputs",
        "bullets": [
            f"Diluted shares + option overhang: AV OVERVIEW reports {overview.get('SharesOutstanding', 'n/a') if overview else 'n/a'}; option overhang requires DEF 14A",
            "NOL carryforwards / tax shield: 10-K tax footnote",
            "Pension / OPEB liabilities: 10-K postretirement note",
            "Deferred revenue (leading indicator): 10-Q balance sheet",
            "Asset impairments / goodwill at risk: 10-K MD&A + impairment note",
        ],
    }
    macro_section = {"heading": "Macro Backdrop (FRED)", "bullets": _macro_bullets(macro)}
    lock_section = {
        "heading": "Lock Status",
        "bullets": [
            f"Foundation score: {case.foundation_score}",
            f"Status: {_lock_state(case)}",
            "Findings advance to LOCKED only after third-party validation (CHP).",
        ],
    }

    bottom = (
        f"{brief.company} ({brief.ticker}) — SEC deep-research scan over "
        f"{', '.join(brief.filings_in_scope)} across {brief.fiscal_years_back} fiscal years. "
        f"Foundation score {case.foundation_score}; lock state {_lock_state(case)}. "
        "See Red Flag Scan and Forward-Looking Signals for the actionable summary."
    )

    return SECDeepDiveMemo(
        title=f"SEC Deep-Dive Memo — {brief.company} ({brief.ticker})",
        decision_id=case.decision_id,
        lock_state=_lock_state(case),
        bottom_line=bottom,
        sections=[
            snapshot_section,
            filings_section,
            biz_section,
            health_section,
            redflag_section,
            governance_section,
            forward_section,
            valuation_section,
            macro_section,
            lock_section,
        ],
        sources=[
            "SEC EDGAR — 10-K, 10-Q, 8-K, DEF 14A (per filing date, accession cited)",
            "AlphaVantage OVERVIEW / INCOME_STATEMENT / CASH_FLOW / EARNINGS",
            "FRED macro panel",
        ],
    )


def build_initiation_of_coverage(
    *,
    brief: InitiationBrief,
    case: DecisionCase,
    turns: List[TurnResult],
    overview: Optional[Dict[str, Any]] = None,
    income: Optional[Dict[str, Any]] = None,
    quote: Optional[Dict[str, Any]] = None,
    earnings: Optional[Dict[str, Any]] = None,
    macro: Optional[Dict[str, Dict[str, Any]]] = None,
    edgar_filings: Optional[List[FilingRef]] = None,
    eight_k_sweep: Optional[List[FilingRef]] = None,
    latest_10k: Optional[FilingRef] = None,
    latest_10q: Optional[FilingRef] = None,
) -> InitiationOfCoverage:
    by_agent = _by_agent(turns)
    fundamentals = by_agent.get("fundamentals")
    diligence = by_agent.get("diligence")
    markets = by_agent.get("markets")

    price_now: Optional[float] = None
    quote_date = "n/a"
    if quote:
        gq = quote.get("Global Quote") or {}
        try:
            price_now = float(gq.get("05. price"))
        except (TypeError, ValueError):
            price_now = None
        quote_date = gq.get("07. latest trading day", "n/a")

    target = brief.target_price_usd
    upside_pct: Optional[float] = None
    if target and price_now:
        upside_pct = (target / price_now - 1.0) * 100

    snapshot_bullets = [
        f"Current price: {price_now if price_now is not None else 'DATA NEEDED'} [AV GLOBAL_QUOTE, {quote_date}]",
        f"Target price: {target if target is not None else 'DATA NEEDED'}",
        f"Implied upside: {upside_pct:+.1f}%" if upside_pct is not None else "Implied upside: DATA NEEDED",
        f"Investment rating (seed): {brief.rating_seed}",
        f"Primary valuation method: {brief.valuation_method_preference}",
    ] + _overview_bullets(overview)

    snapshot_section = {"heading": "1. Key Data & Forecast Snapshot", "bullets": snapshot_bullets}
    thesis_section = {
        "heading": "2. Investment Thesis (Tear-sheet)",
        "bullets": [
            f"Why now (1): {brief.investment_thesis_seed or 'see Fundamentals agent'}",
            "Why now (2): see Markets agent — peer multiple vs forward growth",
            "Why now (3): see Diligence agent — risk-adjusted positioning",
            f"Positioning: {brief.industry or 'n/a'} — {brief.rating_seed} initiation",
        ],
    }
    positives_section = {
        "heading": "3. Investment Positives",
        "bullets": _agent_bullets(fundamentals)
        + (
            [f"Driver hint: {d}" for d in brief.key_drivers_hint] if brief.key_drivers_hint else []
        ),
    }
    peer_section = {
        "heading": "4. Competitive / Peer Analysis",
        "bullets": [f"Peer set: {', '.join(brief.peers) or 'DATA NEEDED'}"],
        "table": _peer_table(overview, brief.peers),
    }
    estimates_section = {
        "heading": "5. Estimates & Operating Assumptions",
        "bullets": _income_summary_bullets(income)
        + [f"Forward years modeled: {brief.forecast_years}"]
        + _earnings_bullets(earnings),
    }
    valuation_section = {
        "heading": "6. Valuation",
        "bullets": _agent_bullets(markets)
        + [
            f"Primary method: {brief.valuation_method_preference}",
            "Cross-check: forward P/E vs peer median (DATA NEEDED — pull peer overviews)",
        ],
    }
    risks_section = {"heading": "7. Key Risks", "bullets": _agent_bullets(diligence)}
    appendix_section = {
        "heading": "8. Appendix",
        "bullets": [
            "Expanded model — to be assembled from AV INCOME_STATEMENT + BALANCE_SHEET + CASH_FLOW",
            "Cohort analysis — DATA NEEDED",
            "Disclosure boilerplate — to be appended per house style",
        ],
    }
    filings_section = {
        "heading": "Appendix B. Primary Sources — Recent SEC Filings (EDGAR)",
        "bullets": _filings_bullets(
            edgar_filings,
            eight_k_sweep=eight_k_sweep,
            latest_10k=latest_10k,
            latest_10q=latest_10q,
        ),
    }
    macro_section = {"heading": "Macro Backdrop (FRED)", "bullets": _macro_bullets(macro)}
    lock_section = {
        "heading": "Lock + Replay",
        "bullets": [
            f"Foundation score: {case.foundation_score}",
            f"Status: {_lock_state(case)}",
            "Initiation locks only after third-party validation (CHP).",
        ],
    }

    target_str = f"${target:,.2f}" if target else "DATA NEEDED"
    bottom = (
        f"{brief.company} ({brief.ticker}) — initiation at {brief.rating_seed}; "
        f"target {target_str}; primary lens {brief.valuation_method_preference}. "
        f"Foundation score {case.foundation_score}; lock state {_lock_state(case)}."
    )

    return InitiationOfCoverage(
        title=f"Initiation of Coverage — {brief.company} ({brief.ticker})",
        decision_id=case.decision_id,
        lock_state=_lock_state(case),
        bottom_line=bottom,
        sections=[
            snapshot_section,
            thesis_section,
            positives_section,
            peer_section,
            estimates_section,
            valuation_section,
            risks_section,
            appendix_section,
            filings_section,
            macro_section,
            lock_section,
        ],
        sources=[
            "AlphaVantage OVERVIEW / GLOBAL_QUOTE / INCOME_STATEMENT / EARNINGS",
            "FRED macro panel",
            "SEC EDGAR — recent filings cited per accession in Appendix B",
            "Peer comp data (per-ticker AV OVERVIEW pulls)",
        ],
    )
