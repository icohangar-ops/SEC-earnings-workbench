# Cell 1 — Install dependencies
# ============================================================
# SEC Earnings Workbench — Peer Batch Processing Pipeline
# Runs in Microsoft Fabric with Azure AI Foundry (Kimi K2.6 + GPT-4o)
#
# Pipeline: For each company in the peer group:
#   AlphaVantage + FRED + EDGAR data pull ->
#   AI-powered multi-agent reasoning (Fundamentals, Diligence, Markets) ->
#   CHP hardening -> Research artifact ->
#   Cross-company Comparative Analysis -> Delta tables
#
# Rate-limit aware: AlphaVantage free tier = 5 req/min, 25/day
# EDGAR = 10 req/sec (with proper User-Agent)
# ============================================================

# %%
# Cell 2 — Configuration
# ============================================================
import os

# Azure AI Foundry — Primary model (multi-agent research)
AZURE_AI_ENDPOINT = os.getenv(
    "AZURE_AI_ENDPOINT",
    "https://samd-5839-resource.services.ai.azure.com/openai/v1",
)
AZURE_AI_KEY = os.getenv("AZURE_AI_KEY", "YOUR_KEY_HERE")
AZURE_AI_DEPLOYMENT = os.getenv("AZURE_AI_DEPLOYMENT", "Kimi-K2.6")

# Azure AI Foundry — Partner model (CHP adjudicator, dual-model consensus)
AZURE_AI_PARTNER_DEPLOYMENT = os.getenv("AZURE_AI_PARTNER_DEPLOYMENT", "gpt-4o")
USE_PARTNER_MODEL = os.getenv("USE_PARTNER_MODEL", "true").lower() == "true"

# AlphaVantage
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")

# Twelve Data (supplementary)
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

# FRED (optional — leave blank for graceful degradation)
FRED_KEY = os.getenv("FRED_API_KEY", "")

# Azure AI Foundry — Embedding model for RAG over SEC filings
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")

# Batch configuration
AV_RATE_LIMIT_SECONDS = int(os.getenv("AV_RATE_LIMIT_SECONDS", "15"))  # seconds between AV calls (free tier: 5/min)
AV_DAILY_LIMIT = int(os.getenv("AV_DAILY_LIMIT", "25"))  # daily AV call limit (free tier)
BATCH_MAX_AI_RETRIES = int(os.getenv("BATCH_MAX_AI_RETRIES", "3"))  # retries for AI calls
BATCH_AI_RETRY_DELAY = int(os.getenv("BATCH_AI_RETRY_DELAY", "10"))  # seconds between AI retries

# Validation
missing = []
if AZURE_AI_KEY == "YOUR_KEY_HERE" or not AZURE_AI_KEY:
    missing.append("AZURE_AI_KEY")
if not ALPHAVANTAGE_KEY:
    missing.append("ALPHAVANTAGE_API_KEY")

print(f"AI Foundry endpoint: {AZURE_AI_ENDPOINT}")
print(f"Primary model: {AZURE_AI_DEPLOYMENT}")
if USE_PARTNER_MODEL:
    print(f"Partner model (CHP): {AZURE_AI_PARTNER_DEPLOYMENT}")
else:
    print(f"Partner model: DISABLED (single-model mode)")
print(f"AlphaVantage: {'configured' if ALPHAVANTAGE_KEY else 'NOT SET'}")
print(f"Twelve Data: {'configured' if TWELVE_DATA_KEY else 'NOT SET'}")
print(f"FRED: {'configured' if FRED_KEY else 'NOT SET (graceful degradation)'}")
print(f"AV rate limit: {AV_RATE_LIMIT_SECONDS}s between calls")
print(f"AV daily limit: {AV_DAILY_LIMIT} calls")
if missing:
    print(f"\n  Missing env vars: {', '.join(missing)}")
    print(f"   Set them in Fabric notebook parameters or .env before running.")

# %%
# Cell 3 — Install OpenAI client
# ============================================================
print("Installing openai and requests...")
%pip install openai requests -q
print("Dependencies installed.")

# %%
# Cell 4 — Data ingestion functions (shared with research pipeline)
# ============================================================
import json
import urllib.request
import urllib.error
import urllib.parse
import time
from datetime import datetime


def fetch_alphavantage(function, symbol, extra_params=None):
    """Fetch data from AlphaVantage REST API with rate-limit tracking."""
    params = {
        "function": function,
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_KEY,
    }
    if extra_params:
        params.update(extra_params)
    url = f"https://www.alphavantage.co/query?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "Note" in data:
            print(f"  AV rate limited: {data['Note'][:80]}")
            return None
        if "Error Message" in data:
            print(f"  AV error: {data['Error Message']}")
            return None
        return data
    except Exception as e:
        print(f"  AV fetch failed for {symbol} {function}: {e}")
        return None


def fetch_edgar_filing_index(ticker):
    """Fetch recent SEC filings from EDGAR for a ticker."""
    try:
        with urllib.request.urlopen(
            "https://www.sec.gov/files/company_tickers.json",
            timeout=30,
        ) as resp:
            ticker_index = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  EDGAR ticker index failed: {e}")
        return []

    cik = None
    for entry in ticker_index.values():
        if entry.get("ticker", "").upper() == ticker.upper():
            cik = int(entry["cik_str"])
            break
    if cik is None:
        print(f"  No CIK found for {ticker}")
        return []

    subs_url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    req = urllib.request.Request(
        subs_url,
        headers={"User-Agent": "sec-earnings-workbench cubiczan contact@example.com"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(resp.read()).decode("utf-8")
        subs = json.loads(raw)
    except Exception as e:
        print(f"  EDGAR submissions failed: {e}")
        return []

    recent = (subs.get("filings") or {}).get("recent") or {}
    accession = recent.get("accessionNumber") or []
    forms = recent.get("form") or []
    filing_date = recent.get("filingDate") or []
    report_date = recent.get("reportDate") or []
    primary_doc = recent.get("primaryDocument") or []
    is_xbrl = recent.get("isXBRL") or []

    filings = []
    wanted = {"10-K", "10-Q", "8-K", "DEF 14A"}
    for i, acc in enumerate(accession[:30]):
        form = (forms[i] if i < len(forms) else "").upper()
        if form not in wanted:
            continue
        filings.append({
            "cik": cik,
            "ticker": ticker,
            "company_name": ticker,
            "form": form,
            "filing_date": filing_date[i] if i < len(filing_date) else "",
            "report_date": report_date[i] if i < len(report_date) else "",
            "accession_no": acc,
            "primary_document": primary_doc[i] if i < len(primary_doc) else "",
            "is_xbrl": bool(is_xbrl[i]) if i < len(is_xbrl) else False,
            "ingested_at": datetime.utcnow().isoformat() + "Z",
        })
        if len(filings) >= 12:
            break
    return filings


def fetch_edgar_filing_text(filing_url):
    """Fetch raw text from a filing document."""
    req = urllib.request.Request(
        filing_url,
        headers={"User-Agent": "sec-earnings-workbench cubiczan contact@example.com"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000]
    except Exception as e:
        print(f"  Filing text fetch failed: {e}")
        return ""


# --- FRED Macro Panel --------------------------------------------------
DEFAULT_FRED_PANEL = {
    "DGS10": "10-Year Treasury Yield",
    "DGS2": "2-Year Treasury Yield",
    "DFF": "Federal Funds Effective Rate",
    "T10Y2Y": "10Y-2Y Yield Spread",
    "CPIAUCSL": "CPI All Urban Consumers (SA)",
    "UNRATE": "Unemployment Rate",
}


def fetch_fred_macro_panel(panel=None):
    """Fetch latest observation for each FRED series in the panel."""
    if not FRED_KEY:
        print("  FRED_API_KEY not set - macro panel skipped.")
        return []
    panel = panel or DEFAULT_FRED_PANEL
    results = []
    for series_id, label in panel.items():
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={FRED_KEY}"
            f"&file_type=json&sort_order=desc&limit=1"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            obs = data.get("observations", [])
            if obs:
                results.append({
                    "series_id": series_id,
                    "label": label,
                    "value": float(obs[0].get("value", 0)),
                    "as_of": obs[0].get("date", ""),
                    "source": "FRED",
                    "pulled_at": datetime.utcnow().isoformat() + "Z",
                })
        except Exception as e:
            print(f"  FRED {series_id} failed: {e}")
    return results


# --- SEC Filing Chunking for RAG ---------------------------------------
def chunk_text(text, chunk_size=1500, overlap=200):
    """Split text into overlapping chunks for embedding."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


print("Data ingestion functions defined.")

# %%
# Cell 5 — AI Foundry integration (dual-model: Kimi K2.6 + GPT-4o)
# ============================================================
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint=AZURE_AI_ENDPOINT,
    api_key=AZURE_AI_KEY,
    api_version="2024-06-01",
)

partner_client = AzureOpenAI(
    azure_endpoint=AZURE_AI_ENDPOINT,
    api_key=AZURE_AI_KEY,
    api_version="2024-06-01",
) if USE_PARTNER_MODEL else None


def ai_complete(
    system_prompt,
    user_prompt,
    temperature=0.3,
    max_tokens=4000,
    use_partner=False,
):
    """Call Azure AI Foundry with retry logic for batch resilience."""
    model_client = partner_client if (use_partner and partner_client) else client
    deployment = (
        AZURE_AI_PARTNER_DEPLOYMENT
        if (use_partner and partner_client)
        else AZURE_AI_DEPLOYMENT
    )
    last_error = None
    for attempt in range(BATCH_MAX_AI_RETRIES):
        try:
            response = model_client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            print(f"    AI call attempt {attempt+1}/{BATCH_MAX_AI_RETRIES} failed: {e}")
            if attempt < BATCH_MAX_AI_RETRIES - 1:
                time.sleep(BATCH_AI_RETRY_DELAY * (attempt + 1))
    raise last_error  # type: ignore


# Test connectivity
print("Testing AI Foundry connectivity...")
test_response = ai_complete(
    "You are a financial research assistant. Respond in one sentence.",
    "What is the S&P 500?"
)
print(f"  Primary ({AZURE_AI_DEPLOYMENT}): {test_response[:120]}...")

if USE_PARTNER_MODEL and partner_client:
    test_partner = ai_complete(
        "You are a financial research assistant. Respond in one sentence.",
        "What is the S&P 500?",
        use_partner=True,
    )
    print(f"  Partner ({AZURE_AI_PARTNER_DEPLOYMENT}): {test_partner[:120]}...")

print("AI Foundry connected successfully!")

# --- Embedding client for RAG over SEC filings ------------------------
import numpy as np

embedding_client = None
EMBEDDING_DIM = 1536

if AZURE_EMBEDDING_DEPLOYMENT and AZURE_AI_KEY not in ("", "YOUR_KEY_HERE"):
    try:
        embedding_client = AzureOpenAI(
            azure_endpoint=AZURE_AI_ENDPOINT,
            api_key=AZURE_AI_KEY,
            api_version="2024-06-01",
        )
        print(f"  Embedding model: {AZURE_EMBEDDING_DEPLOYMENT}")
    except Exception as e:
        print(f"  Embedding client init failed: {e}")
else:
    print("  Embedding model: NOT CONFIGURED (RAG will use text fallback)")


def embed_texts(texts):
    """Embed a list of texts using Azure OpenAI."""
    global EMBEDDING_DIM
    if not embedding_client:
        return [np.zeros(EMBEDDING_DIM)] * len(texts)
    try:
        response = embedding_client.embeddings.create(
            model=AZURE_EMBEDDING_DEPLOYMENT,
            input=texts,
        )
        embs = [np.array(d.embedding) for d in response.data]
        if embs:
            EMBEDDING_DIM = len(embs[0])
        return embs
    except Exception as e:
        print(f"  Embedding failed: {e}")
        return [np.zeros(EMBEDDING_DIM)] * len(texts)


def retrieve_chunks(query, chunks_with_embeddings, top_k=5):
    """Retrieve the most relevant filing chunks for a query via cosine similarity."""
    if not chunks_with_embeddings:
        return ""
    query_emb = embed_texts([query])[0]
    if np.linalg.norm(query_emb) == 0:
        return ""
    scored = []
    for chunk, emb in chunks_with_embeddings:
        emb_norm = np.linalg.norm(emb)
        if emb_norm == 0:
            scored.append((chunk, 0.0))
        else:
            score = float(np.dot(query_emb, emb) / (emb_norm * np.linalg.norm(query_emb)))
            scored.append((chunk, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]
    return "\n\n---\n\n".join(
        f"[Relevance: {s:.3f}]\n{c}" for c, s in top
    )


# %%
# Cell 6 — Batch Configuration
# ============================================================
# Define the primary company and all peers to process.
# Each entry gets the full pipeline: data -> 3 agents -> CHP -> artifact.
# After all companies are processed, a Comparative Analysis is generated.
# ============================================================

BATCH_CONFIG = {
    "primary": {
        "ticker": "MSFT",
        "company": "Microsoft Corp.",
        "industry": "Software/Cloud",
        "task_type": "initiation",
        "rating_seed": "Buy",
        "target_price": 520.0,
        "valuation_method": "EV/EBITDA",
        "key_drivers": ["Azure ARR growth", "Copilot attach rate", "GitHub enterprise expansion"],
        "thesis_seed": "Cloud + AI attach with operating-margin tailwind",
    },
    "peers": [
        {
            "ticker": "GOOGL",
            "company": "Alphabet Inc.",
            "industry": "Software/Cloud",
            "task_type": "company_research",
            "rating_seed": "",
            "target_price": None,
            "valuation_method": "",
            "key_drivers": ["Google Cloud growth", "AI integration in Search", "YouTube monetization"],
            "thesis_seed": "",
        },
        {
            "ticker": "AMZN",
            "company": "Amazon.com Inc.",
            "industry": "Software/Cloud",
            "task_type": "company_research",
            "rating_seed": "",
            "target_price": None,
            "valuation_method": "",
            "key_drivers": ["AWS reacceleration", "Advertising growth", "Operating leverage"],
            "thesis_seed": "",
        },
        {
            "ticker": "ORCL",
            "company": "Oracle Corp.",
            "industry": "Software/Cloud",
            "task_type": "company_research",
            "rating_seed": "",
            "target_price": None,
            "valuation_method": "",
            "key_drivers": ["Cloud infrastructure growth", "Cerner integration", "OCI multi-cloud"],
            "thesis_seed": "",
        },
    ],
}

# Build flat list of all companies to process (primary first)
ALL_COMPANIES = [BATCH_CONFIG["primary"]] + BATCH_CONFIG["peers"]
PRIMARY_TICKER = BATCH_CONFIG["primary"]["ticker"]
PEER_TICKERS = [p["ticker"] for p in BATCH_CONFIG["peers"]]

print(f"Peer Batch Configuration:")
print(f"  Primary: {BATCH_CONFIG['primary']['ticker']} ({BATCH_CONFIG['primary']['company']})")
print(f"  Peers:   {', '.join(PEER_TICKERS)}")
print(f"  Total companies: {len(ALL_COMPANIES)}")
print(f"  Estimated AV calls: {len(ALL_COMPANIES) * 4} (may hit free-tier daily limit of {AV_DAILY_LIMIT})")
print(f"  Estimated AI calls: {len(ALL_COMPANIES) * 5 + 1} (5 per company + 1 comparative)")

# %%
# Cell 7 — FRED Macro Panel (pulled once, shared across all companies)
# ============================================================
print(f"\n{'='*60}")
print("Pulling FRED macro panel (shared across all companies)...")
print(f"{'='*60}")

macro_data = fetch_fred_macro_panel()
print(f"  FRED series pulled: {len(macro_data)}")
for m in macro_data:
    print(f"    {m['label']}: {m['value']} (as of {m['as_of']})")

macro_context_str = ""
if macro_data:
    macro_context_str = "\n".join(
        f"  - {m['label']}: {m['value']} (as of {m['as_of']})"
        for m in macro_data
    )

# Track AlphaVantage call count for rate limit enforcement
av_call_count = 0


# %%
# Cell 8 — Single-company pipeline function
# ============================================================
def process_company(config, macro_ctx, peer_tickers_for_context):
    """Run the full pipeline for a single company and return structured results.

    Args:
        config: dict with ticker, company, industry, task_type, etc.
        macro_ctx: string with FRED macro context
        peer_tickers_for_context: list of peer tickers (for Markets Agent)

    Returns:
        dict with keys: ticker, company, fundamental_snapshot, income_summary,
                        earnings_history, price_now, fundamentals_analysis,
                        diligence_analysis, markets_analysis, chp_assessment,
                        foundation_score, chp_verdict, lock_state, final_artifact,
                        edgar_filings, rag_used, errors
    """
    global av_call_count

    ticker = config["ticker"]
    company = config["company"]
    industry = config.get("industry", "")
    task_type = config.get("task_type", "company_research")
    key_drivers = config.get("key_drivers", [])
    rating_seed = config.get("rating_seed", "")
    target_price = config.get("target_price")
    valuation_method = config.get("valuation_method", "")

    result = {
        "ticker": ticker,
        "company": company,
        "fundamental_snapshot": {},
        "income_summary": [],
        "earnings_history": [],
        "price_now": None,
        "fundamentals_analysis": "",
        "diligence_analysis": "",
        "markets_analysis": "",
        "chp_assessment": "",
        "foundation_score": 0,
        "chp_verdict": "FAIL",
        "lock_state": "HALT",
        "final_artifact": "",
        "edgar_filings": [],
        "rag_used": False,
        "errors": [],
    }

    # ---- Data Ingestion ----
    print(f"\n  [{ticker}] Pulling AlphaVantage data...")

    def rate_limited_av_call(function, symbol):
        global av_call_count
        av_call_count += 1
        if av_call_count > AV_DAILY_LIMIT:
            print(f"    [{ticker}] AV daily limit reached ({AV_DAILY_LIMIT}). Skipping remaining calls.")
            return None
        if av_call_count > 1:
            print(f"    [{ticker}] AV call #{av_call_count}, sleeping {AV_RATE_LIMIT_SECONDS}s...")
            time.sleep(AV_RATE_LIMIT_SECONDS)
        return fetch_alphavantage(function, symbol)

    overview_data = rate_limited_av_call("OVERVIEW", ticker)
    income_data = rate_limited_av_call("INCOME_STATEMENT", ticker)
    earnings_data = rate_limited_av_call("EARNINGS", ticker)
    quote_data = rate_limited_av_call("GLOBAL_QUOTE", ticker)

    print(f"  [{ticker}] AV OVERVIEW: {'OK' if overview_data else 'MISSING'}")
    print(f"  [{ticker}] AV INCOME: {'OK' if income_data else 'MISSING'}")
    print(f"  [{ticker}] AV EARNINGS: {'OK' if earnings_data else 'MISSING'}")
    print(f"  [{ticker}] AV QUOTE: {'OK' if quote_data else 'MISSING'}")

    # EDGAR filings
    print(f"  [{ticker}] Pulling SEC EDGAR filings...")
    edgar_filings = fetch_edgar_filing_index(ticker)
    result["edgar_filings"] = edgar_filings
    print(f"  [{ticker}] EDGAR filings: {len(edgar_filings)}")

    # Build fundamental snapshot
    fundamental_snapshot = {}
    if overview_data:
        fundamental_snapshot = {
            "ticker": ticker,
            "sector": overview_data.get("Sector", "n/a"),
            "industry": overview_data.get("Industry", "n/a"),
            "market_cap": overview_data.get("MarketCapitalization"),
            "pe_ratio": overview_data.get("PERatio"),
            "forward_pe": overview_data.get("ForwardPE"),
            "profit_margin": overview_data.get("ProfitMargin"),
            "operating_margin_ttm": overview_data.get("OperatingMarginTTM"),
            "revenue_ttm": overview_data.get("RevenueTTM"),
            "eps_ttm": overview_data.get("EPS"),
            "beta": overview_data.get("Beta"),
            "week52_low": overview_data.get("52WeekLow"),
            "week52_high": overview_data.get("52WeekHigh"),
            "shares_outstanding": overview_data.get("SharesOutstanding"),
            "latest_quarter": overview_data.get("LatestQuarter"),
            "source": "AlphaVantage",
            "pulled_at": datetime.utcnow().isoformat() + "Z",
        }
    result["fundamental_snapshot"] = fundamental_snapshot

    # Build income summary
    income_summary = []
    if income_data:
        for rpt in (income_data.get("annualReports") or [])[:3]:
            income_summary.append({
                "fiscal_date": rpt.get("fiscalDateEnding"),
                "revenue": rpt.get("totalRevenue"),
                "gross_profit": rpt.get("grossProfit"),
                "ebit": rpt.get("operatingIncome"),
                "net_income": rpt.get("netIncome"),
            })
    result["income_summary"] = income_summary

    # Build earnings history
    earnings_history = []
    if earnings_data:
        for rpt in (earnings_data.get("quarterlyEarnings") or [])[:6]:
            earnings_history.append({
                "date": rpt.get("fiscalDateEnding"),
                "reported_eps": rpt.get("reportedEPS"),
                "estimated_eps": rpt.get("estimatedEPS"),
                "surprise_pct": rpt.get("surprisePercentage"),
            })
    result["earnings_history"] = earnings_history

    # Build quote snapshot
    price_now = None
    if quote_data and quote_data.get("Global Quote"):
        try:
            price_now = float(quote_data["Global Quote"].get("05. price", 0))
        except (ValueError, TypeError):
            pass
    result["price_now"] = price_now

    # ---- RAG over SEC Filings ----
    filing_text_sample = ""
    rag_chunks = []

    if edgar_filings:
        filings_to_fetch = []
        for form_type in ["10-K", "10-Q", "DEF 14A"]:
            filing = next((f for f in edgar_filings if f["form"] == form_type), None)
            if filing:
                filings_to_fetch.append(filing)

        if filings_to_fetch:
            print(f"  [{ticker}] RAG: Fetching {len(filings_to_fetch)} filing(s)...")
            all_filing_text = ""
            for filing in filings_to_fetch:
                furl = (f"https://www.sec.gov/Archives/edgar/data/"
                       f"{filing['cik']}/{filing['accession_no'].replace('-', '')}/"
                       f"{filing['primary_document']}")
                text = fetch_edgar_filing_text(furl)
                if text:
                    all_filing_text += f"\n\n=== {filing['form']} filed {filing['filing_date']} ===\n{text}"

            filing_text_sample = all_filing_text[:8000]
            chunks = chunk_text(all_filing_text, chunk_size=1500, overlap=200)
            print(f"  [{ticker}] RAG: {len(chunks)} chunks from {len(all_filing_text)} chars")

            if embedding_client and chunks:
                print(f"  [{ticker}] RAG: Embedding {len(chunks)} chunks...")
                all_embeddings = []
                for i in range(0, len(chunks), 20):
                    batch = chunks[i:i + 20]
                    embs = embed_texts(batch)
                    all_embeddings.extend(embs)
                    if i + 20 < len(chunks):
                        time.sleep(1)
                rag_chunks = list(zip(chunks, all_embeddings))
                result["rag_used"] = True
                print(f"  [{ticker}] RAG: {len(rag_chunks)} chunks embedded")
            elif chunks:
                filing_text_sample = all_filing_text[:3000]

    # ---- Check data sufficiency ----
    if not overview_data:
        result["errors"].append("AlphaVantage OVERVIEW unavailable")
    if not income_data:
        result["errors"].append("AlphaVantage INCOME_STATEMENT unavailable")

    # ---- Fundamentals Agent ----
    print(f"  [{ticker}] Running Fundamentals Agent...")
    fundamentals_system = """You are a senior equity research analyst specializing in business model analysis.
You produce structured, source-cited research outputs. Every claim must cite a primary source
(10-K/10-Q/AlphaVantage OVERVIEW/EARNINGS) with a date.

Rules:
- Separate facts from estimates; every estimate must show its formula and inputs
- When AlphaVantage disagrees with a 10-K, the 10-K wins - flag the gap
- Bare percentages without a base period are a hallucination risk - always pair % with the base level and date
- Map revenue by segment from the latest 10-K first; fall back to product when segments are coarse
- KPI definitions must match the latest 10-K, not a stale comparable
"""

    fundamentals_context = f"""RESEARCH TARGET:
- Company: {company} ({ticker})
- Industry: {industry}
- Peers: {', '.join(peer_tickers_for_context)}

FUNDAMENTAL SNAPSHOT (AlphaVantage):
{json.dumps(fundamental_snapshot, indent=2, default=str)}

INCOME STATEMENT SUMMARY (3 years):
{json.dumps(income_summary, indent=2, default=str)}

EARNINGS HISTORY (6 quarters):
{json.dumps(earnings_history, indent=2, default=str)}
"""

    if rag_chunks:
        rag_fundamentals = retrieve_chunks(
            f"business model revenue drivers financial health {ticker} {company}",
            rag_chunks, top_k=5,
        )
        if rag_fundamentals:
            fundamentals_context += f"""
RELEVANT SEC FILING EXCERPTS (RAG-retrieved):
{rag_fundamentals}
"""
    elif filing_text_sample:
        fundamentals_context += f"""
LATEST 10-K EXCERPT (for RAG grounding):
{filing_text_sample[:3000]}
"""

    fundamentals_prompt = f"""Produce a business model analysis for {company} ({ticker}).
Structure: 1) Business Model Map 2) Revenue Drivers 3) Financial Health 4) KPIs to Watch 5) Confidence Assessment.
Keep response under 2000 words for batch processing efficiency."""

    try:
        fundamentals_analysis = ai_complete(fundamentals_system, fundamentals_context + "\n\n" + fundamentals_prompt, temperature=0.3, max_tokens=3500)
        result["fundamentals_analysis"] = fundamentals_analysis
        print(f"  [{ticker}] Fundamentals: {len(fundamentals_analysis)} chars")
    except Exception as e:
        result["errors"].append(f"Fundamentals Agent failed: {e}")
        result["fundamentals_analysis"] = f"[ERROR] {e}"

    # ---- Diligence Agent ----
    print(f"  [{ticker}] Running Diligence Agent...")
    diligence_system = """You are a forensic accounting and due diligence specialist.
Rules:
- Every flag must cite a filing type + filing date
- Quantify: SBC % of revenue, GAAP-vs-non-GAAP gap, FCF-vs-NI divergence
- Off-balance-sheet exposure is most common in growth companies
- Lead with the largest-magnitude finding
"""

    sec_filings_summary = "\n".join(
        f"  - {f['form']}: filed {f['filing_date']} ({f['accession_no']})"
        for f in edgar_filings[:10]
    )

    diligence_context = f"""RESEARCH TARGET: {company} ({ticker}) | Industry: {industry}

FUNDAMENTAL SNAPSHOT: {json.dumps(fundamental_snapshot, indent=2, default=str)}
INCOME STATEMENT (3 years): {json.dumps(income_summary, indent=2, default=str)}
RECENT SEC FILINGS: {sec_filings_summary}
FUNDAMENTALS OUTPUT: {result['fundamentals_analysis'][:1500]}
"""

    if rag_chunks:
        rag_diligence = retrieve_chunks(f"risk factors red flags governance SBC {ticker}", rag_chunks, top_k=5)
        if rag_diligence:
            diligence_context += f"\nRELEVANT SEC FILING EXCERPTS (RAG):\n{rag_diligence}"
    elif filing_text_sample:
        diligence_context += f"\n10-K EXCERPT (risk): {filing_text_sample[:3000]}"

    diligence_prompt = f"""Perform a diligence scan on {company} ({ticker}).
Structure: 1) Red Flag Scan 2) Governance Read 3) Risk Register 4) Going-Concern Check 5) What Would Change Your Read.
Keep response under 1500 words for batch processing efficiency."""

    try:
        diligence_analysis = ai_complete(diligence_system, diligence_context + "\n\n" + diligence_prompt, temperature=0.3, max_tokens=3000)
        result["diligence_analysis"] = diligence_analysis
        print(f"  [{ticker}] Diligence: {len(diligence_analysis)} chars")
    except Exception as e:
        result["errors"].append(f"Diligence Agent failed: {e}")
        result["diligence_analysis"] = f"[ERROR] {e}"

    # ---- Markets Agent ----
    print(f"  [{ticker}] Running Markets Agent...")
    markets_system = """You are a senior markets and valuation analyst.
Rules:
- Always pair a primary multiple with a peer median and a macro overlay
- Multiple expansion under tightening rates rarely persists
- Forward consensus is a herd anchor - note dispersion, not just median
"""

    markets_context = f"""RESEARCH TARGET: {company} ({ticker})
Industry: {industry} | Peers: {', '.join(peer_tickers_for_context)}
Current Price: ${price_now or 'DATA NEEDED'} | Valuation: {valuation_method or 'N/A'}

FUNDAMENTAL SNAPSHOT: {json.dumps(fundamental_snapshot, indent=2, default=str)}
INCOME STATEMENT: {json.dumps(income_summary, indent=2, default=str)}
FUNDAMENTALS: {result['fundamentals_analysis'][:1200]}
DILIGENCE: {result['diligence_analysis'][:1200]}
"""

    if macro_ctx:
        markets_context += f"\nMACRO BACKDROP (FRED):\n{macro_ctx}"

    if rag_chunks:
        rag_markets = retrieve_chunks(f"valuation peer comparison {ticker}", rag_chunks, top_k=3)
        if rag_markets:
            markets_context += f"\nRELEVANT FILINGS (RAG):\n{rag_markets}"

    markets_prompt = f"""Produce a markets analysis for {company} ({ticker}).
Structure: 1) Key Data Snapshot 2) Peer Analysis 3) Valuation View 4) Thesis Triggers 5) Recommendation.
Keep response under 1500 words for batch processing efficiency."""

    try:
        markets_analysis = ai_complete(markets_system, markets_context + "\n\n" + markets_prompt, temperature=0.3, max_tokens=3000)
        result["markets_analysis"] = markets_analysis
        print(f"  [{ticker}] Markets: {len(markets_analysis)} chars")
    except Exception as e:
        result["errors"].append(f"Markets Agent failed: {e}")
        result["markets_analysis"] = f"[ERROR] {e}"

    # ---- CHP Hardening ----
    print(f"  [{ticker}] Running CHP Foundation Hardening...")
    chp_system = """You are a Consensus Hardening Protocol (CHP) adjudicator.
Stress-test the research: identify weakest assumptions, attack them, score 0-100.
Verdict: PASS (>=70), REFRAME (40-69), FAIL (<40)."""

    chp_prompt = f"""Review multi-agent research for {company} ({ticker}).

FUNDAMENTALS: {result['fundamentals_analysis'][:1500]}
DILIGENCE: {result['diligence_analysis'][:1500]}
MARKETS: {result['markets_analysis'][:1500]}

PRODUCE:
1. Foundation Disclosure (3 weakest assumptions, 2 invalidation conditions, key vulnerability)
2. Foundation Attack
3. Foundation Score (0-100)
4. Verdict: PASS, REFRAME, or FAIL (one word)"""

    try:
        chp_assessment = ai_complete(chp_system, chp_prompt, temperature=0.2, max_tokens=2500, use_partner=USE_PARTNER_MODEL)
        result["chp_assessment"] = chp_assessment

        # Parse score
        import re
        score_match = re.search(r"foundation score[^:]*:\s*(\d+)", chp_assessment, re.IGNORECASE)
        foundation_score = int(score_match.group(1)) if score_match else 50
        result["foundation_score"] = foundation_score

        chp_verdict = "PASS"
        if "REFRAME" in chp_assessment.upper():
            chp_verdict = "REFRAME"
        elif "FAIL" in chp_assessment.upper() and "failure" not in chp_assessment.lower()[:200]:
            chp_verdict = "FAIL"
        result["chp_verdict"] = chp_verdict
        result["lock_state"] = (
            "PROVISIONAL_LOCK" if foundation_score >= 70
            else ("REFRAME_REQUIRED" if foundation_score >= 40 else "HALT")
        )
        print(f"  [{ticker}] CHP: Score={foundation_score}, Verdict={chp_verdict}, Lock={result['lock_state']}")
    except Exception as e:
        result["errors"].append(f"CHP failed: {e}")
        result["chp_assessment"] = f"[ERROR] {e}"
        result["foundation_score"] = 0

    # ---- Synthesize Artifact ----
    print(f"  [{ticker}] Synthesizing research artifact...")
    if task_type == "initiation":
        artifact_system = "You are a senior equity research writer producing a Goldman Sachs-style Initiation of Coverage."
        artifact_prompt = f"""Produce an Initiation of Coverage for {company} ({ticker}).
Current Price: ${price_now or 'DATA NEEDED'} | Target: ${target_price or 'N/A'} | Rating: {rating_seed or 'N/A'}
CHP Score: {result['foundation_score']} | Lock: {result['lock_state']} | Peers: {', '.join(peer_tickers_for_context)}

FUNDAMENTALS: {result['fundamentals_analysis']}
DILIGENCE: {result['diligence_analysis']}
MARKETS: {result['markets_analysis']}

Structure (markdown, under 3000 words):
# Initiation of Coverage - {company} ({ticker})
## 1. Key Data & Forecast Snapshot
## 2. Investment Thesis
## 3. Investment Positives
## 4. Competitive / Peer Analysis
## 5. Estimates & Operating Assumptions
## 6. Valuation
## 7. Key Risks
## 8. Appendix (Sources, Macro, Lock Status)"""
    else:
        artifact_system = "You are a senior equity research analyst producing a Business Model Memo."
        artifact_prompt = f"""Produce a Business Model Memo for {company} ({ticker}).
CHP Score: {result['foundation_score']} | Lock: {result['lock_state']} | Peers: {', '.join(peer_tickers_for_context)}

FUNDAMENTALS: {result['fundamentals_analysis']}
DILIGENCE: {result['diligence_analysis']}
MARKETS: {result['markets_analysis']}

Structure (markdown, under 2500 words):
# Business Model Memo - {company} ({ticker})
## 1. Snapshot
## 2. Business Model Map
## 3. Three-Year Income Trajectory
## 4. Revenue Drivers
## 5. Unit Economics
## 6. KPIs to Watch
## 7. Peer Snapshot
## 8. Risks & Sensitivities
## 9. What Would Change the Thesis
## Macro Backdrop | Lock Status"""

    try:
        final_artifact = ai_complete(artifact_system, artifact_prompt, temperature=0.2, max_tokens=5000)
        result["final_artifact"] = final_artifact
        print(f"  [{ticker}] Artifact: {len(final_artifact)} chars")
    except Exception as e:
        result["errors"].append(f"Artifact synthesis failed: {e}")
        result["final_artifact"] = f"[ERROR] {e}"

    return result


print("Single-company pipeline function defined.")

# %%
# Cell 9 — Execute batch pipeline for all companies
# ============================================================
print(f"\n{'='*60}")
print(f"PEER BATCH PIPELINE - Processing {len(ALL_COMPANIES)} companies")
print(f"{'='*60}")

batch_results = {}
batch_start_time = datetime.utcnow()

for idx, company_config in enumerate(ALL_COMPANIES):
    ticker = company_config["ticker"]
    company = company_config["company"]
    print(f"\n{'='*60}")
    print(f"  [{idx+1}/{len(ALL_COMPANIES)}] Processing: {company} ({ticker})")
    print(f"{'='*60}")

    try:
        result = process_company(company_config, macro_context_str, PEER_TICKERS)
        batch_results[ticker] = result

        # Summary
        print(f"\n  [{ticker}] DONE:")
        print(f"    AV calls used so far: {av_call_count}/{AV_DAILY_LIMIT}")
        print(f"    CHP Score: {result['foundation_score']} | Verdict: {result['chp_verdict']} | Lock: {result['lock_state']}")
        if result["errors"]:
            print(f"    Errors: {result['errors']}")
    except Exception as e:
        print(f"\n  [{ticker}] FATAL ERROR: {e}")
        batch_results[ticker] = {
            "ticker": ticker,
            "company": company,
            "errors": [str(e)],
            "foundation_score": 0,
            "chp_verdict": "FAIL",
            "lock_state": "HALT",
        }

batch_end_time = datetime.utcnow()
batch_duration = (batch_end_time - batch_start_time).total_seconds()

# Summary table
print(f"\n{'='*60}")
print("BATCH EXECUTION SUMMARY")
print(f"{'='*60}")
print(f"{'Ticker':<8} {'Company':<25} {'Score':>5} {'Verdict':<10} {'Lock':<20} {'Errors'}")
print("-" * 90)
for ticker, r in batch_results.items():
    score = r.get("foundation_score", 0)
    verdict = r.get("chp_verdict", "FAIL")
    lock = r.get("lock_state", "HALT")
    errors = len(r.get("errors", []))
    company = r.get("company", "?")[:24]
    print(f"{ticker:<8} {company:<25} {score:>5} {verdict:<10} {lock:<20} {errors}")
print("-" * 90)
print(f"Total duration: {batch_duration:.0f}s ({batch_duration/60:.1f}min)")
print(f"AV calls consumed: {av_call_count}/{AV_DAILY_LIMIT}")

# %%
# Cell 10 — Comparative Analysis Agent (cross-company synthesis)
# ============================================================
print(f"\n{'='*60}")
print("Running Comparative Analysis Agent (cross-company)")
print(f"{'='*60}\n")

comparative_system = """You are a senior equity research strategist producing a cross-company
comparative analysis (also called a "Tear Sheet" or "Peer Group Monitor").

Your job is to synthesize the individual company analyses into an actionable
comparison that highlights relative value, risk-adjusted positioning,
and key differentiators across the peer group.

Rules:
- Every comparative claim must be grounded in the individual company analyses
- Use tables for side-by-side metric comparison
- Relative positioning must cite specific numbers, not vague adjectives
- Highlight the best risk/reward in the peer group
- Macro context affects all peers — note differential sensitivity
- The primary company should receive deeper treatment than peers
"""

# Build comparative context from batch results
comparative_context = f"""PRIMARY COMPANY: {BATCH_CONFIG['primary']['company']} ({PRIMARY_TICKER})
PEER GROUP: {', '.join(PEER_TICKERS)}
INDUSTRY: {BATCH_CONFIG['primary']['industry']}
ANALYSIS DATE: {batch_start_time.strftime('%Y-%m-%d')}

MACRO BACKDROP (FRED):
{macro_context_str}

"""

# Add each company's results
for ticker, r in batch_results.items():
    is_primary = ticker == PRIMARY_TICKER
    label = "PRIMARY" if is_primary else "PEER"
    price = r.get("price_now")
    fs = r.get("fundamental_snapshot", {})

    comparative_context += f"""
{'='*40}
{label}: {r.get('company', ticker)} ({ticker})
CHP Foundation Score: {r.get('foundation_score', 0)} | Lock: {r.get('lock_state', 'HALT')}
Current Price: ${price or 'N/A'}
Market Cap: {fs.get('market_cap', 'N/A')} | P/E: {fs.get('pe_ratio', 'N/A')} | Fwd P/E: {fs.get('forward_pe', 'N/A')}
Revenue TTM: {fs.get('revenue_ttm', 'N/A')} | EPS TTM: {fs.get('eps_ttm', 'N/A')}
Beta: {fs.get('beta', 'N/A')} | Profit Margin: {fs.get('profit_margin', 'N/A')}

FUNDAMENTALS ANALYSIS SUMMARY:
{r.get('fundamentals_analysis', '[NOT AVAILABLE]')[:1200]}

DILIGENCE ANALYSIS SUMMARY:
{r.get('diligence_analysis', '[NOT AVAILABLE]')[:800]}

MARKETS ANALYSIS SUMMARY:
{r.get('markets_analysis', '[NOT AVAILABLE]')[:800]}

"""

comparative_prompt = f"""Produce a comprehensive cross-company comparative analysis for the following peer group:

PRIMARY: {BATCH_CONFIG['primary']['company']} ({PRIMARY_TICKER})
PEERS: {', '.join(f"{BATCH_CONFIG['peers'][i]['company']} ({t})" for i, t in enumerate(PEER_TICKERS))}

PRODUCE THE FOLLOWING (markdown format):

# Peer Group Comparative Analysis
_date: {batch_start_time.strftime('%Y-%m-%d')} | primary: **{PRIMARY_TICKER}**

## 1. Executive Summary
- One paragraph on the peer group dynamics and key takeaway

## 2. Side-by-Side Metrics Table
| Metric | {PRIMARY_TICKER} | {' | '.join(PEER_TICKERS)} |
Include: Market Cap, P/E, Fwd P/E, EV/EBITDA (est.), Revenue TTM, Revenue Growth, Margin, Beta, CHP Score

## 3. Relative Value Ranking
- Rank all companies by risk-adjusted value (1 = most attractive)
- Justify each ranking with specific numbers

## 4. Differentiated Strengths & Weaknesses
- For each company: one bull case point, one bear case point
- Cite which agent finding supports each

## 5. Cross-Company Risk Assessment
- Systemic risks affecting the entire group
- Company-specific risks
- Concentration risk (are they all exposed to the same driver?)

## 6. Macro Sensitivity Analysis
- How would each company be affected by:
  a) 100bps rate cut
  b) Recession scenario
  c) AI spending acceleration/deceleration

## 7. Primary Company Deep Dive: {BATCH_CONFIG['primary']['company']}
- Why {PRIMARY_TICKER} vs the peer group
- Specific recommendation with confidence level
- Key catalysts and timeline

## 8. Actionable Outputs
- Best risk/reward in group
- Most underappreciated
- Most overvalued (if any)
- Pair trade suggestions (long X, short Y)"""

try:
    comparative_analysis = ai_complete(
        comparative_system,
        comparative_context + "\n\n" + comparative_prompt,
        temperature=0.3,
        max_tokens=6000,
    )
    print(comparative_analysis[:500] + "...\n")
    print(f"[Comparative Analysis completed - {len(comparative_analysis)} chars]")
except Exception as e:
    comparative_analysis = f"[ERROR] Comparative analysis failed: {e}"
    print(f"ERROR: {e}")

# %%
# Cell 11 — Write all results to Delta tables
# ============================================================
print(f"\n{'='*60}")
print("Writing batch results to Delta tables...")
print(f"{'='*60}\n")

from pyspark.sql import Row

now = datetime.utcnow().isoformat() + "Z"
all_session_rows = []
all_agent_rows = []
all_artifact_rows = []
all_audit_rows = []

for ticker, r in batch_results.items():
    session_id = f"batch-{PRIMARY_TICKER}-{ticker}-{batch_start_time.strftime('%Y%m%d%H%M%S')}"

    # 1. Research session
    task_type = next(
        (c["task_type"] for c in ALL_COMPANIES if c["ticker"] == ticker),
        "company_research",
    )
    company_name = r.get("company", ticker)

    all_session_rows.append(Row(
        decision_id=session_id,
        title=f"{company_name} {task_type.replace('_', ' ').title()} (batch)",
        task_type=task_type,
        company=company_name,
        ticker=ticker,
        industry=r.get("fundamental_snapshot", {}).get("industry", "") or next(
            (c.get("industry", "") for c in ALL_COMPANIES if c["ticker"] == ticker), ""
        ),
        status=r.get("lock_state", "HALT"),
        foundation_score=r.get("foundation_score", 0),
        r0_verdict=r.get("chp_verdict", "FAIL") if r.get("chp_verdict") in ("PASS", "HALT") else "PASS",
        foundation_verdict=r.get("chp_verdict", "FAIL"),
        origin_model=AZURE_AI_DEPLOYMENT,
        partner_model=AZURE_AI_PARTNER_DEPLOYMENT if USE_PARTNER_MODEL else "none",
        created_at=now,
    ))

    # 2. Agent outputs
    for agent_name in ["fundamentals", "diligence", "markets"]:
        analysis = r.get(f"{agent_name}_analysis", "")
        all_agent_rows.append(Row(
            decision_id=session_id,
            agent_name=agent_name,
            recommendation=analysis[:2000] if analysis else "",
            confidence="HIGH" if analysis and "[ERROR]" not in analysis else "LOW",
            playbook_deltas=0,
            produces=f"{agent_name}_analysis",
            consumes="",
            failure_mode=None if analysis and "[ERROR]" not in analysis else analysis[:200],
            ran_at=now,
        ))

    # 3. Research artifact
    all_artifact_rows.append(Row(
        decision_id=session_id,
        artifact_type=task_type,
        title=r.get("final_artifact", "").split("\n")[0].replace("#", "").strip()[:200],
        lock_state=r.get("lock_state", "HALT"),
        rating_seed=next(
            (c.get("rating_seed", "") for c in ALL_COMPANIES if c["ticker"] == ticker), ""
        ),
        target_price=next(
            (c.get("target_price") for c in ALL_COMPANIES if c["ticker"] == ticker), None
        ),
        valuation_method=next(
            (c.get("valuation_method", "") for c in ALL_COMPANIES if c["ticker"] == ticker), ""
        ),
        peers=",".join(PEER_TICKERS),
        artifact_md=r.get("final_artifact", ""),
        sources=f"AlphaVantage; SEC EDGAR; FRED macro panel",
        created_at=now,
    ))

    # 4. Audit trail
    for agent_name in ["fundamentals", "diligence", "markets"]:
        all_audit_rows.append(Row(
            decision_id=session_id,
            agent=agent_name,
            claim="batch_analysis",
            expansion_excerpt=f"{ticker} {agent_name} agent output in peer batch",
            grounding_source="AlphaVantage + SEC EDGAR",
            grounding_confidence="HIGH",
            risk_flag=None,
            logged_at=now,
        ))

# Write sessions
existing_sessions = spark.table("research_sessions")
new_sessions = spark.createDataFrame(all_session_rows)
all_sessions = existing_sessions.union(new_sessions)
all_sessions.write.format("delta").mode("overwrite").saveAsTable("research_sessions")
print(f"  research_sessions: {all_sessions.count()} total records")

# Write agent outputs
existing_agents = spark.table("agent_outputs")
new_agents = spark.createDataFrame(all_agent_rows)
all_agents = existing_agents.union(new_agents)
all_agents.write.format("delta").mode("overwrite").saveAsTable("agent_outputs")
print(f"  agent_outputs: {all_agents.count()} total records")

# Write artifacts
existing_artifacts = spark.table("research_artifacts")
new_artifacts = spark.createDataFrame(all_artifact_rows)
all_artifacts = existing_artifacts.union(new_artifacts)
all_artifacts.write.format("delta").mode("overwrite").saveAsTable("research_artifacts")
print(f"  research_artifacts: {all_artifacts.count()} total records")

# Write audit trail
existing_audit = spark.table("audit_trail")
new_audit = spark.createDataFrame(all_audit_rows)
all_audit = existing_audit.union(new_audit)
all_audit.write.format("delta").mode("overwrite").saveAsTable("audit_trail")
print(f"  audit_trail: {all_audit.count()} total records")

# ---- Write peer_comparisons table (new) ----
try:
    peer_comparison_row = Row(
        batch_id=f"batch-{PRIMARY_TICKER}-{batch_start_time.strftime('%Y%m%d%H%M%S')}",
        primary_ticker=PRIMARY_TICKER,
        primary_company=BATCH_CONFIG["primary"]["company"],
        peer_tickers=",".join(PEER_TICKERS),
        industry=BATCH_CONFIG["primary"]["industry"],
        comparative_md=comparative_analysis,
        companies_processed=len(batch_results),
        avg_foundation_score=sum(r.get("foundation_score", 0) for r in batch_results.values()) / max(len(batch_results), 1),
        pass_count=sum(1 for r in batch_results.values() if r.get("chp_verdict") == "PASS"),
        reframe_count=sum(1 for r in batch_results.values() if r.get("chp_verdict") == "REFRAME"),
        fail_count=sum(1 for r in batch_results.values() if r.get("chp_verdict") == "FAIL"),
        av_calls_used=av_call_count,
        duration_seconds=batch_duration,
        macro_json=json.dumps(macro_data, default=str) if macro_data else "[]",
        created_at=now,
    )

    # Check if table exists, create if not
    try:
        spark.table("peer_comparisons")
        existing_comps = spark.table("peer_comparisons")
        new_comps = spark.createDataFrame([peer_comparison_row])
        all_comps = existing_comps.union(new_comps)
        all_comps.write.format("delta").mode("overwrite").saveAsTable("peer_comparisons")
    except Exception:
        spark.createDataFrame([peer_comparison_row]).write.format("delta").mode("overwrite").saveAsTable("peer_comparisons")

    print(f"  peer_comparisons: written (new table)")
except Exception as e:
    print(f"  peer_comparisons: FAILED to write - {e}")
    print(f"    Note: Run the setup notebook first to create the peer_comparisons table schema.")

# %%
# Cell 12 — Batch Summary Dashboard
# ============================================================
print(f"\n{'='*60}")
print(f"PEER BATCH PIPELINE COMPLETE")
print(f"{'='*60}")
print(f"  Primary:   {BATCH_CONFIG['primary']['company']} ({PRIMARY_TICKER})")
print(f"  Peers:     {', '.join(PEER_TICKERS)}")
print(f"  Duration:  {batch_duration:.0f}s ({batch_duration/60:.1f}min)")
print(f"  AV calls:  {av_call_count}/{AV_DAILY_LIMIT}")
print(f"")

for ticker, r in batch_results.items():
    score = r.get("foundation_score", 0)
    verdict = r.get("chp_verdict", "FAIL")
    lock = r.get("lock_state", "HALT")
    artifact_len = len(r.get("final_artifact", ""))
    errors = r.get("errors", [])
    rag = "RAG" if r.get("rag_used") else "text"

    print(f"  {ticker:<6} | Score: {score:>3} | {verdict:<8} | {lock:<20} | {artifact_len:>5} chars | {rag}")
    for err in errors:
        print(f"         | ERROR: {err}")

print(f"\n{'='*60}")
print(f"Comparative Analysis: {'generated' if '[ERROR]' not in comparative_analysis else 'FAILED'}")
print(f"  Length: {len(comparative_analysis)} chars")
print(f"{'='*60}")
print(f"All results written to Delta tables in Fabric Lakehouse.")
