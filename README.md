# SEC / Earnings / Company Research Workbench

CHP-hardened, shared-context platform where **Fundamentals**, **Diligence**, and **Markets** agents collaborate on **company research**, **SEC deep dives**, and **Initiation of Coverage** reports — every claim grounded in primary sources (SEC filings, AlphaVantage fundamentals, FRED macro series) with a single auditable reasoning trail.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](tests/)

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
| **External grounding** | Every session pulls **AlphaVantage** fundamentals (OVERVIEW, INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, EARNINGS, GLOBAL_QUOTE, NEWS_SENTIMENT) and a **FRED** macro panel (rates, yield curve, CPI, unemployment). Claims cite source + date — never bare percentages. |

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
  │
  ▼
seed shared ContextEngine with company + AV entities + FRED entities
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

Two providers, both stdlib-only HTTP, both with a 24-hour on-disk cache under `~/.cache/research-workbench/`.

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

### Graceful degradation

If no API key is set, the corresponding client returns `None` and the artifact emits `"DATA NEEDED"` markers — matching the prompt-spec instruction. The pipeline still runs end-to-end.

---

## Architecture

```
                    ┌──────────────────────────┐
                    │   ContextEngine          │
   ┌───── shared ──▶│   subject + AV entities  │◀───── shared ─────┐
   │                │   + FRED entities + CHP  │                   │
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

research-bench data --ticker TICKER  # AV + FRED smoke test
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

## License

MIT. See [LICENSE](LICENSE).
