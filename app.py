import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import auth
import market
import portfolio
import ui
from chatbot import answer
from core import (MARKET, MODEL_NAMES, STOCKS, holding_view, market_overview, price_history,
                  rank_all, run, score_symbol)

st.set_page_config(page_title="MarketLens - understand stocks with AI", page_icon="📈", layout="wide")
ui.inject()


# ============================ LOGIN ============================
def login_page():
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        ui.brand()
        st.markdown(
            """<div class='hero'><span class='pill'>New to the share market? Start here</span>
            <h1>Know <em>when to buy</em> and <em>when to sell</em> &mdash; in plain English.</h1>
            <p>MarketLens scans the entire NSE market every day, tells you how the market is running, and gives
            a price to buy, a price to sell for profit and a price to limit a loss. No experience needed.</p>
            <div class='feat'><i>🌤️</i><div><b>Daily market check</b><br>Is the market up or down today, and why?</div></div>
            <div class='feat'><i>💰</i><div><b>Every NSE stock</b><br>1,600+ companies with prices, buy ranges and Buy / Wait / Sell signals.</div></div>
            <div class='feat'><i>🧺</i><div><b>Your buys</b><br>Track what you own and see if each stock may rise or fall.</div></div>
            <div class='feat'><i>💬</i><div><b>Ask anything</b><br>The assistant in the corner explains every word.</div></div>
            </div>""", unsafe_allow_html=True)
    with right:
        st.write("")
        st.write("")
        with st.container(border=True):
            st.markdown("### Welcome 👋")
            tab_in, tab_up = st.tabs(["Log in", "Create free account"])
            with tab_in:
                with st.form("login"):
                    u = st.text_input("Username")
                    p = st.text_input("Password", type="password")
                    if st.form_submit_button("Log in", type="primary", use_container_width=True):
                        if auth.login(u, p):
                            st.session_state.user = u.strip().lower()
                            st.rerun()
                        st.error("Wrong username or password.")
            with tab_up:
                with st.form("signup"):
                    u = st.text_input("Choose a username")
                    p = st.text_input("Choose a password", type="password", help="At least 6 characters")
                    if st.form_submit_button("Sign up", type="primary", use_container_width=True):
                        ok, msg = auth.register(u, p)
                        (st.success if ok else st.error)(msg)
        st.caption("Educational project. Not investment advice.")
    ui.footer()


if "user" not in st.session_state:
    login_page()
    st.stop()
USER = st.session_state.user


# ============================ DATA ============================
@st.cache_data(show_spinner=False, ttl=3600)
def cached_rank(version):
    return rank_all()


@st.cache_data(show_spinner=False, ttl=3600)
def cached_overview(version):
    return market_overview(cached_rank(version), market.scan_all())


@st.cache_data(show_spinner=False, ttl=3600)
def cached_all(version):
    """Every NSE stock (price rules) + AI scores for the Nifty 50 merged in."""
    scan, rank = market.scan_all(), cached_rank(version)
    m = scan.copy()
    r = rank.set_index("Ticker")
    m["P(up) next day"] = m["Ticker"].map(r["P(up) next day"])
    m["Backtest accuracy"] = m["Ticker"].map(r["Backtest accuracy"])
    m["Edge vs always-UP"] = m["Ticker"].map(r["Edge vs always-UP"])
    m["Confidence"] = m["Ticker"].map(r["Confidence"]).fillna("Not scored")
    m["Signal"] = m["Ticker"].map(r["Signal"]).fillna(m["Signal"])
    m["Why"] = m["Ticker"].map(r["Why"]).fillna(m["Why"])
    m["Sector"] = m["Ticker"].map(r["Sector"]).fillna(m["Sector"])
    m["Basis"] = np.where(m["Ticker"].isin(r.index), "AI + price rules", "Price rules only")
    missing = rank[~rank["Ticker"].isin(m["Ticker"])]
    m = pd.concat([m, missing.assign(Basis="AI + price rules")], ignore_index=True)
    return m.sort_values("Value traded (Cr/day)", ascending=False, na_position="last").reset_index(drop=True)


@st.cache_data(show_spinner=False, ttl=60)
def cached_live(tickers):
    return market.live_quotes(list(tickers))


@st.cache_data(show_spinner=False, ttl=600)
def cached_symbol(sym):
    return score_symbol(sym)


@st.cache_data(show_spinner=False, ttl=3600)
def cached_run(tk, ts):
    r = run(tk, ts)
    return r["table"], r["curves"], r["latest_prob_up"], r["latest_date"], r["up_rate"]


def get_rank():
    with st.spinner("Scanning the market: downloading today's prices and running the AI on every stock "
                    "(about a minute the first time)..."):
        return cached_rank(market.data_version())


def get_all():
    if not market.scan_exists():
        bar = st.progress(0.0, text="Scanning every NSE stock (1-2 minutes, only the first time)...")
        market.scan_all(progress=lambda p: bar.progress(min(p, 1.0), text=f"Scanning every NSE stock... {p:.0%}"))
        bar.empty()
    get_rank()
    return cached_all(market.data_version())


@st.fragment(run_every="15s")
def auto_refresh():
    """Starts a market refresh when one is due and reloads the page when new data is ready."""
    running = market.refresh_in_background()
    version = market.data_version()
    if not running and st.session_state.setdefault("shown_version", version) != version:
        st.session_state.shown_version = version
        st.rerun(scope="app")
    t = market.updated_at()
    if t:
        st.caption(f"Market data updated {t:%d %b, %H:%M} IST"
                   + (" · fetching newer prices in the background..." if running else
                      " · refreshes every 10 minutes while the market is open"))


def open_stock(name):
    st.session_state.sel = name
    st.switch_page(PG["stock"])


def lookup(allv, ticker):
    """Best available row: full AI analysis if possible, else the price-rule row from the scan."""
    hit = allv[allv["Ticker"] == ticker]
    if len(hit) and hit.iloc[0]["Basis"] == "AI + price rules":
        return hit.iloc[0]
    try:
        return cached_symbol(ticker)
    except Exception:
        if len(hit):
            return hit.iloc[0]
        raise


# ============================ PAGES ============================
@st.fragment(run_every="60s")
def live_strip():
    q = cached_live((MARKET,)).get(MARKET)
    if q:
        p, prev, ts = q
        tone = "up" if p >= prev else "down"
        st.markdown(f"<div class='simple'>🔴 <b>LIVE</b> &nbsp; Nifty 50 &nbsp;<b>{p:,.2f}</b> &nbsp;"
                    f"<span class='{tone}'>{p / prev - 1:+.2%}</span> &nbsp;·&nbsp; last tick {ts:%H:%M} IST "
                    f"· refreshes every minute (Yahoo prices can be delayed up to ~15 min)</div>",
                    unsafe_allow_html=True)


def page_home():
    get_all()
    rank = get_rank()
    mo = cached_overview(market.data_version())
    st.markdown(f"<div class='hero'><span class='pill'>Prices for {mo['as_of']:%d %b %Y}</span>"
                f"<h1>How is the market <em>running today?</em></h1></div>", unsafe_allow_html=True)
    live_strip()
    ui.mood_banner(mo)
    ui.simple("The <b>Nifty 50</b> is a score of India's 50 biggest companies. If it is rising, the market is "
              "generally doing well. We also count how many stocks rose today and what the AI expects tomorrow.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nifty 50", f"{mo['price']:,.0f}", f"{mo['change']['1 day']:+.2%} today")
    c2.metric("Past month", f"{mo['change']['1 month']:+.1%}", f"3 months {mo['change']['3 months']:+.1%}",
              delta_color="off")
    c3.metric("Stocks rising today", f"{mo['advancers']:,} of {mo['n_stocks']:,}", "whole NSE market", delta_color="off")
    p_idx = mo["index_p_up"]
    c4.metric("AI view for tomorrow", "Up" if p_idx and p_idx > 0.5 else "Down" if p_idx else "n/a",
              f"{p_idx:.0%} chance of rising" if p_idx else None, delta_color="off")

    l, r = st.columns([3, 2], gap="large")
    with l:
        ui.section("Nifty 50 – last year")
        h = mo["history"]
        fig = go.Figure(go.Scatter(x=h.index, y=h.values, line=dict(color="#2dd4bf", width=2), fill="tozeroy",
                                   fillcolor="rgba(45,212,191,.08)"))
        fig.update_yaxes(range=[h.min() * 0.97, h.max() * 1.02])
        st.plotly_chart(ui.style_fig(fig), width="stretch")
    with r:
        ui.section("Which areas are moving?", "Average change today by sector (Nifty 50 stocks).")
        sec = mo["sectors"].copy()
        sec["Today"] *= 100
        fig = px.bar(sec.sort_values("Today"), x="Today", y="Sector", orientation="h",
                     color="Today", color_continuous_scale=["#f87171", "#475569", "#4ade80"],
                     color_continuous_midpoint=0, labels={"Today": "% change today", "Sector": ""})
        fig.update_layout(coloraxis_showscale=False, height=360)
        st.plotly_chart(ui.style_fig(fig), width="stretch")

    g, lo = st.columns(2, gap="large")
    for col, title, df, tone in ((g, "🚀 Top gainers today", mo["gainers"], "up"),
                                 (lo, "📉 Top losers today", mo["losers"], "down")):
        with col:
            ui.section(title)
            for _, x in df.iterrows():
                st.markdown(f"**{x['Stock']}** &nbsp; {ui.inr(x['Price'])} &nbsp; "
                            f"<span class='{tone}'>{x['Day change']:+.2%}</span> &nbsp; "
                            f"<small>signal: {x['Signal']}</small>", unsafe_allow_html=True)

    ui.section("Best-ranked stocks for tomorrow", "Nifty 50 stocks sorted by the AI's chance that the price rises.")
    for col, (_, row) in zip(st.columns(3), rank.head(3).iterrows()):
        with col:
            st.markdown(ui.stock_card(row), unsafe_allow_html=True)
            st.button(f"View {row['Stock']} plan →", key=f"h_{row['Stock']}", on_click=open_stock,
                      args=(row["Stock"],), use_container_width=True)
    st.write("")
    s = cached_all(market.data_version())["Signal"].value_counts()
    st.caption("Signal counts below cover every NSE stock scanned.")
    a, b, c = st.columns(3)
    a.metric("🟢 Buy signals", int(s.get("Buy", 0)))
    b.metric("🟡 Wait", int(s.get("Wait", 0)))
    c.metric("🔴 Sell / avoid", int(s.get("Sell", 0)))
    st.warning("The AI is right about 50% of the time on next-day moves, close to a coin flip. "
               "Treat every signal as an idea to study, not a promise of profit.")
    if st.button("🔄 Re-scan the market now"):
        st.cache_data.clear()
        rank_all(force=True)
        st.rerun()


def page_market():
    st.title("All NSE stocks: prices & signals")
    allv = get_all()
    st.caption(f"{len(allv):,} actively traded NSE companies · latest prices for {allv['As of'].max():%d %b %Y}. "
               "Tiny, rarely-traded stocks are left out.")
    ui.simple("<b>Buy range</b>: a price zone near recent lows. <b>Sell for profit</b>: where to take your gain. "
              "<b>Stop-loss</b>: where to get out if it keeps falling. <b>Signal</b>: BUY / WAIT / SELL. "
              "Nifty 50 stocks get the AI's opinion too; all others use price-trend rules only.")
    f1, f2, f3, f4 = st.columns([2, 1.2, 1.3, 1.1])
    q = f1.text_input("Search", placeholder="Search a company or symbol, e.g. Tata, bank, IRCTC",
                      label_visibility="collapsed")
    sector = f2.selectbox("Sector", ["All sectors"] + sorted(x for x in allv["Sector"].unique() if x != "-"),
                          label_visibility="collapsed")
    pick = f3.segmented_control("Signal", ["All", "Buy", "Wait", "Sell"], default="All",
                                label_visibility="collapsed")
    only_ai = f4.toggle("AI-scored only", help="Show only Nifty 50 stocks that have the AI's opinion.")
    view = allv
    if q:
        view = view[view["Stock"].str.contains(q, case=False, regex=False)
                    | view["Ticker"].str.contains(q, case=False, regex=False)
                    | view["Sector"].str.contains(q, case=False, regex=False)]
    if sector != "All sectors":
        view = view[view["Sector"] == sector]
    if pick not in (None, "All"):
        view = view[view["Signal"] == pick]
    if only_ai:
        view = view[view["Basis"] == "AI + price rules"]
    view = view.reset_index(drop=True).copy()
    if view.empty:
        st.info("No stocks match. Try clearing a filter.")
        return
    live = st.toggle("🔴 Live prices for the first 100 rows shown",
                     help="Fetches the latest minute prices from Yahoo (can be delayed ~15 min).")
    if live:
        qts = cached_live(tuple(view["Ticker"].head(100)))
        for i, t in enumerate(view["Ticker"].head(100)):
            if t in qts:
                p, prev, _ = qts[t]
                view.loc[i, "Price"], view.loc[i, "Day change"] = p, p / prev - 1
    st.caption(f"Showing {len(view):,} stocks, sorted by trading activity.")
    tbl = pd.DataFrame({
        "Company": view["Stock"], "Symbol": view["Ticker"].str.replace(".NS", "", regex=False),
        "Sector": view["Sector"], "Price (₹)": view["Price"], "Today %": view["Day change"] * 100,
        "Buy from (₹)": view["Buy from"], "Buy up to (₹)": view["Buy up to"],
        "Sell for profit (₹)": view["Sell target"], "Stop-loss (₹)": view["Stop-loss"],
        "Signal": view["Signal"], "Chance of rising": view["P(up) next day"] * 100, "Basis": view["Basis"]})
    cfg = {c: st.column_config.NumberColumn(format="%.2f") for c in tbl.columns if "₹" in c}
    cfg["Today %"] = st.column_config.NumberColumn(format="%+.2f%%")
    cfg["Chance of rising"] = st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%")
    ev = st.dataframe(tbl, hide_index=True, width="stretch", height=560, column_config=cfg,
                      on_select="rerun", selection_mode="single-row")
    if ev.selection.rows:
        r = view.loc[ev.selection.rows[0]]
        st.button(f"Open full plan for {r['Stock']} →", type="primary", on_click=open_stock, args=(r["Ticker"],))
    else:
        st.caption("Tip: click a row to open that stock's full plan.")


def page_stock():
    st.title("Stock plan")
    allv = get_all()
    tickers = list(allv["Ticker"])
    label = {t: f"{n}  ({t.replace('.NS', '')})" for t, n in zip(allv["Ticker"], allv["Stock"])}
    sel = st.session_state.get("sel", tickers[0])
    sel = sel if sel in label else next((t for t, n in zip(allv["Ticker"], allv["Stock"]) if n == sel), tickers[0])
    c1, c2 = st.columns([2, 2])
    tk = c1.selectbox("Choose a company (type to search)", tickers, index=tickers.index(sel),
                      format_func=lambda t: label[t])
    st.session_state.sel = tk
    custom = c2.text_input("…or any NSE symbol not in the list", placeholder="e.g. IRCTC, DMART, PAYTM")
    try:
        with st.spinner("Analysing..."):
            row = lookup(allv, custom.strip().upper() + ".NS" if custom.strip() else tk)
    except Exception:
        st.error("Couldn't find enough price history for that symbol. Check the NSE symbol and try again.")
        return
    name = row["Stock"]
    if pd.isna(row["P(up) next day"]):
        st.info("AI analysis wasn't possible for this stock (too little history), so the plan uses price rules only.")

    sig_color = {"Buy": "up", "Sell": "down", "Wait": ""}[row["Signal"]]
    st.markdown(f"<div class='verdict'><h3>{name}: {ui.inr(row['Price'])} &nbsp;·&nbsp; "
                f"<span class='{sig_color}'>{row['Signal'].upper()}</span></h3>"
                f"<p>{row['Why']} Last close: {row['As of']:%d %b %Y}.</p></div>", unsafe_allow_html=True)
    ui.section("Your price plan")
    ui.price_plan(row)
    ui.simple(f"If you buy near {ui.inr(row['Price'])}, a good plan is to sell when it reaches "
              f"<b>{ui.inr(row['Sell target'])}</b> (profit) or if it drops to <b>{ui.inr(row['Stop-loss'])}</b> "
              f"(so a bad trade doesn't hurt you much). Review again in about 1–2 weeks.")
    ui.section("Where is the price now?", "Compared with its lowest and highest price in the last year.")
    ui.gauge(row["Price"], row["52w low"], row["52w high"],
             f"1-year low {ui.inr(row['52w low'])}", f"1-year high {ui.inr(row['52w high'])}")
    hist = price_history(row["Ticker"])
    fig = go.Figure(go.Scatter(x=hist.index, y=hist.values, name="Price", line=dict(color="#e6edf7", width=2)))
    fig.add_hline(y=row["Sell target"], line_dash="dot", line_color="#4ade80", annotation_text="Sell for profit")
    fig.add_hline(y=row["Stop-loss"], line_dash="dot", line_color="#f87171", annotation_text="Stop-loss")
    fig.add_hrect(y0=row["Buy from"], y1=row["Buy up to"], fillcolor="#2dd4bf", opacity=.15, line_width=0)
    st.plotly_chart(ui.style_fig(fig), width="stretch")

    if pd.isna(row["P(up) next day"]):
        return
    ui.section("How the AI did", "Tested on days it had never seen (2023 onward).")
    st.metric("Chance of rising tomorrow", f"{row['P(up) next day']:.0%}")
    if not st.toggle("Show the AI's test results (takes a few seconds)", key="show_ai_test"):
        return
    with st.spinner("Testing the AI on past days..."):
        table, curves, probs, ldate, up_rate = cached_run(row["Ticker"], "2023-01-01")
    acc = table.loc[MODEL_NAMES, "Accuracy"].mean()
    m2, m3 = st.columns(2)
    m2.metric("AI was right", f"{acc:.0%} of days", help="50% is the same as flipping a coin.")
    m3.metric("Days the stock rose", f"{up_rate:.0%}", help="Guessing 'up' every day would score this.")
    ui.simple("If the AI is right about as often as the stock simply rises, it has added no real skill. "
              "That is common — large stocks are hard to predict.")
    with st.expander("See detailed results for each AI model"):
        t1, t2 = st.tabs(["Growth of ₹1 vs just holding", "Results table"])
        with t1:
            st.caption("What ₹1 would have become after trading costs of 0.1% per trade.")
            fig2 = px.line(curves, labels={"value": "Growth of ₹1", "index": "", "variable": ""})
            st.plotly_chart(ui.style_fig(fig2), width="stretch")
        with t2:
            st.dataframe(table.style.format({"Accuracy": "{:.1%}", "Final return": "{:+.1%}"}, na_rep="-"),
                         width="stretch")


@st.fragment(run_every="60s")
def holdings_view(allv, hold):
    """Re-runs every minute so prices and verdicts stay live (Yahoo data, may be delayed ~15 min)."""
    rows = []
    for _, h in hold.iterrows():
        try:
            r = lookup(allv, h["ticker"]).copy()
        except Exception:
            continue
        rows.append([h, r])
    qts = cached_live(tuple(r["Ticker"] for _, r in rows))
    stamp = None
    for h, r in rows:
        if r["Ticker"] in qts:
            r["Price"], _, stamp = qts[r["Ticker"]]
    rows = [(h, r, holding_view(r, h["buy_price"])) for h, r in rows]
    if not rows:
        st.warning("Couldn't load prices for your stocks right now.")
        return
    invested = sum(h["buy_price"] * h["qty"] for h, _, _ in rows)
    value = sum(r["Price"] * h["qty"] for h, r, _ in rows)
    rising = sum(hv["outlook"] == "May rise" for _, _, hv in rows)
    falling = sum(hv["outlook"] == "May fall" for _, _, hv in rows)
    sells = sum(hv["verdict"] != "HOLD" for _, _, hv in rows)
    if stamp is not None:
        st.caption(f"🔴 Live prices · last tick {stamp:%H:%M} IST · refreshes every minute")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("You invested", f"₹{invested:,.0f}")
    m2.metric("Worth now", f"₹{value:,.0f}", f"{value - invested:+,.0f} ₹ ({value / invested - 1:+.1%})")
    m3.metric("Outlook for tomorrow", f"{rising} may rise", f"{falling} may fall", delta_color="off")
    m4.metric("Need attention", f"{sells} stock(s)", "consider selling" if sells else "all on plan", delta_color="off")
    if sells:
        names = ", ".join(r["Stock"] for _, r, hv in rows if hv["verdict"] != "HOLD")
        st.warning(f"Check these: {names}. See the sell advice on their cards below.")
    ui.simple("<b>May rise / May fall</b> is the AI's guess for tomorrow only (right about 50% of the time; "
              "stocks outside the Nifty 50 have no AI guess). The <b>sell prices</b> are the real plan: sell for "
              "profit at the target, or exit at the stop-loss so a loss stays small.")

    for i in range(0, len(rows), 3):
        for col, (h, r, hv) in zip(st.columns(3), rows[i:i + 3]):
            with col:
                st.markdown(ui.holding_card(r, hv, h["qty"], h["buy_price"]), unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                b1.button("Plan", key=f"p{h['id']}", on_click=open_stock, args=(r["Ticker"],),
                          use_container_width=True)
                if b2.button("Remove", key=f"d{h['id']}", use_container_width=True):
                    portfolio.remove(USER, h["id"])
                    st.rerun(scope="app")
        st.write("")

    pl = pd.DataFrame({"Stock": [r["Stock"] for _, r, _ in rows],
                       "Profit / loss (₹)": [(r["Price"] - h["buy_price"]) * h["qty"] for h, r, _ in rows]})
    fig = px.bar(pl, x="Stock", y="Profit / loss (₹)", color="Profit / loss (₹)",
                 color_continuous_scale=["#f87171", "#475569", "#4ade80"], color_continuous_midpoint=0)
    fig.update_layout(coloraxis_showscale=False, height=300)
    ui.section("Profit / loss by stock")
    st.plotly_chart(ui.style_fig(fig), width="stretch")


def page_buys():
    st.title("Your buys")
    st.caption("Add the stocks you bought. We track them live and tell you if each one may rise or fall, "
               "and when to sell. Any NSE stock works.")
    allv = get_all()
    hold = portfolio.listing(USER)

    with st.expander("➕ Add a stock you bought", expanded=hold.empty):
        tickers = list(allv["Ticker"])
        label = {t: f"{n}  ({t.replace('.NS', '')})" for t, n in zip(allv["Ticker"], allv["Stock"])}
        c1, c2, c3, c4 = st.columns([2.2, 1.1, 1.3, 1.1])
        tk = c1.selectbox("Company (type to search)", tickers, format_func=lambda t: label[t], key="b_choice")
        other = c1.text_input("…or an NSE symbol not in the list", placeholder="e.g. IRCTC")
        qty = c2.number_input("Shares bought", min_value=1, value=10, step=1)
        default = float(allv.loc[allv["Ticker"] == tk, "Price"].iloc[0])
        paid = c3.number_input("Price paid per share (₹)", min_value=0.01, value=round(default, 2), step=1.0,
                               key=f"b_paid_{tk}")
        when = c4.date_input("Date bought")
        if st.button("Add to my buys", type="primary"):
            sym = other.strip().upper() + ".NS" if other.strip() else tk
            try:
                lookup(allv, sym)
            except Exception:
                st.error("Couldn't find that symbol. Check the NSE symbol.")
                st.stop()
            portfolio.add(USER, sym, qty, paid, when)
            st.success("Added!")
            st.rerun()

    if hold.empty:
        st.info("You haven't added any stocks yet. Add one above to see its outlook and sell plan.")
        ui.simple("Once you add a stock, we show your live profit or loss, whether the AI thinks it "
                  "<b>may rise or fall</b> tomorrow, and the exact prices at which to <b>sell for profit</b> or "
                  "<b>sell to limit a loss</b>.")
        return
    holdings_view(allv, hold)


def page_learn():
    st.title("Learn the basics")
    st.caption("Everything you need to understand this site, with no prior knowledge.")
    ui.section("Share market in 4 ideas")
    steps = [("A share is a piece of a company", "Buying a share of Reliance makes you a very small owner of Reliance."),
             ("Price moves every day", "If more people want to buy than sell, the price rises. If more want to sell, it falls."),
             ("Profit = sell higher than you bought", "Buy at ₹100, sell at ₹110 → ₹10 profit per share. Sell at ₹90 → ₹10 loss."),
             ("Risk is real", "Prices can fall and stay low. Spread money across several companies and only invest what you can afford to lose.")]
    for i, (h, p) in enumerate(steps, 1):
        st.markdown(f"<div class='step'><div class='n'>{i}</div><div><h4>{h}</h4><p>{p}</p></div></div>",
                    unsafe_allow_html=True)
    ui.section("Words you will see here")
    gloss = {
        "NSE": "National Stock Exchange - the marketplace where Indian shares are traded.",
        "Nifty 50": "An index (score) of India's 50 biggest companies. It shows how the overall market is doing.",
        "Market mood": "Our summary of whether the market is Bullish (rising), Bearish (falling) or Mixed.",
        "Gainers / losers": "Stocks that rose or fell the most today.",
        "Closing price": "The last price a share traded at on the previous trading day.",
        "Buy range": "A price range near recent lows. Buying here avoids paying a sudden spike price.",
        "Sell for profit (target)": "A price where you sell to lock in your gain.",
        "Stop-loss": "A price where you sell to stop a loss growing bigger. It's a safety net.",
        "Signal (Buy / Wait / Sell)": "Our overall suggestion today, combining the AI's view and price conditions.",
        "May rise / May fall": "The AI's guess for tomorrow. It is usually only slightly better than a coin flip.",
        "ATR": "Average True Range - how much a stock normally moves in a day. Used to set sensible targets.",
        "RSI": "A 0-100 gauge of how fast a price rose. Above 70 means it may be overheated.",
        "Backtest": "Replaying the AI on past days it hadn't seen, to check whether it would have worked.",
        "Diversification": "Spreading money over different companies so one bad stock hurts less.",
    }
    for k, v in gloss.items():
        st.markdown(f"**{k}** — {v}")
    ui.section("How our AI works")
    how = [("Collect data", "10 years of daily prices from Yahoo Finance for 48 big companies, plus the Nifty 50."),
           ("Spot patterns", "Recent returns, trend lines, RSI, MACD, volume and volatility."),
           ("Train 3 AI models", "Logistic Regression, Random Forest and XGBoost learn from 2015-2022."),
           ("Test honestly", "They are then judged on 2023 onward, data they have never seen."),
           ("Report the truth", "Accuracy is about 50%, so we show confidence labels and never promise profit.")]
    for i, (h, p) in enumerate(how, 1):
        st.markdown(f"<div class='step'><div class='n'>{i}</div><div><h4>{h}</h4><p>{p}</p></div></div>",
                    unsafe_allow_html=True)
    st.info("Buy ranges, targets and stop-losses come from simple volatility rules (ATR), not from the AI. "
            "The AI only provides the 'chance of rising tomorrow'. The market scan refreshes every 10 minutes "
            "while the market is open.")


# ============================ SHELL ============================
PG = {
    "home": st.Page(page_home, title="Market today", icon="🌤️", url_path="home", default=True),
    "market": st.Page(page_market, title="All stocks", icon="💹", url_path="market"),
    "stock": st.Page(page_stock, title="Stock plan", icon="🔍", url_path="stock"),
    "buys": st.Page(page_buys, title="Your buys", icon="🧺", url_path="buys"),
    "learn": st.Page(page_learn, title="Learn", icon="📘", url_path="learn"),
}

with st.container(key="topbar"):
    b, u = st.columns([3, 2])
    with b:
        ui.brand()
    with u:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"<div class='user-chip'>👤 {USER}</div>", unsafe_allow_html=True)
        if c2.button("Log out", use_container_width=True):
            for k in ("user", "chat", "sel"):
                st.session_state.pop(k, None)
            st.rerun()

nav = st.navigation(list(PG.values()), position="top")
st.session_state.shown_version = market.data_version()
auto_refresh()
nav.run()
ui.footer()

# ============================ FLOATING CHATBOT ============================
GREETING = ("Hi! I'm the MarketLens assistant 👋 Ask me things like *Will TCS rise tomorrow?*, "
            "*Which stocks may give a hike?*, *Should I sell Reliance?* or *How are my stocks doing?*")
st.session_state.setdefault("chat", [{"role": "assistant", "content": GREETING}])


def ask(q):
    q = q.strip()
    if not q:
        return
    try:
        allv = get_all()
        hold = []
        for _, h in portfolio.listing(USER).iterrows():
            try:
                r = lookup(allv, h["ticker"])
                hold.append({"row": r, "buy": h["buy_price"], "qty": h["qty"], "hv": holding_view(r, h["buy_price"])})
            except Exception:
                pass

        def analyze(r):
            """Add the AI view for a stock the user asks about, if it hasn't been scored yet."""
            if r["Basis"] == "AI + price rules":
                return r
            try:
                return cached_symbol(r["Ticker"])
            except Exception:
                return r

        data = {"all": allv, "overview": cached_overview(market.data_version()), "holdings": hold,
                "analyze": analyze}
        reply = answer(q, data, st.session_state.chat[1:], st.session_state.get("api_key") or None)
    except Exception as e:
        reply = f"Sorry, I couldn't load the market data just now ({type(e).__name__}). Please try again."
    st.session_state.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": reply}]


def submit():
    ask(st.session_state.get("chat_text", ""))


with st.container(key="chatfab"):
    with st.popover("Chat"):
        st.markdown(f"<div class='chat-head'><img src=\"{ui.LOGO_URI}\"><div><b>MarketLens Assistant</b>"
                    f"<span>Ask in simple words</span></div></div>", unsafe_allow_html=True)
        box = st.container(height=300, border=False)
        with box:
            for m in st.session_state.chat:
                st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else None).write(m["content"])
        q1, q2, q3 = st.columns(3)
        q1.button("Top picks", on_click=ask, args=("Which stocks may give a hike today?",), use_container_width=True)
        q2.button("My stocks", on_click=ask, args=("How are my stocks doing?",), use_container_width=True)
        q3.button("Market", on_click=ask, args=("How is the market today?",), use_container_width=True)
        with st.form("chatform", clear_on_submit=True, border=False):
            c_in, c_btn = st.columns([4, 1])
            c_in.text_input("Message", key="chat_text", placeholder="Ask a question...",
                            label_visibility="collapsed")
            c_btn.form_submit_button("➤", on_click=submit, use_container_width=True)
        with st.expander("Optional: use Claude for smarter answers"):
            st.text_input("Claude API key", type="password", key="api_key")
