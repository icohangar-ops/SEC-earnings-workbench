"""Persistence-oriented tests for CHP registry-backed flows."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cme.chp import (  # noqa: E402
    CHPOrchestrator,
    DecisionRegistry,
    Phase,
    ThirdPartyValidation,
    ValidationResult,
)
from cme.finance import CapitalAllocationInput, build_capital_allocation_case  # noqa: E402


def test_registry_persists_received_packet_and_validation(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry = DecisionRegistry()
    orch = CHPOrchestrator(registry=registry)
    case, disclosure, attack = build_capital_allocation_case(
        CapitalAllocationInput(
            title="Fund enterprise workflow",
            company="Acme",
            proposal_summary="Should we fund a new enterprise workflow team this quarter?",
            investment_amount_usd=2_500_000,
            expected_payback_months=14,
            minimum_runway_months=12,
            current_runway_months=18,
            strategic_priorities=["Expand enterprise ARR"],
            key_risks=["Adoption lag"],
            expected_upside=["Higher ACV"],
        )
    )
    report = orch.run_initial_session(case=case, foundation_disclosure=disclosure, foundation_attack=attack)
    registry.save(registry_path)

    loaded = DecisionRegistry.load(registry_path)
    orch2 = CHPOrchestrator(registry=loaded)
    packet = "BEGIN_PAYLOAD [RX] [ABC123]\npartner body\nEND_PAYLOAD [RX] [ABC123]"
    updated = orch2.receive_partner_packet(
        decision_id=report.case.decision_id,
        partner_packet=packet,
        phase=Phase.SPEC,
        round_number=1,
        payload_echo="[RX] [ABC123] CONFIRMED",
        snapshot_status="PROVISIONAL_LOCK",
    )
    assert updated.current_round == 1
    assert updated.rounds[-1].payload_id == "ABC123"

    orch2.apply_validation(
        updated.decision_id,
        ThirdPartyValidation(
            validator="fresh_instance",
            item="Investment spec v1",
            challenge="downside stress",
            result=ValidationResult.CONFIRM,
            rationale="still coherent",
        ),
    )
    loaded.save(registry_path)

    reloaded = DecisionRegistry.load(registry_path)
    final = reloaded.get(updated.decision_id)
    assert final is not None
    assert final.status.value == "LOCKED"
    assert "Investment spec v1" in final.locked_decisions
