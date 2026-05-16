# Cell 1 — Install dependencies
# ============================================================
# SEC Earnings Workbench — Fabric Lakehouse Table Setup
# Creates all Delta tables for the research pipeline.
# ============================================================

# %%
# Cell 2 — sec_filings: SEC EDGAR filing metadata
# ============================================================
sec_filings_seed = [
    {
        "cik": 320193,
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "accession_no": "0000320193-24-000123",
        "primary_document": "a10-k2024928.htm",
        "is_xbrl": True,
        "ingested_at": "2025-05-03T00:00:00Z",
    },
    {
        "cik": 320193,
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "form": "10-Q",
        "filing_date": "2025-02-01",
        "report_date": "2024-12-28",
        "accession_no": "0000320193-25-000012",
        "primary_document": "a10-q20241228.htm",
        "is_xbrl": True,
        "ingested_at": "2025-05-03T00:00:00Z",
    },
    {
        "cik": 789019,
        "ticker": "MSFT",
        "company_name": "Microsoft Corp.",
        "form": "10-K",
        "filing_date": "2024-10-25",
        "report_date": "2024-06-30",
        "accession_no": "0000789019-24-000456",
        "primary_document": "a10-k20240630.htm",
        "is_xbrl": True,
        "ingested_at": "2025-05-03T00:00:00Z",
    },
]

sec_filings_df = spark.createDataFrame(sec_filings_seed)
sec_filings_df.write.format("delta").mode("overwrite").saveAsTable("sec_filings")
print(f"sec_filings: {spark.table('sec_filings').count()} records")

# %%
# Cell 3 — company_fundamentals: AlphaVantage overview snapshots
# ============================================================
fundamentals_seed = [
    {
        "ticker": "AAPL",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3500000000000,
        "pe_ratio": 35.2,
        "forward_pe": 30.1,
        "profit_margin": 0.263,
        "operating_margin_ttm": 0.298,
        "revenue_ttm": 394000000000,
        "eps_ttm": 6.52,
        "beta": 1.25,
        "week52_low": 164.08,
        "week52_high": 260.10,
        "shares_outstanding": 15115000000,
        "latest_quarter": "2024-09-28",
        "dividend_yield": 0.005,
        "source": "AlphaVantage",
        "pulled_at": "2025-05-03T00:00:00Z",
    },
    {
        "ticker": "MSFT",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "market_cap": 3100000000000,
        "pe_ratio": 37.8,
        "forward_pe": 33.5,
        "profit_margin": 0.351,
        "operating_margin_ttm": 0.442,
        "revenue_ttm": 245000000000,
        "eps_ttm": 11.41,
        "beta": 0.89,
        "week52_low": 362.90,
        "week52_high": 468.35,
        "shares_outstanding": 7432000000,
        "latest_quarter": "2024-06-30",
        "dividend_yield": 0.007,
        "source": "AlphaVantage",
        "pulled_at": "2025-05-03T00:00:00Z",
    },
    {
        "ticker": "GOOGL",
        "sector": "Communication Services",
        "industry": "Internet Content & Information",
        "market_cap": 2100000000000,
        "pe_ratio": 24.5,
        "forward_pe": 22.1,
        "profit_margin": 0.241,
        "operating_margin_ttm": 0.321,
        "revenue_ttm": 340000000000,
        "eps_ttm": 6.79,
        "beta": 1.06,
        "week52_low": 141.80,
        "week52_high": 191.75,
        "shares_outstanding": 12220000000,
        "latest_quarter": "2024-09-30",
        "dividend_yield": 0.005,
        "source": "AlphaVantage",
        "pulled_at": "2025-05-03T00:00:00Z",
    },
]

fundamentals_df = spark.createDataFrame(fundamentals_seed)
fundamentals_df.write.format("delta").mode("overwrite").saveAsTable("company_fundamentals")
print(f"company_fundamentals: {spark.table('company_fundamentals').count()} records")

# %%
# Cell 4 — macro_indicators: FRED macro panel snapshots
# ============================================================
macro_seed = [
    {"series_id": "DGS10", "label": "10-Year Treasury Yield", "value": 4.52, "as_of": "2025-05-02", "source": "FRED", "pulled_at": "2025-05-03T00:00:00Z"},
    {"series_id": "DGS2", "label": "2-Year Treasury Yield", "value": 4.28, "as_of": "2025-05-02", "source": "FRED", "pulled_at": "2025-05-03T00:00:00Z"},
    {"series_id": "DFF", "label": "Federal Funds Effective Rate", "value": 5.33, "as_of": "2025-05-01", "source": "FRED", "pulled_at": "2025-05-03T00:00:00Z"},
    {"series_id": "T10Y2Y", "label": "10Y-2Y Yield Spread", "value": 0.24, "as_of": "2025-05-02", "source": "FRED", "pulled_at": "2025-05-03T00:00:00Z"},
    {"series_id": "CPIAUCSL", "label": "CPI All Urban Consumers (SA)", "value": 314.54, "as_of": "2025-03-01", "source": "FRED", "pulled_at": "2025-05-03T00:00:00Z"},
    {"series_id": "UNRATE", "label": "Unemployment Rate", "value": 4.2, "as_of": "2025-04-01", "source": "FRED", "pulled_at": "2025-05-03T00:00:00Z"},
]

macro_df = spark.createDataFrame(macro_seed)
macro_df.write.format("delta").mode("overwrite").saveAsTable("macro_indicators")
print(f"macro_indicators: {spark.table('macro_indicators').count()} records")

# %%
# Cell 5 — research_sessions: CHP DecisionCase + session metadata
# ============================================================
sessions_seed = [
    {
        "decision_id": "demo-session-001",
        "title": "MSFT Initiation of Coverage",
        "task_type": "initiation",
        "company": "Microsoft Corp.",
        "ticker": "MSFT",
        "industry": "Software/Cloud",
        "status": "EXPLORING",
        "foundation_score": 72,
        "r0_verdict": "PASS",
        "foundation_verdict": "PASS",
        "origin_model": "Kimi-K2.6",
        "partner_model": "GPT-4o",
        "created_at": "2025-05-03T00:00:00Z",
    },
]

sessions_df = spark.createDataFrame(sessions_seed)
sessions_df.write.format("delta").mode("overwrite").saveAsTable("research_sessions")
print(f"research_sessions: {spark.table('research_sessions').count()} records")

# %%
# Cell 6 — agent_outputs: Per-agent turn results and recommendations
# ============================================================
agent_outputs_seed = [
    {
        "decision_id": "demo-session-001",
        "agent_name": "fundamentals",
        "recommendation": "Map Azure ARR growth + Copilot attach rate as primary revenue drivers",
        "confidence": "HIGH",
        "playbook_deltas": 0,
        "produces": "business_model,revenue_drivers,financial_health",
        "consumes": "",
        "failure_mode": None,
        "ran_at": "2025-05-03T00:00:00Z",
    },
    {
        "decision_id": "demo-session-001",
        "agent_name": "diligence",
        "recommendation": "No material weakness; GAAP-to-non-GAAP reconciliation clean; SBC ~3% of revenue",
        "confidence": "HIGH",
        "playbook_deltas": 0,
        "produces": "red_flag_scan,governance_read,risk_register",
        "consumes": "business_model",
        "failure_mode": None,
        "ran_at": "2025-05-03T00:00:01Z",
    },
    {
        "decision_id": "demo-session-001",
        "agent_name": "markets",
        "recommendation": "EV/EBITDA 28x vs peer median 24x; premium justified by cloud growth margin expansion",
        "confidence": "HIGH",
        "playbook_deltas": 0,
        "produces": "peer_view,valuation_view,thesis_triggers",
        "consumes": "business_model",
        "failure_mode": None,
        "ran_at": "2025-05-03T00:00:02Z",
    },
]

agent_outputs_df = spark.createDataFrame(agent_outputs_seed)
agent_outputs_df.write.format("delta").mode("overwrite").saveAsTable("agent_outputs")
print(f"agent_outputs: {spark.table('agent_outputs').count()} records")

# %%
# Cell 7 — research_artifacts: Final generated research reports
# ============================================================
artifacts_seed = [
    {
        "decision_id": "demo-session-001",
        "artifact_type": "initiation_of_coverage",
        "title": "Initiation of Coverage - Microsoft Corp. (MSFT)",
        "lock_state": "PROVISIONAL_LOCK",
        "rating_seed": "Buy",
        "target_price": 520.0,
        "valuation_method": "EV/EBITDA",
        "peers": "GOOGL,AMZN,ORCL",
        "artifact_md": "# Initiation of Coverage - Microsoft Corp. (MSFT)\n\n_Demo seed — full artifact generated by pipeline_",
        "sources": "AlphaVantage OVERVIEW / GLOBAL_QUOTE / INCOME_STATEMENT / EARNINGS; FRED macro panel; SEC EDGAR",
        "created_at": "2025-05-03T00:00:03Z",
    },
]

artifacts_df = spark.createDataFrame(artifacts_seed)
artifacts_df.write.format("delta").mode("overwrite").saveAsTable("research_artifacts")
print(f"research_artifacts: {spark.table('research_artifacts').count()} records")

# %%
# Cell 8 — audit_trail: Per-claim provenance tracking
# ============================================================
audit_seed = [
    {
        "decision_id": "demo-session-001",
        "agent": "fundamentals",
        "claim": "Reframe",
        "expansion_excerpt": "Subject: MSFT. Reframe as a business-model and earnings-quality question",
        "grounding_source": "alphavantage.OVERVIEW",
        "grounding_confidence": "HIGH",
        "risk_flag": None,
        "logged_at": "2025-05-03T00:00:00Z",
    },
    {
        "decision_id": "demo-session-001",
        "agent": "diligence",
        "claim": "Constraints",
        "expansion_excerpt": "Every flag must cite a filing type + filing date",
        "grounding_source": "SEC EDGAR",
        "grounding_confidence": "HIGH",
        "risk_flag": None,
        "logged_at": "2025-05-03T00:00:01Z",
    },
    {
        "decision_id": "demo-session-001",
        "agent": "markets",
        "claim": "Assumptions",
        "expansion_excerpt": "Peer set is comparable on demand factor and capital intensity",
        "grounding_source": "FRED",
        "grounding_confidence": "MEDIUM",
        "risk_flag": None,
        "logged_at": "2025-05-03T00:00:02Z",
    },
]

audit_df = spark.createDataFrame(audit_seed)
audit_df.write.format("delta").mode("overwrite").saveAsTable("audit_trail")
print(f"audit_trail: {spark.table('audit_trail').count()} records")

# %%
# Cell 9 — peer_comparisons: Cross-company comparative analysis results (new for peer batch pipeline)
# ============================================================
peer_comparisons_seed = [
    {
        "batch_id": "demo-batch-001",
        "primary_ticker": "MSFT",
        "primary_company": "Microsoft Corp.",
        "peer_tickers": "GOOGL,AMZN,ORCL",
        "industry": "Software/Cloud",
        "comparative_md": "# Peer Group Comparative Analysis\n\n_Demo seed — full comparative analysis generated by peer batch pipeline_",
        "companies_processed": 4,
        "avg_foundation_score": 0,
        "pass_count": 0,
        "reframe_count": 0,
        "fail_count": 0,
        "av_calls_used": 0,
        "duration_seconds": 0.0,
        "macro_json": "[]",
        "created_at": "2025-05-03T00:00:00Z",
    },
]

peer_comparisons_df = spark.createDataFrame(peer_comparisons_seed)
peer_comparisons_df.write.format("delta").mode("overwrite").saveAsTable("peer_comparisons")
print(f"peer_comparisons: {spark.table('peer_comparisons').count()} records")

# %%
# Cell 10 — Verify all tables
# ============================================================
tables = ["sec_filings", "company_fundamentals", "macro_indicators",
          "research_sessions", "agent_outputs", "research_artifacts", "audit_trail",
          "peer_comparisons"]

print("=" * 60)
print("SEC Earnings Workbench — Lakehouse Delta Tables Created")
print("=" * 60)
for t in tables:
    count = spark.table(t).count()
    print(f"  {t}: {count} records")
print("=" * 60)
print("All 8 Delta tables ready in Fabric Lakehouse!")
