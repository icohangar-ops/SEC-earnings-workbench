"""End-to-end skeleton tests for CHP capital allocation sessions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cme.chp import CHPOrchestrator  # noqa: E402
from cme.finance import CapitalAllocationInput, build_capital_allocation_case  # noqa: E402


def test_capital_allocation_builder_and_orchestrator():
    case, disclosure, attack = build_capital_allocation_case(
        CapitalAllocationInput(
            title="Fund enterprise workflow",
            company="Acme",
            proposal_summary="Should we fund a new enterprise workflow team this quarter?",
            investment_amount_usd=2_500_000,
            expected_payback_months=14,
            minimum_runway_months=12,
            current_runway_months=18,
            strategic_priorities=["Expand enterprise ARR", "Preserve capital discipline"],
            key_risks=["Adoption lag", "Implementation complexity"],
            expected_upside=["Higher ACV", "Lower churn in strategic accounts"],
        )
    )
    orch = CHPOrchestrator()
    report = orch.run_initial_session(
        case=case,
        foundation_disclosure=disclosure,
        foundation_attack=attack,
    )

    assert report.case.decision_id.startswith("cap-")
    assert report.case.context_check is not None
    assert report.case.model_parity is not None
    assert report.case.foundation_score == attack.foundation_score
    assert "BEGIN_PAYLOAD" in report.initial_packet
    assert report.case.status.value in {"EXPLORING", "REFRAME_REQUIRED", "HALT"}
