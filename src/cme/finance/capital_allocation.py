"""Capital-allocation domain adapter for CHP sessions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from cme.chp.models import DecisionCase, Dossier, FoundationAttack, FoundationDisclosure


@dataclass
class CapitalAllocationInput:
    title: str
    company: str
    proposal_summary: str
    investment_amount_usd: float
    expected_payback_months: int
    minimum_runway_months: int
    current_runway_months: int
    strategic_priorities: List[str]
    key_risks: List[str]
    expected_upside: List[str]
    owner: str = "cfo"
    origin_system: str = "Claude"
    origin_model: str = "GPT-5.4"
    partner_system: str = "Partner"
    partner_model: str = "GPT-5-equivalent"
    decision_id: str | None = None
    high_stakes: bool = True


def build_capital_allocation_case(
    payload: CapitalAllocationInput,
) -> tuple[DecisionCase, FoundationDisclosure, FoundationAttack]:
    decision_id = payload.decision_id or _decision_id(payload.title)
    dossier = Dossier(
        core_problem=payload.proposal_summary,
        goal_state=[
            f"Payback <= {payload.expected_payback_months} months",
            f"Runway stays >= {payload.minimum_runway_months} months",
        ]
        + payload.expected_upside[:2],
        current_state=[
            f"Current runway is {payload.current_runway_months} months",
            f"Proposed investment is ${payload.investment_amount_usd:,.0f}",
        ],
        prior_decisions=[],
        constraints=[
            f"Do not reduce runway below {payload.minimum_runway_months} months",
            "Require a single accountable owner",
        ],
        unknowns=[
            "Execution timing confidence",
            "Benefit realization timing",
        ],
        scope=[
            "Foundation attack",
            "Spec lock",
            "Implementation QA",
        ],
        origin_direction=[
            "Prefer milestone-gated release of capital",
            "Require explicit flip criteria before full commitment",
        ],
        structural_vulnerabilities=[
            "Revenue timing may lag implementation spend",
            "Strategic upside may be overstated relative to execution capacity",
        ],
    )
    case = DecisionCase(
        decision_id=decision_id,
        title=payload.title,
        domain="capital_allocation",
        created_at=datetime.now(timezone.utc).isoformat(),
        owner=payload.owner,
        high_stakes=payload.high_stakes,
        origin_system=payload.origin_system,
        origin_model=payload.origin_model,
        partner_system=payload.partner_system,
        partner_model=payload.partner_model,
        dossier=dossier,
    )
    disclosure = FoundationDisclosure(
        weakest_assumptions=[
            f"Expected payback in {payload.expected_payback_months} months is achievable",
            "Strategic upside is material enough to justify the spend",
            "Organization can absorb implementation complexity without harming core execution",
        ],
        invalidation_conditions=[
            f"Runway drops below {payload.minimum_runway_months} months under downside conditions",
            "Adoption or value realization slips by more than one planning cycle",
        ],
        key_vulnerability="The case depends on timing assumptions that may look disciplined in theory but fail in operating reality.",
    )
    score = _foundation_score(payload)
    attack = FoundationAttack(
        assumption_attacks=[
            "Payback may be based on optimistic adoption rather than contracted demand.",
            "Strategic upside may be real but not near-term enough for this capital window.",
            "Execution load may crowd out current priorities and erode realized return.",
        ],
        invalidation_exploitation=[
            "If spend lands before benefits, the runway floor can be breached quickly.",
            "If adoption slips one planning cycle, the economics may fall outside hurdle tolerance.",
        ],
        vulnerability_strike="The proposal is most exposed where timing, not direction, carries the business case.",
        foundation_score=score,
        attack_summary="The case is directionally credible but timing-sensitive. It can proceed only if capital release is gated and downside triggers are explicit.",
    )
    dossier.foundation_score = score
    return case, disclosure, attack


def _decision_id(title: str) -> str:
    seed = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    return f"cap-{seed[:32]}"


def _foundation_score(payload: CapitalAllocationInput) -> int:
    score = 78
    if payload.current_runway_months < payload.minimum_runway_months + 3:
        score -= 10
    if payload.expected_payback_months > 18:
        score -= 8
    if len(payload.key_risks) >= 4:
        score -= 4
    if payload.investment_amount_usd >= 5_000_000:
        score -= 3
    return max(55, min(92, score))
