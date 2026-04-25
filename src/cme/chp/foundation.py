"""Foundation-stage helpers for CHP."""
from __future__ import annotations

from cme.chp.models import FoundationAttack, FoundationDisclosure, Verdict


def foundation_verdict(attack: FoundationAttack) -> Verdict:
    return Verdict.PASS if attack.foundation_score >= 70 else Verdict.REFRAME


def validate_foundation_pair(
    disclosure: FoundationDisclosure, attack: FoundationAttack
) -> list[str]:
    errors = disclosure.validate() + attack.validate()
    if disclosure.weakest_assumptions and attack.assumption_attacks:
        if len(attack.assumption_attacks) < min(3, len(disclosure.weakest_assumptions)):
            errors.append("attack must address each disclosed weak assumption")
    return errors
