"""MarketsAgent — produces peer view, valuation cross-check, thesis triggers.

Consumes ``business_model`` and uses the FRED macro panel + AV peer overviews
to land a multiples-based valuation read with macro context attached.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cme.agent import AgentCapability, MeshAgent
from cme.playbook import Bullet, Playbook
from cme.protocol import CompressionStep, ConfidenceLevel, ExpansionStep


def _seed_playbook() -> Playbook:
    pb = Playbook(name="markets-playbook")
    starter = [
        (
            "strategies_and_hard_rules",
            "Always pair a primary multiple (P/E or EV/EBITDA) with a peer median and a macro overlay.",
        ),
        (
            "strategies_and_hard_rules",
            "Convert peer figures to USD before comparing — international comps mislead at face value.",
        ),
        (
            "verification_checklist",
            "Confirm peer set actually shares the same demand factor, not just sector tag.",
        ),
        (
            "troubleshooting_and_pitfalls",
            "Multiple expansion under tightening rates rarely persists; surface the rates context explicitly.",
        ),
        (
            "troubleshooting_and_pitfalls",
            "Forward consensus is a herd anchor — note the dispersion, not just the median.",
        ),
    ]
    for section, content in starter:
        new_id = pb._next_id(section)
        pb.bullets[new_id] = Bullet(id=new_id, section=section, content=content, helpful=2)
    return pb


def _macro_snapshot(notes: List[Any]) -> Dict[str, Any]:
    macro: Dict[str, Any] = {}
    for n in notes:
        attrs = getattr(n, "attributes", None) or (n.get("attributes") if isinstance(n, dict) else None)
        if attrs and attrs.get("source") == "FRED":
            macro[attrs.get("series_id", "?")] = attrs
    return macro


class MarketsAgent(MeshAgent):
    def __init__(self) -> None:
        super().__init__(
            name="markets",
            capability=AgentCapability(
                domain="markets",
                produces=["peer_view", "valuation_view", "thesis_triggers"],
                consumes=["business_model"],
            ),
            playbook=_seed_playbook(),
        )

    def expand(self, problem: str, context: Dict[str, Any]) -> List[ExpansionStep]:
        notes = context.get("relevant_notes", []) or context.get("entities", [])
        macro = _macro_snapshot(notes)
        rates = macro.get("DGS10", {}).get("value", "n/a")
        spread = macro.get("T10Y2Y", {}).get("value", "n/a")
        return [
            ExpansionStep(
                label="Reframe",
                content=(
                    f"Reframe '{problem[:80]}' as a relative-value question: where does the "
                    f"primary multiple sit vs the peer median, and is that consistent with the "
                    f"current macro state (10Y={rates}, 10Y-2Y={spread})?"
                ),
            ),
            ExpansionStep(
                label="Constraints",
                content=(
                    "Hard: peer set must share the same demand factor. "
                    "Soft: prefer EV/EBITDA in industrials/services; P/E in consumer; EV/Revenue "
                    "for unprofitable growth."
                ),
            ),
            ExpansionStep(
                label="Alternatives",
                content=(
                    "(A) Forward P/E vs peer median; (B) EV/EBITDA vs peer median; "
                    "(C) Sum-of-parts when segments have distinct economics; (D) DCF cross-check "
                    "anchored to FCF and a discount rate read off the FRED rate panel."
                ),
            ),
            ExpansionStep(
                label="Assumptions",
                content=(
                    "Peer set is comparable on demand factor and capital intensity. "
                    "Macro panel reflects the current discount-rate environment."
                ),
                uncertainty_flags=[
                    "Peer comparability degrades when one peer has acquired aggressively",
                ],
            ),
            ExpansionStep(
                label="Edge cases",
                content=(
                    "If macro tightens 50bps in the relevant tenor, peer multiples typically "
                    "compress 10-20%. If the company carries a one-off margin tailwind, the "
                    "forward multiple is overstated."
                ),
            ),
            ExpansionStep(
                label="Cross-domain analogy",
                content=(
                    "Treat valuation like a relative-strength signal: the multiple gap vs peers, "
                    "not the absolute multiple, is the actionable read."
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
        macro = _macro_snapshot(notes)
        rates = macro.get("DGS10", {}).get("value", "n/a")
        rec = (
            f"Anchor valuation in the primary multiple appropriate to the industry, "
            f"cross-check against peer median, and overlay the FRED macro panel "
            f"(10Y={rates}). Surface dispersion of forward consensus, not just the "
            "median, and flag any one-off items that distort the multiple. Land "
            "thesis triggers as concrete, observable events with a date or window."
        )
        steps = [
            CompressionStep(
                label="Integrate",
                content=(
                    "Multiple choice depends on industry; macro context is mandatory; "
                    "consensus dispersion is the cleanest signal of conviction."
                ),
            ),
            CompressionStep(
                label="Commit",
                content=(
                    "Primary multiple + peer median + macro overlay + dispersion. "
                    "Three thesis triggers, each observable with a date or trigger event."
                ),
            ),
        ]
        outputs = {
            "peer_view": "peer set sized to demand factor; international peers in USD",
            "valuation_view": "primary multiple + peer median + macro overlay",
            "thesis_triggers": "three observable triggers with dates or trigger events",
        }
        return (
            rec,
            steps,
            ConfidenceLevel.HIGH,
            (
                "Would change if peer set is rebuilt around a different demand factor, "
                "or if the macro panel shifts the discount-rate read materially."
            ),
            outputs,
        )
