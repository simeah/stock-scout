"""
pages/2_portfolio.py
====================
Step 2: Review and edit the parsed portfolio.
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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Review Portfolio — StockScout", page_icon="📊", layout="wide")

st.title("📊 Review Portfolio")

if not st.session_state.get("portfolio_ready") or not st.session_state.portfolio:
    st.warning("No portfolio set up yet. Go to **Setup Portfolio** first.")
    st.stop()

portfolio = st.session_state.portfolio
st.caption(f"{len(portfolio)} stocks configured")

# ── Edit each stock ───────────────────────────────────────────────────────────
updated = []
for i, stock in enumerate(portfolio):
    pos   = stock.get("position","LONG")
    color = {"LONG":"🟢","SHORT":"🔴","WATCHLIST":"👀"}.get(pos,"⚪")

    with st.expander(f"{color} **{stock['ticker']}** — {stock['name']} ({pos})", expanded=False):
        col1, col2, col3 = st.columns([1,2,1])

        with col1:
            new_ticker = st.text_input("Ticker", value=stock["ticker"], key=f"ticker_{i}").upper()
            new_name   = st.text_input("Company Name", value=stock.get("name",""), key=f"name_{i}")
            new_pos    = st.selectbox(
                "Position", ["LONG","SHORT","WATCHLIST"],
                index=["LONG","SHORT","WATCHLIST"].index(pos),
                key=f"pos_{i}",
            )

        with col2:
            new_thesis = st.text_area(
                "Thesis",
                value=stock.get("thesis",""),
                height=150,
                key=f"thesis_{i}",
            )

        with col3:
            kw_text = st.text_area(
                "Keywords (one per line)",
                value="\n".join(stock.get("keywords",[])),
                height=150,
                key=f"kw_{i}",
            )

        updated.append({
            **stock,
            "ticker":   new_ticker,
            "name":     new_name,
            "position": new_pos,
            "thesis":   new_thesis,
            "keywords": [k.strip() for k in kw_text.split("\n") if k.strip()],
        })

# ── Save changes ──────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1,1,2])
with col1:
    if st.button("💾 Save Changes", type="primary"):
        st.session_state.portfolio = updated
        st.success("✅ Portfolio saved!")

with col2:
    # Export to JSON
    json_str = json.dumps(updated, indent=2)
    st.download_button(
        "⬇️ Export JSON",
        data=json_str,
        file_name="stockscout_portfolio.json",
        mime="application/json",
    )

with col3:
    uploaded = st.file_uploader("📤 Import JSON", type="json", label_visibility="collapsed")
    if uploaded:
        try:
            imported = json.load(uploaded)
            st.session_state.portfolio       = imported
            st.session_state.portfolio_ready = True
            st.success(f"✅ Imported {len(imported)} stocks.")
            st.rerun()
        except Exception as ex:
            st.error(f"❌ Import error: {ex}")

# ── Raw JSON view ─────────────────────────────────────────────────────────────
with st.expander("🔍 View raw JSON"):
    st.json(updated)
