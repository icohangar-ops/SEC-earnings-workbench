"""High-level CHP orchestration for finance decision sessions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cme.chp.foundation import foundation_verdict, validate_foundation_pair
from cme.chp.gates import evaluate_r0_gate
from cme.chp.models import (
    ContextCheck,
    DecisionCase,
    FoundationAttack,
    FoundationDisclosure,
    Phase,
    RoundRecord,
    SessionStatus,
    Verdict,
)
from cme.chp.parity import assess_model_parity
from cme.chp.payloads import build_payload_envelope, extract_payload_id, validate_payload_envelope
from cme.chp.registry import DecisionRegistry
from cme.chp.validators import apply_third_party_validation
from cme.context import ContextEngine


@dataclass
class CHPReport:
    case: DecisionCase
    foundation_disclosure: FoundationDisclosure
    foundation_attack: FoundationAttack
    r0_verdict: Verdict
    foundation_verdict: Verdict
    initial_packet: str

    def render(self) -> str:
        context_check = self.case.context_check.to_dict() if self.case.context_check else {}
        parity = self.case.model_parity.to_dict() if self.case.model_parity else {}
        lines = [
            "# CHP Session",
            f"Decision: {self.case.title}",
            f"Status: {self.case.status.value}",
            "",
            "## Context Check",
        ]
        for key, value in context_check.items():
            lines.append(f"- {key}: {value}")
        lines.extend(
            [
                "",
                "## Model Parity",
            ]
        )
        for key, value in parity.items():
            if value is not None:
                lines.append(f"- {key}: {value}")
        lines.extend(
            [
                "",
                "## R0 Gate",
                f"- verdict: {self.r0_verdict.value}",
                "",
                "## Foundation",
                f"- weakest_assumptions: {len(self.foundation_disclosure.weakest_assumptions)}",
                f"- foundation_score: {self.foundation_attack.foundation_score}",
                f"- verdict: {self.foundation_verdict.value}",
                "",
                "## Initial Packet",
                self.initial_packet,
            ]
        )
        return "\n".join(lines)


class CHPOrchestrator:
    """Minimal orchestration layer for CHP-backed decision sessions."""

    def __init__(
        self,
        *,
        registry: Optional[DecisionRegistry] = None,
        context: Optional[ContextEngine] = None,
    ) -> None:
        self.registry = registry or DecisionRegistry()
        self.context = context or ContextEngine()

    def run_initial_session(
        self,
        *,
        case: DecisionCase,
        foundation_disclosure: FoundationDisclosure,
        foundation_attack: FoundationAttack,
    ) -> CHPReport:
        case.context_check = self._context_check(case)
        case.model_parity = assess_model_parity(case.origin_model, case.partner_model)

        r0 = evaluate_r0_gate(
            solvable=True,
            scoped=bool(case.dossier and case.dossier.scope),
            valid=bool(case.dossier and case.dossier.current_state),
            worth_it=case.high_stakes or case.domain in {"capital_allocation", "board_decision"},
        )

        foundation_errors = validate_foundation_pair(foundation_disclosure, foundation_attack)
        if foundation_errors:
            raise ValueError("; ".join(foundation_errors))

        f_verdict = foundation_verdict(foundation_attack)
        case.foundation_score = foundation_attack.foundation_score
        if case.dossier:
            case.dossier.foundation_score = foundation_attack.foundation_score
            case.structural_vulnerabilities = list(case.dossier.structural_vulnerabilities)

        if r0.verdict == Verdict.HALT:
            case.status = SessionStatus.HALT
        elif f_verdict == Verdict.REFRAME:
            case.status = SessionStatus.REFRAME_REQUIRED
        else:
            case.status = SessionStatus.EXPLORING

        packet = self._build_initial_packet(case, foundation_disclosure, foundation_attack, r0.verdict, f_verdict)
        self.registry.add(case)
        return CHPReport(
            case=case,
            foundation_disclosure=foundation_disclosure,
            foundation_attack=foundation_attack,
            r0_verdict=r0.verdict,
            foundation_verdict=f_verdict,
            initial_packet=packet,
        )

    def receive_partner_packet(
        self,
        *,
        decision_id: str,
        partner_packet: str,
        phase: Phase,
        round_number: int,
        payload_echo: str = "",
        snapshot_status: str = "EXPLORING",
    ) -> DecisionCase:
        case = self.registry.get(decision_id)
        if not case:
            raise KeyError(f"Unknown decision_id: {decision_id}")
        if not validate_payload_envelope(partner_packet):
            raise ValueError("partner packet failed payload envelope validation")
        payload_id = extract_payload_id(partner_packet)
        if not payload_id:
            raise ValueError("partner packet is missing a payload id")
        record = RoundRecord(
            decision_id=decision_id,
            phase=phase,
            round_number=round_number,
            payload_id=payload_id,
            partner_packet=partner_packet,
            payload_echo_confirmed=bool(payload_echo),
            state_snapshot={
                "status": snapshot_status,
                "payload_echo": payload_echo or "MISSING",
            },
        )
        case.add_round(record)
        case.status = SessionStatus(snapshot_status)
        return case

    def apply_validation(self, decision_id: str, validation) -> DecisionCase:
        case = self.registry.get(decision_id)
        if not case:
            raise KeyError(f"Unknown decision_id: {decision_id}")
        apply_third_party_validation(case, validation)
        return case

    def _context_check(self, case: DecisionCase) -> ContextCheck:
        related = []
        if case.dossier and case.dossier.core_problem:
            related = self.registry.find_related(case.dossier.core_problem)
        exact = [item for item in related if item.title == case.title]
        if exact:
            assessment = "DUPLICATE"
            action = "HALT_DUPLICATE"
        elif related:
            assessment = "RELATED"
            action = "AUTO_POPULATE"
        else:
            assessment = "SPARSE"
            action = "PROCEED"
        prior_versions = ["chp-v1"] if related else []
        return ContextCheck(
            memory_tools="AVAILABLE",
            prior_sessions_count=len(related),
            prior_lock_versions=prior_versions,
            legacy_warning=False,
            related_locks=[item.decision_id for item in related if item.locked_decisions],
            assessment=assessment,
            action=action,
        )

    def _build_initial_packet(
        self,
        case: DecisionCase,
        disclosure: FoundationDisclosure,
        attack: FoundationAttack,
        r0_verdict: Verdict,
        foundation_gate: Verdict,
    ) -> str:
        dossier = case.dossier.to_dict() if case.dossier else {}
        body_lines = [
            f"From: {case.origin_system}",
            f"To: {case.partner_system}",
            "Subject: CHP - Phase 0 Round 0",
            "",
            "CORE_PROBLEM_STATEMENT:",
            dossier.get("core_problem", "UNKNOWN"),
            "",
            "R0_GATE:",
            f"- verdict: {r0_verdict.value}",
            "",
            "FOUNDATION_DISCLOSURE:",
        ]
        for idx, item in enumerate(disclosure.weakest_assumptions, 1):
            body_lines.append(f"{idx}. {item}")
        body_lines.append("INVALIDATION_CONDITIONS:")
        for idx, item in enumerate(disclosure.invalidation_conditions, 1):
            body_lines.append(f"{idx}. {item}")
        body_lines.append(f"KEY_VULNERABILITY: {disclosure.key_vulnerability}")
        body_lines.extend(
            [
                "",
                "FOUNDATION_ATTACK:",
                f"- score: {attack.foundation_score}",
                f"- verdict: {foundation_gate.value}",
                f"- summary: {attack.attack_summary}",
                "",
                "DOSSIER:",
                str(dossier),
            ]
        )
        envelope = build_payload_envelope("\n".join(body_lines))
        return envelope.render()
