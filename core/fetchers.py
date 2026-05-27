"""
core/fetchers.py
================
All news source fetchers. Each returns a list of raw article dicts.

Sources:
  - Google News RSS      (free, no key)
  - SEC EDGAR 8-K        (free, no key)
  - Generic RSS feeds    (TrendForce, FDA, etc.)
  - Earnings transcripts (earningscall.biz + SEC EDGAR exhibits)
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
import feedparser
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# HTTP HELPERS
# ──────────────────────────────────────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SEC_HEADERS = {
    "User-Agent": "StockScout research@stockscout.app",
    "Accept":     "application/json",
}


def _get(url: str, headers: dict = None, timeout: int = 20) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=headers or BROWSER_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  [WARN] {type(e).__name__} — {url}")
    return None


def _parse_feed(url: str, label: str) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries:
            title   = getattr(e, "title",     "").strip()
            link    = getattr(e, "link",      "")
            pub     = getattr(e, "published", "") or getattr(e, "updated", "")
            snippet = getattr(e, "summary",   "")
            if snippet:
                snippet = BeautifulSoup(snippet, "lxml").get_text(separator=" ", strip=True)[:400]
            if title:
                items.append({"title": title, "link": link, "published": pub,
                              "source_label": label, "snippet": snippet})
        return items
    except Exception as ex:
        print(f"  [WARN] Feed parse error ({label}): {ex}")
        return []

# ──────────────────────────────────────────────────────────────────────────────
# FETCHERS
# ──────────────────────────────────────────────────────────────────────────────

def google_news(query: str, label: str = "Google News") -> list[dict]:
    """Fetch from Google News RSS."""
    url = (f"https://news.google.com/rss/search"
           f"?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en")
    return _parse_feed(url, label)


def rss_feed(url: str, label: str) -> list[dict]:
    """Fetch from generic RSS feed."""
    return _parse_feed(url, label)


def sec_edgar_8k(cik: str, company: str) -> list[dict]:
    """Fetch recent 8-K filings from SEC EDGAR."""
    r = _get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=SEC_HEADERS)
    if not r:
        return []
    try:
        data  = r.json()
        rec   = data.get("filings", {}).get("recent", {})
        forms = rec.get("form",                 [])
        dates = rec.get("filingDate",           [])
        accs  = rec.get("accessionNumber",      [])
        docs  = rec.get("primaryDocument",      [])
        descs = rec.get("primaryDocDescription",[])
        items   = []
        cik_int = str(int(cik))
        for form, date, acc, doc, desc in zip(forms, dates, accs, docs, descs):
            if form in ("8-K", "8-K/A"):
                acc_clean = acc.replace("-", "")
                link  = (f"https://www.sec.gov/Archives/edgar/data/"
                         f"{cik_int}/{acc_clean}/{doc}")
                title = f"{company} 8-K — {desc or 'Filing'} ({date})"
                items.append({"title": title, "link": link, "published": date,
                              "source_label": "SEC EDGAR", "snippet": ""})
            if len(items) >= 5:
                break
        return items
    except Exception as ex:
        print(f"  [WARN] EDGAR ({company}): {ex}")
        return []


def recency_filter(items: list[dict], hours: int) -> list[dict]:
    """Keep only items from the last N hours."""
    from email.utils import parsedate_to_datetime
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    for item in items:
        pub = item.get("published", "")
        if not pub:
            out.append(item)
            continue
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                out.append(item)
        except Exception:
            out.append(item)
    return out


def keyword_filter(items: list[dict], keywords: list[str]) -> list[dict]:
    """Filter to articles matching at least one keyword."""
    if not keywords:
        return items
    kws = [k.lower() for k in keywords]
    return [
        i for i in items
        if any(kw in (i["title"] + " " + i.get("snippet","")).lower() for kw in kws)
    ]


def fetch_for_stock(stock: dict, recency_hours: int = 48) -> list[dict]:
    """
    Fetch news for a stock from configured sources + consensus searches.
    """
    ticker   = stock["ticker"]
    keywords = stock.get("keywords", [])
    raw: list[dict] = []

    sources = stock.get("sources", [])
    
    # Ensure consensus searches are added to sources
    stock = enrich_sources_with_consensus(stock)
    sources = stock.get("sources", [])
    
    print(f"  DEBUG {ticker}: {len(sources)} sources configured")
    for i, src in enumerate(sources, 1):
        if len(src) >= 3:
            label = src[0]
            query = src[2].get("q", "")[:50] if src[1] == "google_news" else src[2].get("company", "")
            print(f"    {i}. {label}: {query}")
    
    # Fetch from all configured sources
    if sources:
        for source_item in sources:
            if isinstance(source_item, (list, tuple)) and len(source_item) >= 3:
                label, fetcher_key, params = source_item[0], source_item[1], source_item[2]
            else:
                continue
            
            try:
                before = len(raw)
                if fetcher_key == "google_news":
                    q = params.get("q", ticker)
                    raw += google_news(q, label=label)
                elif fetcher_key == "sec_edgar":
                    cik = params.get("cik", "")
                    company = params.get("company", "")
                    if cik:
                        raw += sec_edgar_8k(cik, company)
                elif fetcher_key == "rss_feed":
                    url = params.get("url", "")
                    lbl = params.get("label", label)
                    if url:
                        raw += rss_feed(url, lbl)
                after = len(raw)
                print(f"    → {label}: {after - before} articles")
                time.sleep(0.2)
            except Exception as ex:
                print(f"    [WARN] {label}: {ex}")
    else:
        # Fallback: use keywords for Google News searches
        # Group keywords into batches of 4-5
        kw_batches = [keywords[i:i+5] for i in range(0, len(keywords), 5)]
        for batch in kw_batches[:2]:  # max 2 searches to avoid rate limits
            q = " OR ".join(batch)
            raw += google_news(q, label="Google News")
            time.sleep(0.3)
        
        # Also search for company name + ticker
        raw += google_news(f"{stock['name']} {ticker}", label="Google News")
        time.sleep(0.3)
        
        # Add SEC EDGAR if CIK available
        cik = stock.get("cik")
        if cik:
            raw += sec_edgar_8k(cik, stock["name"])

    # Deduplicate by title
    seen, unique = set(), []
    for item in raw:
        key = item["title"].strip().lower()[:120]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Recency filter
    recent = recency_filter(unique, recency_hours)

    # No keyword filter — Google News queries already pre-filtered by search terms
    return recent


# ──────────────────────────────────────────────────────────────────────────────
# KNOWN CIK NUMBERS
# ──────────────────────────────────────────────────────────────────────────────
KNOWN_CIKS = {
    "AAPL":  "0000320193", "MSFT":  "0000789019", "GOOGL": "0001652044",
    "AMZN":  "0001018724", "NVDA":  "0001045810", "META":  "0001326801",
    "TSLA":  "0001318605", "MU":    "0000723125", "PLTR":  "0001321655",
    "HIMS":  "0001773751", "NKE":   "0000320187", "JPM":   "0000019617",
    "LLY":   "0000059478",
}


def enrich_with_cik(stocks: list[dict]) -> list[dict]:
    """Add CIK numbers to stocks where known."""
    for stock in stocks:
        if not stock.get("cik"):
            cik = KNOWN_CIKS.get(stock["ticker"].upper())
            if cik:
                stock["cik"] = cik
    return stocks


def generate_consensus_searches(ticker: str, company: str, position: str) -> list[list]:
    """
    Generate search queries to discover what Wall Street is talking about.
    These are used ONLY during portfolio setup to extract consensus keywords.
    They are NOT used during article fetching.
    """
    searches = [
        f"{ticker} {company} analyst ratings broker views",
        f"{ticker} {company} earnings surprise beat miss",
        f"{ticker} {company} price target raised cut",
        f"{ticker} {company} insider buying selling",
    ]
    return searches


def enrich_sources_with_consensus(stock: dict) -> dict:
    """
    Placeholder - consensus keywords are extracted at portfolio setup time,
    not added as sources. This function is kept for compatibility.
    """
    return stock
