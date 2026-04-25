"""Context Engine.

Implements the Context Engineering Framework's memory architecture:
    - Layered short-term / long-term memory with temporal + importance weighting
    - Fixed-schema self-baking: Entity map, Event record, Task tree
    - Context selection by semantic relevance, recency, frequency
    - Multi-agent context sharing via shared memory with structured messages

Uses a deterministic token-based similarity (no external embedding model) so
the demo is fully offline. Swap ``_score_relevance`` for a real embedding model
in production.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


# --- Schema ---------------------------------------------------------------


@dataclass
class Entity:
    id: str
    type: str  # "org", "person", "product", "metric", ...
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def display(self) -> str:
        name = self.attributes.get("name", self.id)
        return f"{self.type}:{name}"


@dataclass
class Event:
    timestamp: float
    actor: str
    action: str
    object: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    id: str
    goal: str
    status: str = "open"  # open | in_progress | done | blocked
    parent: Optional[str] = None
    subtasks: List[str] = field(default_factory=list)
    owner: Optional[str] = None


@dataclass
class ContextEntry:
    id: str
    content: str
    source_agent: str
    timestamp: float
    importance: float = 0.5  # 0..1
    access_count: int = 0
    tags: List[str] = field(default_factory=list)


# --- Simple lexical relevance --------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b.get(t, 0) for t in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


# --- Engine ---------------------------------------------------------------


class ContextEngine:
    """Shared organizational context for the mesh.

    Thread-safe so multiple agents can read/write concurrently. Short-term
    entries fall out after ``short_term_ttl`` seconds unless promoted by
    importance. Long-term storage is append-only with delta-update semantics.
    """

    def __init__(
        self,
        *,
        short_term_ttl: float = 300.0,
        short_term_threshold: float = 0.3,  # w_temporal threshold
        long_term_threshold: float = 0.6,  # w_importance threshold
    ) -> None:
        self.short_term_ttl = short_term_ttl
        self.short_term_threshold = short_term_threshold
        self.long_term_threshold = long_term_threshold

        self._short_term: Dict[str, ContextEntry] = {}
        self._long_term: Dict[str, ContextEntry] = {}
        self._entities: Dict[str, Entity] = {}
        self._events: List[Event] = []
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.RLock()

    # --- Entity / Event / Task -------------------------------------------

    def upsert_entity(self, entity: Entity) -> None:
        with self._lock:
            existing = self._entities.get(entity.id)
            if existing:
                existing.attributes.update(entity.attributes)
            else:
                self._entities[entity.id] = entity

    def record_event(self, actor: str, action: str, object_: str, **payload: Any) -> Event:
        evt = Event(
            timestamp=time.time(),
            actor=actor,
            action=action,
            object=object_,
            payload=payload,
        )
        with self._lock:
            self._events.append(evt)
        return evt

    def add_task(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task
            if task.parent and task.parent in self._tasks:
                parent = self._tasks[task.parent]
                if task.id not in parent.subtasks:
                    parent.subtasks.append(task.id)

    def update_task(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            if task_id in self._tasks:
                for k, v in changes.items():
                    setattr(self._tasks[task_id], k, v)

    # --- Text context entries (for agent-to-agent sharing) ---------------

    def write(
        self,
        content: str,
        *,
        source_agent: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Write a context entry. High-importance entries go straight to long-term."""
        entry = ContextEntry(
            id=str(uuid.uuid4())[:8],
            content=content,
            source_agent=source_agent,
            timestamp=time.time(),
            importance=max(0.0, min(1.0, importance)),
            tags=tags or [],
        )
        with self._lock:
            if entry.importance >= self.long_term_threshold:
                self._long_term[entry.id] = entry
            else:
                self._short_term[entry.id] = entry
        return entry.id

    def select(
        self,
        query: str,
        *,
        k: int = 5,
        agent: Optional[str] = None,
    ) -> List[ContextEntry]:
        """Select top-k relevant entries for a query.

        Combines: semantic (lexical-cosine), recency, frequency, importance.
        Enforces the Minimal Sufficiency Principle by returning at most ``k``.
        Removes near-duplicates (cosine > 0.85).
        """
        with self._lock:
            self._promote_short_to_long()
            q_tokens = Counter(_tokens(query))
            pool: List[ContextEntry] = list(self._short_term.values()) + list(
                self._long_term.values()
            )
            now = time.time()
            scored: List[tuple[float, ContextEntry]] = []
            seen_counters: List[Counter] = []
            for entry in pool:
                e_tokens = Counter(_tokens(entry.content))
                # Semantic dedupe
                if any(_cosine(e_tokens, c) > 0.85 for c in seen_counters):
                    continue
                semantic = _cosine(q_tokens, e_tokens)
                age = now - entry.timestamp
                recency = math.exp(-age / (self.short_term_ttl * 2))
                freq = math.log1p(entry.access_count) / 5.0
                score = (
                    0.5 * semantic
                    + 0.2 * recency
                    + 0.1 * freq
                    + 0.2 * entry.importance
                )
                if agent and entry.source_agent == agent:
                    score += 0.05
                scored.append((score, entry))
                seen_counters.append(e_tokens)

            scored.sort(key=lambda x: x[0], reverse=True)
            top = [e for _, e in scored[:k]]
            for e in top:
                e.access_count += 1
            return top

    def _promote_short_to_long(self) -> None:
        now = time.time()
        expired_ids = []
        for eid, entry in self._short_term.items():
            age = now - entry.timestamp
            if entry.importance >= self.long_term_threshold:
                self._long_term[eid] = entry
                expired_ids.append(eid)
            elif age > self.short_term_ttl:
                # Drop unless it has been accessed repeatedly
                if entry.access_count >= 3:
                    self._long_term[eid] = entry
                expired_ids.append(eid)
        for eid in expired_ids:
            self._short_term.pop(eid, None)

    # --- Snapshot for agents ---------------------------------------------

    def snapshot_for(self, agent_name: str, query: str, k: int = 5) -> Dict[str, Any]:
        """Produce the structured context package passed to an agent invocation."""
        with self._lock:
            relevant = self.select(query, k=k, agent=agent_name)
            recent_events = self._events[-10:]
            return {
                "agent": agent_name,
                "query": query,
                "entities": [asdict(e) for e in self._entities.values()],
                "recent_events": [asdict(e) for e in recent_events],
                "active_tasks": [
                    asdict(t) for t in self._tasks.values() if t.status != "done"
                ],
                "relevant_notes": [
                    {
                        "id": e.id,
                        "content": e.content,
                        "source_agent": e.source_agent,
                        "tags": e.tags,
                        "importance": e.importance,
                    }
                    for e in relevant
                ],
            }

    def dump(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entities": {k: asdict(v) for k, v in self._entities.items()},
                "events": [asdict(e) for e in self._events],
                "tasks": {k: asdict(v) for k, v in self._tasks.items()},
                "short_term": {k: asdict(v) for k, v in self._short_term.items()},
                "long_term": {k: asdict(v) for k, v in self._long_term.items()},
            }

    def dump_json(self) -> str:
        return json.dumps(self.dump(), indent=2, default=str)
