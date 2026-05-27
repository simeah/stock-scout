"""
core/portfolio.py
=================
Handles the full portfolio setup flow:
  1. Parse free-text input → structured stock JSON
  2. Generate consensus thesis for stocks without one
  3. Validate + extract search terms from thesis
  4. Confirm with user

Portfolio JSON schema per stock:
{
  "ticker":    "AAPL",
  "name":      "Apple Inc",
  "position":  "LONG" | "SHORT" | "WATCHLIST",
  "thesis":    "...",
  "keywords":  ["keyword1", "keyword2", ...],
  "sources":   [...]   <- populated by fetchers.py
}
"""

import json
import time
from core.llm import llm_json, llm_call
from core.fetchers import enrich_with_cik, enrich_sources_with_consensus

# ──────────────────────────────────────────────────────────────────────────────
# PROMPTS
# ──────────────────────────────────────────────────────────────────────────────

PARSE_SYSTEM = """You are a financial assistant helping a retail investor set up
a stock portfolio tracker. Extract structured information from free-text input.

Rules:
- If position is not specified, assume LONG
- If no thesis is provided, set thesis to null (we will generate one)
- Tickers should be uppercase
- Names should be full company names
- Be generous in parsing — if someone says "I own Apple" that's enough

Return ONLY a valid JSON array. No preamble, no markdown.
Each object must have: ticker, name, position, thesis (string or null)

Example output:
[
  {"ticker": "AAPL", "name": "Apple Inc", "position": "LONG", "thesis": "Strong ecosystem lock-in and services growth"},
  {"ticker": "TSLA", "name": "Tesla Inc", "position": "WATCHLIST", "thesis": null}
]"""

VALIDATE_SYSTEM = """You are a financial assistant validating a user's stock portfolio input.

Check each stock for:
1. Is the ticker likely correct? (flag obvious errors)
2. Is the company name consistent with the ticker?
3. Is the position (LONG/SHORT/WATCHLIST) sensible?
4. If a thesis is provided, is it meaningful enough to generate search terms from?

Return a JSON object with:
{
  "valid": true/false,
  "issues": ["list of issues, empty if none"],
  "clarifying_questions": ["questions to ask user if needed, empty if none"],
  "stocks": [same array as input, with any corrections applied]
}"""

THESIS_SYSTEM = """You are a senior equity research analyst. Generate a clear,
factual investment thesis based on the current Wall Street consensus view —
i.e. the average perspective across major sell-side brokers and analysts.

This is NOT a personalised view. It reflects what most mainstream analysts
currently think about this stock.

The thesis should cover:
- What the company does (1 sentence)
- Why the consensus view is positive/negative/neutral (2-3 key reasons)
- Key risks the Street is watching (2-3 risks)
- What news/events would be most important to monitor

Write in plain English — no jargon. Keep it under 150 words.
Return ONLY the thesis text, no headers, no markdown."""

KEYWORDS_SYSTEM = """You are a financial research analyst. Given an investment thesis
for a stock, extract specific search keywords and phrases that would surface
the most relevant news articles.

Rules:
- Focus on specific, distinctive terms (not generic words like "stock" or "market")
- Include: company name variations, key products/services, competitor names,
  regulatory bodies, key executives, industry-specific terms
- Each keyword should be 1-4 words
- Aim for 15-25 keywords
- Think about what trade publications, Reuters, Bloomberg would write about

Return ONLY a JSON array of strings. No preamble, no markdown.
Example: ["Apple iPhone", "App Store revenue", "Tim Cook", "EU DMA Apple", "services growth"]"""


# ──────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def parse_free_text(text: str, provider: str, api_key: str) -> list[dict]:
    """
    Parse free-text stock input into structured list of stock dicts.
    """
    prompt = f"""Extract stock portfolio information from this text:

---
{text}
---

Return a JSON array of stock objects."""

    return llm_json(prompt, system=PARSE_SYSTEM, provider=provider, api_key=api_key)


def validate_portfolio(stocks: list[dict], provider: str, api_key: str) -> dict:
    """
    Validate parsed portfolio. Returns validation result with any issues/questions.
    """
    prompt = f"""Validate this portfolio:

{json.dumps(stocks, indent=2)}

Check tickers, names, positions, and thesis quality."""

    return llm_json(prompt, system=VALIDATE_SYSTEM, provider=provider, api_key=api_key)


def generate_consensus_thesis(ticker: str, name: str, position: str,
                               provider: str, api_key: str) -> str:
    """
    Generate a consensus investment thesis for a stock that didn't have one.
    """
    pos_context = {
        "LONG":      "an investor who owns this stock and expects it to go up",
        "SHORT":     "an investor who is short this stock and expects it to go down",
        "WATCHLIST": "an investor watching this stock for a potential entry point",
    }.get(position, "an investor tracking this stock")

    prompt = f"""Generate an investment thesis for {name} ({ticker}) for {pos_context}.
Focus on the most widely cited reasons for this position based on current analyst consensus."""

    return llm_call(prompt, system=THESIS_SYSTEM, provider=provider, api_key=api_key)


def extract_consensus_keywords(
    ticker: str,
    company: str,
    provider: str,
    api_key: str,
) -> list[str]:
    """
    Extract consensus keywords by searching for what Wall Street is talking about.
    Searches for: analyst ratings, earnings surprises, price targets, insider activity.
    Returns relevant keywords/themes from those searches.
    """
    from core.fetchers import google_news
    import time
    
    consensus_searches = [
        f"{ticker} {company} analyst ratings broker views",
        f"{ticker} {company} earnings surprise beat miss",
        f"{ticker} {company} price target raised cut",
        f"{ticker} {company} insider buying selling",
    ]
    
    # Fetch articles for each consensus search
    all_articles = []
    for search_term in consensus_searches:
        articles = google_news(search_term, label="Consensus")
        all_articles.extend(articles[:5])  # Take top 5 from each search
        time.sleep(0.2)
    
    if not all_articles:
        return []
    
    # Use Claude to extract key themes/keywords from the articles
    article_text = "\n".join([
        f"- {a['title']}: {a.get('snippet', '')[:100]}"
        for a in all_articles
    ])
    
    prompt = f"""From these recent Wall Street articles about {ticker}, extract 5-8 key themes/keywords 
that represent what analysts and investors are focused on (e.g., "earnings growth", "margin pressure", "market share", etc).

Articles:
{article_text}

Return ONLY a JSON array of keywords: ["keyword1", "keyword2", ...]"""

    system = "You are extracting key investment themes from news articles."
    
    try:
        result = llm_json(prompt, system=system, provider=provider, api_key=api_key, max_tokens=500)
        if isinstance(result, list):
            return result
    except Exception as ex:
        print(f"  [WARN] Consensus keyword extraction error: {ex}")
    
    return []


def extract_keywords(ticker: str, name: str, thesis: str,
                     provider: str, api_key: str) -> list[str]:
    """
    Extract search keywords from a thesis.
    """
    prompt = f"""Stock: {name} ({ticker})

Thesis:
{thesis}

Extract specific search keywords for news monitoring."""

    return llm_json(prompt, system=KEYWORDS_SYSTEM, provider=provider, api_key=api_key)


def build_portfolio(
    raw_text:   str,
    provider:   str,
    api_key:    str,
    progress_cb = None,   # optional callback(step: str) for Streamlit progress
    delay:      float = 1.2,
) -> tuple[list[dict], dict]:
    """
    Full portfolio build pipeline.
    Returns (stocks, validation_result).

    Steps:
      1. Parse free text
      2. Validate
      3. Generate missing theses
      4. Extract keywords from all theses
    """
    def _step(msg):
        if progress_cb:
            progress_cb(msg)

    # Step 1: Parse
    _step("🔍 Parsing your stock input…")
    stocks = parse_free_text(raw_text, provider, api_key)
    # Mark user-provided theses
    for s in stocks:
        if s.get("thesis") and not s.get("thesis_source"):
            s["thesis_source"] = "user"
    time.sleep(delay)

    # Step 2: Validate
    _step("✅ Validating portfolio…")
    validation = validate_portfolio(stocks, provider, api_key)
    stocks = validation.get("stocks", stocks)   # use corrected version
    time.sleep(delay)

    # Step 3: Generate missing theses
    for i, stock in enumerate(stocks):
        if not stock.get("thesis"):
            _step(f"📝 Generating consensus thesis for {stock['ticker']}…")
            thesis = generate_consensus_thesis(
                stock["ticker"], stock["name"], stock["position"],
                provider, api_key
            )
            stocks[i]["thesis"]       = thesis
            stocks[i]["thesis_source"] = "consensus"   # Wall Street consensus view
            time.sleep(delay)

    # Step 4: Extract keywords (user + consensus)
    for i, stock in enumerate(stocks):
        _step(f"🔎 Extracting search terms for {stock['ticker']}…")
        
        # User keywords from thesis
        user_keywords = extract_keywords(
            stock["ticker"], stock["name"], stock["thesis"],
            provider, api_key
        )
        stocks[i]["keywords"] = user_keywords
        time.sleep(delay)
        
        # Consensus keywords from Wall Street
        _step(f"📊 Finding consensus themes for {stock['ticker']}…")
        consensus_keywords = extract_consensus_keywords(
            stock["ticker"], stock["name"],
            provider, api_key
        )
        
        # Combine: user keywords + consensus keywords
        stocks[i]["keywords"] = user_keywords + consensus_keywords
        time.sleep(delay)

    # Ensure all stocks have required fields and add consensus searches
    for stock in stocks:
        stock.setdefault("keywords", [])
        stock.setdefault("sources",  [])
        # Add consensus view searches
        stock = enrich_sources_with_consensus(stock)
        stocks[stocks.index(stock)] = stock

    return stocks, validation


def portfolio_to_json(stocks: list[dict]) -> str:
    return json.dumps(stocks, indent=2)


def portfolio_from_json(json_str: str) -> list[dict]:
    return json.loads(json_str)
