"""
pages/1_setup.py
================
Portfolio setup, editing, and scheduler configuration.
"""
import sys
import os

# Add stockscout directory to path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = _current_dir if os.path.exists(os.path.join(_current_dir, 'core')) else os.path.dirname(_current_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)


import streamlit as st
import json
import sys, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portfolio   import build_portfolio
from core.fetchers    import enrich_with_cik
from core.persistence import (save_portfolio, load_portfolio, portfolio_metadata,
                               PORTFOLIO_FILE, DEFAULT_DIR, storage_summary)
from core.scheduler   import (start_weekly_scheduler, stop_scheduler,
                               is_running, next_run_time, cron_instructions)

st.set_page_config(page_title="Setup — StockScout", page_icon="📋", layout="wide")


# ── Auto-load portfolio from disk on first visit ──────────────────────────────
if not st.session_state.get("portfolio_ready"):
    existing = load_portfolio()
    if existing:
        st.session_state.portfolio       = existing
        st.session_state.portfolio_ready = True

# ──────────────────────────────────────────────────────────────────────────────
# PERSISTENT FILE LOCATION BANNER
# ──────────────────────────────────────────────────────────────────────────────
meta = portfolio_metadata()
if meta["exists"]:
    st.success(
        f"📁 **Portfolio file:** `{meta['path']}`  \n"
        f"Last updated: {meta.get('updated_at','unknown')}  &nbsp;|&nbsp;  "
        f"{meta.get('n_stocks',0)} stocks: {', '.join(meta.get('tickers',[]))}  \n"
        f"This file is loaded automatically every time you open StockScout."
    )
else:
    st.info(
        f"📁 **Portfolio will be saved to:** `{meta['path']}`  \n"
        f"Once saved, it loads automatically on every visit."
    )

st.title("📋 Portfolio Setup")

# ── Tab layout ────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "➕ Add / New Portfolio",
    "✏️ Edit Existing",
    "📥 Import / Export",
    "⏰ Schedule",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Add / New Portfolio
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    provider = st.session_state.get("provider","anthropic")
    api_key  = (st.session_state.get("anthropic_key","") if provider == "anthropic"
                else st.session_state.get("gemini_key",""))

    if not api_key:
        st.warning("⚠️ Enter your API key in the sidebar first.")
        st.stop()

    st.subheader("Tell us about your stocks")

    # Demo portfolio button
    col1, col2 = st.columns([3,1])
    with col2:
        if st.button("📦 Load Demo Portfolio", help="Load 5 popular retail stocks with full theses"):
            demo_path = Path(__file__).parent.parent / "demo_portfolio.json"
            if demo_path.exists():
                demo = json.loads(demo_path.read_text())
                st.session_state.portfolio       = demo
                st.session_state.portfolio_ready = True
                save_portfolio(demo)
                st.success("✅ Demo portfolio loaded: AAPL, NVDA, AMZN, JPM, LLY")
                st.rerun()

    with col1:
        st.markdown("""
**Tips — just write naturally:**
- *"I own Apple and Nvidia"* — assumes Long if not specified
- *"I'm short Tesla — valuation is stretched"* — marks as Short
- *"Watching Nike for a potential entry"* — marks as Watchlist
- Add your reason for owning it, or we'll generate a consensus thesis
        """)

    mode = st.radio(
        "Mode",
        ["Create new portfolio", "Add stocks to existing portfolio"],
        horizontal=True,
    )

    existing_context = ""
    if mode == "Add stocks to existing portfolio" and st.session_state.get("portfolio"):
        existing_tickers = [s["ticker"] for s in st.session_state.portfolio]
        existing_context = f"\n\n(Already tracking: {', '.join(existing_tickers)} — only add NEW stocks)"

    raw_input = st.text_area(
        "Your stocks",
        height=180,
        placeholder="e.g. I own Apple - love the services business. Short Tesla - overvalued. Watching Nike.",
    )

    if st.button("🚀 Build Portfolio", type="primary", disabled=not raw_input.strip()):
        progress_area = st.empty()
        status_msgs   = []

        def cb(msg):
            status_msgs.append(msg)
            progress_area.info("\n\n".join(status_msgs))

        with st.spinner("Building your portfolio…"):
            try:
                new_stocks, validation = build_portfolio(
                    raw_text    = raw_input + existing_context,
                    provider    = provider,
                    api_key     = api_key,
                    progress_cb = cb,
                )
                new_stocks = enrich_with_cik(new_stocks)

                if mode == "Add stocks to existing portfolio" and st.session_state.get("portfolio"):
                    existing = {s["ticker"]: s for s in st.session_state.portfolio}
                    for s in new_stocks:
                        existing[s["ticker"]] = s
                    merged = list(existing.values())
                else:
                    merged = new_stocks

                st.session_state.portfolio       = merged
                st.session_state.portfolio_ready = True
                saved_path = save_portfolio(merged)
                progress_area.empty()

            except Exception as ex:
                st.error(f"❌ Error: {ex}")
                st.stop()

        # Validation notices
        for issue in validation.get("issues",[]):
            st.warning(f"⚠️ {issue}")
        for q in validation.get("clarifying_questions",[]):
            st.info(f"💬 {q}")

        st.success(
            f"✅ Portfolio saved to `{saved_path}`  \n"
            f"Stocks: {', '.join(s['ticker'] for s in merged)}"
        )

        # Preview
        for stock in merged:
            pos   = stock.get("position","LONG")
            emoji = {"LONG":"🟢","SHORT":"🔴","WATCHLIST":"👀"}.get(pos,"⚪")
            with st.expander(f"{emoji} **{stock['ticker']}** — {stock['name']} ({pos})"):
                st.markdown(f"**Thesis:** {stock.get('thesis','—')}")
                kws = stock.get("keywords",[])
                st.caption(f"**Keywords ({len(kws)}):** {', '.join(kws[:12])}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Edit Existing Portfolio
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    if not st.session_state.get("portfolio_ready") or not st.session_state.portfolio:
        st.info("No portfolio yet. Use the **Add / New Portfolio** tab first.")
    else:
        portfolio = st.session_state.portfolio
        st.subheader(f"Editing {len(portfolio)} stocks")

        # Quick actions
        col1, col2, col3 = st.columns(3)
        with col3:
            ticker_to_remove = st.selectbox(
                "Remove a stock",
                ["— select —"] + [s["ticker"] for s in portfolio],
                key="remove_sel",
            )
            if ticker_to_remove != "— select —":
                if st.button(f"🗑️ Remove {ticker_to_remove}", type="secondary"):
                    updated = [s for s in portfolio if s["ticker"] != ticker_to_remove]
                    st.session_state.portfolio = updated
                    save_portfolio(updated)
                    st.success(f"Removed {ticker_to_remove}")
                    st.rerun()

        st.divider()

        # Edit each stock inline
        updated_stocks = []
        for i, stock in enumerate(portfolio):
            pos   = stock.get("position","LONG")
            emoji = {"LONG":"🟢","SHORT":"🔴","WATCHLIST":"👀"}.get(pos,"⚪")

            with st.expander(f"{emoji} **{stock['ticker']}** — {stock['name']}", expanded=False):
                c1, c2, c3 = st.columns([1, 2, 1])
                with c1:
                    ticker = st.text_input("Ticker",   value=stock["ticker"],          key=f"e_t_{i}").upper()
                    name   = st.text_input("Name",     value=stock.get("name",""),     key=f"e_n_{i}")
                    pos    = st.selectbox("Position",  ["LONG","SHORT","WATCHLIST"],
                                         index=["LONG","SHORT","WATCHLIST"].index(pos), key=f"e_p_{i}")
                with c2:
                    thesis = st.text_area("Thesis",    value=stock.get("thesis",""),   height=160, key=f"e_th_{i}")
                with c3:
                    kws    = st.text_area("Keywords\n(one per line)",
                                         value="\n".join(stock.get("keywords",[])),    height=160, key=f"e_k_{i}")
                updated_stocks.append({
                    **stock,
                    "ticker":   ticker,
                    "name":     name,
                    "position": pos,
                    "thesis":   thesis,
                    "keywords": [k.strip() for k in kws.split("\n") if k.strip()],
                })

        if st.button("💾 Save All Changes", type="primary"):
            st.session_state.portfolio = updated_stocks
            saved = save_portfolio(updated_stocks)
            st.success(f"✅ Saved to `{saved}`")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Import / Export
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Export")
    if st.session_state.get("portfolio"):
        json_str = json.dumps(st.session_state.portfolio, indent=2)
        st.download_button(
            "⬇️ Download portfolio.json",
            data=json_str,
            file_name="stockscout_portfolio.json",
            mime="application/json",
        )
        st.caption(f"Local save location: `{PORTFOLIO_FILE}`")
    else:
        st.info("No portfolio to export yet.")

    st.divider()
    st.subheader("Import")
    uploaded = st.file_uploader("Upload a portfolio JSON", type="json")
    if uploaded:
        try:
            data = json.load(uploaded)
            stocks = data.get("stocks", data) if isinstance(data, dict) else data
            if st.button("✅ Confirm Import"):
                st.session_state.portfolio       = stocks
                st.session_state.portfolio_ready = True
                save_portfolio(stocks)
                st.success(f"✅ Imported {len(stocks)} stocks.")
                st.rerun()
        except Exception as ex:
            st.error(f"❌ {ex}")

    st.divider()
    st.subheader("📁 Portfolio File Location")
    st.code(str(PORTFOLIO_FILE), language=None)
    st.caption(
        "This file is automatically loaded every time you open StockScout. "
        "Back it up or sync it to cloud storage to preserve your portfolio across machines."
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Schedule
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("⏰ Automated Weekly Run")
    st.markdown(
        "Run the tracker automatically every **Sunday night** so your brief "
        "is ready before the market opens Monday morning."
    )

    col1, col2 = st.columns(2)
    with col1:
        run_hour = st.slider("Run at (hour, 24h)", 18, 23, 21,
                             help="Local server time")
        run_tz   = st.selectbox("Timezone", [
            "Europe/London", "America/New_York", "America/Los_Angeles",
            "Europe/Paris", "Asia/Tokyo", "Australia/Sydney",
        ])

    with col2:
        st.markdown("**Current scheduler status:**")
        if is_running():
            st.success(f"🟢 Running  \nNext run: {next_run_time()}")
            if st.button("⏹️ Stop Scheduler"):
                stop_scheduler()
                st.rerun()
        else:
            st.warning("⚫ Not running")

            def _scheduled_run():
                """Called by scheduler — imports and runs the pipeline headlessly."""
                try:
                    import subprocess, sys
                    subprocess.run([sys.executable, "run_headless.py"], check=True)
                except Exception as ex:
                    print(f"Scheduled run error: {ex}")

            if st.button("▶️ Start Weekly Scheduler", type="primary"):
                ok = start_weekly_scheduler(_scheduled_run, hour=run_hour, timezone=run_tz)
                if ok:
                    st.success(f"✅ Scheduler started — runs every Sunday at {run_hour:02d}:00 {run_tz}")
                    st.rerun()
                else:
                    st.warning("APScheduler not installed. Using cron instead (see below).")

    st.divider()
    st.subheader("🖥️ Cron / Task Scheduler Setup")
    st.markdown("For the most reliable automated runs, set up a system cron job:")
    st.markdown(cron_instructions(hour=run_hour))

    st.info(
        "💡 **Tip:** Running Sunday at 21:00 UK time means results arrive "
        "before Asian markets open and well before US pre-market Monday."
    )
