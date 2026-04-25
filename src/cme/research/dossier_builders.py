"""Brief → CHP DecisionCase + FoundationDisclosure + FoundationAttack.

Each research task type lands the inputs into the canonical CHP shape so the
same hardening pipeline runs on company research, SEC deep dives, and
initiation reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from cme.chp.models import DecisionCase, Dossier, FoundationAttack, FoundationDisclosure
from cme.research.briefs import (
    CompanyBrief,
    InitiationBrief,
    ResearchBrief,
    ResearchTaskType,
    SECDeepDiveBrief,
)


def build_decision_case(
    brief: ResearchBrief,
) -> Tuple[DecisionCase, FoundationDisclosure, FoundationAttack]:
    if isinstance(brief, CompanyBrief):
        return _build_company_case(brief)
    if isinstance(brief, SECDeepDiveBrief):
        return _build_sec_case(brief)
    if isinstance(brief, InitiationBrief):
        return _build_initiation_case(brief)
    raise TypeError(f"Unsupported brief type: {type(brief).__name__}")


def _decision_id(prefix: str, ticker: str, title: str) -> str:
    seed = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    return f"{prefix}-{ticker.lower()}-{seed[:24]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_for(task: ResearchTaskType) -> str:
    return {
        ResearchTaskType.COMPANY_RESEARCH: "company_research",
        ResearchTaskType.SEC_DEEP_DIVE: "sec_deep_dive",
        ResearchTaskType.INITIATION: "initiation_of_coverage",
    }[task]


def _build_company_case(
    brief: CompanyBrief,
) -> Tuple[DecisionCase, FoundationDisclosure, FoundationAttack]:
    decision_id = brief.decision_id or _decision_id("co", brief.ticker, brief.title)
    dossier = Dossier(
        core_problem=brief.problem,
        goal_state=[
            "Decision-ready business-model map with cited drivers and unit economics",
            "Six-to-ten KPI watchlist tied to revenue formulas",
        ],
        current_state=[
            f"Subject: {brief.company} ({brief.ticker})",
            f"Industry hint: {brief.industry or 'not stated'}",
            f"Peer hint: {', '.join(brief.peers) or 'none provided'}",
        ],
        prior_decisions=[],
        constraints=[
            "Primary sources first: 10-K/20-F, 10-Q, IR, transcripts",
            "Cite each fact with source and date; estimates must show formula",
            "Separate facts from estimates; mark unknowns 'Not disclosed'",
        ]
        + brief.constraints,
        unknowns=[
            "Take rates / pricing detail not in public filings",
            "Customer concentration if not disclosed",
            "Region-specific regulatory frictions",
        ],
        scope=[
            "Business model map",
            "Revenue drivers + unit economics",
            "Peer snapshot",
            "Risks + thesis triggers",
        ],
        origin_direction=[
            "Prefer driver equations over narrative",
            "Cite KPIs with the latest reported level and source",
        ],
        structural_vulnerabilities=[
            "Mixing historical fact with forward estimate without explicit labels",
            "KPI definitions can drift between filings — verify against current 10-K",
        ],
    )
    case = DecisionCase(
        decision_id=decision_id,
        title=brief.title,
        domain=_domain_for(brief.task_type),
        created_at=_now(),
        owner=brief.requestor,
        high_stakes=brief.high_stakes,
        origin_system=brief.origin_system,
        origin_model=brief.origin_model,
        partner_system=brief.partner_system,
        partner_model=brief.partner_model,
        dossier=dossier,
    )
    disclosure = FoundationDisclosure(
        weakest_assumptions=[
            "Disclosed revenue mix is current and not stale relative to recent product shifts",
            "KPI definitions in the latest 10-K still match prior comparable disclosures",
            "Take-rate / pricing assumptions hold across the geographies summarized",
        ],
        invalidation_conditions=[
            "Material segment reclassification in latest filing not reflected here",
            "KPI definition change disclosed but not propagated through driver equations",
        ],
        key_vulnerability=(
            "Business-model maps fail when category shifts (e.g. ads→subscription, "
            "marketplace→first-party) are not yet visible in summarized disclosures."
        ),
    )
    score = _company_foundation_score(brief)
    attack = FoundationAttack(
        assumption_attacks=[
            "KPI levels may already have shifted post the cited period.",
            "Take-rate ranges may be implicit; vendor or category mix dilutes them.",
            "Peer set may not match the company's strategic peers as IR frames them.",
        ],
        invalidation_exploitation=[
            "If KPI definitions changed, driver equations silently mis-state revenue.",
            "If segment mix has shifted, gross-margin trends are not comparable YoY.",
        ],
        vulnerability_strike=(
            "Most exposed where summary tables paper over recent disclosure changes."
        ),
        foundation_score=score,
        attack_summary=(
            "Memo is credible if every KPI carries a current source date and "
            "estimate formulas are visible end-to-end."
        ),
    )
    dossier.foundation_score = score
    return case, disclosure, attack


def _build_sec_case(
    brief: SECDeepDiveBrief,
) -> Tuple[DecisionCase, FoundationDisclosure, FoundationAttack]:
    decision_id = brief.decision_id or _decision_id("sec", brief.ticker, brief.title)
    filings = ", ".join(brief.filings_in_scope)
    dossier = Dossier(
        core_problem=brief.problem,
        goal_state=[
            "Red-flag scan with explicit citations to filings and dates",
            "Earnings-quality view: GAAP vs non-GAAP gap, FCF vs NI divergence",
            "Governance read: comp alignment, insider ownership, board independence",
        ],
        current_state=[
            f"Subject: {brief.company} ({brief.ticker})",
            f"Filings in scope: {filings}",
            f"Look-back: {brief.fiscal_years_back} fiscal years",
            f"Red-flag focus: {', '.join(brief.red_flag_focus) or 'standard'}",
        ],
        prior_decisions=[],
        constraints=[
            "Cite each finding with filing type + filing date",
            "Distinguish disclosed facts from analyst inference",
            "Flag covenants, going-concern language, auditor changes explicitly",
        ]
        + brief.constraints,
        unknowns=[
            "Off-balance-sheet exposures via JVs, VIEs, guarantees",
            "Insider sentiment beyond Form 4 selling patterns",
            "Customer concentration in ranges (often grouped in 10-K)",
        ],
        scope=[
            "Business model & moat",
            "Financial health",
            "Red flag scan",
            "Management & governance",
            "Forward-looking signals",
            "Valuation inputs",
        ],
        origin_direction=[
            "Prefer SEC filings over commentary; map every claim to a filing",
            "Surface earnings-quality divergences before red flags",
        ],
        structural_vulnerabilities=[
            "Working-capital anomalies can reverse benignly or signal channel stuffing",
            "Stock-based-comp distortions hide in 'adjusted' metrics",
            "Risk-factor diffs vs prior year often more informative than the list itself",
        ],
    )
    case = DecisionCase(
        decision_id=decision_id,
        title=brief.title,
        domain=_domain_for(brief.task_type),
        created_at=_now(),
        owner=brief.requestor,
        high_stakes=brief.high_stakes,
        origin_system=brief.origin_system,
        origin_model=brief.origin_model,
        partner_system=brief.partner_system,
        partner_model=brief.partner_model,
        dossier=dossier,
    )
    disclosure = FoundationDisclosure(
        weakest_assumptions=[
            "Filings reviewed are the latest available and have not been superseded",
            "Non-GAAP-to-GAAP reconciliation in the filing is mathematically complete",
            "Risk factors added/removed YoY meaningfully reflect management's view",
        ],
        invalidation_conditions=[
            "An 8-K filed after the latest 10-Q materially changes one of the findings",
            "Auditor change or going-concern language present but missed in the scan",
        ],
        key_vulnerability=(
            "SEC scans miss the truth when an 8-K post-dates the 10-Q and shifts the "
            "financial-health read, or when a related-party note is buried."
        ),
    )
    score = _sec_foundation_score(brief)
    attack = FoundationAttack(
        assumption_attacks=[
            "Recent 8-Ks may already invalidate ratios cited from the prior 10-Q.",
            "Stock-based comp adjustments may inflate non-GAAP profitability.",
            "Insider selling under 10b5-1 may look mechanical but reflect a view.",
        ],
        invalidation_exploitation=[
            "Going-concern or auditor-change language flips the entire financial-health read.",
            "Material-weakness disclosure signals control breakdown that distorts every metric.",
        ],
        vulnerability_strike=(
            "Most exposed where 8-Ks post-date the most-cited periodic filing."
        ),
        foundation_score=score,
        attack_summary=(
            "Scan is hardened only if every finding carries a filing-type + date "
            "citation and 8-Ks since the last 10-Q have been swept."
        ),
    )
    dossier.foundation_score = score
    return case, disclosure, attack


def _build_initiation_case(
    brief: InitiationBrief,
) -> Tuple[DecisionCase, FoundationDisclosure, FoundationAttack]:
    decision_id = brief.decision_id or _decision_id("ini", brief.ticker, brief.title)
    target = (
        f"${brief.target_price_usd:,.2f}" if brief.target_price_usd else "to be derived"
    )
    dossier = Dossier(
        core_problem=brief.problem,
        goal_state=[
            "Initiation of Coverage with explicit rating, target, and upside",
            f"Forward model: {brief.forecast_years} years, top-line driver based",
            f"Valuation cross-check via {brief.valuation_method_preference} vs peer median",
        ],
        current_state=[
            f"Subject: {brief.company} ({brief.ticker})",
            f"Industry: {brief.industry or 'not stated'}",
            f"Rating seed: {brief.rating_seed}",
            f"Target seed: {target}",
            f"Peers: {', '.join(brief.peers) or 'to be selected'}",
        ],
        prior_decisions=[],
        constraints=[
            "Cite every statistic with source and date",
            "Mark missing data 'DATA NEEDED' and propose a source",
            "Convert international peer figures to USD",
            "No em dashes in the report body",
        ]
        + brief.constraints,
        unknowns=[
            "Forward consensus revisions vs sell-side range",
            "Peer comp distortions from one-time items",
            "FX assumptions that flip the implied multiple",
        ],
        scope=[
            "Key data + forecast snapshot",
            "Investment thesis tear-sheet",
            "Investment positives",
            "Peer analysis",
            "Forward model + KPIs",
            "Valuation",
            "Risks",
            "Appendix",
        ],
        origin_direction=[
            "Use plain English, active voice; bullet-heavy where useful",
            "Show calculations end-to-end",
        ],
        structural_vulnerabilities=[
            "Peer median comparisons can mislead when peers themselves are mispriced",
            "Multiples can compress without earnings change — risk of false precision",
            "GS-style radar percentile framing can over-anchor the rating",
        ],
    )
    case = DecisionCase(
        decision_id=decision_id,
        title=brief.title,
        domain=_domain_for(brief.task_type),
        created_at=_now(),
        owner=brief.requestor,
        high_stakes=brief.high_stakes,
        origin_system=brief.origin_system,
        origin_model=brief.origin_model,
        partner_system=brief.partner_system,
        partner_model=brief.partner_model,
        dossier=dossier,
    )
    disclosure = FoundationDisclosure(
        weakest_assumptions=[
            f"Forward growth path is achievable over {brief.forecast_years} years",
            f"{brief.valuation_method_preference} multiple is the right primary lens for this industry",
            "Peer median is a defensible cross-check at the proposed valuation date",
        ],
        invalidation_conditions=[
            "Peer set re-rates 25%+ in either direction within the forecast window",
            "Top-line driver assumption misses by more than one revision cycle",
        ],
        key_vulnerability=(
            "Initiations are most fragile where the rating leans on multiple expansion "
            "rather than earnings growth that is already in motion."
        ),
    )
    score = _initiation_foundation_score(brief)
    attack = FoundationAttack(
        assumption_attacks=[
            "Rating may rest on multiple re-rating that the macro context does not support.",
            "Peer set may share the same beta to the macro factor that drives the rating.",
            "Forward model may extrapolate a one-time tailwind as recurring.",
        ],
        invalidation_exploitation=[
            "If macro tightens and the peer median compresses, target falls fastest.",
            "If a key driver KPI mean-reverts, the forecast loses operating-leverage benefit.",
        ],
        vulnerability_strike=(
            "Most exposed where the rating story is multiple expansion under "
            "macro conditions that historically compress the multiple."
        ),
        foundation_score=score,
        attack_summary=(
            "Coverage is defensible if the forecast carries explicit driver KPIs "
            "and the valuation cross-check survives a macro stress."
        ),
    )
    dossier.foundation_score = score
    return case, disclosure, attack


def _company_foundation_score(brief: CompanyBrief) -> int:
    score = 78
    if not brief.peers:
        score -= 6
    if not brief.industry:
        score -= 4
    if len(brief.revenue_streams_hint) >= 3:
        score += 3
    return max(55, min(92, score))


def _sec_foundation_score(brief: SECDeepDiveBrief) -> int:
    score = 80
    if brief.fiscal_years_back < 2:
        score -= 6
    if "8-K" not in brief.filings_in_scope:
        score -= 6
    if not brief.red_flag_focus:
        score -= 3
    return max(55, min(92, score))


def _initiation_foundation_score(brief: InitiationBrief) -> int:
    score = 75
    if not brief.peers:
        score -= 8
    if brief.target_price_usd is None:
        score -= 4
    if brief.forecast_years < 3:
        score -= 3
    if brief.key_drivers_hint:
        score += 3
    return max(55, min(92, score))
