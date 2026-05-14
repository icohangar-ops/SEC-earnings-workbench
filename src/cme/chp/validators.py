"""Third-party validation helpers for CHP lock progression."""
from __future__ import annotations

from cme.chp.models import DecisionCase, SessionStatus, ThirdPartyValidation, ValidationResult


def apply_third_party_validation(case: DecisionCase, validation: ThirdPartyValidation) -> SessionStatus:
    case.third_party_log.append(validation)
    if validation.result == ValidationResult.CONFIRM:
        case.status = SessionStatus.LOCKED
        if validation.item not in case.locked_decisions:
            case.locked_decisions.append(validation.item)
    else:
        case.status = SessionStatus.EXPLORING
        case.flip_criteria.append(f"Validation rejected: {validation.item}")
    return case.status
