"""SEC / Earnings / Company Research Workbench — domain layer.

Three task types:
    - company_research → BusinessModelMemo
    - sec_deep_dive    → SECDeepDiveMemo
    - initiation       → InitiationOfCoverage

Each task runs through CHP foundation hardening, then a Cognitive Mesh of
three agents (Fundamentals, Diligence, Markets) on a shared ContextEngine
seeded with AlphaVantage fundamentals + FRED macro context.
"""

from cme.research.artifacts import (
    BusinessModelMemo,
    InitiationOfCoverage,
    ResearchArtifact,
    SECDeepDiveMemo,
)
from cme.research.audit import AuditEntry, AuditTrail
from cme.research.briefs import (
    CompanyBrief,
    InitiationBrief,
    ResearchBrief,
    ResearchTaskType,
    SECDeepDiveBrief,
)
from cme.research.orchestrator import ResearchSessionReport, ResearchWorkbench

__all__ = [
    "AuditEntry",
    "AuditTrail",
    "BusinessModelMemo",
    "CompanyBrief",
    "InitiationBrief",
    "InitiationOfCoverage",
    "ResearchArtifact",
    "ResearchBrief",
    "ResearchSessionReport",
    "ResearchTaskType",
    "ResearchWorkbench",
    "SECDeepDiveBrief",
    "SECDeepDiveMemo",
]
