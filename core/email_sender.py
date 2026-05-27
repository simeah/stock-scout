"""
core/email_sender.py
====================
Builds and sends the HTML daily brief email via Gmail SMTP.
"""

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from core.scorer import ScoredItem

DIRECTION_STYLE = {
    "UPSIDE":   ("🟢", "#0a7c42", "#e6f4ee"),
    "DOWNSIDE": ("🔴", "#c0392b", "#fdecea"),
    "NEUTRAL":  ("⚪", "#666666", "#f5f5f5"),
}
POSITION_BADGE = {
    "LONG":      ("LONG",      "#0a7c42", "#e6f4ee"),
    "SHORT":     ("SHORT",     "#c0392b", "#fdecea"),
    "WATCHLIST": ("WATCHLIST", "#f5a623", "#fff8ee"),
}
SOURCE_COLORS = {
    "SEC EDGAR":           "#6366f1",
    "Google News":         "#4285f4",
    "Earnings Transcript": "#0891b2",
    "FDA Drug Shortages":  "#dc2626",
    "FTC Press Releases":  "#b45309",
    "DOJ Press Releases":  "#b45309",
    "OpenInsider":         "#7c3aed",
    "TrendForce":          "#0ea5e9",
    "DigiTimes RSS":       "#0ea5e9",
    "Retail Dive":         "#0f766e",
    "Adweek":              "#0f766e",
}
STAR_MAP = {5:"★★★★★",4:"★★★★☆",3:"★★★☆☆",2:"★★☆☆☆",1:"★☆☆☆☆"}


def _stars(s: float) -> str:
    return STAR_MAP.get(round(s), "★☆☆☆☆")


def _source_badge(label: str) -> str:
    color = SOURCE_COLORS.get(label, "#64748b")
    return (f'<span style="background:{color};color:#fff;padding:2px 7px;'
            f'border-radius:10px;font-size:10px;font-weight:600;">{label}</span>')


def build_html(
    all_items:  list[ScoredItem],
    portfolio:  list[dict],
    date_str:   str,
    recency_h:  int = 48,
) -> str:
    upside   = sum(1 for i in all_items if i.direction == "UPSIDE")
    downside = sum(1 for i in all_items if i.direction == "DOWNSIDE")
    neutral  = sum(1 for i in all_items if i.direction == "NEUTRAL")

    rows = ""
    for rank, item in enumerate(all_items, 1):
        emoji, dc, bg   = DIRECTION_STYLE.get(item.direction, DIRECTION_STYLE["NEUTRAL"])
        plabel, pc, pbg = POSITION_BADGE.get(item.position, ("—","#666","#f5f5f5"))
        thesis_cell = ('✅' if (item.thesis_hit == "YES" and item.thesis_source == "user")
                       else '<span style="color:#ddd;">—</span>')
        rows += f"""
        <tr style="background:{bg};border-bottom:1px solid #e8e8e8;">
          <td style="padding:11px 8px;font-size:13px;font-weight:bold;color:#666;text-align:center;">{rank}</td>
          <td style="padding:11px 8px;text-align:center;white-space:nowrap;">
            <span style="background:{pbg};color:{pc};padding:3px 9px;border-radius:10px;
                         font-size:10px;font-weight:bold;">{plabel}</span>
            <div style="font-size:13px;font-weight:700;color:#222;margin-top:3px;">{item.ticker}</div>
          </td>
          <td style="padding:11px 10px;">
            <a href="{item.link}" style="color:{dc};font-size:13px;font-weight:600;
               text-decoration:none;line-height:1.4;">{item.title}</a>
            <div style="margin-top:5px;">
              {_source_badge(item.source_label)}
              <span style="font-size:11px;color:#aaa;margin-left:6px;">{item.published or 'n/a'}</span>
            </div>
            <div style="margin-top:4px;font-size:11px;color:#666;font-style:italic;">{item.reasoning}</div>
          </td>
          <td style="padding:11px 8px;text-align:center;">
            <div style="font-size:10px;color:#bbb;">Stock Impact Score</div>
            <div style="font-size:20px;font-weight:bold;color:{dc};">{item.final_score:.1f}</div>
          </td>
          <td style="padding:11px 8px;text-align:center;">
            <div style="font-size:17px;">{emoji}</div>
            <div style="font-size:10px;color:{dc};font-weight:bold;">{item.direction}</div>
          </td>
          <td style="padding:11px 8px;text-align:center;font-size:16px;">{thesis_cell}</td>
        </tr>"""

    positions_html = " &nbsp;|&nbsp; ".join(
        f'<span style="color:{POSITION_BADGE.get(s["position"],("","#fff",""))[1]};font-weight:600;">'
        f'{s["ticker"]} {s["position"]}</span>'
        for s in portfolio
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
             background:#f0f2f5;margin:0;padding:20px;">
<div style="max-width:1020px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#0f0f1a 0%,#1a1a2e 100%);
              border-radius:10px 10px 0 0;padding:22px 28px;">
    <div style="color:#a0aec0;font-size:10px;letter-spacing:3px;text-transform:uppercase;">
      StockScout Daily Brief</div>
    <div style="color:#fff;font-size:24px;font-weight:700;margin-top:5px;">Portfolio News Tracker</div>
    <div style="margin-top:8px;font-size:12px;">{positions_html}</div>
    <div style="color:#718096;font-size:11px;margin-top:6px;">
      {date_str} &nbsp;|&nbsp; Past {recency_h}h &nbsp;|&nbsp;
      {len(all_items)} signals &nbsp;|&nbsp; Duplicates removed
    </div>
  </div>
  <div style="background:#fff;border:1px solid #e0e0e0;border-top:none;padding:12px 28px;">
    <table style="width:100%;border-collapse:collapse;"><tr>
      <td style="text-align:center;padding:0 12px;">
        <div style="font-size:20px;font-weight:bold;color:#0a7c42;">{upside}</div>
        <div style="font-size:11px;color:#888;">🟢 Upside</div></td>
      <td style="text-align:center;padding:0 12px;border-left:1px solid #eee;">
        <div style="font-size:20px;font-weight:bold;color:#c0392b;">{downside}</div>
        <div style="font-size:11px;color:#888;">🔴 Downside</div></td>
      <td style="text-align:center;padding:0 12px;border-left:1px solid #eee;">
        <div style="font-size:20px;font-weight:bold;color:#999;">{neutral}</div>
        <div style="font-size:11px;color:#888;">⚪ Neutral</div></td>
      <td style="text-align:right;padding:0 0 0 12px;border-left:1px solid #eee;
                 font-size:10px;color:#bbb;line-height:1.6;">
      </td>
    </tr></table>
  </div>
  <div style="background:#fff;border:1px solid #e0e0e0;border-top:none;
              overflow:hidden;border-radius:0 0 10px 10px;">
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="background:#f7f8fa;border-bottom:2px solid #e0e0e0;">
        <th style="padding:9px 8px;font-size:10px;color:#aaa;text-align:center;">#</th>
        <th style="padding:9px 8px;font-size:10px;color:#aaa;text-align:center;text-transform:uppercase;">Stock</th>
        <th style="padding:9px 8px;font-size:10px;color:#aaa;text-align:left;text-transform:uppercase;">Headline &amp; Source</th>
        <th style="padding:9px 8px;font-size:10px;color:#aaa;text-align:center;text-transform:uppercase;">Stock Impact</th>
        <th style="padding:9px 8px;font-size:10px;color:#aaa;text-align:center;text-transform:uppercase;">Signal</th>
        <th style="padding:9px 8px;font-size:10px;color:#aaa;text-align:center;text-transform:uppercase;">My Stock Thesis ✅</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div style="background:#1a1a2e;border-radius:0 0 10px 10px;
              padding:12px 24px;text-align:center;margin-top:4px;">
    <div style="color:#4a5568;font-size:10px;">
      Powered by StockScout &nbsp;|&nbsp; {date_str} &nbsp;|&nbsp;
      Not investment advice. For research purposes only.
    </div>
  </div>
</div></body></html>"""


# Shared StockScout sender address
STOCKSCOUT_SENDER = "automation.test.kitchen@gmail.com"


def send_email(
    html:          str,
    subject:       str,
    recipient:     str,
    gmail_address: str = "",
    app_password:  str = "",
    use_shared_sender: bool = True,
) -> tuple[bool, str]:
    """
    Send HTML email via Gmail SMTP.

    Two modes:
      use_shared_sender=True  — sends from StockScout shared Gmail account.
                                App password read from STOCKSCOUT_APP_PASSWORD
                                environment variable (set on the host server).
                                Users don't need to provide any credentials.

      use_shared_sender=False — sends from the user's own Gmail account.
                                Requires gmail_address + app_password.

    Returns (success, message).
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()  # Load .env file

    if use_shared_sender:
        sender = STOCKSCOUT_SENDER
        pw     = os.getenv("STOCKSCOUT_APP_PASSWORD", "").strip()
        if not pw:
            return False, (
                "❌ Shared sender not configured on this server. "
                "Please use your own Gmail account instead."
            )
    else:
        sender = gmail_address.strip()
        pw     = app_password.replace(" ", "")
        if not sender or not pw:
            return False, "❌ Gmail address and App Password are required."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"StockScout <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    def _try(server):
        server.login(sender, pw)
        server.sendmail(sender, recipient, msg.as_string())

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            _try(s)
        return True, "✅ Email sent successfully."
    except smtplib.SMTPAuthenticationError:
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.ehlo(); s.starttls(); s.ehlo(); _try(s)
            return True, "✅ Email sent successfully."
        except Exception as ex:
            return False, f"❌ Authentication failed: {ex}"
    except Exception as ex:
        return False, f"❌ {ex}"
