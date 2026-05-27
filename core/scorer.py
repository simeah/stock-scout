"""
core/scorer.py
==============
Two-stage LLM scoring:
  Stage 1: Prescreening — quick headline-only pass to filter to top 20
  Stage 2: Full scoring — detailed scoring on 20 articles with dedup + scoring
"""

import json
from dataclasses import dataclass
from core.llm import llm_json


@dataclass
class ScoredItem:
    ticker:        str
    position:      str
    title:         str
    link:          str
    published:     str
    source_label:  str
    snippet:       str = ""
    stock_impact:  float = 0.0
    direction:     str = ""
    thesis_hit:    str = ""
    thesis_source: str = "consensus"  # "user" or "consensus"
    reasoning:     str = ""

    @property
    def final_score(self):
        return self.stock_impact


def prescreener_score(
    items: list[dict],
    stock: dict,
    provider: str,
    api_key: str,
    top_n: int = 10,
) -> list[dict]:
    """
    Stage 1: Quick pre-screening by headline.
    Scores all articles for relevance AND checks semantic similarity.
    Returns top N by relevance, with duplicates removed.
    """
    if len(items) <= top_n:
        return items  # Skip if already small

    ticker = stock["ticker"]
    position = stock.get("position", "LONG")
    thesis = stock.get("thesis", "")

    # Build headline list for quick scoring
    headlines = [
        f"[{i}] {item['title']} — {item.get('snippet', '')[:80]}"
        for i, item in enumerate(items, 1)
    ]

    prompt = f"""Quick relevance screening for {ticker} ({position}).

THESIS: {thesis}

For each headline:
1. Rate relevance to thesis (1-5): 5=highly relevant, 1=not relevant
2. Check if it's a DUPLICATE of any previous headline (covers same story/news)

Headlines:
{chr(10).join(headlines)}

Return ONLY JSON (no preamble):
{{
  "scores": [5, 3, 1, 4, ...],
  "duplicates": [false, true, false, ...]
}}

Mark as duplicate=true if it's the same story as an earlier article."""

    system = "You are a financial analyst doing quick headline screening and deduplication."

    try:
        result = llm_json(
            prompt,
            system=system,
            provider=provider,
            api_key=api_key,
            max_tokens=2000,
        )
        scores = result.get("scores", [])
        duplicates = result.get("duplicates", [])

        # Build list of (article, score, is_duplicate)
        scored = []
        for i in range(min(len(items), len(scores))):
            is_dup = duplicates[i] if i < len(duplicates) else False
            scored.append((items[i], scores[i], is_dup))

        # Remove duplicates first
        filtered = [item for item, score, is_dup in scored if not is_dup]
        
        # Then sort by score and keep top N
        filtered.sort(key=lambda x: x[1], reverse=True)
        filtered = filtered[:top_n]

        return filtered
    except Exception as ex:
        print(f"  [WARN] Prescreener error: {ex}")
        return items[:top_n]  # Fallback: return first N


SCORE_SYSTEM = """You are a senior portfolio manager evaluating news for a stock position.

For each article:
  1. Deduplicate — discard articles covering the same story (keep only the best)
  2. Score survivors:
     - stock_impact (1-5): likelihood to move stock price (5 = >3% move)
     - direction: UPSIDE | DOWNSIDE | NEUTRAL
     - thesis_hit: YES | NO
     - reasoning: one concise sentence

Return ONLY a JSON array with surviving articles (omit duplicates entirely)."""


def score_articles(
    items: list[dict],
    stock: dict,
    provider: str,
    api_key: str,
) -> list[ScoredItem]:
    """
    Stage 2: Full scoring with dedup + scoring in one call.
    Returns scored articles (duplicates already removed by Claude).
    """
    ticker = stock["ticker"]
    position = stock.get("position", "LONG")
    thesis = stock.get("thesis", "No thesis provided.")
    thesis_source = stock.get("thesis_source", "consensus")

    if not items:
        return []

    # Build article list for Claude
    lines = [
        f"[{i}] {item['title']}\n"
        f"    Source: {item['source_label']} | {item.get('published','n/a')}\n"
        f"    Snippet: {item.get('snippet','')[:150]}"
        for i, item in enumerate(items, 1)
    ]

    direction_logic = {
        "LONG": f"LONG {ticker}: Bullish = UPSIDE, Bearish = DOWNSIDE",
        "SHORT": f"SHORT {ticker}: Bearish = UPSIDE, Bullish = DOWNSIDE",
        "WATCHLIST": f"WATCHLIST {ticker}: Positive = UPSIDE, Negative = DOWNSIDE",
    }.get(position, "")

    prompt = f"""Score {len(items)} articles for {position} {ticker}.

THESIS ({thesis_source}):
{thesis}

Direction logic: {direction_logic}

Articles:
{chr(10).join(lines)}

Return JSON array (omit duplicates entirely):
[
  {{"index": 1, "stock_impact": 4, "direction": "UPSIDE", "thesis_hit": "YES", "reasoning": "..."}}
]"""

    try:
        result = llm_json(
            prompt,
            system=SCORE_SYSTEM,
            provider=provider,
            api_key=api_key,
            max_tokens=8096,
        )
        if not isinstance(result, list):
            result = []
    except Exception as ex:
        print(f"  [WARN] Scoring error ({ticker}): {ex}")
        result = []

    # Map by original index
    idx_map = {r.get("index"): r for r in result}
    scored = []
    for i, item in enumerate(items, 1):
        if i not in idx_map:
            continue  # Article was deduplicated by Claude
        s = idx_map[i]
        scored.append(ScoredItem(
            ticker=ticker,
            position=position,
            title=item["title"],
            link=item.get("link", ""),
            published=item.get("published", ""),
            source_label=item.get("source_label", ""),
            snippet=item.get("snippet", ""),
            stock_impact=float(s.get("stock_impact", 1)),
            direction=s.get("direction", "NEUTRAL"),
            thesis_hit=s.get("thesis_hit", "NO"),
            thesis_source=thesis_source,
            reasoning=s.get("reasoning", ""),
        ))

    return scored
