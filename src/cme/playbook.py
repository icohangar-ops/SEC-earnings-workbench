"""Agentic Context Engineering (ACE) Playbook.

Evolving context playbooks with Generator / Reflector / Curator roles.
Uses non-LLM logic to merge delta updates, preventing context collapse.

Key properties from the skill spec:
    - Bullets are structured: {id, helpful, harmful, content, section}
    - Never regenerate; only add/increment/merge deltas
    - Growth phase: append bullets with new IDs
    - Refinement phase: prune harmful/helpful < 0.5, dedupe on >0.85 similarity
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


SECTIONS = (
    "strategies_and_hard_rules",
    "useful_code_snippets",
    "troubleshooting_and_pitfalls",
    "apis_to_use_for_specific_information",
    "verification_checklist",
    "domain_concepts",
)

_PREFIX = {
    "strategies_and_hard_rules": "shr",
    "useful_code_snippets": "code",
    "troubleshooting_and_pitfalls": "ts",
    "apis_to_use_for_specific_information": "api",
    "verification_checklist": "chk",
    "domain_concepts": "dom",
}


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def _tokens(s: str) -> Counter:
    return Counter(t.lower() for t in _TOKEN_RE.findall(s))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b.get(t, 0) for t in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class Bullet:
    id: str
    section: str
    content: str
    helpful: int = 0
    harmful: int = 0

    def render(self) -> str:
        return f"[{self.id}] helpful={self.helpful} harmful={self.harmful} :: {self.content}"

    @property
    def utility(self) -> float:
        total = self.helpful + self.harmful
        if total == 0:
            return 0.5
        return self.helpful / total


@dataclass
class DeltaOp:
    type: str  # ADD | INCREMENT | MERGE | PRUNE
    section: Optional[str] = None
    content: Optional[str] = None
    target_id: Optional[str] = None
    tag: Optional[str] = None  # helpful | harmful
    rationale: str = ""


@dataclass
class Reflection:
    reasoning: str
    key_insight: str
    correct_approach: str
    bullet_tags: List[Dict[str, str]] = field(default_factory=list)


class Playbook:
    """Structured, evolving playbook for an agent.

    Storage is in-memory + JSON-serializable. Merge operations are
    non-LLM and deterministic.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.bullets: Dict[str, Bullet] = {}
        self._counters: Dict[str, int] = {s: 0 for s in SECTIONS}

    # --- Generator-side read ---------------------------------------------

    def render_for_generator(self, sections: Optional[List[str]] = None) -> str:
        sects = sections or list(SECTIONS)
        lines = [f"# PLAYBOOK: {self.name}", ""]
        for sect in sects:
            bullets = [b for b in self.bullets.values() if b.section == sect]
            if not bullets:
                continue
            lines.append(f"## {sect.upper().replace('_', ' ')}")
            bullets.sort(key=lambda b: (-b.utility, b.id))
            for b in bullets:
                lines.append(b.render())
            lines.append("")
        return "\n".join(lines)

    # --- Delta operations -------------------------------------------------

    def apply(self, ops: List[DeltaOp]) -> List[str]:
        """Apply a list of deltas. Returns a human-readable changelog."""
        log: List[str] = []
        for op in ops:
            if op.type == "ADD" and op.section and op.content:
                # Check for near-duplicate
                dup = self._find_duplicate(op.section, op.content)
                if dup:
                    dup.helpful += 1
                    log.append(f"DEDUP {dup.id} (matched new content)")
                    continue
                new_id = self._next_id(op.section)
                self.bullets[new_id] = Bullet(
                    id=new_id, section=op.section, content=op.content.strip()
                )
                log.append(f"ADD   {new_id}: {op.content[:60]}")
            elif op.type == "INCREMENT" and op.target_id and op.tag:
                b = self.bullets.get(op.target_id)
                if b:
                    if op.tag == "helpful":
                        b.helpful += 1
                    elif op.tag == "harmful":
                        b.harmful += 1
                    log.append(f"INC   {b.id} {op.tag} -> h={b.helpful}/x={b.harmful}")
            elif op.type == "PRUNE" and op.target_id:
                if op.target_id in self.bullets:
                    del self.bullets[op.target_id]
                    log.append(f"PRUNE {op.target_id}")
            elif op.type == "MERGE" and op.target_id and op.content:
                b = self.bullets.get(op.target_id)
                if b:
                    b.content = op.content.strip()
                    b.helpful += 1
                    log.append(f"MERGE {b.id}: content revised")
        return log

    def _next_id(self, section: str) -> str:
        self._counters[section] = self._counters.get(section, 0) + 1
        return f"{_PREFIX[section]}-{self._counters[section]:05d}"

    def _find_duplicate(self, section: str, content: str) -> Optional[Bullet]:
        ct = _tokens(content)
        for b in self.bullets.values():
            if b.section != section:
                continue
            if _cosine(_tokens(b.content), ct) > 0.85:
                return b
        return None

    # --- Refinement -------------------------------------------------------

    def refine(self) -> List[str]:
        """Periodic pruning / consolidation. Returns changelog."""
        log: List[str] = []
        # 1. Prune low-utility bullets with enough samples
        to_prune = [
            b.id
            for b in self.bullets.values()
            if (b.helpful + b.harmful) >= 3 and b.utility < 0.4
        ]
        for bid in to_prune:
            del self.bullets[bid]
            log.append(f"PRUNE {bid} (low utility)")
        # 2. Semantic dedupe across same section
        by_section: Dict[str, List[Bullet]] = {}
        for b in self.bullets.values():
            by_section.setdefault(b.section, []).append(b)
        for bullets in by_section.values():
            kept: List[Bullet] = []
            for b in sorted(bullets, key=lambda x: (-x.helpful, x.id)):
                if any(
                    _cosine(_tokens(b.content), _tokens(k.content)) > 0.85 for k in kept
                ):
                    del self.bullets[b.id]
                    log.append(f"DEDUP {b.id}")
                else:
                    kept.append(b)
        return log

    # --- Serialization ----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "bullets": {k: asdict(v) for k, v in self.bullets.items()},
            "counters": dict(self._counters),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Playbook":
        pb = cls(data["name"])
        pb._counters = dict(data.get("counters", {}))
        for k, v in data.get("bullets", {}).items():
            pb.bullets[k] = Bullet(**v)
        return pb


# --- Reflector & Curator --------------------------------------------------


class Reflector:
    """Extracts insights from a reasoning trace + execution signals.

    Not an LLM — applies a pattern ruleset over the trace. In production you'd
    swap ``reflect`` for an LLM call; the interface is identical.
    """

    def reflect(
        self,
        *,
        trajectory_summary: str,
        outcome: str,  # "success" | "failure" | "partial"
        current_playbook: Playbook,
        grounding_issues: Optional[List[str]] = None,
    ) -> Reflection:
        insight_parts = []
        correct = ""
        tags: List[Dict[str, str]] = []

        if outcome == "failure":
            insight_parts.append(
                "A downstream agent could not act on this trajectory; the reasoning "
                "likely skipped a grounding or assumption check."
            )
            correct = (
                "Before committing to a recommendation, restate the binding constraint "
                "and verify it against the shared entity map."
            )
        elif outcome == "partial":
            insight_parts.append(
                "Output was usable but incomplete — expansion converged too quickly."
            )
            correct = (
                "Increase expansion steps or add a cross-domain analogy before compressing."
            )
        else:
            insight_parts.append(
                "Trajectory met the downstream need; note the reusable pattern."
            )
            correct = "Continue applying the same expansion cadence for similar problems."

        if grounding_issues:
            insight_parts.append(
                "Grounding checks surfaced "
                + str(len(grounding_issues))
                + " unsourced claim(s)."
            )
            correct += " Always cite the shared ContextEngine entry when using a factual claim."

        # Tag bullets that appeared in the trajectory as helpful
        for bid, bullet in current_playbook.bullets.items():
            token_b = _tokens(bullet.content)
            token_traj = _tokens(trajectory_summary)
            if _cosine(token_b, token_traj) > 0.25:
                tags.append(
                    {"id": bid, "tag": "helpful" if outcome != "failure" else "harmful"}
                )

        return Reflection(
            reasoning=" ".join(insight_parts),
            key_insight=correct.split(".")[0] + ".",
            correct_approach=correct,
            bullet_tags=tags,
        )


class Curator:
    """Transforms reflections into playbook DeltaOps — never full rewrites."""

    def curate(
        self,
        reflection: Reflection,
        playbook: Playbook,
        *,
        default_section: str = "strategies_and_hard_rules",
    ) -> List[DeltaOp]:
        ops: List[DeltaOp] = []
        # 1. Tag existing bullets
        for tag in reflection.bullet_tags:
            ops.append(
                DeltaOp(
                    type="INCREMENT",
                    target_id=tag["id"],
                    tag=tag["tag"],
                    rationale="reflector feedback",
                )
            )
        # 2. Add the new insight as a rule if not already present
        if reflection.correct_approach:
            ops.append(
                DeltaOp(
                    type="ADD",
                    section=default_section,
                    content=reflection.correct_approach.strip(),
                    rationale=reflection.key_insight,
                )
            )
        return ops
