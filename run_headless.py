"""
run_headless.py
===============
Headless runner for cron / Task Scheduler.
Runs the full pipeline without Streamlit and sends the email brief.

Usage:
    python run_headless.py

    # Or with custom settings:
    python run_headless.py --hours 168 --top 10
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import os
from core.persistence  import load_portfolio, load_settings, SETTINGS_FILE
from core.fetchers     import fetch_for_stock
from core.dedup        import HistoryStore, dedup_against_history, dedup_within_run, article_fingerprint
from core.scorer       import score_articles
from core.email_sender import build_html, send_email

def run(hours: int = 168, top_n: int = 20):
    print(f"\n{'='*60}")
    print(f"  StockScout Headless Run — {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}")

    # ── Load portfolio ────────────────────────────────────────────────────────
    portfolio = load_portfolio()
    if not portfolio:
        print("❌ No portfolio found. Run the Streamlit app first to set up your portfolio.")
        sys.exit(1)
    print(f"✅ Portfolio: {', '.join(s['ticker'] for s in portfolio)}")

    # ── Load settings ─────────────────────────────────────────────────────────
    settings = load_settings()
    provider    = settings.get("provider",      os.getenv("LLM_PROVIDER",    "anthropic"))
    api_key     = settings.get("api_key",       os.getenv("ANTHROPIC_API_KEY","") or os.getenv("GEMINI_API_KEY",""))
    gmail_addr  = settings.get("gmail_address", os.getenv("GMAIL_ADDRESS",   ""))
    gmail_pw    = settings.get("gmail_password",os.getenv("GMAIL_APP_PASSWORD",""))
    recipient   = settings.get("recipient",     os.getenv("RECIPIENT_EMAIL", gmail_addr))

    if not api_key:
        print("❌ No API key found. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env")
        sys.exit(1)

    # ── Run pipeline ──────────────────────────────────────────────────────────
    history    = HistoryStore()
    all_scored = []
    date_str   = datetime.now().strftime("%d %b %Y %H:%M")

    for stock in portfolio:
        ticker = stock["ticker"]
        print(f"\n📡 {ticker} ({stock.get('position','LONG')})")

        items = fetch_for_stock(stock, recency_hours=hours)
        print(f"  📥 {len(items)} articles fetched")

        items = dedup_within_run(items, threshold=0.75)
        seen  = history.get_seen(ticker)
        items, new_fps = dedup_against_history(items, seen)
        print(f"  🔍 {len(items)} after dedup (history: {len(seen)} seen)")

        if not items:
            print(f"  ⚠️  No new articles")
            continue

        from core.scorer import prescreener_score
        prescreened = prescreener_score(items, stock, provider, api_key, top_n=10)
        print(f"  → {len(prescreened)} articles selected for full scoring")
        scored = score_articles(prescreened, stock, provider=provider, api_key=api_key)
        all_scored.extend(scored)

        print(f"  ✅ {len(scored)} signals scored")
        time.sleep(1.2)
        # Don't save to history yet — only after email sent

    if not all_scored:
        print("\n⚠️  No new articles found. No email sent.")
        return

    all_scored.sort(key=lambda x: x.final_score, reverse=True)
    all_scored = all_scored[:top_n]
    print(f"\n📊 {len(all_scored)} top signals (from {sum(1 for _ in all_scored)} total scored)")

    # ── Send email ────────────────────────────────────────────────────────────
    if gmail_addr and gmail_pw and recipient:
        html = build_html(all_scored, portfolio, date_str, hours)
        ok, msg = send_email(
            html          = html,
            subject       = f"StockScout Weekly Brief — {date_str}",
            gmail_address = gmail_addr,
            app_password  = gmail_pw,
            recipient     = recipient,
        )
        print(f"\n📧 {msg}")
    else:
        print("\n⚠️  Email not configured — set GMAIL_ADDRESS, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL in .env")

    print(f"\n{'='*60}")
    print("  Run complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StockScout headless runner")
    parser.add_argument("--hours", type=int, default=168, help="News lookback window in hours (default: 168 = 7 days)")
    parser.add_argument("--top",   type=int, default=20,  help="Top N results total across all stocks")
    args = parser.parse_args()
    run(hours=args.hours, top_n=args.top)
