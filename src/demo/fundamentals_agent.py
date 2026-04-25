"""FundamentalsAgent — produces a business-model + financial view of the subject.

Reads AlphaVantage OVERVIEW / INCOME_STATEMENT entities from the shared
ContextEngine if the orchestrator seeded them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cme.agent import AgentCapability, MeshAgent
from cme.playbook import Bullet, Playbook
from cme.protocol import CompressionStep, ConfidenceLevel, ExpansionStep


def _seed_playbook() -> Playbook:
    pb = Playbook(name="fundamentals-playbook")
    starter = [
        (
            "strategies_and_hard_rules",
            "Always cite a primary source (10-K/10-Q/AV OVERVIEW/EARNINGS) with a date — never assert without grounding.",
        ),
        (
            "strategies_and_hard_rules",
            "Separate facts from estimates: every estimate must show its formula and inputs.",
        ),
        (
            "verification_checklist",
            "Before finalizing revenue drivers: confirm KPI definitions match the latest 10-K, not a stale comparable.",
        ),
        (
            "troubleshooting_and_pitfalls",
            "When AV OVERVIEW disagrees with the latest 10-K (segment reclass, unit changes), the 10-K wins — flag the gap.",
        ),
        (
            "troubleshooting_and_pitfalls",
            "Bare percentages without a base period are a hallucination risk — always pair % with the base level and date.",
        ),
    ]
    for section, content in starter:
        new_id = pb._next_id(section)
        pb.bullets[new_id] = Bullet(id=new_id, section=section, content=content, helpful=2)
    return pb


def _av_overview(notes: List[Any]) -> Dict[str, Any]:
    for n in notes:
        attrs = getattr(n, "attributes", None) or (n.get("attributes") if isinstance(n, dict) else None)
        if attrs and attrs.get("source") == "alphavantage.OVERVIEW":
            return attrs
    return {}


class FundamentalsAgent(MeshAgent):
    def __init__(self) -> None:
        super().__init__(
            name="fundamentals",
            capability=AgentCapability(
                domain="fundamentals",
                produces=["business_model", "revenue_drivers", "financial_health"],
                consumes=[],
            ),
            playbook=_seed_playbook(),
        )

    def expand(self, problem: str, context: Dict[str, Any]) -> List[ExpansionStep]:
        notes = context.get("relevant_notes", []) or context.get("entities", [])
        ov = _av_overview(notes)
        sector = ov.get("sector", "n/a")
        market_cap = ov.get("market_cap", "n/a")
        pe = ov.get("pe_ratio", "n/a")
        pm = ov.get("profit_margin", "n/a")
        ticker = ov.get("ticker", "")
        return [
            ExpansionStep(
                label="Reframe",
                content=(
                    f"Subject: {ticker or 'subject'}. Reframe '{problem[:80]}' as a business-model "
                    f"and earnings-quality question: where does revenue come from, what are the "
                    f"unit economics, and what does the most recent 10-K disclose?"
                ),
            ),
            ExpansionStep(
                label="Constraints",
                content=(
                    "Hard: only cite primary sources (filings, AV OVERVIEW with date, EARNINGS "
                    "history). Soft: peer comparisons must use comparable definitions."
                ),
            ),
            ExpansionStep(
                label="Alternatives",
                content=(
                    "(A) Map revenue by segment from the latest 10-K. (B) Map revenue by product "
                    "if 10-K segments are coarse. (C) Reconcile AV INCOME_STATEMENT to 10-K and "
                    "flag any divergence. (D) Skip mapping and rely on AV OVERVIEW only — only "
                    "acceptable as a last resort."
                ),
                uncertainty_flags=["(D) loses provenance — should be avoided"],
            ),
            ExpansionStep(
                label="Assumptions",
                content=(
                    f"Working assumptions: sector={sector}, market cap={market_cap}, "
                    f"P/E={pe}, profit margin={pm}. KPI definitions in the latest 10-K still "
                    "match the comparable period."
                ),
                uncertainty_flags=["KPI definition stability — verify in 10-K"],
            ),
            ExpansionStep(
                label="Edge cases",
                content=(
                    "If the latest 8-K reclassifies a segment, prior YoY comparisons are not "
                    "valid. If non-GAAP profitability dominates the narrative, reconcile to GAAP "
                    "before relying on margin trend."
                ),
            ),
            ExpansionStep(
                label="Cross-domain analogy",
                content=(
                    "Treat the business-model map like a forensic income-statement walk: each "
                    "line must have a source, and each ratio must have an explicit numerator and "
                    "denominator definition."
                ),
            ),
        ]

    def compress(
        self,
        problem: str,
        expansion: List[ExpansionStep],
        context: Dict[str, Any],
    ) -> Tuple[str, List[CompressionStep], ConfidenceLevel, str, Dict[str, Any]]:
        notes = context.get("relevant_notes", []) or context.get("entities", [])
        ov = _av_overview(notes)
        sector = ov.get("sector", "n/a")
        market_cap = ov.get("market_cap", "n/a")
        rec = (
            f"Recommend business-model map anchored to the latest 10-K (sector={sector}; "
            f"market cap={market_cap}) cross-checked against AV OVERVIEW + INCOME_STATEMENT. "
            "Revenue drivers expressed as equations with explicit KPI definitions and base "
            "periods. Earnings-quality view: GAAP-vs-non-GAAP gap and FCF-vs-NI divergence "
            "called out where present."
        )
        steps = [
            CompressionStep(
                label="Integrate",
                content=(
                    "Binding constraint: every claim cites a primary source with a date. "
                    "Option (D) is dominated — it loses provenance."
                ),
            ),
            CompressionStep(
                label="Commit",
                content=(
                    "Map by segment first (Option A); fall back to product when segments are "
                    "coarse. Reconcile AV to 10-K (Option C) on every quantitative claim."
                ),
            ),
        ]
        outputs = {
            "business_model": "segment-anchored, primary-source first",
            "revenue_drivers": "expressed as equations with KPI defs + base period",
            "financial_health": "GAAP+non-GAAP reconciled; FCF vs NI divergence checked",
        }
        return (
            rec,
            steps,
            ConfidenceLevel.HIGH,
            (
                "Would change if a recent 8-K reclassifies segments, or if AV INCOME_STATEMENT "
                "diverges from the latest 10-K beyond rounding."
            ),
            outputs,
        )
