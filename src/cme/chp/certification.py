"""Proof-carrying gates for research claims.

Attribution: adapted from Georgios Fradelos, PhD, "Certifiable AI Safety
Theory (CAST): Convex-Analytic, Measure-Theoretic, and Proof-Carrying
Deployment Gates for Tool-Using LLM Systems", Geneva, February 12, 2026,
local source AI Governance papers/ssrn-6307158.pdf; and "A Mathematical
Solution to the AI Alignment Problem", Geneva, January 14, 2026, local source
AI Governance papers/ssrn-6307060.pdf.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Protocol


class CertifiableClaim(Protocol):
    agent: str
    claim: str
    grounding_source: str
    grounding_confidence: str
    risk_flag: str


@dataclass(frozen=True)
class ProofCertificate:
    claim_hash: str
    agent: str
    status: str
    reason: str
    allocated_risk_budget: float
    fallback: str = ""
    attribution: str = (
        "Pattern adapted from Georgios Fradelos, PhD, CAST, Geneva, February 12, "
        "2026, local source AI Governance papers/ssrn-6307158.pdf."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        fallback = f" fallback={self.fallback}" if self.fallback else ""
        return (
            f"- {self.status} claim={self.claim_hash[:12]} agent={self.agent} "
            f"risk_budget={self.allocated_risk_budget:.6f}{fallback} :: {self.reason}"
        )


def build_proof_certificates(
    claims: Iterable[CertifiableClaim],
    *,
    global_risk_budget: float = 0.05,
) -> list[ProofCertificate]:
    items = list(claims)
    per_claim_budget = global_risk_budget / max(len(items), 1)
    return [
        certify_claim(claim, allocated_risk_budget=per_claim_budget)
        for claim in items
    ]


def certify_claim(
    claim: CertifiableClaim,
    *,
    allocated_risk_budget: float,
) -> ProofCertificate:
    claim_hash = _hash_claim(claim)
    source = (claim.grounding_source or "").lower()
    confidence = (claim.grounding_confidence or "").lower()
    if source in {"inferred", "pattern-match", ""}:
        return ProofCertificate(
            claim_hash=claim_hash,
            agent=claim.agent,
            status="REJECT",
            reason=f"grounding source '{claim.grounding_source}' is not release-grade",
            allocated_risk_budget=allocated_risk_budget,
            fallback="mark_unknown_or_remove_claim",
        )
    if confidence == "low":
        return ProofCertificate(
            claim_hash=claim_hash,
            agent=claim.agent,
            status="REJECT",
            reason="low confidence claim",
            allocated_risk_budget=allocated_risk_budget,
            fallback="request_more_evidence",
        )
    if claim.risk_flag:
        return ProofCertificate(
            claim_hash=claim_hash,
            agent=claim.agent,
            status="REJECT",
            reason=f"risk flag present: {claim.risk_flag}",
            allocated_risk_budget=allocated_risk_budget,
            fallback="quarantine_for_human_review",
        )
    return ProofCertificate(
        claim_hash=claim_hash,
        agent=claim.agent,
        status="PASS",
        reason="grounded claim cleared release gate",
        allocated_risk_budget=allocated_risk_budget,
    )


def _hash_claim(claim: CertifiableClaim) -> str:
    payload = {
        "agent": claim.agent,
        "claim": claim.claim,
        "source": claim.grounding_source,
        "confidence": claim.grounding_confidence,
        "risk_flag": claim.risk_flag,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
