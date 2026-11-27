"""Look & feel: logo, global CSS, small HTML components."""
from urllib.parse import quote

import pandas as pd
import streamlit as st

LOGO_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
    "<stop offset='0' stop-color='#2dd4bf'/><stop offset='1' stop-color='#6366f1'/></linearGradient></defs>"
    "<rect width='64' height='64' rx='16' fill='url(#g)'/>"
    "<polyline points='12,44 24,32 33,38 50,18' fill='none' stroke='white' stroke-width='5' "
    "stroke-linecap='round' stroke-linejoin='round'/>"
    "<polyline points='40,18 50,18 50,28' fill='none' stroke='white' stroke-width='5' "
    "stroke-linecap='round' stroke-linejoin='round'/></svg>"
)
LOGO_URI = "data:image/svg+xml;utf8," + quote(LOGO_SVG)

CSS = f"""
<style>
#MainMenu, footer, [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{display:none !important;}}
header[data-testid="stHeader"] {{background:transparent;}}
.block-container {{padding-top:1rem; max-width:1180px;}}
html {{scroll-behavior:smooth;}}
[data-testid="stAppViewContainer"] {{
  background: radial-gradient(1100px 560px at 88% -8%, #1b2a4a 0%, transparent 60%),
              radial-gradient(900px 500px at -8% 105%, #0f3b3b 0%, transparent 55%), #0b1220;
}}
h1 {{font-weight:750 !important; letter-spacing:-.5px;}}
h2, h3 {{letter-spacing:-.2px;}}

/* ---------- header ---------- */
.brand {{display:flex; align-items:center; gap:.7rem;}}
.brand img {{width:40px; height:40px;}}
.brand b {{font-size:1.25rem; letter-spacing:.2px;}}
.brand span {{display:block; font-size:.72rem; color:#8aa0c2; margin-top:-2px;}}
.st-key-topbar {{border-bottom:1px solid #1f2b44; padding-bottom:.4rem; margin-bottom:.4rem;}}
.user-chip {{text-align:right; color:#9db0cf; font-size:.85rem; padding-top:.55rem;}}

/* ---------- hero ---------- */
.hero {{padding:1.2rem 0 .5rem;}}
.hero h1 {{font-size:3rem; line-height:1.08; margin:.5rem 0 .9rem;}}
.hero h1 em, .grad {{font-style:normal; background:linear-gradient(90deg,#2dd4bf,#818cf8);
  -webkit-background-clip:text; background-clip:text; color:transparent;}}
.hero p {{color:#9db0cf; font-size:1.08rem; max-width:38rem; line-height:1.6;}}
.pill {{display:inline-block; background:#13203a; border:1px solid #243556; color:#9fe8dc;
  border-radius:999px; padding:.2rem .8rem; font-size:.78rem; margin-bottom:.4rem;}}
.feat {{display:flex; gap:.8rem; align-items:flex-start; margin:.9rem 0; color:#c9d6ee;}}
.feat i {{font-style:normal; background:#16233b; border:1px solid #243556; border-radius:12px;
  padding:.4rem .55rem; font-size:1.1rem;}}
.section-title {{margin:1.6rem 0 .2rem; font-size:1.35rem; font-weight:700;}}
.section-sub {{color:#8aa0c2; margin-bottom:.8rem;}}

/* ---------- cards ---------- */
.card {{background:linear-gradient(180deg,#15203a,#111a2f); border:1px solid #23325a;
  border-radius:16px; padding:1.1rem 1.2rem; height:100%; transition:transform .15s, border-color .15s;}}
.card:hover {{transform:translateY(-2px); border-color:#2f4a86;}}
.card h4 {{margin:0; font-size:1.05rem;}}
.card .tick {{color:#8aa0c2; font-size:.76rem;}}
.card .price {{font-size:1.75rem; font-weight:750; margin:.55rem 0 .1rem;}}
.card .sub {{color:#8aa0c2; font-size:.8rem;}}
.card .row {{display:flex; justify-content:space-between; font-size:.84rem; margin-top:.45rem;
  color:#b6c5e0;}}
.card .row b {{color:#e6edf7;}}
.chip {{float:right; border-radius:999px; padding:.15rem .7rem; font-size:.75rem; font-weight:700;}}
.s-buy {{background:#0f3d36; color:#5eead4; border:1px solid #14675c;}}
.s-wait {{background:#3d3410; color:#fde047; border:1px solid #6b5a14;}}
.s-sell {{background:#3a1a22; color:#fda4af; border:1px solid #6b2a37;}}
.badge {{display:inline-block; border-radius:999px; padding:.12rem .6rem; font-size:.72rem;
  font-weight:600; margin-top:.55rem;}}
.b-good {{background:#0f3d36; color:#5eead4; border:1px solid #14675c;}}
.b-weak {{background:#3d3410; color:#fde047; border:1px solid #6b5a14;}}
.b-none {{background:#26324f; color:#b8c6e4; border:1px solid #3a4a73;}}
.up {{color:#4ade80;}} .down {{color:#f87171;}}

.verdict {{border-radius:16px; padding:1.1rem 1.4rem; border:1px solid #23325a;
  background:linear-gradient(90deg,#15203a,#111a2f); margin:.5rem 0 1rem;}}
.verdict h3 {{margin:0 0 .25rem;}} .verdict p {{margin:0; color:#a9bad6; line-height:1.55;}}
.simple {{background:#0f2433; border:1px solid #1d4257; border-left:4px solid #2dd4bf;
  border-radius:10px; padding:.7rem 1rem; color:#cfe6ef; font-size:.93rem; margin:.4rem 0 1rem;}}
.simple b {{color:#5eead4;}}

/* ---------- price plan ---------- */
.plan {{display:grid; grid-template-columns:repeat(3,1fr); gap:.8rem; margin:.4rem 0 1rem;}}
.plan div {{border-radius:14px; padding:.9rem 1rem; border:1px solid #23325a; background:#111a2f;}}
.plan small {{display:block; color:#8aa0c2; font-size:.76rem;}}
.plan strong {{display:block; font-size:1.35rem; margin:.15rem 0;}}
.plan em {{font-style:normal; color:#8aa0c2; font-size:.78rem;}}
.plan .g {{border-color:#14675c;}} .plan .t {{border-color:#2f4a86;}} .plan .r {{border-color:#6b2a37;}}
.gauge {{position:relative; height:10px; border-radius:99px; margin:1.6rem 0 .3rem;
  background:linear-gradient(90deg,#f87171,#fbbf24 40%,#4ade80);}}
.gauge i {{position:absolute; top:-6px; width:4px; height:22px; background:#fff; border-radius:3px;}}
.gauge-l {{display:flex; justify-content:space-between; color:#8aa0c2; font-size:.76rem;}}

/* ---------- steps ---------- */
.step {{display:flex; gap:1rem; align-items:flex-start; margin:.9rem 0;}}
.step .n {{min-width:40px; height:40px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-weight:750; background:linear-gradient(135deg,#2dd4bf,#6366f1); color:#06101f;}}
.step h4 {{margin:0;}} .step p {{margin:.15rem 0 0; color:#9db0cf; line-height:1.55;}}

/* ---------- footer ---------- */
.footer {{margin-top:3rem; padding:1.4rem 0 5rem; border-top:1px solid #1f2b44; color:#7f93b5;
  font-size:.8rem; line-height:1.6;}}
.disclaimer {{color:#7f93b5; font-size:.78rem;}}

/* ---------- floating chatbot (bottom-right) ---------- */
.st-key-chatfab {{position:fixed; bottom:24px; right:24px; z-index:9999; width:64px !important;}}
.st-key-chatfab button {{width:64px; height:64px; border-radius:50%; padding:0; border:none;
  background:#0b1220 url("{LOGO_URI}") center/44px no-repeat;
  box-shadow:0 8px 24px rgba(45,212,191,.35), 0 0 0 2px #2dd4bf55; transition:transform .15s;}}
.st-key-chatfab button:hover {{transform:scale(1.07);}}
.st-key-chatfab button > div {{display:none;}}
div[data-testid="stPopoverBody"] {{width:390px; max-width:92vw; border:1px solid #23325a;
  border-radius:16px; background:#0f182b;}}
.chat-head {{display:flex; align-items:center; gap:.6rem; padding-bottom:.4rem;
  border-bottom:1px solid #1f2b44; margin-bottom:.4rem;}}
.chat-head img {{width:30px; height:30px;}}
.chat-head b {{display:block; line-height:1.1;}}
.chat-head span {{font-size:.72rem; color:#8aa0c2;}}

@media (max-width:760px) {{ .hero h1 {{font-size:2.1rem;}} .plan {{grid-template-columns:1fr;}} }}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def brand(sub="Understand the stock market with AI"):
    st.markdown(f"<div class='brand'><img src=\"{LOGO_URI}\"><div><b>MarketLens</b>"
                f"<span>{sub}</span></div></div>", unsafe_allow_html=True)


def inr(x):
    return f"₹{x:,.2f}"


def badge(conf):
    cls = {"Some skill": "b-good", "Weak": "b-weak"}.get(conf, "b-none")
    label = {"Some skill": "AI has some skill", "Weak": "AI: weak track record",
             "None": "AI: no proven track record"}.get(conf, "Price rules only")
    return f"<span class='badge {cls}'>{label}</span>"


def chip(signal):
    cls = {"Buy": "s-buy", "Sell": "s-sell"}.get(signal, "s-wait")
    return f"<span class='chip {cls}'>{signal.upper()}</span>"


def stock_card(row):
    p = row["P(up) next day"]
    p_txt = "n/a" if pd.isna(p) else f"{p:.0%}"
    return (f"<div class='card'>{chip(row['Signal'])}<h4>{row['Stock']}</h4>"
            f"<div class='tick'>NSE: {row['Ticker'].replace('.NS', '')}</div>"
            f"<div class='price'>{inr(row['Price'])}</div>"
            f"<div class='sub'>Closing price on {row['As of']:%d %b %Y}</div>"
            f"<div class='row'><span>Good price to buy</span><b>{inr(row['Buy from'])} – {inr(row['Buy up to'])}</b></div>"
            f"<div class='row'><span>Sell for profit at</span><b class='up'>{inr(row['Sell target'])}</b></div>"
            f"<div class='row'><span>Sell to limit loss at</span><b class='down'>{inr(row['Stop-loss'])}</b></div>"
            f"<div class='row'><span>Chance of rising tomorrow</span><b>{p_txt}</b></div>"
            f"{badge(row['Confidence'])}</div>")


def price_plan(row):
    st.markdown(
        f"<div class='plan'>"
        f"<div class='g'><small>🟢 BUY ZONE</small><strong>{inr(row['Buy from'])} – {inr(row['Buy up to'])}</strong>"
        f"<em>A sensible range to buy in. Avoid paying much more than this.</em></div>"
        f"<div class='t'><small>🎯 SELL FOR PROFIT AT</small><strong class='up'>{inr(row['Sell target'])}</strong>"
        f"<em>+{row['Sell target']/row['Price']-1:.1%} from today. Book your gain here.</em></div>"
        f"<div class='r'><small>🛑 SELL TO LIMIT LOSS AT</small><strong class='down'>{inr(row['Stop-loss'])}</strong>"
        f"<em>{row['Stop-loss']/row['Price']-1:.1%} from today. Exit if price falls to this.</em></div></div>",
        unsafe_allow_html=True)


def gauge(value, low, high, left_label, right_label):
    pos = 0 if high == low else min(max((value - low) / (high - low), 0), 1) * 100
    st.markdown(f"<div class='gauge'><i style='left:calc({pos:.0f}% - 2px)'></i></div>"
                f"<div class='gauge-l'><span>{left_label}</span><span>{right_label}</span></div>",
                unsafe_allow_html=True)


def simple(text):
    st.markdown(f"<div class='simple'>💡 <b>In simple words:</b> {text}</div>", unsafe_allow_html=True)


def section(title, sub=""):
    st.markdown(f"<div class='section-title'>{title}</div><div class='section-sub'>{sub}</div>",
                unsafe_allow_html=True)


def footer():
    st.markdown("<div class='footer'><b>MarketLens</b> is a student machine-learning project. It is "
                "<b>not</b> investment advice and not registered with SEBI. Prices come from Yahoo Finance "
                "(end of day, may be delayed). Buy zones, targets and stop-losses are rule-of-thumb levels based on "
                "recent price movement; AI models here are right only about 50% of the time. You can lose money "
                "in shares &mdash; invest only what you can afford to lose and talk to a SEBI-registered advisor.</div>",
                unsafe_allow_html=True)


def holding_card(row, hv, qty, buy_price):
    chip_cls = {"up": "s-buy", "down": "s-sell"}.get(hv["tone"], "s-wait")
    value, pl_amt = row["Price"] * qty, (row["Price"] - buy_price) * qty
    tone = "up" if pl_amt >= 0 else "down"
    out_cls = {"May rise": "up", "May fall": "down"}.get(hv["outlook"], "")
    return (f"<div class='card'><span class='chip {chip_cls}'>{hv['verdict']}</span>"
            f"<h4>{row['Stock']}</h4><div class='tick'>{qty:g} shares · bought at {inr(buy_price)}</div>"
            f"<div class='price {tone}'>{pl_amt:+,.0f} ₹ <small style='font-size:.95rem'>({hv['pl_pct']:+.1%})</small></div>"
            f"<div class='sub'>Now {inr(row['Price'])} · worth ₹{value:,.0f}</div>"
            f"<div class='row'><span>Tomorrow's outlook</span><b class='{out_cls}'>{hv['outlook']}{'' if pd.isna(row['P(up) next day']) else f" ({row['P(up) next day']:.0%})"}</b></div>"
            f"<div class='row'><span>Sell for profit at</span><b class='up'>{inr(hv['target'])}</b></div>"
            f"<div class='row'><span>Sell to limit loss at</span><b class='down'>{inr(hv['stop'])}</b></div>"
            f"<div class='sub' style='margin-top:.5rem'>{hv['msg']}</div>{badge(row['Confidence'])}</div>")


def mood_banner(mo):
    cls = {"Bullish": "up", "Bearish": "down"}.get(mo["mood"], "")
    text = {"Bullish": "Most signs are positive: prices are trending up and most big stocks are rising.",
            "Bearish": "Most signs are negative: prices are trending down and most big stocks are falling.",
            "Mixed": "Signs are mixed: some things look good, others don't. Be selective."}[mo["mood"]]
    st.markdown(f"<div class='verdict'><h3>Market mood: <span class='{cls}'>{mo['mood']}</span></h3>"
                f"<p>{text}<br><small>{' · '.join(mo['reasons'])}</small></p></div>", unsafe_allow_html=True)


def style_fig(fig):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.12, title=None),
                      colorway=["#e6edf7", "#2dd4bf", "#818cf8", "#fbbf24", "#f472b6", "#94a3b8"])
    fig.update_xaxes(gridcolor="#1b2740")
    fig.update_yaxes(gridcolor="#1b2740")
    return fig
