# Ghost Integration — SEC / Earnings / Company Research Workbench

This document describes how [Ghost](https://ghost.build) — the Postgres database built for AI agents — can replace CockroachDB and disk caching with forkable, per-research-session databases.

---

## Overview

Ghost provides unlimited Postgres databases you can create, fork, and discard freely. For the Research Workbench:

- **One database per company/session** — isolated research artifacts per ticker
- **Fork for parallel analysis** — compare different research approaches on the same source data
- **Replace CockroachDB + DiskCache** — simpler Postgres backend with no distributed DB overhead
- **MCP tools for agents** — the Fundamentals/Diligence/Markets agents query live research data

**Key Ghost commands:**
```bash
brew install timescale/tap/ghost       # Install
ghost init                               # Configure
ghost create research-aapl               # One DB per ticker
ghost fork research-aapl research-aapl-peer-comparison  # Fork
ghost sql research-aapl "SELECT * FROM artifacts"  # Query
ghost share research-aapl               # Share with client
```

---

## Integration Points

### 1. Per-Ticker Research Databases

```bash
# Initiate coverage on AAPL
ghost create research-aapl

# Seed with company fundamentals (via Airbyte SDK)
ghost sql research-aapl "
  INSERT INTO company_fundamentals (ticker, metric, value, period)
  VALUES ('AAPL', 'revenue', 391000000000, 'FY2025'),
         ('AAPL', 'net_income', 93700000000, 'FY2025'),
         ('AAPL', 'fcf', 98500000000, 'FY2025');
"

# Run the research pipeline
research-bench initiation AAPL --ghost-db research-aapl

# Fork for a peer comparison
ghost fork research-aapl research-aapl-vs-msft
research-bench company-research MSFT --ghost-db research-aapl-vs-msft
```

### 2. Replace CockroachDB + Disk Cache

The workbench currently uses `CockroachCache` and `DiskCache` with 24-hour TTL for AlphaVantage, FRED, and EDGAR data. Ghost Postgres can serve as a simpler, single-node alternative:

```python
# src/cme/research/data/ghost_cache.py
class GhostCache(DataCache):
    """Replace DiskCache / CockroachCache with Ghost Postgres."""
    
    def __init__(self, ghost_db: str, ttl_hours: int = 24):
        self.db = ghost_db
        self.ttl = ttl_hours
    
    def get(self, key: str):
        result = ghost_sql(self.db, """
            SELECT value FROM data_cache
            WHERE cache_key = $1
              AND fetched_at > now() - interval '$2 hours'
        """, [key, self.ttl])
        return result[0]['value'] if result else None
    
    def set(self, key: str, value: dict):
        ghost_sql(self.db, """
            INSERT INTO data_cache (cache_key, value, fetched_at)
            VALUES ($1, $2, now())
            ON CONFLICT (cache_key) DO UPDATE
              SET value = $2, fetched_at = now()
        """, [key, json.dumps(value)])
```

### 3. MCP Integration for Research Agents

Install Ghost MCP:
```bash
ghost mcp install claude-code
```

**Example agent workflow:**
> Create a Ghost database for AAPL research. Seed it with the company schema. Fetch AAPL fundamentals from AlphaVantage via Airbyte and store them. Run the Fundamentals agent. Fork the DB. On one fork, add Diligence agent findings. On the other, add Markets agent findings. Compare the resulting artifacts.

### 4. Replace CockroachDB ORM Models

The existing CockroachDB models (`src/cme/db/cockroachdb_layer.py`) define `DecisionCaseModel`, `DossierModel`, `ResearchArtifactModel`, `ResearchCache`, `ApiCallLog`, `ModelParityLogs`, `ValidationRecords` — all of which map cleanly to Ghost Postgres tables:

```sql
-- research_artifacts table
CREATE TABLE research_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    artifact_type TEXT NOT NULL,  -- 'business_model', 'sec_deep_dive', 'initiation'
    content JSONB,
    agent_name TEXT,
    session_id UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- api_call_log
CREATE TABLE api_call_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,          -- 'alphavantage', 'fred', 'edgar'
    endpoint TEXT,
    status_code INT,
    latency_ms INT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 5. Fabric Pipeline State

The Fabric notebooks (`notebooks/fabric_*.py`) write to Delta tables. Ghost can store the pipeline run metadata:

```bash
ghost create research-fabric-pipeline
ghost sql research-fabric-pipeline < notebook_metadata_schema.sql
```

---

## Architecture

```
Research Workbench (research-bench CLI)
    │
    ├── Ghost Postgres DB per ticker
    │   ├── research-aapl  ← fundamentals + filings + memo
    │   ├── research-msft  ← fundamentals + filings + memo
    │   └── research-aapl-vs-msft  ← comparison fork
    │
    ├── Ghost MCP tools (ghost_create, ghost_fork, ghost_sql)
    │   └── Claude / Codex / Cursor
    │
    ├── Data Sources via Airbyte
    │   ├── AlphaVantage (fundamentals)
    │   ├── FRED (macro)
    │   └── SEC EDGAR (filings)
    │
    └── CockroachDB → replaced by Ghost
```

---

## Getting Started

1. **Install Ghost:**
   ```bash
   brew install timescale/tap/ghost
   ghost init
   ```
2. **Create a development database:**
   ```bash
   ghost create research-dev
   ```
3. **Run schema:**
   ```bash
   ghost sql research-dev < src/cme/db/ghost_schema.sql
   ```
4. **Install the MCP server:**
   ```bash
   ghost mcp install claude-code
   ```
5. **Add to `.env.example`:**
   ```
   GHOST_API_KEY=***   GHOST_DEFAULT_DB=research-dev
   SEW_DATABASE_URL=   # no longer needed — use Ghost instead
   ```

---

## Resources
- [Ghost Documentation](https://ghost.build/docs)
- [Ghost MCP Tools](https://ghost.build/docs/#mcp-integration)
- [Ghost API Reference](https://ghost.build/docs/#api-reference)
