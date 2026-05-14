"""Consensus Hardening Protocol primitives.

CHP is the decision-governance layer for high-stakes, cross-model finance
workflows. This package provides the canonical data model, gate logic,
payload-integrity helpers, and an in-memory registry that higher-level finance
workflows can build on.
"""

from cme.chp.models import (
    ContextCheck,
    DecisionCase,
    Dossier,
    FoundationAttack,
    FoundationDisclosure,
    ModelParityCheck,
    ModelTier,
    Phase,
    RoundRecord,
    SessionStatus,
    ThirdPartyValidation,
    ValidationResult,
    Verdict,
)
from cme.chp.parity import assess_model_parity
from cme.chp.payloads import (
    PayloadEnvelope,
    build_payload_envelope,
    extract_payload_id,
    payload_echo_confirmed,
    validate_payload_envelope,
)
from cme.chp.gates import evaluate_phase_gate, evaluate_r0_gate
from cme.chp.orchestrator import CHPOrchestrator, CHPReport
from cme.chp.registry import DecisionRegistry
from cme.chp.validators import apply_third_party_validation

__all__ = [
    "ContextCheck",
    "DecisionCase",
    "DecisionRegistry",
    "Dossier",
    "FoundationAttack",
    "FoundationDisclosure",
    "CHPOrchestrator",
    "CHPReport",
    "ModelParityCheck",
    "ModelTier",
    "Phase",
    "PayloadEnvelope",
    "RoundRecord",
    "SessionStatus",
    "ThirdPartyValidation",
    "ValidationResult",
    "Verdict",
    "apply_third_party_validation",
    "assess_model_parity",
    "build_payload_envelope",
    "evaluate_phase_gate",
    "evaluate_r0_gate",
    "extract_payload_id",
    "payload_echo_confirmed",
    "validate_payload_envelope",
]
