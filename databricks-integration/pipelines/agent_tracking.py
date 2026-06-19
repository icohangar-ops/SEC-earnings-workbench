"""
SEC-earnings-workbench — MLflow Agent Tracking

Wraps the multi-agent research pipeline (Fundamentals → Diligence → Markets)
with MLflow experiment tracking. Each agent run is logged as a nested MLflow
run with its inputs, outputs, CHP decision state, and latency metrics.

Compatible with the existing EnterpriseOrchestrator and ContextEngine.
"""

import mlflow
import json
import time
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


EXPERIMENT_NAME = "/Shared/SEC-Workbench/research"


@dataclass
class AgentRunResult:
    agent_name: str
    ticker: str
    memo_type: str
    entities_produced: list[str]
    entities_consumed: list[str]
    duration_seconds: float
    chp_state: str
    confidence_pct: float
    content: dict


def log_research_pipeline(
    ticker: str,
    fundamentals_result: AgentRunResult,
    diligence_result: AgentRunResult,
    markets_result: AgentRunResult,
    chp_final_state: str = "LOCKED",
):
    """
    Log a complete multi-agent research pipeline to MLflow.

    The three agents run in dependency order:
      FundamentalsAgent → DiligenceAgent + MarketsAgent (parallel)

    Each agent is logged as a nested run under the parent pipeline run.
    """
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name=f"research_{ticker}") as parent_run:
        mlflow.set_tag("ticker", ticker)
        mlflow.set_tag("pipeline", "multi_agent_research")
        mlflow.set_tag("chp_final_state", chp_final_state)

        total_duration = (
            fundamentals_result.duration_seconds
            + max(diligence_result.duration_seconds, markets_result.duration_seconds)
        )
        mlflow.log_metric("total_pipeline_duration_s", total_duration)

        for result in [fundamentals_result, diligence_result, markets_result]:
            with mlflow.start_run(
                run_name=f"{result.agent_name}_{ticker}",
                nested=True,
            ):
                mlflow.set_tag("agent", result.agent_name)
                mlflow.set_tag("ticker", ticker)
                mlflow.set_tag("memo_type", result.memo_type)
                mlflow.set_tag("chp_state", result.chp_state)

                mlflow.log_param("entities_consumed", str(result.entities_consumed))
                mlflow.log_param("entities_produced", str(result.entities_produced))

                mlflow.log_metric("duration_seconds", result.duration_seconds)
                mlflow.log_metric("confidence_pct", result.confidence_pct)
                mlflow.log_metric("entity_count", len(result.entities_produced))

                mlflow.log_dict(result.content, f"{result.memo_type}.json")

        avg_confidence = (
            fundamentals_result.confidence_pct
            + diligence_result.confidence_pct
            + markets_result.confidence_pct
        ) / 3
        mlflow.log_metric("avg_confidence_pct", avg_confidence)

        total_entities = (
            len(fundamentals_result.entities_produced)
            + len(diligence_result.entities_produced)
            + len(markets_result.entities_produced)
        )
        mlflow.log_metric("total_entities_produced", total_entities)

        return parent_run.info.run_id


def run_tracked_research(ticker: str, peers: list[str] = None):
    """
    Execute a tracked research pipeline.

    In production, this calls the actual EnterpriseOrchestrator.
    This scaffold demonstrates the MLflow tracking pattern.
    """
    if peers is None:
        peers = []

    # Simulate FundamentalsAgent
    fundamentals = AgentRunResult(
        agent_name="FundamentalsAgent",
        ticker=ticker,
        memo_type="business_model",
        entities_produced=["business_model", "revenue_drivers", "financial_health"],
        entities_consumed=[],
        duration_seconds=12.5,
        chp_state="PROVISIONAL_LOCK",
        confidence_pct=88.0,
        content={
            "business_model": f"{ticker} operates in...",
            "revenue_drivers": ["segment_a", "segment_b"],
            "financial_health": {
                "current_ratio": 1.8,
                "debt_to_equity": 0.45,
                "fcf_yield_pct": 4.2,
            },
        },
    )

    # Simulate DiligenceAgent (depends on business_model)
    diligence = AgentRunResult(
        agent_name="DiligenceAgent",
        ticker=ticker,
        memo_type="red_flag_scan",
        entities_produced=["red_flag_scan", "governance_read", "risk_register"],
        entities_consumed=["business_model"],
        duration_seconds=8.3,
        chp_state="PROVISIONAL_LOCK",
        confidence_pct=92.0,
        content={
            "red_flags": [],
            "governance_score": "B+",
            "risk_register": [
                {"risk": "concentration_risk", "severity": "medium"},
                {"risk": "regulatory_exposure", "severity": "low"},
            ],
        },
    )

    # Simulate MarketsAgent (depends on business_model)
    markets = AgentRunResult(
        agent_name="MarketsAgent",
        ticker=ticker,
        memo_type="peer_view",
        entities_produced=["peer_view", "valuation_view", "thesis_triggers"],
        entities_consumed=["business_model"],
        duration_seconds=10.1,
        chp_state="PROVISIONAL_LOCK",
        confidence_pct=85.0,
        content={
            "peer_set": peers,
            "relative_valuation": "in-line",
            "thesis_triggers": [
                {"trigger": "margin_expansion", "probability": 0.6},
                {"trigger": "new_market_entry", "probability": 0.3},
            ],
        },
    )

    run_id = log_research_pipeline(
        ticker=ticker,
        fundamentals_result=fundamentals,
        diligence_result=diligence,
        markets_result=markets,
        chp_final_state="LOCKED",
    )

    print(f"Research pipeline complete for {ticker}. Run ID: {run_id}")
    return run_id


if __name__ == "__main__":
    run_tracked_research("AAPL", peers=["MSFT", "GOOGL", "META"])
