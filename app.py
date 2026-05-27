"""
StockScout — Retail Stock News Tracker
=======================================
Streamlit entry point.

Run locally:  streamlit run app.py
Deploy free:  https://share.streamlit.io
"""
import sys
import os

# Add stockscout directory to path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = _current_dir if os.path.exists(os.path.join(_current_dir, 'core')) else os.path.dirname(_current_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)



import streamlit as st
from core.persistence import load_portfolio, save_settings, load_settings

st.set_page_config(
    page_title="StockScout",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state defaults ────────────────────────────────────────────────────
defaults = {
    "portfolio":       [],
    "portfolio_ready": False,
    "provider":        "gemini",
    "anthropic_key":   "",
    "gemini_key":      "",
    "openai_key":      "",
    "gmail_address":   "",
    "gmail_password":  "",
    "recipient_email": "",
    "email_mode":      "stockscout",
    "recency_hours":   168,
    "top_n":           20,
    "schedule_enabled":False,
    "schedule_hour":   21,
    "schedule_tz":     "Europe/London",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Auto-load portfolio and settings from disk ────────────────────────────────
if not st.session_state.portfolio_ready:
    saved = load_portfolio()
    if saved:
        st.session_state.portfolio       = saved
        st.session_state.portfolio_ready = True

saved_settings = load_settings()
if saved_settings:
    # Load all settings including API keys
    for k in ("provider","recency_hours","top_n","recipient_email",
              "email_mode","schedule_enabled","schedule_hour","schedule_tz",
              "anthropic_key","gemini_key","openai_key"):
        if k in saved_settings:
            st.session_state[k] = saved_settings[k]

# ── Sidebar — settings only, no nav ──────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/radar.png", width=55)
    st.title("StockScout 📡")
    st.caption("AI-powered stock news tracker")
    st.divider()

    # ── 2. API Key ────────────────────────────────────────────────────────────────
    st.subheader("2️⃣  API Key")
    # Get the index of current provider
    provider_list = ["gemini", "anthropic", "openai"]
    current_provider = st.session_state.get("provider", "gemini")
    try:
        default_index = provider_list.index(current_provider)
    except ValueError:
        default_index = 0
    
    provider = st.radio(
        "Provider",
        provider_list,
        format_func=lambda x: {
            "gemini": "✨ Gemini — Google (FREE)",
            "anthropic": "🤖 Claude — Anthropic (paid)",
            "openai": "🔵 ChatGPT — OpenAI (paid)"
        }.get(x, x),
        horizontal=True,
        index=default_index,
    )
    st.session_state.provider = provider

    if provider == "anthropic":
        key = st.text_input("API Key", value=st.session_state.anthropic_key,
                            type="password", placeholder="sk-ant-...", key="input_anthropic_key")
        st.session_state.anthropic_key = key
        st.caption("Get key → [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)")
    elif provider == "gemini":
        key = st.text_input("API Key", value=st.session_state.gemini_key,
                            type="password", placeholder="AIza...", key="input_gemini_key")
        st.session_state.gemini_key = key
        st.caption("Get key → [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)")
    else:  # openai
        key = st.text_input("API Key", value=st.session_state.openai_key,
                            type="password", placeholder="sk-...", key="input_openai_key")
        st.session_state.openai_key = key
        st.caption("Get key → [platform.openai.com/api-keys](https://platform.openai.com/api-keys)")

    # Gemini setup guide (shown regardless of provider selection)
    with st.expander("📋 How to get a FREE Gemini API key"):
        st.markdown("""
**Simple Setup Guide (2 minutes)**

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your regular Google/Gmail account
3. **Free by Default** — no credit card needed ever
4. Click "Get API key" in the left sidebar
5. Click the blue "Create API Key" button
6. Choose "Create API key in new project"
7. Click "Copy" to copy your key
8. Paste it into the field above ☝️

**💡 Good to Know**
- ✅ **100% Free** — no hidden fees, no billing needed
- ✅ **Daily Limits** — 100,000 requests/day (plenty for StockScout)
- ✅ **No Expiration** — key stays valid unless you delete it
- 🔒 **Secure** — treat it like a password, never share
        """)

    st.divider()

    # ── 3. Email ──────────────────────────────────────────────────────────────
    st.subheader("3️⃣  Email Address")
    email_mode = st.radio(
        "Send from",
        ["stockscout", "my_gmail"],
        format_func=lambda x: (
            "📬 StockScout (no setup needed)"
            if x == "stockscout" else
            "📧 My own Gmail"
        ),
    )
    st.session_state.email_mode = email_mode

    if email_mode == "my_gmail":
        st.session_state.gmail_address  = st.text_input(
            "Your Gmail", value=st.session_state.gmail_address, placeholder="you@gmail.com")
        st.session_state.gmail_password = st.text_input(
            "App Password", value=st.session_state.gmail_password, type="password",
            help="myaccount.google.com/apppasswords — not your login password")
    else:
        st.session_state.gmail_address  = "automation.test.kitchen@gmail.com"
        st.session_state.gmail_password = ""
        st.caption("Sent from `automation.test.kitchen@gmail.com`")

    st.session_state.recipient_email = st.text_input(
        "Deliver brief to",
        value=st.session_state.recipient_email,
        placeholder="you@example.com",
    )

    st.divider()

    # ── 4. Weekly schedule ────────────────────────────────────────────────────
    st.subheader("4️⃣  Weekly Schedule (optional)")
    st.session_state.schedule_enabled = st.toggle(
        "Run automatically every Sunday night",
        value=st.session_state.schedule_enabled,
    )
    if st.session_state.schedule_enabled:
        st.session_state.schedule_hour = st.slider("Run at (hour)", 18, 23, 21)
        st.session_state.schedule_tz   = st.selectbox("Timezone", [
            "Europe/London","America/New_York","America/Los_Angeles",
            "Europe/Paris","Asia/Tokyo","Australia/Sydney",
        ])
        st.caption(
            f"Runs every Sunday at "
            f"{st.session_state.schedule_hour:02d}:00 "
            f"{st.session_state.schedule_tz}"
        )

    st.divider()

    # ── Run settings ──────────────────────────────────────────────────────────
    st.subheader("⚙️ Run Settings")
    st.session_state.recency_hours = st.selectbox(
        "News window",
        [24, 48, 72, 168],
        index=3,
        format_func=lambda x: f"Past {x}h ({x//24}d)",
    )
    st.session_state.top_n = st.slider("Top results to show", 10, 50, 20)

    st.divider()

    # ── Reset dedup history ───────────────────────────────────────────────────
    st.subheader("🔄 Reset Dedup History")
    st.caption("Clear the article history to see all articles again (useful when restarting)")
    if st.button("🗑️ Delete dedup history", type="secondary", use_container_width=True):
        import os
        from pathlib import Path
        history_file = Path.home() / "stockscout" / "history.json"
        if history_file.exists():
            history_file.unlink()
            st.success("✅ Dedup history cleared — starting fresh!")
            st.rerun()
        else:
            st.info("No dedup history found — already starting fresh")

    st.divider()

    # Cost estimate
    n = max(1, len(st.session_state.portfolio))
    st.caption(
        f"**💰 Estimated cost per weekly run ({n} stocks)**\n"
        f"- Claude Sonnet: ~${n * 0.04:.2f}–${n * 0.08:.2f}\n"
        f"- Gemini Flash free tier: $0.00\n"
        f"- Local dedup & storage: $0.00"
    )
    st.caption("📁 Files saved to `~/stockscout/`")

# ── Main page ─────────────────────────────────────────────────────────────────
st.title("📡 StockScout")
st.caption("AI-powered news tracker for your stock portfolio")
st.divider()

# ── Checklist ─────────────────────────────────────────────────────────────────
provider      = st.session_state.get("provider", "anthropic")
api_key       = (st.session_state.get("anthropic_key","") if provider == "anthropic"
                 else st.session_state.get("gemini_key",""))
email_mode    = st.session_state.get("email_mode","stockscout")
recipient     = st.session_state.get("recipient_email","")
gmail_addr    = st.session_state.get("gmail_address","")
gmail_pw      = st.session_state.get("gmail_password","")
portfolio_ok  = st.session_state.get("portfolio_ready") and bool(st.session_state.get("portfolio"))
schedule_on   = st.session_state.get("schedule_enabled", False)

email_ok = bool(recipient) and (
    email_mode == "stockscout" or (bool(gmail_addr) and bool(gmail_pw))
)

st.subheader("Setup checklist")

# ── Item 1: Portfolio ─────────────────────────────────────────────────────────
with st.container():
    c1, c2, c3 = st.columns([0.05, 0.7, 0.25])
    with c1:
        st.markdown("✅" if portfolio_ok else "⬜")
    with c2:
        if portfolio_ok:
            tickers = " · ".join(
                f"{'🟢' if s['position']=='LONG' else '🔴' if s['position']=='SHORT' else '👀'} {s['ticker']}"
                for s in st.session_state.portfolio
            )
            st.markdown(f"**1. Portfolio** &nbsp; {tickers}")
        else:
            st.markdown("**1. Set up your portfolio**")
            st.caption("Add your stocks or load the demo portfolio (AAPL, NVDA, AMZN, JPM, LLY). "
                       "If you skip this, the demo portfolio will be used.")
    with c3:
        if st.button("Go →" if not portfolio_ok else "Edit →",
                     key="ck_portfolio", use_container_width=True):
            st.switch_page("pages/1_setup.py")

# ── Item 2: API Key ───────────────────────────────────────────────────────────
with st.container():
    c1, c2, c3 = st.columns([0.05, 0.7, 0.25])
    with c1:
        st.markdown("✅" if api_key else "❌")
    with c2:
        if api_key:
            label = "Claude · Anthropic (paid)" if provider == "anthropic" else "Gemini · Google (free tier)"
            st.markdown(f"**2. API Key** &nbsp; `{label}`")
        else:
            st.markdown("**2. Add your API key** &nbsp; ← enter in the sidebar")
            st.caption(
                "**Claude (Anthropic)** — paid, most accurate. "
                "[Get key](https://console.anthropic.com/settings/keys)  \n"
                "**Gemini (Google)** — free tier available, 15 calls/min limit. "
                "[Get key](https://aistudio.google.com/apikey)"
            )
    with c3:
        st.markdown("") # No button — configured in sidebar

# ── Item 3: Email ─────────────────────────────────────────────────────────────
with st.container():
    c1, c2, c3 = st.columns([0.05, 0.7, 0.25])
    with c1:
        st.markdown("✅" if email_ok else "❌")
    with c2:
        if email_ok:
            st.markdown(f"**3. Email** &nbsp; Delivering to `{recipient}`")
        else:
            st.markdown("**3. Add your email address** &nbsp; ← enter in the sidebar")
            missing = []
            if not recipient:
                missing.append("recipient email address")
            if email_mode == "my_gmail":
                if not gmail_addr: missing.append("your Gmail address")
                if not gmail_pw:   missing.append("Gmail App Password")
            if missing:
                st.caption(f"Still needed: {', '.join(missing)}")
    with c3:
        st.markdown("")  # configured in sidebar

# ── Item 4: Schedule ──────────────────────────────────────────────────────────
with st.container():
    c1, c2, c3 = st.columns([0.05, 0.7, 0.25])
    with c1:
        st.markdown("✅" if schedule_on else "⬜")
    with c2:
        if schedule_on:
            st.markdown(
                f"**4. Weekly schedule** &nbsp; "
                f"Every Sunday at {st.session_state.schedule_hour:02d}:00 "
                f"{st.session_state.schedule_tz}"
            )
        else:
            st.markdown("**4. Automated weekly runs** &nbsp; *(optional)*")
            st.caption("Enable in the sidebar to receive your brief automatically every Sunday night.")
    with c3:
        st.markdown("")  # configured in sidebar

st.divider()

# ── Save & proceed button ─────────────────────────────────────────────────────
if not api_key or not email_ok:
    missing_items = []
    if not api_key:    missing_items.append("API key")
    if not email_ok:   missing_items.append("email address")
    st.warning(f"⚠️  Please add your {' and '.join(missing_items)} in the sidebar to continue.")
    st.button("💾 Save Settings & Proceed to Portfolio →",
              type="primary", disabled=True, use_container_width=False)
else:
    if st.button("💾 Save Settings & Proceed to Portfolio →",
                 type="primary", use_container_width=False):
        save_settings({
            "provider":        provider,
            "anthropic_key":   st.session_state.get("anthropic_key", ""),
            "gemini_key":      st.session_state.get("gemini_key", ""),
            "openai_key":      st.session_state.get("openai_key", ""),
            "recency_hours":   st.session_state.recency_hours,
            "top_n":           st.session_state.top_n,
            "recipient_email": recipient,
            "email_mode":      email_mode,
            "schedule_enabled":schedule_on,
            "schedule_hour":   st.session_state.schedule_hour,
            "schedule_tz":     st.session_state.schedule_tz,
        })
        st.success("✅ Settings saved.")
        st.switch_page("pages/1_setup.py")

st.divider()

# ── Bottom navigation buttons ─────────────────────────────────────────────────
st.subheader("Navigate")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📋 1️⃣  Setup Portfolio",
                 use_container_width=True, type="secondary", key="btn_setup"):
        st.switch_page("pages/1_setup.py")
    st.caption("Add stocks in plain English. AI generates theses automatically.")

with col2:
    if st.button("📊 2️⃣  Review Portfolio",
                 use_container_width=True, type="secondary", key="btn_review"):
        st.switch_page("pages/2_portfolio.py")
    st.caption("Edit tickers, positions, theses and keywords.")

with col3:
    if st.button("🚀 3️⃣  Run Tracker",
                 use_container_width=True, type="primary", key="btn_run"):
        st.switch_page("pages/3_run_tracker.py")
    st.caption("Fetch, score and rank news. Send your email brief.")
