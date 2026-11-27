"""MarketLens assistant.

It reads the live tables the app already computed (prices, AI scores, market mood, the user's holdings)
and answers the question that was actually asked: a stock's outlook, what to buy or avoid, a sector,
a comparison, "my stocks", market mood or a definition.
If a Claude API key is provided, Claude writes the answer from the same data instead.
"""
import os
import re

import pandas as pd

MODEL = "claude-sonnet-5-5"
NOTE = "_Model-based estimate, not a guarantee. The AI is right about 50% of the time._"

GLOSSARY = {
    "stop-loss": "A **stop-loss** is a price below your buying price where you sell to stop a loss growing. "
                 "Example: bought at ₹100, stop-loss ₹92 means you exit if it falls to ₹92.",
    "target": "A **sell target** (take-profit) is the price where you sell to lock in your gain.",
    "share": "A **share** is a small piece of a company. If the company does well its price usually rises; "
             "you profit by selling higher than you bought. You can also lose money if the price falls.",
    "stock": "A **stock** (share) is a small ownership piece of a company, traded on exchanges like NSE.",
    "nse": "**NSE** (National Stock Exchange) is where Indian company shares are bought and sold.",
    "nifty": "The **Nifty 50** is a score of India's 50 biggest companies. If it rises, the market is generally doing well.",
    "sensex": "The **Sensex** is like the Nifty but tracks 30 big companies on the BSE exchange.",
    "rsi": "**RSI** is a 0-100 gauge of how fast a price has risen. Above 70 = maybe overheated (pullback risk), "
           "below 30 = maybe oversold.",
    "atr": "**ATR** (Average True Range) is how much a stock normally moves in a day. We use it to set sensible "
           "profit targets and stop-losses.",
    "backtest": "A **backtest** replays the AI on past days it had not seen, to check whether it would have worked.",
    "diversif": "**Diversification** means spreading money over different companies and sectors so one bad stock hurts less.",
    "dividend": "A **dividend** is a share of profit a company pays to its shareholders, usually yearly or quarterly.",
    "sip": "A **SIP** invests a fixed amount every month (usually in mutual funds), so you buy gradually instead of timing the market.",
    "mutual fund": "A **mutual fund** pools many people's money and a manager invests it in many stocks or bonds. "
                   "Index funds that copy the Nifty 50 are a simple, low-cost start for beginners.",
    "bullish": "**Bullish** means prices are trending up. **Bearish** means trending down.",
    "bearish": "**Bearish** means prices are trending down. **Bullish** means trending up.",
    "volume": "**Volume** is how many shares were traded. High volume means many people are actively trading it.",
    "market cap": "**Market cap** is a company's total value: share price × number of shares.",
    "p/e": "**P/E ratio** is price divided by yearly profit per share. High P/E = investors expect big growth (or it's expensive).",
    "signal": "Our **signal** is Buy / Wait / Sell. Buy = trend and AI lean up and price isn't overheated; "
              "Sell = AI leans down or price is overheated / in a downtrend; Wait = no clear signal.",
    "buy range": "The **buy range** is a price zone near recent lows. Buying there avoids paying a sudden spike.",
}

SECTOR_WORDS = {
    "it": ["it stock", "it sector", "it compan", "software", "tech stock", "technology", " it "],
    "banking": ["bank"], "finance": ["finance", "nbfc", "financial"], "pharma": ["pharma", "medicine", "drug"],
    "healthcare": ["hospital", "healthcare"], "auto": ["auto", "car ", "cars", "vehicle", "bike"],
    "fmcg": ["fmcg", "consumer goods"], "energy": ["energy", "oil", "gas"], "power": ["power", "electricity"],
    "metals": ["metal", "steel"], "cement": ["cement"], "telecom": ["telecom"], "insurance": ["insurance"],
    "infrastructure": ["infra"], "defence": ["defence", "defense"], "mining": ["mining", "coal"],
    "consumer": ["consumer", "retail"],
}
STOP = set("""the and for buy sell will can are how why what when where which who stock stocks market today price good best
top rise fall hike loss profit gain tomorrow invest share shares should about with this that you own have has from low high
new day risk safe cap one two get now next open long term time week month year bank banks india limited industries
company companies than then them they there give tell show list please predict prediction tomorrow's going does did into
more most less much many very also just like want need help any all some sector sectors compare versus""".split())


def inr(x):
    return f"₹{x:,.2f}"


def _pct(x):
    return f"{x:+.1%}"


def outlook(p):
    if pd.isna(p):
        return "no AI view for this stock (price rules only)"
    if p >= 0.58:
        return f"**likely to rise** ({p:.0%} chance)"
    if p >= 0.52:
        return f"**slightly leaning up** ({p:.0%} chance)"
    if p <= 0.42:
        return f"**likely to fall** ({p:.0%} chance of rising)"
    if p <= 0.48:
        return f"**slightly leaning down** ({p:.0%} chance of rising)"
    return f"**uncertain, roughly 50/50** ({p:.0%} chance of rising)"


# ------------------------------------------------------------------ entity matching
def find_stocks(q, allv):
    """Return rows for stocks mentioned in the question (company name or NSE symbol)."""
    ql = " " + re.sub(r"[^a-z0-9&\-\. ]", " ", q.lower()) + " "
    toks = set(ql.split())
    hits = {}
    names = allv["Stock"].str.lower()
    for i, n in names.items():                      # full company name (longest first handled by dedupe below)
        if len(n) >= 3 and f" {n} " in ql:
            hits[i] = len(n)
    syms = allv["Ticker"].str.replace(".NS", "", regex=False).str.lower()
    for i, s in syms.items():                       # NSE symbol as its own word
        if len(s) >= 3 and s in toks and s not in STOP and i not in hits:
            hits[i] = len(s)
    if not hits:                                    # fuzzy: a distinctive word such as "zomato" or "airtel"
        for t in toks:
            if len(t) >= 4 and t not in STOP:
                m = allv[names.str.contains(rf"\b{re.escape(t)}", regex=True)]
                if 0 < len(m) <= 2 and not any(t in w for ws in SECTOR_WORDS.values() for w in ws):
                    for i in m.index:
                        hits[i] = len(t)
    # drop names contained inside a longer matched name (e.g. "Tata" inside "Tata Steel")
    idx = sorted(hits, key=lambda i: -hits[i])
    keep = []
    for i in idx:
        if not any(names[i] in names[j] and i != j for j in keep):
            keep.append(i)
    return [allv.loc[i] for i in keep[:3]]


def find_sector(q, allv):
    ql = f" {q.lower()} "
    for sec, words in SECTOR_WORDS.items():
        if any(w in ql for w in words):
            hit = [s for s in allv["Sector"].unique() if s.lower() == sec]
            if hit:
                return hit[0]
    return None


# ------------------------------------------------------------------ answer builders
def short_answer(r, focus):
    sig = r["Signal"]
    if focus == "sell":
        return {"Sell": "**Yes, the signals lean toward selling (or avoiding) it.**",
                "Buy": "**No sell signal right now.** If you own it, hold; sell at the target or the stop-loss.",
                "Wait": "**Not urgent.** No clear sell signal; just respect your stop-loss."}[sig]
    if focus == "buy":
        return {"Buy": "**Signal says BUY**, ideally inside the buy range below.",
                "Wait": "**Better to wait.** There is no clear signal yet.",
                "Sell": "**Not now.** The signals lean negative."}[sig]
    return {"Buy": "**Likely to rise (hike).**", "Sell": "**May fall (loss).**",
            "Wait": "**Could go either way.** No clear direction."}[sig]


def stock_reply(r, focus="general"):
    p = r["P(up) next day"]
    lines = [f"**{r['Stock']}** ({r['Ticker'].replace('.NS', '')}) is at **{inr(r['Price'])}** "
             f"({_pct(r['Day change'])} today), signal **{r['Signal'].upper()}**.", "", short_answer(r, focus), ""]
    lines.append(f"- **Tomorrow:** {outlook(p)}.")
    up, dn = r["Sell target"] / r["Price"] - 1, r["Stop-loss"] / r["Price"] - 1
    swing = r["ATR"] / r["Price"]
    verdict = ("Possible **hike**: price could move up toward the target." if r["Signal"] == "Buy"
               else "Possible **loss**: risk of a pullback or further decline." if r["Signal"] == "Sell"
               else "No clear hike or loss expected: it may just drift.")
    lines.append(f"- **Outlook:** {verdict} It normally swings about ±{swing:.1%} a day.")
    if focus in ("sell", "general"):
        lines.append(f"- **Sell for profit at** {inr(r['Sell target'])} ({up:+.1%}); **stop-loss** at "
                     f"{inr(r['Stop-loss'])} ({dn:+.1%}).")
    if focus in ("buy", "general"):
        lines.append(f"- **Good price to buy:** {inr(r['Buy from'])} to {inr(r['Buy up to'])}.")
    mom = r.get("Month change", r.get("60-day momentum", float("nan")))
    mom = 0.0 if pd.isna(mom) else mom
    lines.append(f"- **Why:** {r['Why']} (RSI {r['RSI']:.0f}, recent trend {_pct(mom)}).")
    if not pd.isna(r.get("Backtest accuracy", float("nan"))):
        e = r.get("Edge vs always-UP", float("nan"))
        edge_txt = "" if pd.isna(e) else f"{e:+.1%} vs simply guessing 'up'; "
        lines.append(f"- **Track record:** in testing the AI was right {r['Backtest accuracy']:.0%} of days on this stock "
                     f"({edge_txt}{str(r['Confidence']).lower()}).")
    lines += ["", NOTE]
    return "\n".join(lines)


def compare_reply(a, b):
    def s(r):
        return (f"**{r['Stock']}**: {inr(r['Price'])}, signal {r['Signal'].upper()}, "
                f"{outlook(r['P(up) next day'])}, target {inr(r['Sell target'])}, stop {inr(r['Stop-loss'])}")
    pa, pb = a["P(up) next day"], b["P(up) next day"]
    rank = {"Buy": 2, "Wait": 1, "Sell": 0}
    sa = rank[a["Signal"]] + (0 if pd.isna(pa) else pa)
    sb = rank[b["Signal"]] + (0 if pd.isna(pb) else pb)
    better = a if sa >= sb else b
    return (f"- {s(a)}\n- {s(b)}\n\nOn today's numbers **{better['Stock']}** looks slightly better "
            f"(stronger signal / chance of rising). The gap is small, so diversify instead of choosing one.\n\n{NOTE}")


def top_list(df, n=5):
    out = []
    for _, r in df.head(n).iterrows():
        pu = "" if pd.isna(r["P(up) next day"]) else f", {r['P(up) next day']:.0%} chance of rising"
        out.append(f"- **{r['Stock']}** {inr(r['Price'])} ({_pct(r['Day change'])} today){pu} → "
                   f"sell target {inr(r['Sell target'])}, stop-loss {inr(r['Stop-loss'])}")
    return "\n".join(out)


def rise_reply(allv, sector=None):
    d = allv if sector is None else allv[allv["Sector"] == sector]
    ai = d[(d["Basis"] == "AI + price rules") & (d["Signal"] == "Buy")].sort_values("P(up) next day", ascending=False)
    pr = d[(d["Basis"] != "AI + price rules") & (d["Signal"] == "Buy")].sort_values("Value traded (Cr/day)", ascending=False)
    where = f" in **{sector}**" if sector else ""
    if ai.empty and pr.empty:
        return f"No stocks{where} have a Buy signal today. Waiting is also a valid decision.\n\n{NOTE}"
    parts = [f"Stocks{where} with the best chance of a **hike** today:"]
    if len(ai):
        parts += ["", "**AI + price rules (Nifty 50)**", top_list(ai)]
    if len(pr):
        parts += ["", "**Price-trend rules (other NSE stocks, most traded first)**", top_list(pr)]
    return "\n".join(parts) + f"\n\nAsk about any of them for the full plan.\n\n{NOTE}"


def fall_reply(allv, sector=None):
    d = allv if sector is None else allv[allv["Sector"] == sector]
    ai = d[(d["Basis"] == "AI + price rules") & (d["Signal"] == "Sell")].sort_values("P(up) next day")
    pr = d[(d["Basis"] != "AI + price rules") & (d["Signal"] == "Sell")].sort_values("Value traded (Cr/day)", ascending=False)
    where = f" in **{sector}**" if sector else ""
    if ai.empty and pr.empty:
        return f"No stocks{where} show a Sell signal today.\n\n{NOTE}"
    parts = [f"Stocks{where} with the highest risk of a **loss** (Sell signal):"]
    if len(ai):
        parts += ["", "**AI + price rules (Nifty 50)**", top_list(ai)]
    if len(pr):
        parts += ["", "**Price-trend rules (other NSE stocks)**", top_list(pr)]
    return "\n".join(parts) + f"\n\nIf you own any of them, check the stop-loss in the list.\n\n{NOTE}"


def market_reply(mo):
    ch = mo["change"]
    g = ", ".join(f"{x['Stock']} {_pct(x['Day change'])}" for _, x in mo["gainers"].head(3).iterrows())
    l = ", ".join(f"{x['Stock']} {_pct(x['Day change'])}" for _, x in mo["losers"].head(3).iterrows())
    ai = f"AI view of the Nifty for tomorrow: {mo['index_p_up']:.0%} chance of rising." if mo["index_p_up"] else ""
    return (f"**Market mood: {mo['mood']}.** Nifty 50 is {mo['price']:,.0f} ({_pct(ch['1 day'])} today, "
            f"{_pct(ch['1 month'])} this month). {mo['advancers']:,} of {mo['n_stocks']:,} stocks rose today.\n\n"
            f"- Top gainers: {g}\n- Top losers: {l}\n- {ai}\n\n{NOTE}")


def portfolio_reply(hold):
    if not hold:
        return "You haven't added any stocks yet. Open the **Your buys** tab and add what you bought; then ask me again."
    out, tot_i, tot_v = [], 0, 0
    for h in hold:
        r, hv = h["row"], h["hv"]
        tot_i += h["buy"] * h["qty"]
        tot_v += r["Price"] * h["qty"]
        out.append(f"- **{r['Stock']}**: {_pct(hv['pl_pct'])} ({(r['Price'] - h['buy']) * h['qty']:+,.0f} ₹). "
                   f"Tomorrow: {hv['outlook'].lower()}. Verdict: **{hv['verdict']}**. Sell for profit {inr(hv['target'])}, "
                   f"stop-loss {inr(hv['stop'])}.")
    head = f"You invested ₹{tot_i:,.0f}; it is worth ₹{tot_v:,.0f} ({tot_v / tot_i - 1:+.1%}).\n\n"
    act = [h["row"]["Stock"] for h in hold if h["hv"]["verdict"] != "HOLD"]
    tail = f"\n\n⚠️ Needs attention: {', '.join(act)}." if act else "\n\nAll your stocks are on plan: hold."
    return head + "\n".join(out) + tail + f"\n\n{NOTE}"


# ------------------------------------------------------------------ router
def rule_answer(q, data):
    ql = q.lower().strip()
    allv, mo, hold = data["all"], data.get("overview"), data.get("holdings", [])

    if re.fullmatch(r"(hi|hello|hey|hii|namaste|good (morning|afternoon|evening))\W*", ql):
        return "Hello! Ask me about any stock (e.g. *Will TCS rise?*), what to buy or avoid, the market today, or your own stocks."
    if re.fullmatch(r"(thanks|thank you|ok|okay|great|nice)\W*", ql):
        return "You're welcome! Ask me anything else about stocks or the market."

    if re.search(r"\b(my (stocks?|portfolio|holdings?|buys|shares)|i (own|bought|hold)|am i (in )?(profit|loss))\b", ql):
        return portfolio_reply(hold)

    # definitions first ("what is stop loss")
    if re.search(r"\b(what is|what are|what's|meaning of|define|explain|tell me about)\b", ql):
        for term in sorted(GLOSSARY, key=len, reverse=True):
            if re.search(rf"\b{re.escape(term)}", ql.replace("stop loss", "stop-loss").replace("take profit", "target")):
                return GLOSSARY[term]
    stocks = find_stocks(q, allv)

    focus = "sell" if re.search(r"\b(sell|exit|book|stop|target)\b", ql) else \
            "buy" if re.search(r"\b(buy|entry|invest|purchase)\b", ql) else "general"
    if len(stocks) >= 2 and re.search(r"\b(vs|versus|compare|or|better|between|and)\b", ql):
        return compare_reply(stocks[0], stocks[1])
    if stocks:
        return "\n\n---\n\n".join(stock_reply(data["analyze"](r), focus) for r in stocks[:2])

    sector = find_sector(q, allv)
    wants_fall = re.search(r"\b(fall|drop|loss|lose|avoid|crash|down|decline|negative|sell)\b", ql)
    wants_rise = re.search(r"\b(rise|hike|up|gain|profit|buy|best|top|good|grow|green|invest|recommend|suggest|pick)\b", ql)
    if re.search(r"\b(market|nifty|sensex|indices|index)\b", ql) and not sector:
        return market_reply(mo)
    if sector and (wants_fall and not wants_rise):
        return fall_reply(allv, sector)
    if sector or wants_rise or wants_fall:
        if wants_fall and not wants_rise:
            return fall_reply(allv, sector)
        return rise_reply(allv, sector)
    if re.search(r"\b(accura|reliab|trust|sure|guarantee|correct)", ql):
        return ("The AI is right about **48-52%** of the time on next-day direction, close to a coin flip, so no "
                "prediction is certain. What helps more is the plan: buy near the buy range, sell at the target, "
                "and exit at the stop-loss. Diversify across several stocks.")
    if re.search(r"\b(how does|how do you|how it works|strategy|work)\b", ql):
        return ("Every day I scan all NSE stocks: price trend, RSI and daily swing set the buy range, sell target and "
                "stop-loss. For the Nifty 50 (and any stock you open) three AI models (Logistic Regression, Random "
                "Forest, XGBoost) are trained on 2015-2022 data, tested on 2023+, and give the chance of rising tomorrow.")
    for term in GLOSSARY:
        if re.search(rf"\b{re.escape(term)}", ql):
            return GLOSSARY[term]
    return ("I'm not sure what you mean. Try questions like:\n"
            "- *Will Infosys rise tomorrow?*  /  *Should I sell Reliance?*\n"
            "- *Which stocks may give a hike today?*  /  *Which stocks may fall?*\n"
            "- *Best IT stocks*  /  *TCS vs Infosys*\n"
            "- *How is the market today?*  /  *How are my stocks doing?*\n"
            "- *What is a stop-loss?*")


# ------------------------------------------------------------------ Claude path
SYSTEM = (
    "You are the assistant inside MarketLens, an educational Indian stock-market app. Answer the user's actual "
    "question using ONLY the DATA below (prices, AI chance of rising, signals, buy range, sell target, stop-loss, "
    "market mood, the user's holdings). Be direct and concrete: say whether a stock may rise (hike) or fall (loss), "
    "give the numbers, and explain simply for a beginner. Never invent prices or facts not in DATA. Do not repeat "
    "generic boilerplate; add one short caution that predictions are ~50% accurate and not advice. Under 160 words.")


def context(q, data):
    allv = data["all"]
    parts = []
    for r in find_stocks(q, allv)[:3]:
        r = data["analyze"](r)
        parts.append(stock_reply(r))
    if data.get("overview"):
        parts.append("MARKET: " + market_reply(data["overview"]))
    parts.append("TOP BUYS:\n" + top_list(allv[allv["Signal"] == "Buy"].sort_values("P(up) next day", ascending=False), 5))
    parts.append("TOP SELL/AVOID:\n" + top_list(allv[allv["Signal"] == "Sell"].sort_values("P(up) next day"), 5))
    if data.get("holdings"):
        parts.append("USER HOLDINGS:\n" + portfolio_reply(data["holdings"]))
    return "\n\n".join(parts)


def answer(question, data, history=None, api_key=None):
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    note = ""
    if key:
        try:
            import anthropic
            msgs = [{"role": m["role"], "content": m["content"]} for m in (history or [])][-8:]
            msgs.append({"role": "user", "content": question})
            r = anthropic.Anthropic(api_key=key).messages.create(
                model=MODEL, max_tokens=600, system=SYSTEM + "\n\nDATA:\n" + context(question, data), messages=msgs)
            return r.content[0].text
        except Exception as e:
            note = f"_(Claude unavailable: {type(e).__name__}; using built-in answers.)_\n\n"
    try:
        return note + rule_answer(question, data)
    except Exception:
        return note + "Sorry, I couldn't work that out. Try asking about a specific stock, e.g. *Will TCS rise?*"
