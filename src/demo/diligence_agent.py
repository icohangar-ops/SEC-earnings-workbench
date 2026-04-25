"""DiligenceAgent — produces SEC-flavored red-flag scan, governance read, risks.

Consumes ``business_model`` from FundamentalsAgent (set on shared context) and
runs the prompt-spec'd diligence sweep: revenue-recognition changes, earnings
quality (GAAP vs non-GAAP), insider patterns, board independence, material
weaknesses, related-party transactions, going-concern language.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from cme.agent import AgentCapability, MeshAgent
from cme.playbook import Bullet, Playbook
from cme.protocol import CompressionStep, ConfidenceLevel, ExpansionStep


def _seed_playbook() -> Playbook:
    pb = Playbook(name="diligence-playbook")
    starter = [
        (
            "strategies_and_hard_rules",
            "Always sweep the most recent 8-K *after* the most recent 10-Q before relying on quarterly metrics.",
        ),
        (
            "strategies_and_hard_rules",
            "Risk-factor diffs YoY are usually more informative than the list — extract additions and removals.",
        ),
        (
            "verification_checklist",
            "Confirm: auditor changes, going-concern language, material-weakness disclosures, related-party notes.",
        ),
        (
            "verification_checklist",
            "Quantify: SBC % of revenue, GAAP-vs-non-GAAP gap, FCF-vs-NI divergence, working-capital anomalies.",
        ),
        (
            "troubleshooting_and_pitfalls",
            "10b5-1 plan filings can make insider selling look mechanical, but the plan adoption date itself signals a view.",
        ),
        (
            "troubleshooting_and_pitfalls",
            "Off-balance-sheet exposure (op leases, purchase commitments, guarantees) is the most common 'invisible' risk in growth co's.",
        ),
    ]
    for section, content in starter:
        new_id = pb._next_id(section)
        pb.bullets[new_id] = Bullet(id=new_id, section=section, content=content, helpful=2)
    return pb


class DiligenceAgent(MeshAgent):
    def __init__(self) -> None:
        super().__init__(
            name="diligence",
            capability=AgentCapability(
                domain="diligence",
                produces=["red_flag_scan", "governance_read", "risk_register"],
                consumes=["business_model"],
            ),
            playbook=_seed_playbook(),
        )

    def expand(self, problem: str, context: Dict[str, Any]) -> List[ExpansionStep]:
        return [
            ExpansionStep(
                label="Reframe",
                content=(
                    f"Reframe '{problem[:80]}' as: where would an adversarial reader find a "
                    "fact pattern that contradicts the consensus narrative — in filings, "
                    "governance, or earnings quality?"
                ),
            ),
            ExpansionStep(
                label="Constraints",
                content=(
                    "Hard: every flag must cite a filing type + filing date. "
                    "Soft: prefer YoY risk-factor diffs over snapshot lists."
                ),
            ),
            ExpansionStep(
                label="Alternatives",
                content=(
                    "(A) Earnings-quality first: GAAP vs non-GAAP gap, SBC %, FCF vs NI. "
                    "(B) Governance first: 14A comp design, board independence, activist stakes. "
                    "(C) Disclosure first: 8-K sweep since last 10-Q, going-concern language, auditor changes. "
                    "(D) Off-balance-sheet first: op leases, guarantees, purchase commitments."
                ),
            ),
            ExpansionStep(
                label="Assumptions",
                content=(
                    "Filings reviewed are the latest available. The non-GAAP-to-GAAP "
                    "reconciliation in the filing is mathematically complete."
                ),
                uncertainty_flags=[
                    "Recent 8-K may already shift the read — sweep before locking",
                ],
            ),
            ExpansionStep(
                label="Edge cases",
                content=(
                    "If a material-weakness disclosure is present, every metric is in question. "
                    "If a related-party transaction concentrates revenue or expense, ratios are "
                    "structurally distorted."
                ),
            ),
            ExpansionStep(
                label="Cross-domain analogy",
                content=(
                    "Treat the scan like a forensic-accounting checklist: walk earnings quality, "
                    "off-balance-sheet, governance, and disclosure — flag every divergence."
                ),
            ),
        ]

    def compress(
        self,
        problem: str,
        expansion: List[ExpansionStep],
        context: Dict[str, Any],
    ) -> Tuple[str, List[CompressionStep], ConfidenceLevel, str, Dict[str, Any]]:
        rec = (
            "Run all four sweeps in order — earnings quality, governance, disclosure, "
            "off-balance-sheet — but lead the memo with whichever produced the largest "
            "magnitude finding. Cite filing type + filing date on every flag. Quantify "
            "GAAP vs non-GAAP gap and SBC % of revenue regardless of whether they look benign."
        )
        steps = [
            CompressionStep(
                label="Integrate",
                content=(
                    "All four lenses are complementary; ordering is a presentation choice, "
                    "not a tradeoff."
                ),
            ),
            CompressionStep(
                label="Commit",
                content=(
                    "Lead with the largest-magnitude finding; require a filing-date citation on "
                    "every flag; surface YoY risk-factor diff as a distinct subsection."
                ),
            ),
        ]
        outputs = {
            "red_flag_scan": "earnings-quality + governance + disclosure + OBS, all cited",
            "governance_read": "14A-anchored: comp alignment, independence, activist stakes",
            "risk_register": "ranked by probability x impact, each with a filing citation",
        }
        return (
            rec,
            steps,
            ConfidenceLevel.HIGH,
            (
                "Would change if a recent 8-K materially shifts the financial-health read, or "
                "if the auditor / going-concern language has changed since the cited filing."
            ),
            outputs,
        )
