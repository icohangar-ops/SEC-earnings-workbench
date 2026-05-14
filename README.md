# SEC / Earnings / Company Research Workbench

CHP-hardened, shared-context platform where **Fundamentals**, **Diligence**, and **Markets** agents collaborate on **company research**, **SEC deep dives**, and **Initiation of Coverage** reports — every claim grounded in primary sources (SEC filings, AlphaVantage fundamentals, FRED macro series) with a single auditable reasoning trail.

Now with **Microsoft Fabric + Azure AI Foundry** integration for cloud-native research pipelines.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](tests/)
[![Fabric](https://img.shields.io/badge/Microsoft-Fabric-0078D4)](https://fabric.microsoft.com)
[![AI Foundry](https://img.shields.io/badge/Azure-AI%20Foundry-764ABC)](https://ai.azure.com)

---

## What this is

Equity research, SEC deep dives, and IoC initiations usually fragment across the same three failure modes:

1. **Context fragmentation** — financials, governance, and market view each sit in different artifacts.
2. **Reasoning opacity** — the analyst gets a memo without seeing how each claim was reached.
3. **Soft consensus** — recommendations look unanimous because no one ran the assumptions through adversarial review.

This workbench fuses three well-specified frameworks to fix all three:

| Layer | Role |
|---|---|
| **Cognitive Mesh** | Three specialist agents (Fundamentals, Diligence, Markets) reason on a **shared ContextEngine**. Each agent runs through the Cognitive Mesh Protocol — visible expansion/compression cycles with grounding checks and self-improving playbooks. |
| **Consensus Hardening Protocol (CHP)** | Wraps the multi-agent run in a **DecisionCase** with foundation disclosure → adversarial attack → R0 gate → lock progression. A finding can advance only when foundation passes; LOCKED requires third-party validation. |
| **External grounding** | Every session pulls **AlphaVantage** fundamentals (OVERVIEW, INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, EARNINGS, GLOBAL_QUOTE, NEWS_SENTIMENT), a **FRED** macro panel (rates, yield curve, CPI, unemployment), and **SEC EDGAR** filings (10-K / 10-Q / 8-K sweep / DEF 14A) with real accession numbers. Claims cite source + accession + filing date — never bare percentages. |

Every line in the final memo traces back to:
- the agent that produced it,
- the expansion step in that agent's reasoning,
- the grounding source/date (AV OVERVIEW, FRED series, etc.),
- the CHP foundation findings that hardened or weakened it.

Designed for **corp dev, treasury, and board prep** around peers, targets, and public comps.

---

## Quick start

```bash
git clone https://github.com/zan-maker/sec-earnings-workbench.git
cd sec-earnings-workbench
pip install -e .

cp .env.example .env
# edit .env to add ALPHAVANTAGE_API_KEY and FRED_API_KEY

# Inspect data clients (smoke test API keys)
research-bench data --ticker AAPL

# Run a full Initiation of Coverage on MSFT
research-bench initiation \
  --title "MSFT initiation" --company "Microsoft Corp." --ticker MSFT \
  --problem "Initiate coverage with 12-month rating and target." \
  --industry "Software/Cloud" \
  --peer GOOGL --peer AMZN --peer ORCL \
  --rating Buy --target 520 --method "EV/EBITDA" --years 3 \
  --driver "Azure ARR growth" --driver "Copilot attach rate" \
  --thesis "Cloud + AI attach with operating-margin tailwind"
```

Or without installing:

```bash
PYTHONPATH=src python3 -m cme.cli company-research \
  --title "AAPL business model" --company "Apple Inc." --ticker AAPL \
  --problem "Map AAPL business model and revenue drivers from primary sources." \
  --industry "Consumer Electronics" \
  --peer MSFT --peer GOOGL \
  --revenue-stream iPhone --revenue-stream Services
```

---

## The three research tasks

### `company-research` → BusinessModelMemo

Business-model deep dive (the *Company research* prompt). The system pulls AV OVERVIEW + INCOME_STATEMENT + EARNINGS, runs the three agents on the shared context, and lands a memo with sections matching the prompt: **Snapshot · Business Model Map · Three-Year Income Trajectory · Revenue Drivers · Unit Economics · Customer Segments & GTM · Geography · KPIs to Watch · Peer Snapshot · Risks · Thesis Triggers · Macro Backdrop · Lock Status**.

### `sec-deep-dive` → SECDeepDiveMemo

SEC filing scan (the *SEC filing deep research* prompt). Pulls AV INCOME_STATEMENT + CASH_FLOW + EARNINGS, computes FCF-vs-NI divergence and earnings-quality ratios, and lands the six prompt sections: **Business Model & Moat · Financial Health · Red Flag Scan · Management & Governance · Forward-Looking Signals · Valuation Inputs**, plus FRED macro overlay.

### `initiation` → InitiationOfCoverage

GS-style Initiation of Coverage report (the *Top stock research* prompt). Pulls AV GLOBAL_QUOTE + OVERVIEW + INCOME_STATEMENT + EARNINGS, computes implied upside vs target, and lands the eight prompt sections: **Key Data & Forecast Snapshot · Thesis Tear-sheet · Investment Positives · Peer Analysis · Estimates & Operating Assumptions · Valuation · Key Risks · Appendix**, plus FRED macro overlay.

---

## How a session runs

```
brief
  │
  ▼
build DecisionCase + Dossier ──► CHP foundation disclosure + attack
  │                              R0 gate + parity assessment
  ▼                              initial PAYLOAD envelope
pull AV fundamentals (OVERVIEW, INCOME_STATEMENT, ...)
pull FRED macro panel (DGS10, T10Y2Y, CPI, ...)
pull SEC EDGAR filings (10-K / 10-Q / 8-K sweep / DEF 14A)
  │
  ▼
seed shared ContextEngine with company + AV + FRED + filing entities
  │
  ▼
EnterpriseOrchestrator
  ├─ FundamentalsAgent (produces business_model, revenue_drivers, financial_health)
  ├─ DiligenceAgent    (consumes business_model; produces red_flag_scan, governance_read, risk_register)
  └─ MarketsAgent      (consumes business_model; produces peer_view, valuation_view, thesis_triggers)
  │
  ▼
foundation PASS + no failure mode  ──►  status = PROVISIONAL_LOCK
  │
  ▼
synthesize research artifact (BusinessModel / SECDeepDive / Initiation)
  + AuditTrail linking every claim to expansion step + grounding + CHP findings
  │
  ▼
third-party validation  ──►  status = LOCKED
```

Lock progression is explicit: `EXPLORING → PROVISIONAL_LOCK → LOCKED`. The analyst can stop at any point, reopen items, or re-run with new constraints.

---

## Data layer

Three providers, all stdlib-only HTTP, all with a 24-hour on-disk cache under `~/.cache/research-workbench/`.

### AlphaVantage (`cme.research.data.alphavantage`)
- `OVERVIEW` — sector, industry, market cap, P/E, profit margin, beta, 52-week range
- `INCOME_STATEMENT` — annual + quarterly statements
- `BALANCE_SHEET` — annual + quarterly statements
- `CASH_FLOW` — annual + quarterly statements (used for FCF vs NI divergence)
- `EARNINGS` — EPS reported vs estimate + surprise %
- `GLOBAL_QUOTE` — latest price, used to compute implied upside vs target
- `NEWS_SENTIMENT` — ticker-tagged news with sentiment scores

### FRED (`cme.research.data.fred`)
- Default macro panel: `DGS10`, `DGS2`, `DFF`, `T10Y2Y`, `CPIAUCSL`, `UNRATE`
- Custom panels: pass any dict of `{series_id: label}` to `FredClient.macro_panel()`
- Series metadata + observation history available via `series()` and `latest_observation()`

### SEC EDGAR (`cme.research.data.edgar`)

EDGAR is the **primary-source grounding layer**: every filing-anchored claim in the artifact carries a real accession number and filing date pulled directly from SEC.

- `cik_for(ticker)` / `company_name_for(ticker)` — ticker → CIK lookup via `company_tickers.json`
- `submissions(ticker)` — full filing history (filings.recent + supplementary)
- `recent_filings(ticker, forms=[...], limit=N)` — most-recent slice, optionally filtered to `["10-K", "10-Q", "8-K", "DEF 14A"]`
- `latest_filing(ticker, form)` — most-recent filing of a single form
- `eight_ks_since_last_periodic(ticker)` — implements the DiligenceAgent's "8-K sweep" rule (every 8-K filed *after* the latest 10-K/10-Q)
- `company_facts(ticker)` — XBRL company-facts time series (financial concept history)
- `full_text_search(query, ciks=..., forms=..., date_range=...)` — EFTS search wrapper
- `fetch_document(url)` — raw HTML/text body for any filing
- `extract_text(html)` — stdlib HTML→text (drops `<script>` / `<style>`, collapses whitespace)
- `extract_section(text, "Item 1A. Risk Factors")` — best-effort 10-K item slicer

**SEC fair-access policy.** EDGAR has no API key. SEC requires a `User-Agent` header that identifies the caller as `"<name> <email>"`. The default is sufficient for low-volume identification; set `EDGAR_USER_AGENT` for production use.

**How EDGAR threads through the pipeline.**
1. `ResearchWorkbench._pull_edgar()` calls `recent_filings`, `latest_filing(10-K/10-Q)`, and `eight_ks_since_last_periodic`.
2. Filings are seeded as `Entity(type="sec_filing", ...)` on the shared `ContextEngine` so the **DiligenceAgent** reads real filing dates inside its expansion phase (`Reframe`/`Constraints` cite the latest 10-K accession).
3. Artifacts emit a **"Recent SEC Filings"** bullet section with full citations (`[10-K filed 2025-10-31, accession 0000320193-25-000079]`).
4. The audit trail's **External Grounding Sources** block summarises filings ingested per form (`10-K×1, 10-Q×3, 8-K×6, DEF 14A×1`) and pins the most-recent filing as the primary anchor.

### Graceful degradation

If no API key is set (AV / FRED) or `EDGAR_DISABLED=1`, the corresponding client is skipped and the artifact emits `"DATA NEEDED"` markers — matching the prompt-spec instruction. The pipeline still runs end-to-end and the test suite passes without any network access.

---

## Architecture

```
                    ┌──────────────────────────┐
                    │   ContextEngine          │
   ┌───── shared ──▶│   subject + AV entities  │◀───── shared ─────┐
   │                │   + FRED + EDGAR filings │                   │
   │                │   + CHP foundation       │                   │
   │                └──────────────────────────┘                   │
   ▼                                                                ▼
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ Fundamentals Agent │ │ Diligence Agent    │ │ Markets Agent      │
│  ├─ Playbook (ACE) │ │  ├─ Playbook (ACE) │ │  ├─ Playbook (ACE) │
│  └─ Protocol (CMP) │ │  └─ Protocol (CMP) │ │  └─ Protocol (CMP) │
└──────────┬─────────┘ └──────────┬─────────┘ └──────────┬─────────┘
           │ produces             │ consumes+produces    │ consumes+produces
           ▼                      ▼                      ▼
    business_model         red_flag_scan          peer_view
    revenue_drivers        governance_read        valuation_view
    financial_health       risk_register          thesis_triggers
           │                      │                      │
           └──────────────┬───────┴──────────────┬───────┘
                          ▼                      ▼
                 ┌──────────────────────────────────────────┐
                 │  ResearchWorkbench                       │
                 │   1. CHP DecisionCase + Foundation       │
                 │   2. AV + FRED grounding pull            │
                 │   3. EnterpriseOrchestrator (Mesh)       │
                 │   4. Lock progression                    │
                 │   5. Artifact + AuditTrail               │
                 └──────────────────────────────────────────┘
```

---

## CLI reference

```bash
research-bench company-research      # BusinessModelMemo
  --title TITLE  --company COMPANY  --ticker TICKER
  --problem PROBLEM  [--industry IND]
  [--peer T --peer T ...]
  [--revenue-stream X --revenue-stream X ...]
  [--segment S --segment S ...]  [--geo G --geo G ...]

research-bench sec-deep-dive         # SECDeepDiveMemo
  --title TITLE  --company COMPANY  --ticker TICKER  --problem PROBLEM
  [--filings 10-K 10-Q 8-K "DEF 14A"]
  [--red-flag F --red-flag F ...]   [--years-back N]

research-bench initiation            # InitiationOfCoverage
  --title TITLE  --company COMPANY  --ticker TICKER  --problem PROBLEM
  [--rating Buy/Hold/Sell]  [--target USD]
  [--method EV/EBITDA|P/E|EV/Sales]  [--years N]
  [--driver D --driver D ...]  [--thesis "thesis seed"]

research-bench data --ticker TICKER  # AV + FRED + EDGAR smoke test
research-bench chp-start             # Raw CHP capital allocation session
research-bench chp-validate          # Apply third-party validation (LOCKED)
```

All task subcommands accept `--out-md PATH` (write the markdown report) and `--json` (emit a structured summary).

---

## Programmatic use

```python
from cme.research import (
    CompanyBrief,
    InitiationBrief,
    ResearchWorkbench,
    SECDeepDiveBrief,
)
from demo import FundamentalsAgent, DiligenceAgent, MarketsAgent

bench = ResearchWorkbench(
    agents=[FundamentalsAgent(), DiligenceAgent(), MarketsAgent()],
)

report = bench.run(InitiationBrief(
    title="MSFT initiation",
    company="Microsoft Corp.",
    ticker="MSFT",
    problem="Initiate coverage with 12-month rating and target.",
    peers=["GOOGL", "AMZN", "ORCL"],
    rating_seed="Buy",
    target_price_usd=520.0,
    valuation_method_preference="EV/EBITDA",
    forecast_years=3,
))

print(report.case.status.value)        # PROVISIONAL_LOCK
print(report.artifact.render())        # GS-style IoC memo
print(report.audit.render())           # per-claim provenance

# Advance to LOCKED via third-party validation
bench.lock(report.case.decision_id,
    validator="fresh_instance",
    item="Initiation v1",
    rationale="Sources cited; macro overlay coheres.",
)
```

---

## Tests

```bash
pip install pytest
PYTHONPATH=src pytest tests/ -v
```

The test suite covers all three task types (running without API keys via graceful degradation), lock progression, audit-trail provenance, and the underlying CHP scaffolding.

---

## Use cases

- **Corp dev** — public-comp screen for targets; same memo across multiple tickers with consistent provenance.
- **Treasury** — portfolio of public exposures with red-flag scans and macro overlay.
- **Board prep** — peer / target packets with explicit rating + target + flip criteria.
- **Equity research desk** — initiation drafts with citation discipline enforced at the artifact layer.

---

## Microsoft Fabric + Azure AI Foundry Integration

The workbench now runs as a first-class Microsoft Fabric pipeline with AI-powered research agents via Azure AI Foundry.

### Architecture (Fabric Mode)

```
┌─────────────────────────────────────────────────────┐
│  Azure AI Foundry (Kimi K2.6 / GPT-4o)             │
│  ├─ Fundamentals Agent (AI-powered)                │
│  ├─ Diligence Agent (AI-powered)                   │
│  ├─ Markets Agent (AI-powered)                     │
│  └─ CHP Foundation Adjudicator (AI-powered)        │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  Microsoft Fabric Lakehouse (Delta Tables)          │
│  ├─ sec_filings         — SEC EDGAR filing metadata │
│  ├─ company_fundamentals — AlphaVantage snapshots    │
│  ├─ macro_indicators    — FRED macro panel           │
│  ├─ research_sessions   — CHP DecisionCase records   │
│  ├─ agent_outputs       — Per-agent turn results     │
│  ├─ research_artifacts  — Final research reports     │
│  ├─ peer_comparisons    — Cross-company batch results │
│  └─ audit_trail         — Per-claim provenance       │
└─────────────────────────────────────────────────────┘
```

### Fabric Notebooks

Three notebooks in `notebooks/`:

| Notebook | Purpose |
|---|---|
| `fabric_setup_lakehouse.py` | Create all 8 Delta tables with seed data |
| `fabric_research_pipeline.py` | Full end-to-end AI-powered research pipeline (single company) |
| `fabric_peer_batch.py` | Peer batch processing: runs full pipeline for each company, then cross-company comparative analysis |

### Configuration

```bash
# .env
AZURE_AI_ENDPOINT=https://<resource>.services.ai.azure.com/openai/v1
AZURE_AI_KEY=<api-key>
AZURE_AI_DEPLOYMENT=Kimi-K2.6
FABRIC_WORKSPACE_ID=<workspace-guid>
FABRIC_LAKEHOUSE_ID=<lakehouse-guid>
ALPHAVANTAGE_API_KEY=<key>
FRED_API_KEY=<key>
```

### Delta Table Schema

| Table | Key Columns |
|---|---|
| `sec_filings` | ticker, form, filing_date, accession_no, primary_document, is_xbrl |
| `company_fundamentals` | ticker, sector, industry, market_cap, pe_ratio, profit_margin, revenue_ttm |
| `macro_indicators` | series_id, label, value, as_of (FRED DGS10, T10Y2Y, CPIAUCSL, UNRATE) |
| `research_sessions` | decision_id, ticker, task_type, status, foundation_score, origin_model |
| `agent_outputs` | decision_id, agent_name, recommendation, confidence, produces, consumes |
| `research_artifacts` | decision_id, artifact_type, title, lock_state, rating_seed, target_price |
| `peer_comparisons` | batch_id, primary_ticker, peer_tickers, comparative_md, avg_foundation_score, duration_seconds |
| `audit_trail` | decision_id, agent, claim, grounding_source, grounding_confidence, risk_flag |

### Fabric Notebook Quick Start

**Single-company pipeline:**
1. In Fabric workspace, create a new notebook
2. Attach the Lakehouse via "From OneLake catalog"
3. Paste `fabric_setup_lakehouse.py` cells to create tables
4. Paste `fabric_research_pipeline.py` cells and configure the ticker/task at Cell 6
5. Run all cells — the pipeline pulls data, runs 3 AI agents + CHP, and writes results

**Peer batch pipeline:**
1. Run `fabric_setup_lakehouse.py` first (creates the `peer_comparisons` table)
2. Paste `fabric_peer_batch.py` cells into a new notebook
3. Edit Cell 6 (`BATCH_CONFIG`) to set your primary company and peers
4. Run all cells — the pipeline processes each company, then produces a cross-company comparative analysis
5. All results (per-company + comparative) are written to Delta tables

**Rate-limit awareness:** AlphaVantage free tier allows 25 calls/day, 5/min. The peer batch notebook tracks calls and enforces delays between requests. For 4 companies, expect ~16 AV calls (4 calls x 4 companies) + ~21 AI calls (5 per company + 1 comparative). Total batch runtime: 20-40 minutes depending on AI latency.

### New Source Modules

| Module | Purpose |
|---|---|
| `cme.ai.foundry` | Azure AI Foundry client (OpenAI-compatible) |
| `cme.fabric.client` | Fabric REST API client (Lakehouse metadata) |

---

## License

MIT. See [LICENSE](LICENSE).
