# Airbyte Agents Integration — SEC / Earnings / Company Research Workbench

This document describes how [Airbyte Agents](https://docs.airbyte.com/ai-agents) can enrich your multi-agent research workbench with live data from CRM, support, financial, and analytics connectors.

---

## Overview

Airbyte Agents provides a data and context layer for AI agents. For this workbench, it can:

- **Replace direct API calls** to AlphaVantage, FRED, and SEC EDGAR with managed connectors
- **Add new data domains** (Gong transcripts, Crunchbase funding, Glassdoor reviews, news feeds)
- **Provide MCP-based access** for Claude/Codex agents during research sessions

**Integration options:**
- **[MCP](https://docs.airbyte.com/ai-agents/interfaces/mcp)** — Remote Model Context Protocol server. Best for conversational data access.
- **[SDK](https://docs.airbyte.com/ai-agents/interfaces/sdk)** — Typed Python library. Best for programmatic access in notebooks and pipelines.
- **[CLI/API](https://docs.airbyte.com/ai-agents/interfaces/sdk)** — Shell and HTTP interfaces.

---

## Integration Points

### 1. Data Source Replacement (src/cme/research/data/)

The existing data clients fetch data directly via REST APIs with manual caching. Airbyte connectors can replace these with managed, incremental syncs.

| Current Client | File | Airbyte Alternative | Benefit |
|---------------|------|--------------------|---------|
| `AlphaVantageClient` | `src/cme/research/data/alphavantage.py` | Airbyte AlphaVantage (or FRED, Twelve Data) | Incremental syncs, schema normalization, no 25 req/day limit |
| `FredClient` | `src/cme/research/data/fred.py` | Airbyte FRED connector | Managed API key, scheduled syncs, automatic backfill |
| `EdgarClient` | `src/cme/research/data/edgar.py` | Airbyte SEC EDGAR (custom or generic HTTP source) | No fragile HTML parsing, structured data, incremental filing updates |

**Example — Replacing `FredClient` with Airbyte SDK:**

```python
from airbyte_agent_sdk import connect

async def fetch_macro_panel() -> dict:
    fred = connect("fred")
    try:
        result = await fred.execute("observations", "list", params={
            "series_id": "DGS10,DGS2,DFF,CPIAUCSL,UNRATE",
            "sort_order": "desc",
            "limit": 1,
        })
        panel = {}
        for obs in result.data:
            panel[obs["series_id"]] = float(obs["value"])
        return panel
    finally:
        await fred.close()
```

### 2. New Data Domains via MCP

The agent's `expand()` step in `MeshAgent.act()` (`src/cme/agent.py`) receives a `context` dict with entities and events. Airbyte MCP can add new data dimensions to this context.

**Setup:**
```json
{
  "mcpServers": {
    "airbyte": {
      "url": "https://mcp.airbyte.ai/mcp"
    }
  }
}
```

**Recommended connectors for research enrichment:**

| Connector | Data Provided | Research Use |
|-----------|--------------|-------------|
| **Gong** | Call recordings, transcripts, activity stats | Earnings call sentiment, management tone |
| **Crunchbase** (via API) | Funding rounds, acquisitions, investors | Growth trajectory, M&A pipeline |
| **HubSpot / Salesforce** | CRM pipeline, deal stages, customer data | Demand validation, customer concentration |
| **Zendesk / Intercom** | Support tickets, satisfaction scores | Product quality signal |
| **Slack** | Channel messages, threads | Internal sentiment, org health |
| **Google Analytics / Mixpanel** | Web traffic, user engagement | Digital presence, customer acquisition cost |

### 3. Research Artifact Enrichment

Artifact builders (`src/cme/research/artifacts.py`) synthesize final output. Airbyte-sourced data feeds directly into these:

- `BusinessModelMemo` — enrich with Stripe MRR, HubSpot pipeline, customer churn data
- `SECDeepDiveMemo` — enrich with Gong call analysis, insider trading data
- `InitiationOfCoverage` — enrich with market data from FRED, analyst ratings

### 4. Microsoft Fabric / Delta Lake Pipeline

The workbench already has Fabric notebooks (`notebooks/fabric_*.py`) that write to Delta tables. Airbyte can:

- **Source data → Fabric Lakehouse**: Use Airbyte destinations to write connector data directly to the existing 8 Delta tables
- **Replace PySpark ingestion**: Use Airbyte schedules instead of manual notebook runs for data refresh
- **Add new data feeds**: Stream Gong transcripts, insider trades, and news to separate Delta tables

### 5. CockroachDB Caching Layer

The existing `CockroachCache` and `DiskCache` (24-hour TTL) can be supplemented by Airbyte's incremental sync state tracking — no need to re-fetch data that hasn't changed.

---

## Getting Started

1. **Sign up** at [app.airbyte.ai](https://app.airbyte.ai).
2. **Install the SDK** into your Python environment:
   ```bash
   uv add airbyte-agent-sdk
   ```
3. **Set credentials** in your `.env`:
   ```
   AIRBYTE_CLIENT_ID=your_client_id
   AIRBYTE_CLIENT_SECRET=your_client_secret
   ```
4. **Add an `airbyte_connectors.py` client module** (see example below) alongside the existing data clients.

### Example: airbyte_connectors.py

```python
"""Airbyte connector wrappers for the research workbench."""
import os
from airbyte_agent_sdk import connect

# Environment config
AIRBYTE_CLIENT_ID = os.getenv("AIRBYTE_CLIENT_ID")
AIRBYTE_CLIENT_SECRET = os.getenv("AIRBYTE_CLIENT_SECRET")

async def get_earnings_call_summary(ticker: str) -> dict | None:
    """Fetch recent earnings call data from Gong via Airbyte."""
    gong = connect("gong")
    try:
        result = await gong.execute("calls", "search", params={
            "query": ticker,
            "limit": 5,
            "sort": "date_desc",
        })
        return result.data
    finally:
        await gong.close()

async def get_insider_trades(ticker: str) -> list:
    """Fetch insider trading activity via Airbyte SEC/OpenInsider connector."""
    sec = connect("sec-edgar")  # or custom connector
    try:
        result = await sec.execute("filings", "list", params={
            "ticker": ticker,
            "form_type": "4",
            "limit": 20,
        })
        return result.data
    finally:
        await sec.close()
```

---

## Connector Catalog

Airbyte Agents supports 30+ connectors. For the research workbench, the most relevant are:

| Category | Connectors |
|----------|-----------|
| **Financial Data** | AlphaVantage, FRED, Yahoo Finance (via API) |
| **SEC/Regulatory** | SEC EDGAR (custom), OpenInsider |
| **CRM** | Salesforce, HubSpot, Zendesk Sell |
| **Communications** | Gong, Slack, Outlook |
| **Analytics** | Google Analytics, Mixpanel, Amplitude |
| **Data Warehouse** | Snowflake, BigQuery, Postgres, Redshift |

Full catalog: [docs.airbyte.com/ai-agents/connectors](https://docs.airbyte.com/ai-agents/connectors)
