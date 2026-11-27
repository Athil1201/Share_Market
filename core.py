"""Core pipeline: data -> features -> time-split models -> backtest -> daily market scan."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import ta
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

CACHE = Path(__file__).parent / "data_cache"
CACHE.mkdir(exist_ok=True)

# Nifty 50: (display name, NSE ticker, sector)
_UNIVERSE = [
    ("Reliance", "RELIANCE", "Energy"), ("ONGC", "ONGC", "Energy"), ("NTPC", "NTPC", "Power"),
    ("Power Grid", "POWERGRID", "Power"), ("Coal India", "COALINDIA", "Mining"),
    ("TCS", "TCS", "IT"), ("Infosys", "INFY", "IT"), ("HCL Tech", "HCLTECH", "IT"),
    ("Wipro", "WIPRO", "IT"), ("Tech Mahindra", "TECHM", "IT"),
    ("HDFC Bank", "HDFCBANK", "Banking"), ("ICICI Bank", "ICICIBANK", "Banking"),
    ("SBI", "SBIN", "Banking"), ("Kotak Bank", "KOTAKBANK", "Banking"),
    ("Axis Bank", "AXISBANK", "Banking"), ("IndusInd Bank", "INDUSINDBK", "Banking"),
    ("Bajaj Finance", "BAJFINANCE", "Finance"), ("Bajaj Finserv", "BAJAJFINSV", "Finance"),
    ("Shriram Finance", "SHRIRAMFIN", "Finance"),
    ("HDFC Life", "HDFCLIFE", "Insurance"), ("SBI Life", "SBILIFE", "Insurance"),
    ("Maruti Suzuki", "MARUTI", "Auto"), ("Mahindra & Mahindra", "M&M", "Auto"),
    ("Bajaj Auto", "BAJAJ-AUTO", "Auto"), ("Eicher Motors", "EICHERMOT", "Auto"),
    ("Hero MotoCorp", "HEROMOTOCO", "Auto"), ("Tata Motors PV", "TMPV", "Auto"),
    ("Hindustan Unilever", "HINDUNILVR", "FMCG"), ("ITC", "ITC", "FMCG"),
    ("Nestle India", "NESTLEIND", "FMCG"), ("Tata Consumer", "TATACONSUM", "FMCG"),
    ("Titan", "TITAN", "Consumer"), ("Asian Paints", "ASIANPAINT", "Consumer"),
    ("Trent", "TRENT", "Consumer"), ("Eternal (Zomato)", "ETERNAL", "Consumer"),
    ("Sun Pharma", "SUNPHARMA", "Pharma"), ("Cipla", "CIPLA", "Pharma"),
    ("Dr Reddy's", "DRREDDY", "Pharma"), ("Apollo Hospitals", "APOLLOHOSP", "Healthcare"),
    ("L&T", "LT", "Infrastructure"), ("UltraTech Cement", "ULTRACEMCO", "Cement"),
    ("Grasim", "GRASIM", "Cement"), ("Adani Ports", "ADANIPORTS", "Infrastructure"),
    ("Adani Enterprises", "ADANIENT", "Conglomerate"), ("Tata Steel", "TATASTEEL", "Metals"),
    ("JSW Steel", "JSWSTEEL", "Metals"), ("Hindalco", "HINDALCO", "Metals"),
    ("Bharti Airtel", "BHARTIARTL", "Telecom"), ("Bharat Electronics", "BEL", "Defence"),
]
STOCKS = {n: f"{t}.NS" for n, t, _ in _UNIVERSE}
SECTORS = {f"{t}.NS": sec for _, t, sec in _UNIVERSE}
NAMES = {f"{t}.NS": n for n, t, _ in _UNIVERSE}
MARKET = "^NSEI"
COST_PER_TRADE = 0.001  # 0.1% per position change (brokerage + STT + charges, approx.)


def _csv(ticker):
    return CACHE / (ticker.replace("^", "").replace("&", "_") + ".csv")


IST = timezone(timedelta(hours=5, minutes=30))
REFRESH_SECONDS = 600  # while the market is open, data is refreshed every 10 minutes


def market_open(now=None):
    """NSE hours, Mon-Fri 09:15-15:30 IST, plus 20 minutes so delayed closing prices arrive.
    Exchange holidays are not known here."""
    now = now or datetime.now(IST)
    return now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) < (15, 50)


def last_close(now=None):
    """Timestamp of the most recent weekday 15:50 IST."""
    now = now or datetime.now(IST)
    t = now.replace(hour=15, minute=50, second=0, microsecond=0)
    while t > now or t.weekday() >= 5:
        t -= timedelta(days=1)
    return t.timestamp()


def _fresh(f):
    """Market open: downloaded in the last 10 minutes. Closed: downloaded after the last close."""
    if not f.exists():
        return False
    saved = f.stat().st_mtime
    return time.time() - saved < REFRESH_SECONDS if market_open() else saved >= last_close()


def save_atomic(f, write):
    """Write to a temp file, then swap it in, so a reader never sees a half-written file."""
    tmp = f.with_name(f"{f.name}.{threading.get_ident()}.tmp")
    write(tmp)
    for attempt in range(20):
        try:
            tmp.replace(f)
            return
        except PermissionError:  # Windows: the old file is being read right now
            if attempt == 19:
                raise
            time.sleep(0.1)


def latest(prefix):
    """Newest saved result (prefix_YYYY-MM-DD.pkl), or None."""
    return max(CACHE.glob(f"{prefix}_*.pkl"), default=None)


def keep_only(f, prefix):
    for old in CACHE.glob(f"{prefix}_*.pkl"):
        if old != f:
            try:
                old.unlink(missing_ok=True)
            except PermissionError:
                pass


def prefetch(tickers, start="2015-01-01", force=False):
    """Download all stale tickers in one batch request and cache each as CSV."""
    need = [t for t in dict.fromkeys(tickers) if force or not _fresh(_csv(t))]
    if not need:
        return
    try:
        data = yf.download(need, start=start, auto_adjust=True, progress=False,
                           group_by="ticker", threads=True)
    except Exception:
        return
    if not isinstance(data.columns, pd.MultiIndex):
        return
    top = set(data.columns.get_level_values(0))
    for t in need:
        if t in top:
            df = data[t].dropna()
            if len(df) > 300:
                save_atomic(_csv(t), df.to_csv)


def _download(ticker):
    f = _csv(ticker)
    if not _fresh(f):
        prefetch([ticker])
    if not f.exists():
        raise ValueError(f"No price data found for {ticker}")
    return pd.read_csv(f, index_col=0, parse_dates=True)


def build_dataset(ticker):
    """Every feature at row t uses data up to the close of day t only.
    Target at row t = 1 if close[t+1] > close[t] (the future)."""
    df = _download(ticker)
    mkt = _download(MARKET)["Close"].rename("nifty")
    d = pd.DataFrame(index=df.index)
    c = df["Close"]
    for n in (1, 5, 20):
        d[f"ret_{n}"] = c.pct_change(n)
    d["sma20_gap"] = c / c.rolling(20).mean() - 1
    d["sma50_gap"] = c / c.rolling(50).mean() - 1
    d["rsi14"] = ta.momentum.RSIIndicator(c).rsi()
    macd = ta.trend.MACD(c)
    d["macd_diff"] = macd.macd_diff() / c
    d["bb_pos"] = ta.volatility.BollingerBands(c).bollinger_pband()
    d["vol_chg"] = df["Volume"].pct_change().replace([np.inf, -np.inf], np.nan)
    d["vol_20d"] = c.pct_change().rolling(20).std()
    d = d.join(mkt.pct_change().rename("nifty_ret_1"))
    d["next_ret"] = c.pct_change().shift(-1)           # realised return of next day
    d["target"] = (d["next_ret"] > 0).astype(int)
    d["close"] = c
    d = d.dropna(subset=[x for x in d.columns if x not in ("next_ret", "target")])
    return d


def feature_cols(d):
    return [x for x in d.columns if x not in ("next_ret", "target", "close")]


def time_split(d, test_start="2023-01-01"):
    train, test = d[d.index < test_start], d[d.index >= test_start]
    # drop last row from test (no known next day) and from train
    return train.dropna(subset=["next_ret"]), test.dropna(subset=["next_ret"])


def get_models(fast=False):
    return {
        "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "Random Forest": RandomForestClassifier(n_estimators=120 if fast else 300, max_depth=5,
                                                min_samples_leaf=20, random_state=42,
                                                n_jobs=1 if fast else -1),
        "XGBoost": XGBClassifier(n_estimators=100 if fast else 200, max_depth=3, n_jobs=1, learning_rate=0.03, subsample=0.8,
                                 colsample_bytree=0.8, random_state=42, eval_metric="logloss"),
    }


def backtest(signal, next_ret, cost=COST_PER_TRADE):
    """signal[t]=1 -> hold stock on day t+1, else sit in cash. Cost on each position change."""
    signal = pd.Series(signal, index=next_ret.index).astype(float)
    trades = signal.diff().abs().fillna(signal.abs())
    strat = signal * next_ret - trades * cost
    return (1 + strat).cumprod(), int(trades.sum())


def run(ticker, test_start="2023-01-01"):
    d = build_dataset(ticker)
    train, test = time_split(d, test_start)
    cols = feature_cols(d)
    Xtr, ytr, Xte, yte = train[cols], train["target"], test[cols], test["target"]

    rows, curves, preds = [], {}, {}
    baselines = {
        "Baseline: always UP": np.ones(len(test), dtype=int),
        "Baseline: same as today": (test["ret_1"] > 0).astype(int).values,
    }
    results = dict(baselines)
    fitted = {}
    for name, m in get_models().items():
        m.fit(Xtr, ytr)
        results[name] = m.predict(Xte)
        fitted[name] = m
    bh = (1 + test["next_ret"]).cumprod()
    curves["Buy & Hold"] = bh
    for name, p in results.items():
        acc = float((p == yte.values).mean())
        eq, n = backtest(p, test["next_ret"])
        curves[name] = eq
        rows.append({"Model": name, "Accuracy": acc, "Final return": eq.iloc[-1] - 1,
                     "Trades": n, "Beats buy&hold": bool(eq.iloc[-1] > bh.iloc[-1])})
        preds[name] = p
    table = pd.DataFrame(rows).set_index("Model")
    table.loc["Buy & Hold"] = [np.nan, bh.iloc[-1] - 1, 1, False]
    latest = d.iloc[[-1]][cols]  # most recent day -> prediction for the next session
    latest_pred = {n: float(m.predict_proba(latest)[0, 1]) for n, m in fitted.items()}
    return dict(table=table, curves=pd.DataFrame(curves), latest_prob_up=latest_pred,
                latest_date=d.index[-1], fitted=fitted, cols=cols, test=test,
                up_rate=float(yte.mean()),
                mom_60=float(d["close"].iloc[-1] / d["close"].iloc[-61] - 1))


MODEL_NAMES = ["Logistic Regression", "Random Forest", "XGBoost"]


def quick_score(ticker, test_start="2023-01-01"):
    """Fit the 3 models once, measure out-of-sample accuracy, and score tomorrow. One row per stock."""
    d = build_dataset(ticker)
    train, test = time_split(d, test_start)
    if len(test) < 100 or len(train) < 300:
        raise ValueError("not enough history")
    cols = feature_cols(d)
    accs, probs = [], []
    for m in get_models(fast=True).values():
        m.fit(train[cols], train["target"])
        accs.append(float((m.predict(test[cols]) == test["target"].values).mean()))
        probs.append(float(m.predict_proba(d.iloc[[-1]][cols])[0, 1]))
    p_up, acc, up_rate = float(np.mean(probs)), float(np.mean(accs)), float(test["target"].mean())
    edge = acc - up_rate
    conf = "Some skill" if edge > 0.02 else "Weak" if edge > 0 else "None"
    c = d["close"]
    return {"Stock": NAMES.get(ticker, ticker.replace(".NS", "")), "Ticker": ticker,
            "Sector": SECTORS.get(ticker, "-"), "P(up) next day": p_up,
            "Day change": float(c.iloc[-1] / c.iloc[-2] - 1), "Week change": float(c.iloc[-1] / c.iloc[-6] - 1),
            "60-day momentum": float(c.iloc[-1] / c.iloc[-61] - 1), "Backtest accuracy": acc,
            "Edge vs always-UP": edge, "Confidence": conf, **price_levels(ticker, p_up, conf)}


def score_symbol(symbol):
    """Analyse any NSE symbol on demand (e.g. 'zomato' -> ZOMATO.NS)."""
    t = symbol.strip().upper()
    if not t.endswith(".NS") and not t.startswith("^"):
        t += ".NS"
    return quick_score(t)


def rank_all(force=False):
    """Return the last saved ranking straight away. Rebuild it only if forced or none exists."""
    saved = latest("rank")
    if saved and not force:
        return pd.read_pickle(saved)
    f = CACHE / f"rank_{date.today()}.pkl"
    prefetch(list(STOCKS.values()) + [MARKET], force=force)

    def one(t):
        try:
            return quick_score(t)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = [r for r in ex.map(one, STOCKS.values()) if r]
    df = pd.DataFrame(rows).sort_values("P(up) next day", ascending=False).reset_index(drop=True)
    save_atomic(f, df.to_pickle)
    keep_only(f, "rank")
    return df


def market_overview(rank, scan=None):
    """Daily health check of the Indian market: Nifty trend + breadth + movers + sectors + AI mood."""
    n = _download(MARKET)
    c = n["Close"]
    price, prev = float(c.iloc[-1]), float(c.iloc[-2])
    sma50, sma200 = float(c.rolling(50).mean().iloc[-1]), float(c.rolling(200).mean().iloc[-1])
    rsi = float(ta.momentum.RSIIndicator(c).rsi().iloc[-1])
    ch = {"1 day": price / prev - 1, "1 week": price / float(c.iloc[-6]) - 1,
          "1 month": price / float(c.iloc[-22]) - 1, "3 months": price / float(c.iloc[-64]) - 1}
    bd = rank if scan is None else scan          # breadth over the whole market when a full scan is given
    movers = bd if scan is None else bd[bd["Value traded (Cr/day)"] >= 10]   # ignore illiquid spikes
    adv = int((bd["Day change"] > 0).sum())
    breadth = adv / len(bd)
    ai_up = float((rank["P(up) next day"] > 0.5).mean())
    score = int(price > sma50) + int(price > sma200) + int(ch["1 month"] > 0) + int(breadth > 0.5)
    mood = "Bullish" if score >= 3 else "Bearish" if score <= 1 else "Mixed"
    reasons = [f"Nifty 50 is {'above' if price > sma50 else 'below'} its 50-day average",
               f"and {'above' if price > sma200 else 'below'} its 200-day average",
               f"{adv} of {len(bd)} stocks rose today",
               f"1-month change is {ch['1 month']:+.1%}"]
    try:
        idx_p = quick_score(MARKET)["P(up) next day"]
    except Exception:
        idx_p = None
    sectors = (rank.groupby("Sector").agg(Stocks=("Stock", "count"), Today=("Day change", "mean"),
                                          Week=("Week change", "mean"), Buy=("Signal", lambda x: int((x == "Buy").sum())))
               .sort_values("Today", ascending=False).reset_index())
    return {"price": price, "as_of": n.index[-1], "change": ch, "rsi": rsi, "sma50": sma50, "sma200": sma200,
            "advancers": adv, "decliners": len(bd) - adv, "n_stocks": len(bd), "breadth": breadth, "ai_up": ai_up,
            "mood": mood, "reasons": reasons, "index_p_up": idx_p, "sectors": sectors,
            "gainers": movers.nlargest(5, "Day change"), "losers": movers.nsmallest(5, "Day change"),
            "history": c.iloc[-250:]}


def holding_view(row, buy_price):
    """What the plan says for a stock you already own, bought at buy_price."""
    price, atr = row["Price"], row["ATR"]
    target, stop = buy_price + 3 * atr, buy_price - 2 * atr
    p = row["P(up) next day"]
    outlook = "May rise" if p >= 0.52 else "May fall" if p <= 0.48 else "Uncertain"
    if price <= stop:
        verdict, tone, msg = "SELL", "down", "Price hit your stop-loss level. Selling limits further loss."
    elif price >= target:
        verdict, tone, msg = "SELL (take profit)", "up", "Price reached your profit target. Book the gain."
    elif row["Signal"] == "Sell":
        verdict, tone, msg = "CONSIDER SELLING", "down", row["Why"]
    elif row["Signal"] == "Buy":
        verdict, tone, msg = "HOLD", "up", "Models lean up. Keep holding; sell at the target or stop-loss."
    else:
        verdict, tone, msg = "HOLD", "", "No target or stop-loss hit yet. Keep holding and check again soon."
    return {"target": target, "stop": stop, "pl_pct": price / buy_price - 1, "outlook": outlook,
            "verdict": verdict, "tone": tone, "msg": msg}


def price_levels(ticker, p_up, conf):
    """Simple, transparent price plan built from volatility (ATR), not from the ML model:
    buy zone = between the 10-day low / (price - 1 ATR) and today's price,
    target = price + 3 ATR, stop-loss = price - 2 ATR (about 1.5 : 1 reward-to-risk)."""
    df = _download(ticker)
    c = df["Close"]
    price = float(c.iloc[-1])
    atr = float(ta.volatility.AverageTrueRange(df["High"], df["Low"], c).average_true_range().iloc[-1])
    rsi = float(ta.momentum.RSIIndicator(c).rsi().iloc[-1])
    low10 = float(df["Low"].iloc[-10:].min())
    buy_from = max(low10, price - atr)
    if p_up <= 0.48 or rsi >= 75:
        signal = "Sell"
        why = ("Models lean down for tomorrow." if p_up <= 0.48
               else "Price has run up very fast (overbought); a pullback is common.")
    elif p_up >= 0.52 and conf != "None" and rsi < 70:
        signal = "Buy"
        why = "Models lean up and have shown some skill on this stock; price is not overheated."
    else:
        signal = "Wait"
        why = "No clear signal. The models are near 50/50 or have shown no skill on this stock."
    return {"Price": price, "As of": df.index[-1], "ATR": atr, "RSI": rsi,
            "Buy from": buy_from, "Buy up to": price,
            "Sell target": price + 3 * atr, "Stop-loss": price - 2 * atr,
            "52w low": float(c.iloc[-252:].min()), "52w high": float(c.iloc[-252:].max()),
            "Signal": signal, "Why": why}


def price_history(ticker, days=250):
    """For charts: use the saved copy so the page doesn't wait. Download only if there is none."""
    f = _csv(ticker)
    df = pd.read_csv(f, index_col=0, parse_dates=True) if f.exists() else _download(ticker)
    return df["Close"].iloc[-days:]
