#!/usr/bin/env bash
# Quick CLI examples for the SEC / Earnings / Company Research Workbench.
# Requires .env with ALPHAVANTAGE_API_KEY and FRED_API_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Data smoke test ==="
PYTHONPATH=src python3 -m cme.cli data --ticker AAPL

echo ""
echo "=== Company research: AAPL ==="
PYTHONPATH=src python3 -m cme.cli company-research \
  --title "AAPL business model deep dive" \
  --company "Apple Inc." --ticker AAPL \
  --problem "Map AAPL business model and revenue drivers from primary sources." \
  --industry "Consumer Electronics / Services" \
  --peer MSFT --peer GOOGL --peer AMZN \
  --revenue-stream iPhone --revenue-stream Services --revenue-stream Wearables \
  --segment Consumer --segment Enterprise --segment Education \
  --geo Americas --geo Europe --geo "Greater China"

echo ""
echo "=== SEC deep dive: NVDA ==="
PYTHONPATH=src python3 -m cme.cli sec-deep-dive \
  --title "NVDA SEC filing deep scan" \
  --company "NVIDIA Corp." --ticker NVDA \
  --problem "Surface red flags and earnings-quality signals from NVDA SEC filings." \
  --industry "Semiconductors" \
  --peer AMD --peer AVGO --peer INTC \
  --red-flag "customer concentration" --red-flag "inventory build" --red-flag "SBC % revenue" \
  --years-back 3

echo ""
echo "=== Initiation of coverage: MSFT ==="
PYTHONPATH=src python3 -m cme.cli initiation \
  --title "MSFT initiation of coverage" \
  --company "Microsoft Corp." --ticker MSFT \
  --problem "Initiate coverage on MSFT with a 12-month rating and target." \
  --industry "Software / Cloud" \
  --peer GOOGL --peer AMZN --peer ORCL \
  --rating Buy --target 520 --method "EV/EBITDA" --years 3 \
  --driver "Azure ARR growth" --driver "Copilot attach rate" --driver "Op margin" \
  --thesis "Cloud + AI attach with sustained operating-margin tailwind"
