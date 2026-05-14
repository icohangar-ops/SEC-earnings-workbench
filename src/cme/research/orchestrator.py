"""ResearchWorkbench — fuses Mesh agents with CHP hardening + external data.

A single ``run(brief)`` does the following:

    1. Builds a CHP ``DecisionCase`` + ``FoundationDisclosure`` + ``FoundationAttack``
       from the brief.
    2. Pulls real grounding data — AlphaVantage company fundamentals + FRED
       macro panel — and caches both onto the shared ``ContextEngine`` so all
       three agents see the same numeric context.
    3. Runs the ``EnterpriseOrchestrator`` (Fundamentals → Diligence → Markets,
       topologically sorted) so each agent contributes a reasoning trace and
       playbook deltas on shared context.
    4. Advances the CHP session: R0 gate, foundation verdict, parity
       assessment, initial payload envelope. If foundation passes and no
       failure modes triggered, the session advances to ``PROVISIONAL_LOCK``.
    5. Synthesizes a domain-specific research artifact tied back to every
       claim's origin via an ``AuditTrail`` that includes the AlphaVantage +
       FRED grounding sources.

The output is a ``ResearchSessionReport`` that renders to a single
research-ready markdown document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cme.agent import MeshAgent, TurnResult
from cme.bridge import EntryPoint
from cme.chp.foundation import foundation_verdict, validate_foundation_pair
from cme.chp.gates import evaluate_r0_gate
from cme.chp.models import (
    DecisionCase,
    FoundationAttack,
    FoundationDisclosure,
    SessionStatus,
    ThirdPartyValidation,
    ValidationResult,
    Verdict,
)
from cme.chp.orchestrator import CHPOrchestrator
from cme.chp.parity import assess_model_parity
from cme.chp.payloads import build_payload_envelope
from cme.chp.registry import DecisionRegistry
from cme.chp.validators import apply_third_party_validation
from cme.context import ContextEngine, Entity, Task
from cme.orchestrator import EnterpriseOrchestrator, OrchestrationReport

from cme.research.artifacts import (
    BusinessModelMemo,
    InitiationOfCoverage,
    ResearchArtifact,
    SECDeepDiveMemo,
    build_business_model_memo,
    build_initiation_of_coverage,
    build_sec_deep_dive_memo,
)
from cme.research.audit import AuditTrail, build_audit_trail
from cme.research.briefs import (
    CompanyBrief,
    InitiationBrief,
    ResearchBrief,
    ResearchTaskType,
    SECDeepDiveBrief,
)
from cme.research.data import (
    AlphaVantageClient,
    AlphaVantageError,
    EdgarClient,
    EdgarError,
    FilingRef,
    FredClient,
    FredError,
)
from cme.research.dossier_builders import build_decision_case


@dataclass
class ResearchSessionReport:
    brief: ResearchBrief
    case: DecisionCase
    foundation_disclosure: FoundationDisclosure
    foundation_attack: FoundationAttack
    r0_verdict: Verdict
    foundation_verdict: Verdict
    initial_packet: str
    orchestration: OrchestrationReport
    artifact: ResearchArtifact
    audit: AuditTrail
    overview: Optional[Dict[str, Any]] = None
    macro: Optional[Dict[str, Dict[str, Any]]] = None
    edgar_filings: List[FilingRef] = field(default_factory=list)
    data_warnings: List[str] = field(default_factory=list)
    turns: List[TurnResult] = field(default_factory=list)

    def render(self) -> str:
        sections = [
            "# Research Workbench Session",
            f"**Task:** {self.brief.task_type.value}",
            f"**Title:** {self.brief.title}",
            f"**Subject:** {self.brief.company} ({self.brief.ticker})",
            f"**Lock state:** `{self.case.status.value}`",
            f"**Foundation score:** {self.case.foundation_score}  ·  "
            f"R0: `{self.r0_verdict.value}`  ·  Foundation: `{self.foundation_verdict.value}`",
            "",
            self.artifact.render(),
            "",
            self.audit.render(),
            "",
            "## Initial CHP Packet",
            "```",
            self.initial_packet,
            "```",
            "",
            "## Mesh Orchestration Detail",
            self.orchestration.render(),
        ]
        if self.data_warnings:
            sections.insert(7, "## Data Warnings\n" + "\n".join(f"- {w}" for w in self.data_warnings) + "\n")
        return "\n".join(sections)


class ResearchWorkbench:
    """High-level research workbench. Mesh agents + CHP hardening on shared
    context, with AlphaVantage + FRED grounding."""

    def __init__(
        self,
        *,
        agents: List[MeshAgent],
        registry: Optional[DecisionRegistry] = None,
        context: Optional[ContextEngine] = None,
        alpha_vantage: Optional[AlphaVantageClient] = None,
        fred: Optional[FredClient] = None,
        edgar: Optional[EdgarClient] = None,
    ) -> None:
        if not agents:
            raise ValueError("ResearchWorkbench requires at least one MeshAgent")
        self.agents = agents
        self.registry = registry or DecisionRegistry()
        self.context = context or ContextEngine()
        self.alpha_vantage = alpha_vantage or AlphaVantageClient()
        self.fred = fred or FredClient()
        self.edgar = edgar or EdgarClient()
        self._chp = CHPOrchestrator(registry=self.registry, context=self.context)
        self._mesh = EnterpriseOrchestrator(agents=self.agents, context=self.context)

    # --- Public API ------------------------------------------------------

    def run(self, brief: ResearchBrief) -> ResearchSessionReport:
        case, disclosure, attack = build_decision_case(brief)

        data_warnings: List[str] = []
        overview, income, cash_flow, earnings, quote = self._pull_alpha_vantage(brief, data_warnings)
        macro = self._pull_fred(data_warnings)
        edgar_filings, eight_k_sweep, latest_10k, latest_10q = self._pull_edgar(brief, data_warnings)

        self._seed_context(
            brief,
            case,
            overview=overview,
            macro=macro,
            filings=edgar_filings,
            eight_k_sweep=eight_k_sweep,
        )

        chp_report = self._chp.run_initial_session(
            case=case,
            foundation_disclosure=disclosure,
            foundation_attack=attack,
        )

        orchestration = self._mesh.orchestrate(
            brief.problem,
            entry_point=EntryPoint.PROBLEM,
            workflow_title=f"{brief.task_type.value}: {brief.title[:60]}",
        )

        self._advance_lock_state(chp_report.case, chp_report.foundation_verdict, orchestration.turns)

        artifact = self._build_artifact(
            brief,
            chp_report.case,
            orchestration.turns,
            overview=overview,
            income=income,
            cash_flow=cash_flow,
            earnings=earnings,
            quote=quote,
            macro=macro,
            edgar_filings=edgar_filings,
            eight_k_sweep=eight_k_sweep,
            latest_10k=latest_10k,
            latest_10q=latest_10q,
        )
        audit = build_audit_trail(
            turns=orchestration.turns,
            case=chp_report.case,
            disclosure=disclosure,
            attack=attack,
            overview=overview,
            macro=macro,
            edgar_filings=edgar_filings,
            extra_sources=[
                f"Brief task type: {brief.task_type.value}",
            ],
        )

        return ResearchSessionReport(
            brief=brief,
            case=chp_report.case,
            foundation_disclosure=disclosure,
            foundation_attack=attack,
            r0_verdict=chp_report.r0_verdict,
            foundation_verdict=chp_report.foundation_verdict,
            initial_packet=chp_report.initial_packet,
            orchestration=orchestration,
            artifact=artifact,
            audit=audit,
            overview=overview,
            macro=macro,
            edgar_filings=edgar_filings,
            data_warnings=data_warnings,
            turns=orchestration.turns,
        )

    def lock(
        self,
        decision_id: str,
        *,
        validator: str,
        item: str,
        rationale: str,
        challenge: str = "Stress test before lock progression.",
        confirm: bool = True,
    ) -> DecisionCase:
        case = self.registry.get(decision_id)
        if not case:
            raise KeyError(f"Unknown decision_id: {decision_id}")
        validation = ThirdPartyValidation(
            validator=validator,
            item=item,
            challenge=challenge,
            result=ValidationResult.CONFIRM if confirm else ValidationResult.REJECT,
            rationale=rationale,
        )
        apply_third_party_validation(case, validation)
        return case

    # --- Internals -------------------------------------------------------

    def _pull_alpha_vantage(
        self, brief: ResearchBrief, warnings: List[str]
    ) -> tuple:
        overview = income = cash_flow = earnings = quote = None
        if not self.alpha_vantage.is_live:
            warnings.append("ALPHAVANTAGE_API_KEY not set — fundamentals not pulled.")
            return overview, income, cash_flow, earnings, quote
        ticker = brief.ticker
        try:
            overview = self.alpha_vantage.overview(ticker)
        except AlphaVantageError as exc:
            warnings.append(f"AV OVERVIEW failed: {exc}")
        try:
            income = self.alpha_vantage.income_statement(ticker)
        except AlphaVantageError as exc:
            warnings.append(f"AV INCOME_STATEMENT failed: {exc}")
        # Cash flow / earnings / quote only fetched when needed by artifact.
        try:
            if isinstance(brief, (SECDeepDiveBrief, InitiationBrief, CompanyBrief)):
                earnings = self.alpha_vantage.earnings(ticker)
        except AlphaVantageError as exc:
            warnings.append(f"AV EARNINGS failed: {exc}")
        try:
            if isinstance(brief, SECDeepDiveBrief):
                cash_flow = self.alpha_vantage.cash_flow(ticker)
        except AlphaVantageError as exc:
            warnings.append(f"AV CASH_FLOW failed: {exc}")
        try:
            if isinstance(brief, InitiationBrief):
                quote = self.alpha_vantage.global_quote(ticker)
        except AlphaVantageError as exc:
            warnings.append(f"AV GLOBAL_QUOTE failed: {exc}")
        return overview, income, cash_flow, earnings, quote

    def _pull_fred(self, warnings: List[str]) -> Optional[Dict[str, Dict[str, Any]]]:
        if not self.fred.is_live:
            warnings.append("FRED_API_KEY not set — macro panel not pulled.")
            return None
        try:
            return self.fred.macro_panel()
        except FredError as exc:
            warnings.append(f"FRED macro_panel failed: {exc}")
            return None

    def _pull_edgar(
        self, brief: ResearchBrief, warnings: List[str]
    ) -> tuple:
        """Return (recent_filings, 8k_sweep, latest_10k, latest_10q).

        Filings are pulled directly from SEC EDGAR (no API key needed; rate-
        limited on a 24h disk cache). On any failure we degrade gracefully and
        emit a warning so the rest of the pipeline keeps running.
        """
        recent: List[FilingRef] = []
        eight_k_sweep: List[FilingRef] = []
        latest_10k: Optional[FilingRef] = None
        latest_10q: Optional[FilingRef] = None
        if not self.edgar or not self.edgar.is_live:
            warnings.append("EDGAR_DISABLED — SEC filings not pulled.")
            return recent, eight_k_sweep, latest_10k, latest_10q
        # Choose forms by task type; SEC deep dive widens the net.
        if isinstance(brief, SECDeepDiveBrief):
            forms = list(brief.filings_in_scope) or ["10-K", "10-Q", "8-K", "DEF 14A"]
            limit = 30
        else:
            forms = ["10-K", "10-Q", "8-K", "DEF 14A"]
            limit = 12
        try:
            cik = self.edgar.cik_for(brief.ticker)
            if cik is None:
                warnings.append(
                    f"EDGAR: no CIK match for ticker {brief.ticker} — filings not pulled."
                )
                return recent, eight_k_sweep, latest_10k, latest_10q
            recent = self.edgar.recent_filings(brief.ticker, forms=forms, limit=limit)
            latest_10k = self.edgar.latest_filing(brief.ticker, "10-K")
            latest_10q = self.edgar.latest_filing(brief.ticker, "10-Q")
            eight_k_sweep = self.edgar.eight_ks_since_last_periodic(brief.ticker)
        except EdgarError as exc:
            warnings.append(f"EDGAR fetch failed for {brief.ticker}: {exc}")
        except Exception as exc:  # network unreachable, etc — never crash run()
            warnings.append(f"EDGAR fetch raised {type(exc).__name__}: {exc}")
        return recent, eight_k_sweep, latest_10k, latest_10q

    def _seed_context(
        self,
        brief: ResearchBrief,
        case: DecisionCase,
        *,
        overview: Optional[Dict[str, Any]],
        macro: Optional[Dict[str, Dict[str, Any]]],
        filings: Optional[List[FilingRef]] = None,
        eight_k_sweep: Optional[List[FilingRef]] = None,
    ) -> None:
        self.context.upsert_entity(
            Entity(
                id="subject",
                type="company",
                attributes={
                    "name": brief.company,
                    "ticker": brief.ticker,
                    "industry": brief.industry,
                },
            )
        )
        if overview:
            self.context.upsert_entity(
                Entity(
                    id=f"av-overview-{brief.ticker.lower()}",
                    type="external_data",
                    attributes={
                        "source": "alphavantage.OVERVIEW",
                        "ticker": brief.ticker,
                        "sector": overview.get("Sector"),
                        "industry": overview.get("Industry"),
                        "market_cap": overview.get("MarketCapitalization"),
                        "pe_ratio": overview.get("PERatio"),
                        "profit_margin": overview.get("ProfitMargin"),
                        "latest_quarter": overview.get("LatestQuarter"),
                    },
                )
            )
        # Seed EDGAR filings into shared context so agents (esp. Diligence) can
        # cite real filing dates from their expand() phase.
        for i, f in enumerate((filings or [])[:12]):
            self.context.upsert_entity(
                Entity(
                    id=f"sec-filing-{i}-{f.accession_no}",
                    type="sec_filing",
                    attributes={
                        "ticker": brief.ticker,
                        "form": f.form,
                        "filing_date": f.filing_date,
                        "report_date": f.report_date,
                        "accession_no": f.accession_no,
                        "primary_doc_url": f.primary_doc_url,
                        "is_xbrl": f.is_xbrl,
                        "citation": f.citation(),
                        "source": "SEC EDGAR",
                    },
                )
            )
        for j, f in enumerate(eight_k_sweep or []):
            self.context.upsert_entity(
                Entity(
                    id=f"8k-sweep-{j}-{f.accession_no}",
                    type="sec_filing_8k_sweep",
                    attributes={
                        "ticker": brief.ticker,
                        "form": f.form,
                        "filing_date": f.filing_date,
                        "accession_no": f.accession_no,
                        "primary_doc_url": f.primary_doc_url,
                        "citation": f.citation(),
                        "source": "SEC EDGAR (8-K sweep since latest periodic)",
                    },
                )
            )
        if macro:
            for sid, entry in macro.items():
                if "value" in entry:
                    self.context.upsert_entity(
                        Entity(
                            id=f"fred-{sid}",
                            type="macro_indicator",
                            attributes={
                                "series_id": sid,
                                "label": entry.get("label", sid),
                                "value": entry["value"],
                                "as_of": entry.get("date"),
                                "source": "FRED",
                            },
                        )
                    )
        self.context.upsert_entity(
            Entity(
                id=case.decision_id,
                type="decision_case",
                attributes={
                    "title": case.title,
                    "domain": case.domain,
                    "owner": case.owner,
                    "high_stakes": case.high_stakes,
                    "task_type": brief.task_type.value,
                    "ticker": brief.ticker,
                },
            )
        )
        if case.dossier:
            for i, c in enumerate(case.dossier.constraints[:6]):
                self.context.upsert_entity(
                    Entity(
                        id=f"{case.decision_id}-constraint-{i}",
                        type="constraint",
                        attributes={"text": c},
                    )
                )
        for i, peer in enumerate(brief.peers[:6]):
            self.context.upsert_entity(
                Entity(
                    id=f"peer-{peer.lower()}",
                    type="peer",
                    attributes={"ticker": peer, "rank": i},
                )
            )
        self.context.add_task(
            Task(
                id=f"task-{case.decision_id}",
                goal=f"Harden {brief.task_type.value}: {brief.title}",
                status="in_progress",
                owner=case.owner,
            )
        )
        self.context.record_event(
            actor="research_workbench",
            action="session_open",
            object_=case.decision_id,
        )

    def _advance_lock_state(
        self, case: DecisionCase, f_verdict: Verdict, turns: List[TurnResult]
    ) -> None:
        any_failure = any(
            note.startswith("warning:") for t in turns for note in t.handoff_notes
        )
        if case.status in {SessionStatus.HALT, SessionStatus.REFRAME_REQUIRED}:
            return
        if f_verdict == Verdict.PASS and not any_failure:
            case.status = SessionStatus.PROVISIONAL_LOCK

    def _build_artifact(
        self,
        brief: ResearchBrief,
        case: DecisionCase,
        turns: List[TurnResult],
        *,
        overview: Optional[Dict[str, Any]],
        income: Optional[Dict[str, Any]],
        cash_flow: Optional[Dict[str, Any]],
        earnings: Optional[Dict[str, Any]],
        quote: Optional[Dict[str, Any]],
        macro: Optional[Dict[str, Dict[str, Any]]],
        edgar_filings: Optional[List[FilingRef]] = None,
        eight_k_sweep: Optional[List[FilingRef]] = None,
        latest_10k: Optional[FilingRef] = None,
        latest_10q: Optional[FilingRef] = None,
    ) -> ResearchArtifact:
        if isinstance(brief, CompanyBrief):
            return build_business_model_memo(
                brief=brief,
                case=case,
                turns=turns,
                overview=overview,
                income=income,
                earnings=earnings,
                macro=macro,
                edgar_filings=edgar_filings,
                eight_k_sweep=eight_k_sweep,
                latest_10k=latest_10k,
                latest_10q=latest_10q,
            )
        if isinstance(brief, SECDeepDiveBrief):
            return build_sec_deep_dive_memo(
                brief=brief,
                case=case,
                turns=turns,
                overview=overview,
                income=income,
                cash_flow=cash_flow,
                earnings=earnings,
                macro=macro,
                edgar_filings=edgar_filings,
                eight_k_sweep=eight_k_sweep,
                latest_10k=latest_10k,
                latest_10q=latest_10q,
            )
        if isinstance(brief, InitiationBrief):
            return build_initiation_of_coverage(
                brief=brief,
                case=case,
                turns=turns,
                overview=overview,
                income=income,
                quote=quote,
                earnings=earnings,
                macro=macro,
                edgar_filings=edgar_filings,
                eight_k_sweep=eight_k_sweep,
                latest_10k=latest_10k,
                latest_10q=latest_10q,
            )
        raise TypeError(f"Unsupported brief type: {type(brief).__name__}")

    # Re-expose CHP primitives for callers that want raw access ----------

    @staticmethod
    def assess_parity(origin_model: str, partner_model: str):
        return assess_model_parity(origin_model, partner_model)

    @staticmethod
    def evaluate_r0(case: DecisionCase) -> Verdict:
        return evaluate_r0_gate(
            solvable=True,
            scoped=bool(case.dossier and case.dossier.scope),
            valid=bool(case.dossier and case.dossier.current_state),
            worth_it=case.high_stakes,
        ).verdict

    @staticmethod
    def validate_foundation(
        disclosure: FoundationDisclosure, attack: FoundationAttack
    ) -> List[str]:
        return validate_foundation_pair(disclosure, attack)

    @staticmethod
    def envelope(body: str) -> str:
        return build_payload_envelope(body).render()

    @staticmethod
    def foundation_pass(attack: FoundationAttack) -> bool:
        return foundation_verdict(attack) == Verdict.PASS
