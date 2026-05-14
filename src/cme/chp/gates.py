"""Session gate logic for CHP."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from cme.chp.models import SessionStatus, Verdict


@dataclass(frozen=True)
class GateEvaluation:
    results: Dict[str, str]
    verdict: Verdict


def evaluate_r0_gate(*, solvable: bool, scoped: bool, valid: bool, worth_it: bool) -> GateEvaluation:
    results = {
        "Solvable": "PASS" if solvable else "FATAL",
        "Scoped": "PASS" if scoped else "FATAL",
        "Valid": "PASS" if valid else "FATAL",
        "Worth_it": "PASS" if worth_it else "FATAL",
    }
    verdict = Verdict.PASS if all(v == "PASS" for v in results.values()) else Verdict.HALT
    return GateEvaluation(results=results, verdict=verdict)


def evaluate_phase_gate(round_number: int, phase_one_status: SessionStatus) -> Verdict:
    if round_number <= 2:
        return Verdict.PASS
    if phase_one_status in (SessionStatus.PROVISIONAL_LOCK, SessionStatus.LOCKED, SessionStatus.CONVERGED):
        return Verdict.PASS
    return Verdict.PHASE_GATE_FAIL
