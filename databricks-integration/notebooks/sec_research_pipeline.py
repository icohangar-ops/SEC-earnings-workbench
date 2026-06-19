# Databricks notebook source
# MAGIC %md
# MAGIC # SEC Earnings Workbench — Databricks Research Pipeline
# MAGIC
# MAGIC EDGAR filing ingestion, XBRL financial analysis, and multi-agent
# MAGIC research tracking on Delta Lake.

# COMMAND ----------

# MAGIC %pip install requests

# COMMAND ----------

import mlflow
from pyspark.sql import functions as F

CATALOG = "sec_workbench"
SCHEMA = "edgar_data"

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

mlflow.set_experiment("/Shared/SEC-Workbench/research")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configure Research Universe

# COMMAND ----------

# Research targets
PRIMARY_TICKER = "AAPL"
PEER_TICKERS = ["MSFT", "GOOGL", "META", "AMZN"]
ALL_TICKERS = [PRIMARY_TICKER] + PEER_TICKERS
FILING_TYPES = ["10-K", "10-Q", "8-K"]

print(f"Primary: {PRIMARY_TICKER}")
print(f"Peers: {PEER_TICKERS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Ingest EDGAR Filings (Bronze)

# COMMAND ----------

# MAGIC %run ../pipelines/edgar_lakehouse

# COMMAND ----------

filings_df = ingest_filings(ALL_TICKERS, FILING_TYPES)
print(f"\nTotal filings ingested: {filings_df.count()}")
display(filings_df.orderBy(F.desc("filing_date")).limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Ingest XBRL Financial Facts (Bronze)

# COMMAND ----------

xbrl_df = ingest_xbrl_facts(ALL_TICKERS)
print(f"\nTotal XBRL facts: {xbrl_df.count()}")

concept_counts = xbrl_df.groupBy("ticker", "concept").count().orderBy("ticker", F.desc("count"))
display(concept_counts.limit(30))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Build Financial Metrics (Silver)

# COMMAND ----------

financials = build_silver_financials()
display(financials.orderBy("ticker", F.desc("fiscal_year")).limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Earnings Quality Analysis

# COMMAND ----------

quality = financials.select(
    "ticker", "fiscal_year", "fiscal_period",
    "earnings_quality", "earnings_quality_flag",
    "fcf_ni_divergence", "revenue_growth_pct"
).filter(F.col("earnings_quality").isNotNull())

display(quality.orderBy("ticker", F.desc("fiscal_year")))

# Low quality flags
low_quality = quality.filter(F.col("earnings_quality_flag") == "LOW_QUALITY")
if low_quality.count() > 0:
    print(f"⚠ {low_quality.count()} LOW_QUALITY earnings periods detected:")
    display(low_quality)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Peer Comparison (Gold)

# COMMAND ----------

peers = build_gold_peer_comparison(ALL_TICKERS)
display(peers)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Run Tracked Multi-Agent Research

# COMMAND ----------

# MAGIC %run ../pipelines/agent_tracking

# COMMAND ----------

from pipelines.agent_tracking import run_tracked_research

run_id = run_tracked_research(PRIMARY_TICKER, peers=PEER_TICKERS)
print(f"Research run: {run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Store Agent Memo to Gold Layer

# COMMAND ----------

sample_memo = {
    "business_model": f"{PRIMARY_TICKER} is a consumer electronics and services company",
    "revenue_drivers": ["iPhone", "Services", "Mac", "iPad", "Wearables"],
    "financial_health": {
        "current_ratio": 1.07,
        "debt_to_equity": 1.76,
        "fcf_yield_pct": 3.8,
    },
    "thesis": "Services growth offsets hardware cyclicality",
}

store_agent_memo(
    ticker=PRIMARY_TICKER,
    agent_name="FundamentalsAgent",
    memo_type="business_model",
    content=sample_memo,
    run_id=run_id,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Pipeline Summary

# COMMAND ----------

print("=== EDGAR Lakehouse Summary ===")
for table in [
    "bronze_filings", "bronze_xbrl_facts",
    "silver_financials",
    "gold_peer_comparison", "gold_agent_memos",
]:
    try:
        count = spark.read.format("delta").table(f"{CATALOG}.{SCHEMA}.{table}").count()
        print(f"  {table}: {count} rows")
    except Exception:
        print(f"  {table}: not yet created")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Review MLflow Experiments

# COMMAND ----------

experiment = mlflow.get_experiment_by_name("/Shared/SEC-Workbench/research")
if experiment:
    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
        max_results=10,
    )
    display(runs[["run_id", "tags.ticker", "tags.pipeline", "metrics.total_pipeline_duration_s", "status"]])
