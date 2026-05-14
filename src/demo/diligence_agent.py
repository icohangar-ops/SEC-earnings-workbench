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
        # Pull EDGAR filings out of shared context so we can name real dates.
        filings: List[Dict[str, Any]] = []
        sweep: List[Dict[str, Any]] = []
        for ent in context.get("entities", []) or []:
            if ent.get("type") == "sec_filing":
                filings.append(ent.get("attributes", {}) or {})
            elif ent.get("type") == "sec_filing_8k_sweep":
                sweep.append(ent.get("attributes", {}) or {})
        latest_10k = next((f for f in filings if (f.get("form") or "").upper() == "10-K"), None)
        latest_10q = next((f for f in filings if (f.get("form") or "").upper() == "10-Q"), None)
        anchor_lines: List[str] = []
        if latest_10k:
            anchor_lines.append(
                f"latest 10-K filed {latest_10k.get('filing_date')} (acc {latest_10k.get('accession_no')})"
            )
        if latest_10q:
            anchor_lines.append(
                f"latest 10-Q filed {latest_10q.get('filing_date')} (acc {latest_10q.get('accession_no')})"
            )
        anchor_blurb = (
            "Anchor on " + "; ".join(anchor_lines) if anchor_lines else "Filings not yet pulled — degrade gracefully."
        )
        sweep_dates = ", ".join(s.get("filing_date", "") for s in sweep[:4])
        sweep_blurb = (
            f"8-K sweep since latest periodic returned {len(sweep)} filings ({sweep_dates}) — "
            "every quantitative claim must be qualified against these material-event disclosures."
            if sweep
            else (
                "8-K sweep is empty (or filings not yet pulled) — periodic-filing read is the "
                "current source of truth."
            )
        )

        return [
            ExpansionStep(
                label="Reframe",
                content=(
                    f"Reframe '{problem[:80]}' as: where would an adversarial reader find a "
                    "fact pattern that contradicts the consensus narrative — in filings, "
                    f"governance, or earnings quality? {anchor_blurb}"
                ),
            ),
            ExpansionStep(
                label="Constraints",
                content=(
                    "Hard: every flag must cite a filing type + filing date. "
                    "Soft: prefer YoY risk-factor diffs over snapshot lists. "
                    f"{sweep_blurb}"
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
                    f"Recent 8-K sweep flagged {len(sweep)} filings — may shift the read"
                    if sweep
                    else "Recent 8-K may already shift the read — sweep before locking",
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
