# SEC Earnings Workbench — CockroachDB Persistence Layer
"""
SQLAlchemy ORM layer backed by CockroachDB for distributed,
ACID-compliant storage of all SEC research and CHP decision data.

Connection: CockroachDB Serverless on GCP (sec_earnings_workbench database)

Domain entities:
  - DecisionCases: CHP consensus-hardened decision cases
  - Dossiers: decision context dossiers
  - ResearchArtifacts: business model memos, SEC deep-dives, IoCs
  - ResearchCache: distributed cache replacing on-disk JSON cache
  - ApiCallLog: audit trail for external API calls (EDGAR, AV, FRED)
  - ModelParityLogs: cross-model comparison records
  - ValidationRecords: third-party validation (CHP) results
"""

from __future__ import annotations

import json
import os
import logging
import hashlib
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, String, Integer, Numeric, Date, DateTime,
    Text, ForeignKey, Index, JSON, func, select, desc, update, delete,
    Boolean, Float, LargeBinary,
)
from sqlalchemy.orm import (
    declarative_base, relationship, Session, sessionmaker,
)
from sqlalchemy.dialects.postgresql import JSONB

logger = logging.getLogger("sec_earnings_workbench.db")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COCKROACH_URL = (
    "cockroachdb+psycopg2://cubiczan:oY-hPkgXtZjc6kGqY67Gyg@"
    "vortex-giraffe-15678.jxf.gcp-us-east1.cockroachlabs.cloud:26257/"
    "sec_earnings_workbench?sslmode=require"
)
DATABASE_URL = os.getenv("SEW_DATABASE_URL", COCKROACH_URL)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


# ---------------------------------------------------------------------------
# Base Model
# ---------------------------------------------------------------------------

Base = declarative_base()


class TimestampMixin:
    """Common timestamp fields for all models."""
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class DecisionCaseModel(TimestampMixin, Base):
    """CHP (Consensus Hardening Protocol) decision cases."""
    __tablename__ = "decision_cases"

    decision_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    domain = Column(String, default="")
    owner = Column(String, default="")
    status = Column(String, default="EXPLORING",
                    index=True)  # EXPLORING, PROVISIONAL, LOCKED, CONVERGED, etc.
    high_stakes = Column(Boolean, default=False)
    current_phase = Column(String, default="FOUNDATION")  # FOUNDATION, SPEC, IMPLEMENTATION
    current_round = Column(Integer, default=0)
    origin_system = Column(String, default="Claude")
    origin_model = Column(String, default="UNKNOWN")
    partner_system = Column(String, default="UNKNOWN")
    partner_model = Column(String, default="UNKNOWN")
    foundation_score = Column(Integer, nullable=True)
    locked_decisions = Column(JSONB, default=[])
    structural_vulnerabilities = Column(JSONB, default=[])
    blind_spots = Column(JSONB, default=[])
    flip_criteria = Column(JSONB, default=[])

    # Serialized sub-objects
    context_check = Column(JSONB, default={})
    model_parity = Column(JSONB, default={})
    dossier = Column(JSONB, default={})  # Full Dossier dataclass as JSON

    dossiers = relationship("DossierModel", back_populates="case_rel",
                            cascade="all, delete-orphan")
    artifacts = relationship("ResearchArtifactModel", back_populates="case_rel",
                             cascade="all, delete-orphan")
    rounds = relationship("RoundRecordModel", back_populates="case_rel",
                          cascade="all, delete-orphan")
    validations = relationship("ValidationRecordModel", back_populates="case_rel",
                               cascade="all, delete-orphan")


class DossierModel(TimestampMixin, Base):
    """Decision context dossier — structured context for each case."""
    __tablename__ = "dossiers"

    dossier_id = Column(String, primary_key=True,
                        server_default=func.gen_random_uuid())
    decision_id = Column(String, ForeignKey("decision_cases.decision_id"),
                         nullable=False, index=True)
    core_problem = Column(Text, nullable=False)
    goal_state = Column(JSONB, default=[])
    current_state = Column(JSONB, default=[])
    prior_decisions = Column(JSONB, default=[])
    constraints = Column(JSONB, default=[])
    unknowns = Column(JSONB, default=[])
    scope = Column(JSONB, default=[])
    origin_direction = Column(JSONB, default=[])
    prior_round_summary = Column(JSONB, default=[])
    unknowns_carried = Column(JSONB, default=[])
    foundation_score = Column(Integer, nullable=True)
    structural_vulnerabilities = Column(JSONB, default=[])

    case_rel = relationship("DecisionCaseModel", back_populates="dossiers")


class ResearchArtifactModel(TimestampMixin, Base):
    """Research output artifacts (memos, deep-dives, IoCs)."""
    __tablename__ = "research_artifacts"

    artifact_id = Column(String, primary_key=True,
                         server_default=func.gen_random_uuid())
    decision_id = Column(String, ForeignKey("decision_cases.decision_id"),
                         nullable=False, index=True)
    artifact_type = Column(String, nullable=False)  # business_model_memo, sec_deep_dive, initiation_of_coverage
    company = Column(String, default="")
    ticker = Column(String, default="")
    title = Column(String, nullable=False)
    lock_state = Column(String, default="")
    bottom_line = Column(Text, default="")
    sections = Column(JSONB, default=[])  # list of {heading, bullets, table, body}
    sources = Column(JSONB, default=[])
    rendered_markdown = Column(Text, default="")  # pre-rendered output

    case_rel = relationship("DecisionCaseModel", back_populates="artifacts")


class RoundRecordModel(TimestampMixin, Base):
    """CHP round-by-round records."""
    __tablename__ = "round_records"

    round_id = Column(String, primary_key=True,
                      server_default=func.gen_random_uuid())
    decision_id = Column(String, ForeignKey("decision_cases.decision_id"),
                         nullable=False, index=True)
    phase = Column(String, default="FOUNDATION")
    round_number = Column(Integer, default=0)
    payload_id = Column(String, default="")
    origin_packet = Column(Text, default="")
    partner_packet = Column(Text, default="")
    payload_echo_confirmed = Column(Boolean, default=False)
    state_snapshot = Column(JSONB, default={})
    verdict = Column(String, default="")  # PASS, FAIL, CONVERGED, etc.

    case_rel = relationship("DecisionCaseModel", back_populates="rounds")


class ValidationRecordModel(TimestampMixin, Base):
    """Third-party validation results from CHP."""
    __tablename__ = "validation_records"

    validation_id = Column(String, primary_key=True,
                           server_default=func.gen_random_uuid())
    decision_id = Column(String, ForeignKey("decision_cases.decision_id"),
                         nullable=False, index=True)
    validator = Column(String, default="")
    item = Column(String, default="")
    challenge = Column(Text, default="")
    result = Column(String, default="CONFIRM")  # CONFIRM, REJECT
    rationale = Column(Text, default="")

    case_rel = relationship("DecisionCaseModel", back_populates="validations")


class ResearchCacheModel(Base):
    """Distributed cache replacing on-disk JSON cache."""
    __tablename__ = "research_cache"

    cache_id = Column(String, primary_key=True,
                      server_default=func.gen_random_uuid())
    cache_key = Column(String, nullable=False, unique=True)
    cache_hash = Column(String(64), nullable=False, index=True)
    value_json = Column(JSONB, default={})
    ttl_seconds = Column(Integer, default=86400)
    hits = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))


class ApiCallLogModel(TimestampMixin, Base):
    """Audit trail for external API calls."""
    __tablename__ = "api_call_log"

    log_id = Column(String, primary_key=True,
                    server_default=func.gen_random_uuid())
    api_source = Column(String, nullable=False)  # EDGAR, ALPHAVANTAGE, FRED
    endpoint = Column(String, default="")
    ticker = Column(String, default="")
    request_params = Column(JSONB, default={})
    response_status = Column(Integer, default=0)
    response_time_ms = Column(Integer, default=0)
    error_message = Column(Text, default="")
    data_source = Column(String, default="")
    cached = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_api_source_date", "api_source", "created_at"),
    )


class ModelParityLogModel(TimestampMixin, Base):
    """Cross-model comparison records."""
    __tablename__ = "model_parity_logs"

    parity_id = Column(String, primary_key=True,
                       server_default=func.gen_random_uuid())
    decision_id = Column(String, ForeignKey("decision_cases.decision_id"),
                         nullable=True, index=True)
    origin_model = Column(String, default="")
    partner_model = Column(String, default="")
    delta_description = Column(Text, default="")
    advisory = Column(Text, default="")
    verdict = Column(String, default="")  # aligned, divergent, critical_divergence


# ---------------------------------------------------------------------------
# Repository Classes
# ---------------------------------------------------------------------------

class DecisionCaseRepository:
    @staticmethod
    def get_all(session: Session) -> list[dict]:
        rows = session.execute(
            select(DecisionCaseModel).order_by(desc(DecisionCaseModel.created_at))
        ).scalars().all()
        return [
            {
                "decision_id": r.decision_id,
                "title": r.title,
                "domain": r.domain,
                "status": r.status,
                "phase": r.current_phase,
                "round": r.current_round,
                "foundation_score": r.foundation_score,
                "high_stakes": r.high_stakes,
                "artifacts_count": len(r.artifacts),
                "locked": r.status in ("LOCKED", "CONVERGED"),
            }
            for r in rows
        ]

    @staticmethod
    def get_locked(session: Session) -> list[dict]:
        rows = session.execute(
            select(DecisionCaseModel).where(
                DecisionCaseModel.status.in_(["LOCKED", "CONVERGED"])
            )
        ).scalars().all()
        return [
            {
                "decision_id": r.decision_id,
                "title": r.title,
                "domain": r.domain,
                "foundation_score": r.foundation_score,
            }
            for r in rows
        ]

    @staticmethod
    def find_related(session: Session, query: str) -> list[dict]:
        q = query.lower()
        rows = session.execute(
            select(DecisionCaseModel).where(
                (DecisionCaseModel.title.ilike(f"%{q}%")) |
                (DecisionCaseModel.domain.ilike(f"%{q}%"))
            ).limit(20)
        ).scalars().all()
        return [
            {
                "decision_id": r.decision_id,
                "title": r.title,
                "domain": r.domain,
                "status": r.status,
            }
            for r in rows
        ]


class ResearchArtifactRepository:
    @staticmethod
    def get_by_ticker(session: Session, ticker: str) -> list[dict]:
        rows = session.execute(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.ticker == ticker
            ).order_by(desc(ResearchArtifactModel.created_at))
        ).scalars().all()
        return [
            {
                "artifact_id": r.artifact_id,
                "type": r.artifact_type,
                "company": r.company,
                "ticker": r.ticker,
                "title": r.title,
                "lock_state": r.lock_state,
                "created": str(r.created_at),
            }
            for r in rows
        ]

    @staticmethod
    def get_by_decision(session: Session, decision_id: str) -> list[dict]:
        rows = session.execute(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.decision_id == decision_id
            ).order_by(ResearchArtifactModel.created_at)
        ).scalars().all()
        return [
            {
                "artifact_id": r.artifact_id,
                "type": r.artifact_type,
                "title": r.title,
                "lock_state": r.lock_state,
            }
            for r in rows
        ]


class ResearchCacheRepository:
    """Drop-in replacement for DiskCache using CockroachDB."""

    @staticmethod
    def _make_hash(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def get(session: Session, key: str) -> Optional[dict]:
        cache_hash = ResearchCacheRepository._make_hash(key)
        row = session.execute(
            select(ResearchCacheModel).where(
                ResearchCacheModel.cache_key == key
            )
        ).scalars().first()
        if row and row.expires_at and row.expires_at > datetime.now(row.expires_at.tzinfo):
            return row.value_json
        return None

    @staticmethod
    def set(session: Session, key: str, value: dict, ttl: int = 86400) -> None:
        from datetime import timedelta
        cache_hash = ResearchCacheRepository._make_hash(key)
        expires = datetime.now() + timedelta(seconds=ttl)
        existing = session.execute(
            select(ResearchCacheModel).where(
                ResearchCacheModel.cache_key == key
            )
        ).scalars().first()
        if existing:
            existing.value_json = value
            existing.cache_hash = cache_hash
            existing.expires_at = expires
            existing.hits += 1
        else:
            session.add(ResearchCacheModel(
                cache_key=key,
                cache_hash=cache_hash,
                value_json=value,
                ttl_seconds=ttl,
                expires_at=expires,
            ))


class ApiCallLogRepository:
    @staticmethod
    def get_stats(session: Session) -> dict:
        total = session.execute(
            select(func.count()).select_from(ApiCallLogModel)
        ).scalar() or 0
        cached = session.execute(
            select(func.count()).select_from(ApiCallLogModel).where(
                ApiCallLogModel.cached == True
            )
        ).scalar() or 0
        by_source = session.execute(
            select(
                ApiCallLogModel.api_source,
                func.count().label("calls"),
                func.avg(ApiCallLogModel.response_time_ms).label("avg_ms"),
            ).group_by(ApiCallLogModel.api_source)
        ).all()
        return {
            "total_calls": total,
            "cached_hits": cached,
            "cache_hit_rate": round(cached / total * 100, 1) if total > 0 else 0,
            "by_source": [
                {"source": r.api_source, "calls": r.calls,
                 "avg_ms": round(float(r.avg_ms or 0), 1)}
                for r in by_source
            ],
        }


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

def health_check() -> dict:
    """Verify CockroachDB connection and return cluster info."""
    session = get_session()
    try:
        row = session.execute(func.current_timestamp()).scalar()
        case_count = session.execute(
            select(func.count()).select_from(DecisionCaseModel)
        ).scalar()
        artifact_count = session.execute(
            select(func.count()).select_from(ResearchArtifactModel)
        ).scalar()
        cache_count = session.execute(
            select(func.count()).select_from(ResearchCacheModel)
        ).scalar()
        return {
            "status": "ok",
            "connected": True,
            "server_time": str(row),
            "decision_cases": case_count,
            "research_artifacts": artifact_count,
            "cache_entries": cache_count,
            "backend": "CockroachDB",
        }
    except Exception as e:
        return {"status": "error", "connected": False, "error": str(e)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

def create_tables():
    """Create all tables in CockroachDB."""
    Base.metadata.create_all(bind=engine)
    logger.info("All tables created successfully")


if __name__ == "__main__":
    create_tables()
    print("Tables created.")
    print(health_check())
