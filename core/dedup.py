"""
core/dedup.py
=============
Semantic deduplication using TF-IDF cosine similarity.
No model downloads required — uses scikit-learn only.

Two modes:
  1. Within-run dedup:   remove near-duplicate articles in the current fetch
  2. Cross-run dedup:    remove articles already seen in previous runs (via history store)
"""

import json
import hashlib
import numpy as np
from typing import Optional


def _tfidf_similarity(texts: list[str]) -> np.ndarray:
    """Return cosine similarity matrix for a list of texts."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    if len(texts) < 2:
        return np.ones((len(texts), len(texts)))
    vec    = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=5000)
    matrix = vec.fit_transform(texts)
    return cosine_similarity(matrix)


def dedup_within_run(items: list[dict], threshold: float = 0.60) -> list[dict]:
    """
    Remove near-duplicate articles within the current fetch.
    Keeps the first (usually most authoritative) article per cluster.
    threshold: cosine similarity above which articles are considered duplicates.
    """
    if len(items) <= 1:
        return items

    texts  = [i["title"] + " " + i.get("snippet", "") for i in items]
    sim    = _tfidf_similarity(texts)
    keep   = []
    dropped = set()

    for i in range(len(items)):
        if i in dropped:
            continue
        keep.append(i)
        for j in range(i + 1, len(items)):
            if j not in dropped and sim[i][j] >= threshold:
                dropped.add(j)

    return [items[i] for i in keep]


def article_fingerprint(item: dict) -> str:
    """Stable hash for an article — used for cross-run dedup."""
    key = (item.get("title", "") + item.get("link", "")).strip().lower()
    return hashlib.md5(key.encode()).hexdigest()


def dedup_against_history(
    items:   list[dict],
    history: set[str],
    threshold: float = 0.60,
) -> tuple[list[dict], set[str]]:
    """
    Remove articles already seen in previous runs.

    Args:
        items:     current fetch
        history:   set of fingerprints from previous runs
        threshold: TF-IDF similarity threshold for semantic matching

    Returns:
        (new_items, new_fingerprints)
    """
    # Fast exact/near-exact match via fingerprint
    candidates = []
    new_fps    = set()
    for item in items:
        fp = article_fingerprint(item)
        if fp not in history:
            candidates.append(item)
            new_fps.add(fp)

    return candidates, new_fps


# ──────────────────────────────────────────────────────────────────────────────
# HISTORY STORE  (local JSON)
# ──────────────────────────────────────────────────────────────────────────────

class HistoryStore:
    """
    Tracks seen article fingerprints to avoid showing the same
    article across multiple runs.

    Backed by a local JSON file at ~/stockscout/history.json.
    """

    def __init__(self, path: str = "stockscout_history.json"):
        self.path = path
        self._data: dict[str, list[str]] = {}   # ticker → [fingerprint, ...]
        self._load()

    def _load(self):
        import os
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_seen(self, ticker: str) -> set[str]:
        return set(self._data.get(ticker, []))

    def add_seen(self, ticker: str, fingerprints: set[str], titles: dict = None):
        """Add fingerprints to history. titles parameter is optional for future use."""
        existing = set(self._data.get(ticker, []))
        updated  = existing | fingerprints
        # Keep last 2000 per ticker to avoid unbounded growth
        self._data[ticker] = list(updated)[-2000:]
        self._save()

    def clear(self, ticker: Optional[str] = None):
        if ticker:
            self._data.pop(ticker, None)
        else:
            self._data = {}
        self._save()

    def stats(self) -> dict:
        return {t: len(fps) for t, fps in self._data.items()}
