"""
pages/3_run_tracker.py
======================
Step 3: Run the news tracker and view/email results.

Pipeline per stock:
  1. Fetch articles from all sources
  2. TF-IDF within-run dedup (removes near-duplicates in current fetch)
  3. History dedup (removes articles seen in previous runs)
  4. LLM scoring (scores only — no dedup instruction to Claude)

All stocks merged → sorted by final_score → top N total shown.
"""
import sys
import os

# Add stockscout directory to path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = _current_dir if os.path.exists(os.path.join(_current_dir, 'core')) else os.path.dirname(_current_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)


import streamlit as st
import time
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fetchers      import fetch_for_stock
from core.dedup         import HistoryStore, dedup_against_history, dedup_within_run, article_fingerprint
from core.scorer        import score_articles, ScoredItem
from core.email_sender  import build_html, send_email
from core.persistence   import HISTORY_FILE

st.set_page_config(page_title="Run Tracker — StockScout", page_icon="🚀", layout="wide")

st.title("🚀 Run News Tracker")

# ── Guards ────────────────────────────────────────────────────────────────────
if not st.session_state.get("portfolio_ready") or not st.session_state.portfolio:
    st.warning("No portfolio configured. Go to **Setup Portfolio** first.")
    st.stop()

provider = st.session_state.get("provider", "anthropic")
api_key  = (st.session_state.get("anthropic_key","") if provider == "anthropic"
            else st.session_state.get("gemini_key",""))
if not api_key:
    st.warning("Please enter your API key in the sidebar.")
    st.stop()

portfolio     = st.session_state.portfolio
recency_hours = st.session_state.get("recency_hours", 168)
top_n         = st.session_state.get("top_n", 20)

# ── History store ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_history_store():
    return HistoryStore(str(HISTORY_FILE))

history = get_history_store()

# ── Run controls ──────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    tickers = ", ".join(
        f"{'🟢' if s['position']=='LONG' else '🔴' if s['position']=='SHORT' else '👀'} {s['ticker']}"
        for s in portfolio
    )
    st.markdown(f"**Portfolio:** {tickers}")
    st.caption(
        f"Window: past {recency_hours}h ({recency_hours//24}d) &nbsp;|&nbsp; "
        f"Top {top_n} total articles &nbsp;|&nbsp; "
        f"Provider: {provider} &nbsp;|&nbsp; "
        f"Dedup: TF-IDF + history before LLM"
    )
with col2:
    run_clicked = st.button("▶️ Run Now", type="primary", use_container_width=True)

st.divider()

# ── Pipeline ──────────────────────────────────────────────────────────────────
if run_clicked:
    all_scored: list[ScoredItem] = []
    date_str = datetime.now().strftime("%d %b %Y %H:%M")
    total_fetched     = 0
    total_after_dedup = 0
    total_after_hist  = 0

    for stock in portfolio:
        ticker = stock["ticker"]
        pos    = stock.get("position", "LONG")
        emoji  = {"LONG":"🟢","SHORT":"🔴","WATCHLIST":"👀"}.get(pos,"⚪")

        st.subheader(f"{emoji} {ticker} — {pos}")

        with st.status(f"Processing {ticker}…", expanded=True) as status:

            # ── Step 1: Fetch ─────────────────────────────────────────────────
            st.write("🔍 Fetching articles…")
            items = fetch_for_stock(stock, recency_hours=recency_hours)
            total_fetched += len(items)
            st.write(f"  → {len(items)} articles after keyword filter")

            if not items:
                status.update(label=f"{ticker} — no articles found", state="complete")
                continue

            # ── Step 2: TF-IDF within-run dedup ──────────────────────────────
            before = len(items)
            items  = dedup_within_run(items, threshold=0.75)
            removed = before - len(items)
            st.write(f"  → {len(items)} after within-run dedup ({removed} near-duplicates removed)")
            total_after_dedup += len(items)

            # ── Step 3: History dedup (cross-run) ────────────────────────────
            seen             = history.get_seen(ticker)
            items, new_fps   = dedup_against_history(items, seen)
            hist_removed     = (before - removed) - len(items)
            st.write(
                f"  → {len(items)} after history dedup "
                f"({hist_removed} already seen in previous runs, "
                f"{len(seen)} total in history)"
            )
            total_after_hist += len(items)

            if not items:
                status.update(label=f"{ticker} — no new articles", state="complete")
                # Still save fingerprints so we don't reprocess next time
                continue

            # ── Step 4: Pre-screening (quick headline pass to top 20) ──────
            st.write(f"  🔍 Screening {len(items)} articles…")
            st.write(f"  ✂️ Removing duplicates and scoring by relevance…")
            from core.scorer import prescreener_score
            prescreened = prescreener_score(items, stock, provider, api_key, top_n=10)
            st.write(f"  → Top {len(prescreened)} articles selected")

            # ── Step 5: Full scoring (dedup + score on pre-screened articles) ──────
            st.write(f"  🤖 Claude: dedup + score {len(prescreened)} articles…")
            scored = score_articles(
                items    = prescreened,
                stock    = stock,
                provider = provider,
                api_key  = api_key,
            )
            all_scored.extend(scored)

        # Don't save to history yet — only after full run completes and email sent

        time.sleep(1.2)  # Rate limit safety for Gemini

    # ── Pipeline summary ──────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📥 Fetched",          total_fetched)
    col2.metric("✂️ After dedup",      total_after_dedup)
    col3.metric("📚 After history",    total_after_hist)
    col4.metric("🤖 LLM calls made",   len(portfolio))
    st.caption(
        f"Token savings: ~{max(0, total_fetched - total_after_hist)} articles "
        f"removed before LLM → estimated ${max(0, total_fetched - total_after_hist) * 0.002:.2f} saved"
    )

    if not all_scored:
        st.info("No new articles found. Try widening the time window in the sidebar.")
        st.stop()

    # ── Sort globally and take top N ──────────────────────────────────────────
    all_scored.sort(key=lambda x: x.final_score, reverse=True)
    top_results = all_scored[:top_n]

    st.session_state["last_results"] = top_results
    st.session_state["last_all"]     = all_scored
    st.session_state["last_date"]    = date_str

# ── Display results ───────────────────────────────────────────────────────────
if st.session_state.get("last_results"):
    results  = st.session_state["last_results"]
    all_res  = st.session_state.get("last_all", results)
    date_str = st.session_state.get("last_date", datetime.now().strftime("%d %b %Y"))

    st.subheader(f"📊 Top {len(results)} signals (ranked by score across all stocks)")

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🟢 Upside",      sum(1 for r in results if r.direction == "UPSIDE"))
    col2.metric("🔴 Downside",    sum(1 for r in results if r.direction == "DOWNSIDE"))
    col3.metric("⚪ Neutral",     sum(1 for r in results if r.direction == "NEUTRAL"))
    col4.metric("✅ Thesis Hits", sum(1 for r in results if r.thesis_hit == "YES"))

    # Per-stock breakdown
    with st.expander("📊 Per-stock breakdown"):
        tickers_in_results = sorted(set(r.ticker for r in all_res))
        for t in tickers_in_results:
            stock_items = [r for r in all_res if r.ticker == t]
            shown       = [r for r in results  if r.ticker == t]
            avg_score   = round(sum(r.final_score for r in stock_items) / len(stock_items), 1) if stock_items else 0
            st.markdown(
                f"**{t}** — {len(stock_items)} scored, "
                f"{len(shown)} in top {top_n}, "
                f"avg score {avg_score}"
            )

    st.divider()

    # Results table
    DIRECTION_EMOJI = {"UPSIDE":"🟢","DOWNSIDE":"🔴","NEUTRAL":"⚪"}
    POSITION_LABEL  = {"LONG":"🟢 LONG","SHORT":"🔴 SHORT","WATCHLIST":"👀 WATCHLIST"}

    for rank, item in enumerate(results, 1):
        d_emoji = DIRECTION_EMOJI.get(item.direction, "⚪")
        p_label = POSITION_LABEL.get(item.position, item.position)
        # Only show thesis checkmark if it's user thesis AND thesis_hit is YES
        thesis_display = "✅ My Stock Thesis" if (item.thesis_hit == "YES" and item.thesis_source == "user") else ""

        with st.container():
            col1, col2, col3, col4 = st.columns([0.5, 1, 5, 2])
            with col1:
                st.markdown(f"**#{rank}**")
            with col2:
                st.markdown(f"**{item.ticker}**")
                st.caption(p_label)
            with col3:
                st.markdown(f"[**{item.title}**]({item.link})")
                st.caption(f"`{item.source_label}` &nbsp;|&nbsp; {item.published or 'n/a'}")
                st.caption(f"*{item.reasoning}*")
            with col4:
                st.markdown(f"**Stock Impact Score: {item.final_score:.1f}**")
                st.markdown(f"{d_emoji} {item.direction}")
                if thesis_display:
                    st.markdown(thesis_display)
        st.divider()

    # ── Email ─────────────────────────────────────────────────────────────────
    st.subheader("📧 Send Brief")
    col1, col2 = st.columns([2, 1])
    with col1:
        recipient = st.text_input(
            "Deliver to",
            value=st.session_state.get("recipient_email", ""),
            placeholder="you@example.com",
        )
    with col2:
        send_clicked = st.button("📤 Send Email Brief", type="secondary",
                                 use_container_width=True)

    if send_clicked:
        email_mode = st.session_state.get("email_mode", "stockscout")
        html       = build_html(results, portfolio, date_str, recency_hours)

        if email_mode == "stockscout":
            success, msg = send_email(
                html              = html,
                subject           = f"StockScout Brief — {date_str}",
                recipient         = recipient or st.session_state.get("recipient_email",""),
                use_shared_sender = True,
            )
        else:
            gmail  = st.session_state.get("gmail_address","")
            app_pw = st.session_state.get("gmail_password","")
            if not gmail or not app_pw:
                st.error("Please configure Gmail address and App Password in the sidebar.")
                st.stop()
            success, msg = send_email(
                html              = html,
                subject           = f"StockScout Brief — {date_str}",
                recipient         = recipient or gmail,
                gmail_address     = gmail,
                app_password      = app_pw,
                use_shared_sender = False,
            )

        if success:
            st.success(msg)
            
            # ── Save to history ONLY after successful email ────────────────────
            st.write("💾 Saving article history…")
            for stock in portfolio:
                ticker = stock["ticker"]
                # Save fingerprints of articles that were shown in the top results
                stock_results = [r for r in results if r.ticker == ticker]
                if stock_results:
                    fps = {article_fingerprint({"title": r.title}): r.title for r in stock_results}
                    history.add_seen(ticker, set(fps.keys()), titles=fps)
            st.caption("✅ History saved — duplicate articles will be filtered next run")
        else:
            st.error(msg)

    # ── Download ──────────────────────────────────────────────────────────────
    html = build_html(results, portfolio, date_str, recency_hours)
    st.download_button(
        "⬇️ Download HTML Brief",
        data      = html,
        file_name = f"stockscout_{datetime.now().strftime('%Y%m%d')}.html",
        mime      = "text/html",
    )

    # ── History stats ─────────────────────────────────────────────────────────
    with st.expander("📁 Article History (dedup store)"):
        stats = history.stats()
        if stats:
            st.caption("Articles stored per ticker (title hashes only — no content):")
            for ticker, count in sorted(stats.items()):
                st.markdown(f"- **{ticker}**: {count} articles seen")
        else:
            st.caption("No history yet — will populate after first run.")
        st.caption(f"Stored at: `{HISTORY_FILE}`")
