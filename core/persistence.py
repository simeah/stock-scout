"""
core/persistence.py
===================
Handles all local file storage for StockScout.

Everything is saved to one folder on your computer: ~/stockscout/
  (Mac:    /Users/yourname/stockscout/
   Windows: C:\\Users\\yourname\\stockscout\\
   Linux:   /home/yourname/stockscout/)

Files saved:
  portfolio.json   Your stocks, positions, theses, keywords
  settings.json    App preferences (window, top N, timezone, email)
  history.json     Hashes of article titles already shown to you
                   (prevents duplicates across runs — no article content stored)
  logs/run.log     Timestamped log of each scheduled run

NOT saved here:
  API keys         Never written to disk by the app (stay in .env or sidebar)
  Article content  Only a short hash of the title is stored, not the text
  Personal data    Nothing beyond what you explicitly enter
"""

import os
import json
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
DEFAULT_DIR    = Path.home() / "stockscout"
PORTFOLIO_FILE = DEFAULT_DIR / "portfolio.json"
SETTINGS_FILE  = DEFAULT_DIR / "settings.json"
HISTORY_FILE   = DEFAULT_DIR / "history.json"
LOGS_DIR       = DEFAULT_DIR / "logs"
RUN_LOG        = LOGS_DIR    / "run.log"


def ensure_dir():
    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True,    exist_ok=True)


def storage_summary() -> dict:
    """
    Return a human-readable summary of all files stored on disk.
    Used by the UI to show the user exactly what is saved.
    """
    ensure_dir()
    files = []

    def _file_info(path: Path, description: str, contains: str) -> dict:
        exists = path.exists()
        size   = round(path.stat().st_size / 1024, 1) if exists else 0
        return {
            "path":        str(path),
            "name":        path.name,
            "description": description,
            "contains":    contains,
            "exists":      exists,
            "size_kb":     size,
        }

    files.append(_file_info(
        PORTFOLIO_FILE,
        "Your Portfolio",
        "Stock tickers, company names, positions (Long/Short/Watchlist), "
        "investment theses, and search keywords. This is your main config file.",
    ))
    files.append(_file_info(
        SETTINGS_FILE,
        "App Settings",
        "Your preferences: news window (hours), top N results, timezone, "
        "email address. Does NOT contain API keys or passwords.",
    ))
    files.append(_file_info(
        HISTORY_FILE,
        "Article History",
        "MD5 fingerprints (short hashes) of article titles you have already seen. "
        "Prevents the same news appearing in every run. "
        "No article content, no URLs, no personal data — just hashes.",
    ))
    files.append(_file_info(
        RUN_LOG,
        "Run Log",
        "Timestamped log entries from each scheduled run (date, stocks processed, "
        "number of articles found). Useful for checking Sunday night runs completed.",
    ))

    return {
        "folder": str(DEFAULT_DIR),
        "files":  files,
    }


# ── Portfolio ─────────────────────────────────────────────────────────────────

def save_portfolio(stocks: list[dict], path: Path = None) -> Path:
    ensure_dir()
    p = Path(path) if path else PORTFOLIO_FILE
    with open(p, "w") as f:
        json.dump({
            "version":    "1.0",
            "updated_at": datetime.now().isoformat(),
            "stocks":     stocks,
        }, f, indent=2)
    return p


def load_portfolio(path: Path = None) -> list[dict] | None:
    p = Path(path) if path else PORTFOLIO_FILE
    if not p.exists():
        return None
    try:
        with open(p) as f:
            data = json.load(f)
        return data.get("stocks", data) if isinstance(data, dict) else data
    except Exception:
        return None


def portfolio_metadata(path: Path = None) -> dict:
    p = Path(path) if path else PORTFOLIO_FILE
    if not p.exists():
        return {"exists": False, "path": str(p)}
    try:
        stat   = p.stat()
        with open(p) as f:
            data = json.load(f)
        stocks = data.get("stocks", data) if isinstance(data, dict) else data
        return {
            "exists":     True,
            "path":       str(p),
            "folder":     str(DEFAULT_DIR),
            "updated_at": data.get("updated_at", "unknown") if isinstance(data, dict) else "unknown",
            "n_stocks":   len(stocks) if isinstance(stocks, list) else 0,
            "tickers":    [s.get("ticker","?") for s in stocks] if isinstance(stocks, list) else [],
            "size_kb":    round(stat.st_size / 1024, 1),
        }
    except Exception as ex:
        return {"exists": True, "path": str(p), "error": str(ex)}


# ── Settings ──────────────────────────────────────────────────────────────────

def save_settings(settings: dict, path: Path = None) -> Path:
    """
    Save app preferences. API keys are saved to local file only (never to cloud).
    """
    ensure_dir()
    # Allow API keys in local settings (not transmitted anywhere)
    safe_keys = {"provider", "recency_hours", "top_n", "recipient_email",
                 "email_mode", "schedule_enabled", "schedule_hour", "schedule_tz",
                 "anthropic_key", "gemini_key", "openai_key"}
    safe = {k: v for k, v in settings.items() if k in safe_keys}
    p = Path(path) if path else SETTINGS_FILE
    with open(p, "w") as f:
        json.dump(safe, f, indent=2)
    return p


def load_settings(path: Path = None) -> dict:
    p = Path(path) if path else SETTINGS_FILE
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Run log ───────────────────────────────────────────────────────────────────

def log_run(message: str):
    ensure_dir()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(RUN_LOG, "a") as f:
        f.write(f"[{ts}] {message}\n")


def read_log(n_lines: int = 50) -> str:
    if not RUN_LOG.exists():
        return "No runs logged yet."
    lines = RUN_LOG.read_text().strip().split("\n")
    return "\n".join(lines[-n_lines:])
