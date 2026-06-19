"""
SEC-earnings-workbench — Delta Lake EDGAR Pipeline

Medallion architecture for SEC filing analysis at scale:

  Bronze: Raw EDGAR filings (10-K, 10-Q, 8-K, DEF 14A), XBRL facts, company metadata
  Silver: Extracted sections, financial ratios, earnings quality metrics
  Gold:   Multi-agent research memos, peer comparisons, thesis triggers

Replaces the SQLAlchemy/PostgreSQL storage with Delta Lake + Unity Catalog
while preserving compatibility with the existing multi-agent orchestrator.
"""

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window
from delta.tables import DeltaTable
import mlflow
import requests
import json
import re
import os
from datetime import datetime, timezone
from html.parser import HTMLParser


CATALOG = os.environ.get("DATABRICKS_CATALOG", "sec_workbench")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "edgar_data")
USER_AGENT = os.environ.get("EDGAR_USER_AGENT", "CritMinResearch research@example.com")
SEC_BASE = "https://efts.sec.gov/LATEST"
EDGAR_BASE = "https://data.sec.gov"


def get_spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()


class HTMLTextExtractor(HTMLParser):
    """Strip HTML tags to extract plain text from SEC filings."""

    def __init__(self):
        super().__init__()
        self.result = []

    def handle_data(self, data):
        self.result.append(data)

    def get_text(self):
        return " ".join(self.result)


def strip_html(html: str) -> str:
    extractor = HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


# ---------------------------------------------------------------------------
# EDGAR API Helpers
# ---------------------------------------------------------------------------


def _sec_headers():
    return {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def fetch_company_tickers() -> dict:
    """Fetch the SEC company tickers mapping."""
    url = f"{EDGAR_BASE}/files/company_tickers.json"
    resp = requests.get(url, headers=_sec_headers(), timeout=15)
    return resp.json()


def cik_for_ticker(ticker: str) -> str:
    """Resolve ticker to zero-padded CIK."""
    tickers = fetch_company_tickers()
    for entry in tickers.values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker {ticker} not found in SEC database")


def fetch_recent_filings(ticker: str, forms: list[str] = None, limit: int = 40) -> list[dict]:
    """Fetch recent filings for a company from EDGAR."""
    if forms is None:
        forms = ["10-K", "10-Q", "8-K"]

    cik = cik_for_ticker(ticker)
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=_sec_headers(), timeout=15)
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    filings = []
    for i in range(min(limit, len(recent.get("form", [])))):
        form = recent["form"][i]
        if form in forms:
            filings.append({
                "ticker": ticker.upper(),
                "cik": cik,
                "form": form,
                "filing_date": recent["filingDate"][i],
                "accession_number": recent["accessionNumber"][i],
                "primary_document": recent.get("primaryDocument", [""])[i] if i < len(recent.get("primaryDocument", [])) else "",
                "company_name": data.get("name", ""),
            })

    return filings


def fetch_company_facts(ticker: str) -> dict:
    """Fetch XBRL financial facts for a company."""
    cik = cik_for_ticker(ticker)
    url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    resp = requests.get(url, headers=_sec_headers(), timeout=15)
    return resp.json()


# ---------------------------------------------------------------------------
# Bronze Layer — Raw EDGAR Ingestion
# ---------------------------------------------------------------------------


def ingest_filings(tickers: list[str], forms: list[str] = None) -> DataFrame:
    """Fetch and store filing metadata for multiple tickers."""
    spark = get_spark()

    all_filings = []
    for ticker in tickers:
        try:
            filings = fetch_recent_filings(ticker, forms)
            for f in filings:
                f["ingested_at"] = datetime.now(timezone.utc).isoformat()
            all_filings.extend(filings)
            print(f"  {ticker}: {len(filings)} filings")
        except Exception as e:
            print(f"  [WARN] {ticker}: {e}")

    if not all_filings:
        print("[WARN] No filings ingested")
        return spark.createDataFrame([], T.StructType([]))

    df = spark.createDataFrame(all_filings)
    df = df.withColumn("filing_date", F.to_date("filing_date"))
    df = df.withColumn("ingested_at", F.to_timestamp("ingested_at"))

    bronze_table = f"{CATALOG}.{SCHEMA}.bronze_filings"
    df.write.format("delta").mode("append").saveAsTable(bronze_table)

    print(f"[Bronze] Ingested {len(all_filings)} filings -> {bronze_table}")
    return df


def ingest_xbrl_facts(tickers: list[str]) -> DataFrame:
    """Fetch and store XBRL financial facts."""
    spark = get_spark()

    all_facts = []
    for ticker in tickers:
        try:
            facts_data = fetch_company_facts(ticker)
            us_gaap = facts_data.get("facts", {}).get("us-gaap", {})

            for concept, details in us_gaap.items():
                for unit_type, entries in details.get("units", {}).items():
                    for entry in entries[-20:]:  # last 20 periods
                        all_facts.append({
                            "ticker": ticker.upper(),
                            "concept": concept,
                            "unit": unit_type,
                            "value": float(entry.get("val", 0)),
                            "end_date": entry.get("end", ""),
                            "filed_date": entry.get("filed", ""),
                            "form": entry.get("form", ""),
                            "fiscal_year": entry.get("fy", 0),
                            "fiscal_period": entry.get("fp", ""),
                            "ingested_at": datetime.now(timezone.utc).isoformat(),
                        })
            print(f"  {ticker}: {len([f for f in all_facts if f['ticker'] == ticker.upper()])} facts")
        except Exception as e:
            print(f"  [WARN] {ticker} XBRL: {e}")

    if not all_facts:
        return spark.createDataFrame([], T.StructType([]))

    df = spark.createDataFrame(all_facts)
    df = df.withColumn("end_date", F.to_date("end_date"))
    df = df.withColumn("filed_date", F.to_date("filed_date"))
    df = df.withColumn("ingested_at", F.to_timestamp("ingested_at"))

    bronze_table = f"{CATALOG}.{SCHEMA}.bronze_xbrl_facts"
    df.write.format("delta").mode("append").saveAsTable(bronze_table)

    print(f"[Bronze] Ingested {len(all_facts)} XBRL facts -> {bronze_table}")
    return df


# ---------------------------------------------------------------------------
# Silver Layer — Financial Metrics + Earnings Quality
# ---------------------------------------------------------------------------


def build_silver_financials() -> DataFrame:
    """
    Compute financial ratios and earnings quality metrics from XBRL data.
    Replicates the cme.finance module logic:
    - FCF vs Net Income divergence
    - Earnings quality ratios
    - Revenue growth
    """
    spark = get_spark()

    facts = spark.read.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_xbrl_facts")

    # Pivot key concepts into columns per ticker/period
    key_concepts = [
        "Revenues", "NetIncomeLoss", "OperatingIncomeLoss",
        "CashAndCashEquivalentsAtCarryingValue",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "Assets", "Liabilities", "StockholdersEquity",
    ]

    filtered = facts.filter(F.col("concept").isin(key_concepts))

    pivoted = (
        filtered
        .filter(F.col("form").isin(["10-K", "10-Q"]))
        .groupBy("ticker", "fiscal_year", "fiscal_period")
        .pivot("concept")
        .agg(F.last("value"))
    )

    revenue_col = "Revenues"
    net_income_col = "NetIncomeLoss"
    op_cf_col = "NetCashProvidedByUsedInOperatingActivities"
    capex_col = "PaymentsToAcquirePropertyPlantAndEquipment"

    silver = pivoted
    if revenue_col in [c for c in pivoted.columns]:
        window = Window.partitionBy("ticker").orderBy("fiscal_year", "fiscal_period")
        silver = silver.withColumn(
            "prev_revenue", F.lag(revenue_col).over(window)
        )
        silver = silver.withColumn(
            "revenue_growth_pct",
            F.when(
                F.col("prev_revenue").isNotNull() & (F.col("prev_revenue") != 0),
                (F.col(revenue_col) - F.col("prev_revenue")) / F.abs(F.col("prev_revenue")) * 100
            )
        )

    if net_income_col in pivoted.columns and op_cf_col in pivoted.columns:
        silver = silver.withColumn(
            "fcf",
            F.col(op_cf_col) - F.coalesce(F.col(capex_col), F.lit(0))
            if capex_col in pivoted.columns
            else F.col(op_cf_col)
        )
        silver = silver.withColumn(
            "fcf_ni_divergence",
            F.when(
                F.col(net_income_col) != 0,
                (F.col("fcf") - F.col(net_income_col)) / F.abs(F.col(net_income_col)) * 100
            )
        )
        silver = silver.withColumn(
            "earnings_quality",
            F.when(
                F.col(net_income_col) != 0,
                F.col(op_cf_col) / F.col(net_income_col)
            )
        )
        silver = silver.withColumn(
            "earnings_quality_flag",
            F.when(F.col("earnings_quality") < 0.8, "LOW_QUALITY")
            .when(F.col("earnings_quality") > 1.5, "CASH_RICH")
            .otherwise("NORMAL")
        )

    silver_table = f"{CATALOG}.{SCHEMA}.silver_financials"
    silver.write.format("delta").mode("overwrite").saveAsTable(silver_table)

    print(f"[Silver] Financial metrics -> {silver_table}")
    return silver


# ---------------------------------------------------------------------------
# Gold Layer — Research Memos + Agent Outputs
# ---------------------------------------------------------------------------


def store_agent_memo(
    ticker: str,
    agent_name: str,
    memo_type: str,
    content: dict,
    run_id: str = "",
) -> DataFrame:
    """
    Store multi-agent research memo output to Gold layer.
    Compatible with the ContextEngine entity model from SEC-earnings-workbench.
    """
    spark = get_spark()

    row = {
        "ticker": ticker.upper(),
        "agent_name": agent_name,
        "memo_type": memo_type,
        "content_json": json.dumps(content),
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    df = spark.createDataFrame([row])
    df = df.withColumn("created_at", F.to_timestamp("created_at"))

    gold_table = f"{CATALOG}.{SCHEMA}.gold_agent_memos"
    df.write.format("delta").mode("append").saveAsTable(gold_table)

    print(f"[Gold] {agent_name}/{memo_type} for {ticker} -> {gold_table}")
    return df


def build_gold_peer_comparison(tickers: list[str]) -> DataFrame:
    """Build peer comparison table from Silver financials."""
    spark = get_spark()

    silver = spark.read.format("delta").table(f"{CATALOG}.{SCHEMA}.silver_financials")

    latest = (
        silver
        .filter(F.col("ticker").isin([t.upper() for t in tickers]))
        .withColumn("rn", F.row_number().over(
            Window.partitionBy("ticker").orderBy(F.desc("fiscal_year"), F.desc("fiscal_period"))
        ))
        .filter(F.col("rn") == 1)
        .drop("rn")
    )

    gold_table = f"{CATALOG}.{SCHEMA}.gold_peer_comparison"
    latest.write.format("delta").mode("overwrite").saveAsTable(gold_table)

    print(f"[Gold] Peer comparison for {tickers} -> {gold_table}")
    return latest


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


def run_full_pipeline(tickers: list[str], forms: list[str] = None):
    """Execute the complete EDGAR -> Delta Lake pipeline."""
    if forms is None:
        forms = ["10-K", "10-Q", "8-K"]

    with mlflow.start_run(run_name=f"edgar_pipeline_{'_'.join(tickers[:3])}"):
        mlflow.set_tag("pipeline", "sec_earnings_workbench")
        mlflow.set_tag("tickers", ",".join(tickers))

        # Bronze
        filings_df = ingest_filings(tickers, forms)
        mlflow.log_metric("filings_ingested", filings_df.count() if filings_df.columns else 0)

        xbrl_df = ingest_xbrl_facts(tickers)
        mlflow.log_metric("xbrl_facts_ingested", xbrl_df.count() if xbrl_df.columns else 0)

        # Silver
        financials = build_silver_financials()
        mlflow.log_metric("financial_metrics_rows", financials.count())

        # Gold
        peers = build_gold_peer_comparison(tickers)
        mlflow.log_metric("peer_comparison_rows", peers.count())

        print(f"EDGAR pipeline complete for {tickers}")


if __name__ == "__main__":
    run_full_pipeline(["AAPL", "MSFT", "GOOGL", "TSLA"])
