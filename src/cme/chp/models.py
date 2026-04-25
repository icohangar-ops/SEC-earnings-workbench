"""Canonical data model for Consensus Hardening Protocol."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Phase(int, Enum):
    FOUNDATION = 0
    SPEC = 1
    IMPLEMENTATION = 2


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    HALT = "HALT"
    REFRAME = "REFRAME"
    ITERATE = "ITERATE"
    CONVERGED = "CONVERGED"
    PHASE_GATE_FAIL = "PHASE_GATE_FAIL"


class SessionStatus(str, Enum):
    EXPLORING = "EXPLORING"
    PROVISIONAL = "PROVISIONAL"
    PROVISIONAL_LOCK = "PROVISIONAL_LOCK"
    LOCKED = "LOCKED"
    CONVERGED = "CONVERGED"
    UNRESOLVED = "UNRESOLVED"
    REFRAME_REQUIRED = "REFRAME_REQUIRED"
    HALT = "HALT"


class ValidationResult(str, Enum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"


class ModelTier(str, Enum):
    SMALL = "small"
    MID = "mid"
    HIGH = "high"
    FRONTIER = "frontier"
    UNKNOWN = "unknown"


@dataclass
class ContextCheck:
    memory_tools: str = "UNAVAILABLE"
    prior_sessions_count: int = 0
    prior_lock_versions: List[str] = field(default_factory=list)
    legacy_warning: bool = False
    related_locks: List[str] = field(default_factory=list)
    assessment: str = "SPARSE"
    action: str = "PROCEED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextCheck":
        return cls(**data)


@dataclass
class ModelParityCheck:
    origin: str
    partner: str
    delta: str
    advisory: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelParityCheck":
        return cls(**data)


@dataclass
class Dossier:
    core_problem: str
    goal_state: List[str] = field(default_factory=list)
    current_state: List[str] = field(default_factory=list)
    prior_decisions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    scope: List[str] = field(default_factory=list)
    origin_direction: List[str] = field(default_factory=list)
    prior_round_summary: List[str] = field(default_factory=list)
    unknowns_carried: List[str] = field(default_factory=list)
    foundation_score: Optional[int] = None
    structural_vulnerabilities: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.core_problem or self.core_problem == "UNKNOWN":
            errors.append("core_problem is required")
        populated = sum(
            1
            for field_value in (
                self.goal_state,
                self.current_state,
                self.constraints,
                self.scope,
            )
            if field_value
        )
        if populated < 3:
            errors.append("dossier must include at least three populated context sections")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dossier":
        return cls(**data)


@dataclass
class FoundationDisclosure:
    weakest_assumptions: List[str] = field(default_factory=list)
    invalidation_conditions: List[str] = field(default_factory=list)
    key_vulnerability: str = ""

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.weakest_assumptions or len(self.weakest_assumptions) > 3:
            errors.append("weakest_assumptions must include 1-3 items")
        if not self.invalidation_conditions or len(self.invalidation_conditions) > 2:
            errors.append("invalidation_conditions must include 1-2 items")
        if not self.key_vulnerability:
            errors.append("key_vulnerability is required")
        return errors


@dataclass
class FoundationAttack:
    assumption_attacks: List[str] = field(default_factory=list)
    invalidation_exploitation: List[str] = field(default_factory=list)
    vulnerability_strike: str = ""
    foundation_score: int = 0
    attack_summary: str = ""

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.assumption_attacks:
            errors.append("assumption_attacks is required")
        if not self.vulnerability_strike:
            errors.append("vulnerability_strike is required")
        if not 0 <= self.foundation_score <= 100:
            errors.append("foundation_score must be between 0 and 100")
        return errors


@dataclass
class ThirdPartyValidation:
    validator: str
    item: str
    challenge: str
    result: ValidationResult
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["result"] = self.result.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThirdPartyValidation":
        return cls(
            validator=data["validator"],
            item=data["item"],
            challenge=data["challenge"],
            result=ValidationResult(data["result"]),
            rationale=data["rationale"],
        )


@dataclass
class RoundRecord:
    decision_id: str
    phase: Phase
    round_number: int
    payload_id: str
    origin_packet: str = ""
    partner_packet: str = ""
    payload_echo_confirmed: bool = False
    state_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["phase"] = self.phase.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoundRecord":
        return cls(
            decision_id=data["decision_id"],
            phase=Phase(data["phase"]),
            round_number=data["round_number"],
            payload_id=data["payload_id"],
            origin_packet=data.get("origin_packet", ""),
            partner_packet=data.get("partner_packet", ""),
            payload_echo_confirmed=data.get("payload_echo_confirmed", False),
            state_snapshot=data.get("state_snapshot", {}),
        )


@dataclass
class DecisionCase:
    decision_id: str
    title: str
    domain: str
    created_at: str
    owner: str
    status: SessionStatus = SessionStatus.EXPLORING
    high_stakes: bool = False
    current_phase: Phase = Phase.FOUNDATION
    current_round: int = 0
    origin_system: str = "Claude"
    origin_model: str = "UNKNOWN"
    partner_system: str = "UNKNOWN"
    partner_model: str = "UNKNOWN"
    context_check: Optional[ContextCheck] = None
    model_parity: Optional[ModelParityCheck] = None
    dossier: Optional[Dossier] = None
    foundation_score: Optional[int] = None
    locked_decisions: List[str] = field(default_factory=list)
    structural_vulnerabilities: List[str] = field(default_factory=list)
    blind_spots: List[str] = field(default_factory=list)
    flip_criteria: List[str] = field(default_factory=list)
    third_party_log: List[ThirdPartyValidation] = field(default_factory=list)
    rounds: List[RoundRecord] = field(default_factory=list)

    def add_round(self, record: RoundRecord) -> None:
        self.rounds.append(record)
        self.current_phase = record.phase
        self.current_round = record.round_number

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "title": self.title,
            "domain": self.domain,
            "created_at": self.created_at,
            "owner": self.owner,
            "status": self.status.value,
            "high_stakes": self.high_stakes,
            "current_phase": self.current_phase.value,
            "current_round": self.current_round,
            "origin_system": self.origin_system,
            "origin_model": self.origin_model,
            "partner_system": self.partner_system,
            "partner_model": self.partner_model,
            "context_check": self.context_check.to_dict() if self.context_check else None,
            "model_parity": self.model_parity.to_dict() if self.model_parity else None,
            "dossier": self.dossier.to_dict() if self.dossier else None,
            "foundation_score": self.foundation_score,
            "locked_decisions": self.locked_decisions,
            "structural_vulnerabilities": self.structural_vulnerabilities,
            "blind_spots": self.blind_spots,
            "flip_criteria": self.flip_criteria,
            "third_party_log": [item.to_dict() for item in self.third_party_log],
            "rounds": [record.to_dict() for record in self.rounds],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionCase":
        case = cls(
            decision_id=data["decision_id"],
            title=data["title"],
            domain=data["domain"],
            created_at=data["created_at"],
            owner=data["owner"],
            status=SessionStatus(data.get("status", SessionStatus.EXPLORING.value)),
            high_stakes=data.get("high_stakes", False),
            current_phase=Phase(data.get("current_phase", Phase.FOUNDATION.value)),
            current_round=data.get("current_round", 0),
            origin_system=data.get("origin_system", "Claude"),
            origin_model=data.get("origin_model", "UNKNOWN"),
            partner_system=data.get("partner_system", "UNKNOWN"),
            partner_model=data.get("partner_model", "UNKNOWN"),
            context_check=ContextCheck.from_dict(data["context_check"]) if data.get("context_check") else None,
            model_parity=ModelParityCheck.from_dict(data["model_parity"]) if data.get("model_parity") else None,
            dossier=Dossier.from_dict(data["dossier"]) if data.get("dossier") else None,
            foundation_score=data.get("foundation_score"),
            locked_decisions=list(data.get("locked_decisions", [])),
            structural_vulnerabilities=list(data.get("structural_vulnerabilities", [])),
            blind_spots=list(data.get("blind_spots", [])),
            flip_criteria=list(data.get("flip_criteria", [])),
            third_party_log=[ThirdPartyValidation.from_dict(item) for item in data.get("third_party_log", [])],
            rounds=[RoundRecord.from_dict(item) for item in data.get("rounds", [])],
        )
        return case
