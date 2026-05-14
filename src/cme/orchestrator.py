"""EnterpriseOrchestrator — coordinates MeshAgents on a shared context.

The orchestrator:

    1. Accepts a problem from a human user
    2. Selects and sequences agents whose capabilities match the problem
    3. Runs each agent under the Cognitive Mesh Protocol
    4. Routes structured outputs through the ContextEngine
    5. Passes the collected agent outputs into the BridgeFramework to produce
       a final Statement + executable Workflow
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cme.agent import MeshAgent, TurnResult
from cme.bridge import (
    BridgeFramework,
    Consequences,
    EntryPoint,
    Workflow,
    WhyLink,
)
from cme.context import ContextEngine


@dataclass
class OrchestrationReport:
    problem: str
    turns: List[TurnResult]
    workflow: Workflow
    duration_ms: int
    context_snapshot: Dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        sections = [
            f"# Orchestration Report",
            f"**Problem:** {self.problem}",
            f"**Agents:** {', '.join(t.agent for t in self.turns)}",
            f"**Duration:** {self.duration_ms}ms",
            "",
            "---",
            "",
        ]
        for t in self.turns:
            sections.append(f"## Agent Turn — {t.agent}")
            sections.append(t.trace.render())
            if t.deltas_applied:
                sections.append("")
                sections.append("### Playbook Deltas")
                for d in t.deltas_applied:
                    sections.append(f"  - {d}")
            if t.handoff_notes:
                sections.append("")
                sections.append("### Handoff Notes")
                for n in t.handoff_notes:
                    sections.append(f"  - {n}")
            sections.append("")
            sections.append("---")
            sections.append("")
        sections.append(self.workflow.render())
        return "\n".join(sections)


class EnterpriseOrchestrator:
    def __init__(
        self,
        *,
        agents: List[MeshAgent],
        context: Optional[ContextEngine] = None,
        bridge: Optional[BridgeFramework] = None,
    ) -> None:
        self.agents = {a.name: a for a in agents}
        self.context = context or ContextEngine()
        self.bridge = bridge or BridgeFramework()

    # --- Sequencing ------------------------------------------------------

    def _sequence(self, required_outputs: List[str]) -> List[MeshAgent]:
        """Topologically sort agents so producers run before consumers."""
        producers: Dict[str, MeshAgent] = {}
        for agent in self.agents.values():
            for out in agent.capability.produces:
                producers.setdefault(out, agent)

        ordered: List[MeshAgent] = []
        visited: set = set()

        def visit(agent: MeshAgent) -> None:
            if agent.name in visited:
                return
            visited.add(agent.name)
            for inp in agent.capability.consumes:
                producer = producers.get(inp)
                if producer and producer.name != agent.name:
                    visit(producer)
            ordered.append(agent)

        target_agents = [a for a in self.agents.values() if not required_outputs or any(
            out in required_outputs for out in a.capability.produces
        )]
        if not target_agents:
            target_agents = list(self.agents.values())

        for a in target_agents:
            visit(a)

        return ordered

    # --- Main driver -----------------------------------------------------

    def orchestrate(
        self,
        problem: str,
        *,
        entry_point: EntryPoint = EntryPoint.PROBLEM,
        required_outputs: Optional[List[str]] = None,
        workflow_title: Optional[str] = None,
    ) -> OrchestrationReport:
        start = time.time()
        self.context.record_event(actor="orchestrator", action="intake", object_=problem)

        ordered = self._sequence(required_outputs or [])
        turns: List[TurnResult] = []
        agent_outputs_for_bridge: List[Dict[str, Any]] = []

        for agent in ordered:
            result = agent.act(problem, shared_context=self.context)
            turns.append(result)
            agent_outputs_for_bridge.append(
                {
                    "agent": agent.name,
                    "title": result.trace.recommendation[:80],
                    "recommendation": result.trace.recommendation,
                    "rationale": f"{agent.capability.domain} reasoning "
                    f"(confidence={result.trace.confidence.value})",
                    "inputs": agent.capability.consumes,
                    "outputs": agent.capability.produces,
                }
            )

        # --- Build statement from the collected turns ----------------------
        statement = self._synthesize_statement(
            problem=problem, entry_point=entry_point, turns=turns
        )
        workflow = self.bridge.build_workflow(
            title=workflow_title or f"Response to: {problem[:60]}",
            statement=statement,
            agent_outputs=agent_outputs_for_bridge,
        )

        duration_ms = int((time.time() - start) * 1000)
        return OrchestrationReport(
            problem=problem,
            turns=turns,
            workflow=workflow,
            duration_ms=duration_ms,
            context_snapshot=self.context.dump(),
        )

    # --- Statement synthesis --------------------------------------------

    def _synthesize_statement(
        self, *, problem: str, entry_point: EntryPoint, turns: List[TurnResult]
    ):
        # Observable tension = the problem itself restated
        observable = (
            f"Today: {problem} — {len(turns)} specialist agent(s) produced recommendations "
            f"through {sum(len(t.trace.expansion) for t in turns)} expansion steps."
        )

        # 5 Whys — derived from each agent's top expansion step (first {n} agents)
        whys: List[WhyLink] = []
        for t in turns[:5]:
            if not t.trace.expansion:
                continue
            first = t.trace.expansion[0]
            whys.append(
                WhyLink(
                    question=f"Why does {t.agent} see this matter?",
                    answer=f"{first.label}: {first.content}",
                )
            )
        while len(whys) < 3:  # ensure minimum depth per spec
            whys.append(
                WhyLink(
                    question="Why is this still unresolved?",
                    answer="Because the binding constraint has not been named in shared context.",
                )
            )

        # Consequences — pull highest-confidence agent's recommendation as financial impact
        hi_conf = sorted(
            turns, key=lambda t: {"high": 3, "medium": 2, "low": 1}[t.trace.confidence.value], reverse=True
        )
        financial = (
            hi_conf[0].trace.recommendation
            if hi_conf
            else "Impact not yet quantified."
        )
        consequences = Consequences(
            strategic="Mesh loses coherence; agents optimize locally without shared context.",
            cultural="Teams re-solve the same problems in parallel, eroding trust in the system.",
            financial=financial[:200],
            timeline="2 quarters",
        )

        strategic_connection = (
            "This connects to the organization's mission of shipping decisions that are "
            "both technically rigorous and human-auditable. Every multi-agent output must "
            "trace back to an observable organizational signal."
        )

        return self.bridge.build_statement(
            entry_point=entry_point,
            observable_tension=observable,
            whys=whys,
            consequences=consequences,
            strategic_connection=strategic_connection,
        )
