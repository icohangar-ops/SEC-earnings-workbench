"""Audit trail fusing Mesh reasoning, shared context, CHP foundation state, and
the external grounding sources (AlphaVantage filings, FRED macro panel).

Each ``AuditEntry`` ties one fact in the final research artifact back to:
    - the agent that produced it,
    - the expansion step in that agent's reasoning,
    - the grounding source/confidence,
    - the CHP foundation findings that hardened or weakened it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from cme.agent import TurnResult
from cme.chp.certification import ProofCertificate, build_proof_certificates
from cme.chp.models import DecisionCase, FoundationAttack, FoundationDisclosure
from cme.protocol import ExpansionStep, GroundingCheck
from cme.research.data import FilingRef


@dataclass
class AuditEntry:
    agent: str
    claim: str
    expansion_label: str
    expansion_excerpt: str
    grounding_source: str
    grounding_confidence: str
    risk_flag: str = ""

    def render(self) -> str:
        risk = f" [RISK: {self.risk_flag}]" if self.risk_flag else ""
        return (
            f"- **{self.agent}** | {self.expansion_label} | source={self.grounding_source} "
            f"| conf={self.grounding_confidence}{risk}\n"
            f"  - claim: {self.claim}\n"
            f"  - excerpt: {self.expansion_excerpt}"
        )


@dataclass
class AuditTrail:
    entries: List[AuditEntry] = field(default_factory=list)
    foundation_findings: List[str] = field(default_factory=list)
    structural_vulnerabilities: List[str] = field(default_factory=list)
    failure_modes: List[str] = field(default_factory=list)
    context_writes: List[str] = field(default_factory=list)
    external_sources: List[str] = field(default_factory=list)
    proof_certificates: List[ProofCertificate] = field(default_factory=list)

    def render(self) -> str:
        lines = ["## Audit Trail", ""]
        if self.external_sources:
            lines.append("### External Grounding Sources")
            for src in self.external_sources:
                lines.append(f"- {src}")
            lines.append("")
        if self.foundation_findings:
            lines.append("### CHP Foundation Findings")
            for f in self.foundation_findings:
                lines.append(f"- {f}")
            lines.append("")
        if self.structural_vulnerabilities:
            lines.append("### Structural Vulnerabilities")
            for v in self.structural_vulnerabilities:
                lines.append(f"- {v}")
            lines.append("")
        if self.failure_modes:
            lines.append("### Detected Failure Modes")
            for m in self.failure_modes:
                lines.append(f"- {m}")
            lines.append("")
        if self.proof_certificates:
            lines.append("### Proof-Carrying Claim Gates")
            for cert in self.proof_certificates:
                lines.append(cert.render())
            lines.append("")
        lines.append("### Per-Claim Provenance")
        for e in self.entries:
            lines.append(e.render())
        if self.context_writes:
            lines.append("")
            lines.append("### Shared-Context Writes")
            for w in self.context_writes:
                lines.append(f"- {w}")
        return "\n".join(lines)


def build_audit_trail(
    *,
    turns: Iterable[TurnResult],
    case: DecisionCase,
    disclosure: FoundationDisclosure,
    attack: FoundationAttack,
    overview: Optional[Dict[str, Any]] = None,
    macro: Optional[Dict[str, Dict[str, Any]]] = None,
    edgar_filings: Optional[List[FilingRef]] = None,
    extra_sources: Optional[List[str]] = None,
) -> AuditTrail:
    entries: List[AuditEntry] = []
    failure_modes: List[str] = []
    context_writes: List[str] = []

    for turn in turns:
        trace = turn.trace
        for step in trace.expansion:
            grounding = _grounding_for_step(step, trace.grounding)
            entries.append(
                AuditEntry(
                    agent=turn.agent,
                    claim=step.label,
                    expansion_label=step.label,
                    expansion_excerpt=step.content[:160],
                    grounding_source=grounding.source if grounding else "inferred",
                    grounding_confidence=(
                        grounding.confidence.value if grounding else trace.confidence.value
                    ),
                    risk_flag=grounding.risk_flag if grounding and grounding.risk_flag else "",
                )
            )
        final_grounding = trace.grounding[-1] if trace.grounding else None
        entries.append(
            AuditEntry(
                agent=turn.agent,
                claim="recommendation",
                expansion_label="Recommendation",
                expansion_excerpt=trace.recommendation[:160],
                grounding_source=(
                    final_grounding.source if final_grounding else "inferred"
                ),
                grounding_confidence=trace.confidence.value,
                risk_flag=(
                    final_grounding.risk_flag
                    if final_grounding and final_grounding.risk_flag
                    else ""
                ),
            )
        )
        for note in turn.handoff_notes:
            if note.startswith("warning:"):
                failure_modes.append(f"{turn.agent}: {note[len('warning:'):]}")
        context_writes.append(
            f"{turn.agent} wrote recommendation to shared context (importance derived from "
            f"confidence={trace.confidence.value})"
        )

    foundation_findings = [
        f"R0 dossier scope populated: {bool(case.dossier and case.dossier.scope)}",
        f"Foundation score: {attack.foundation_score} (>=70 hardens)",
        f"Disclosed weak assumptions: {len(disclosure.weakest_assumptions)}",
        f"Attack vectors: {len(attack.assumption_attacks)}",
        f"Key vulnerability: {disclosure.key_vulnerability}",
        f"Attack summary: {attack.attack_summary}",
    ]
    if edgar_filings:
        # Pull a primary anchor citation into the foundation findings — every
        # claim in the artifact can then be traced back to at least one
        # primary filing.
        anchor = next(
            (f for f in edgar_filings if f.form in {"10-K", "10-Q"}),
            edgar_filings[0],
        )
        foundation_findings.append(
            f"Primary filing anchor: {anchor.citation()} ({anchor.primary_doc_url})"
        )

    external_sources: List[str] = []
    if overview:
        latest = overview.get("LatestQuarter", "n/a")
        external_sources.append(
            f"AlphaVantage OVERVIEW for {overview.get('Symbol', '?')} (latest quarter {latest})"
        )
    if macro:
        ids = ", ".join(sorted(macro.keys()))
        external_sources.append(f"FRED macro panel ({ids})")
    if edgar_filings:
        # Summarize counts per form so the audit-trail block is scannable.
        by_form: Dict[str, int] = {}
        for f in edgar_filings:
            by_form[f.form] = by_form.get(f.form, 0) + 1
        breakdown = ", ".join(f"{form}×{n}" for form, n in sorted(by_form.items()))
        latest = max(edgar_filings, key=lambda f: f.filing_date)
        external_sources.append(
            f"SEC EDGAR — {len(edgar_filings)} filings ingested ({breakdown}); "
            f"most recent: {latest.citation()}"
        )
    elif edgar_filings is not None:
        external_sources.append("SEC EDGAR — no filings ingested (graceful degradation).")
    if extra_sources:
        external_sources.extend(extra_sources)

    proof_certificates = build_proof_certificates(entries)

    return AuditTrail(
        entries=entries,
        foundation_findings=foundation_findings,
        structural_vulnerabilities=list(case.dossier.structural_vulnerabilities)
        if case.dossier
        else [],
        failure_modes=failure_modes,
        context_writes=context_writes,
        external_sources=external_sources,
        proof_certificates=proof_certificates,
    )


def _grounding_for_step(
    step: ExpansionStep, grounding: List[GroundingCheck]
) -> Optional[GroundingCheck]:
    needle = step.content[:60]
    for g in grounding:
        if g.claim.startswith(needle[:40]):
            return g
    return None
