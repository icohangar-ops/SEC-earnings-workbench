"""Basic tests for the Consensus Hardening Protocol scaffold."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cme.chp import (  # noqa: E402
    ContextCheck,
    DecisionCase,
    DecisionRegistry,
    Dossier,
    Phase,
    RoundRecord,
    SessionStatus,
    ThirdPartyValidation,
    ValidationResult,
    assess_model_parity,
    apply_third_party_validation,
    build_payload_envelope,
    evaluate_phase_gate,
    evaluate_r0_gate,
    payload_echo_confirmed,
    validate_payload_envelope,
)


def test_payload_envelope_roundtrip():
    envelope = build_payload_envelope("hello world", route="RX", payload_id="ABC123")
    rendered = envelope.render()
    assert validate_payload_envelope(rendered)
    assert payload_echo_confirmed("RX", "ABC123", "[RX] [ABC123] CONFIRMED")


def test_model_parity_detects_large_gap():
    parity = assess_model_parity("gpt-5.4", "haiku")
    assert parity.delta == "SIGNIFICANT"


def test_r0_gate_halts_on_fatal():
    gate = evaluate_r0_gate(solvable=True, scoped=False, valid=True, worth_it=True)
    assert gate.verdict.value == "HALT"
    assert gate.results["Scoped"] == "FATAL"


def test_phase_gate_fails_after_round_two_without_lock():
    verdict = evaluate_phase_gate(3, SessionStatus.EXPLORING)
    assert verdict.value == "PHASE_GATE_FAIL"


def test_registry_and_validation_promote_lock():
    case = DecisionCase(
        decision_id="dec-1",
        title="Fund enterprise tier",
        domain="capital_allocation",
        created_at="2026-04-25T10:00:00Z",
        owner="cfo",
        status=SessionStatus.PROVISIONAL_LOCK,
        dossier=Dossier(core_problem="Should we fund the tier?", goal_state=["grow"], current_state=["cash"], constraints=["runway"], scope=["decision"]),
        context_check=ContextCheck(memory_tools="AVAILABLE"),
    )
    case.add_round(RoundRecord(decision_id="dec-1", phase=Phase.SPEC, round_number=2, payload_id="ABC123"))
    registry = DecisionRegistry()
    registry.add(case)

    status = apply_third_party_validation(
        case,
        ThirdPartyValidation(
            validator="fresh_instance",
            item="Investment spec v1",
            challenge="downside stress",
            result=ValidationResult.CONFIRM,
            rationale="holds up under challenge",
        ),
    )

    assert status == SessionStatus.LOCKED
    assert registry.get("dec-1") is case
    assert "Investment spec v1" in case.locked_decisions
