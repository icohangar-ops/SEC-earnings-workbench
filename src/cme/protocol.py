"""Cognitive Mesh Protocol.

Structured expansion/compression reasoning with grounding checks, following the
cognitive-mesh-protocol skill spec. Each agent invocation produces a
``ReasoningTrace`` that captures the breathing cycle, grounding verdicts, and
final recommendation — so downstream agents can audit and refine the reasoning
rather than just consuming the conclusion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


class ProblemType(str, Enum):
    STRATEGIC = "strategic"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    TECHNICAL = "technical"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ExpansionStep:
    label: str
    content: str
    uncertainty_flags: List[str] = field(default_factory=list)


@dataclass
class CompressionStep:
    label: str
    content: str


@dataclass
class GroundingCheck:
    claim: str
    source: str  # "verified", "inferred", "pattern-match"
    confidence: ConfidenceLevel
    risk_flag: Optional[str] = None


@dataclass
class ReasoningTrace:
    problem: str
    problem_type: ProblemType
    classification_rationale: str
    expansion: List[ExpansionStep] = field(default_factory=list)
    compression: List[CompressionStep] = field(default_factory=list)
    grounding: List[GroundingCheck] = field(default_factory=list)
    recommendation: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    what_would_change: str = ""
    cycle_count: int = 1

    def render(self) -> str:
        """Render the trace in the SKILL-defined response format."""
        lines = [
            "## Problem Classification",
            f"{self.problem_type.value.title()} — {self.classification_rationale}",
            "",
            "## Reasoning Process",
        ]
        lines.append(f"### Expansion Cycle (count={self.cycle_count})")
        for i, step in enumerate(self.expansion, 1):
            lines.append(f"{i}. **{step.label}** — {step.content}")
            for flag in step.uncertainty_flags:
                lines.append(f"   - ⚠ {flag}")
        lines.append("")
        lines.append("### Compression Cycle")
        for i, step in enumerate(self.compression, 1):
            lines.append(f"{i}. **{step.label}** — {step.content}")
        lines.append("")
        lines.append("## Grounding Check")
        for g in self.grounding:
            risk = f" [RISK: {g.risk_flag}]" if g.risk_flag else ""
            lines.append(
                f"- {g.claim} :: source={g.source} confidence={g.confidence.value}{risk}"
            )
        lines.append("")
        lines.append("## Final Recommendation")
        lines.append(f"{self.recommendation}")
        lines.append(f"Confidence: **{self.confidence.value}**")
        lines.append("")
        lines.append("## What Would Change This")
        lines.append(self.what_would_change or "—")
        return "\n".join(lines)


# --- Hallucination-risk heuristics ----------------------------------------

_RISK_PATTERNS = (
    "studies show",
    "research indicates",
    "it is well known",
    "industry standard is",
)


def detect_hallucination_risk(text: str) -> Optional[str]:
    lower = text.lower()
    for pat in _RISK_PATTERNS:
        if pat in lower:
            return f"unsourced authority phrase: '{pat}'"
    # Specific numeric confidence without anchor
    import re

    if re.search(r"\b(\d{2,3})%\b", text) and "estimated" not in lower and "assume" not in lower:
        return "specific percentage without stated source"
    return None


class CognitiveMeshProtocol:
    """Orchestrates the expansion/compression cycle for a single reasoning pass.

    An agent supplies two callbacks:
        - ``expansion_fn(problem, context) -> list[ExpansionStep]``
        - ``compression_fn(problem, expansion, context) -> (recommendation, list[CompressionStep])``

    The protocol adds problem classification, grounding checks, failure-mode
    detection, and renders a structured trace.
    """

    def __init__(
        self,
        *,
        classifier: Optional[Callable[[str], "tuple[ProblemType, str]"]] = None,
    ) -> None:
        self._classifier = classifier or self._default_classifier

    # --- classification ----------------------------------------------------

    @staticmethod
    def _default_classifier(problem: str) -> "tuple[ProblemType, str]":
        p = problem.lower()
        if any(w in p for w in ("market", "revenue", "strategy", "competitor", "invest", "budget")):
            return ProblemType.STRATEGIC, "mentions strategic/market/financial terms"
        if any(w in p for w in ("design", "architecture", "user experience", "workflow")):
            return ProblemType.CREATIVE, "design/architecture framing"
        if any(w in p for w in ("debug", "implementation", "algorithm", "api", "database")):
            return ProblemType.TECHNICAL, "implementation-focused terminology"
        return ProblemType.ANALYTICAL, "default — multi-variable analysis"

    # --- public API --------------------------------------------------------

    def run(
        self,
        problem: str,
        *,
        expansion_fn: Callable[[str, dict], List[ExpansionStep]],
        compression_fn: Callable[[str, List[ExpansionStep], dict], "tuple[str, List[CompressionStep], ConfidenceLevel, str]"],
        context: Optional[dict] = None,
        cycles: int = 1,
    ) -> ReasoningTrace:
        context = context or {}
        ptype, rationale = self._classifier(problem)
        trace = ReasoningTrace(
            problem=problem,
            problem_type=ptype,
            classification_rationale=rationale,
            cycle_count=cycles,
        )

        all_expansion: List[ExpansionStep] = []
        for _ in range(max(1, cycles)):
            steps = expansion_fn(problem, context)
            all_expansion.extend(steps)
        trace.expansion = all_expansion

        rec, comp_steps, conf, what_would_change = compression_fn(
            problem, all_expansion, context
        )
        trace.compression = comp_steps
        trace.recommendation = rec
        trace.confidence = conf
        trace.what_would_change = what_would_change

        trace.grounding = self._ground(trace)
        return trace

    # --- grounding ---------------------------------------------------------

    def _ground(self, trace: ReasoningTrace) -> List[GroundingCheck]:
        checks: List[GroundingCheck] = []
        for step in trace.expansion:
            risk = detect_hallucination_risk(step.content)
            if risk:
                checks.append(
                    GroundingCheck(
                        claim=step.content[:80] + "…",
                        source="pattern-match",
                        confidence=ConfidenceLevel.LOW,
                        risk_flag=risk,
                    )
                )
        rec_risk = detect_hallucination_risk(trace.recommendation)
        checks.append(
            GroundingCheck(
                claim=f"recommendation: {trace.recommendation[:60]}…",
                source="inferred" if rec_risk else "verified",
                confidence=trace.confidence,
                risk_flag=rec_risk,
            )
        )
        return checks

    # --- failure-mode detection -------------------------------------------

    @staticmethod
    def detect_failure_mode(trace: ReasoningTrace) -> Optional[str]:
        texts = [s.content for s in trace.expansion]
        if len(texts) >= 3 and len(set(t[:40] for t in texts)) == 1:
            return "FOSSIL_STATE: repeating same idea across expansion steps"
        if len(trace.compression) == 0 and len(texts) > 6:
            return "CHAOS_STATE: wide expansion with no compression"
        risky = sum(1 for g in trace.grounding if g.risk_flag)
        if risky >= 3:
            return "HALLUCINATION_RISK: multiple ungrounded claims"
        return None
