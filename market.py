"""Whole-NSE scan (all ~2,400 listed equities) + live quotes.

Tier 1 (every stock): price, change, trend, RSI, ATR levels -> rule-based signal. Fast.
Tier 2 (Nifty 50 + any stock you open): the ML models from core.py -> chance of rising tomorrow.
"""
import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from functools import partial

import numpy as np
import pandas as pd
import requests
import ta
import yfinance as yf

from core import (CACHE, IST, NAMES, REFRESH_SECONDS, SECTORS, keep_only, last_close, latest, market_open,
                  rank_all, save_atomic)

log = logging.getLogger(__name__)

EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CHUNK = 150


def universe():
    """All NSE-listed equities (EQ series). Cached for a week; falls back to the Nifty 50 list."""
    f = CACHE / "equity_list.csv"
    if not f.exists() or time.time() - f.stat().st_mtime > 7 * 86400:
        try:
            r = requests.get(EQUITY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = [c.strip() for c in df.columns]
            df = df[df["SERIES"].str.strip() == "EQ"][["SYMBOL", "NAME OF COMPANY"]]
            df.to_csv(f, index=False)
        except Exception:
            if not f.exists():
                return pd.DataFrame({"SYMBOL": [t.replace(".NS", "") for t in NAMES],
                                     "NAME OF COMPANY": list(NAMES.values())})
    return pd.read_csv(f)


def _one(sym, df, names):
    df = df.dropna(subset=["Close"])
    if len(df) < 120:
        return None
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    price = float(c.iloc[-1])
    if price < 5 or float((c * v).iloc[-20:].mean()) < 2e6:  # skip penny / illiquid names
        return None
    atr = float(ta.volatility.AverageTrueRange(h, l, c).average_true_range().iloc[-1])
    rsi = float(ta.momentum.RSIIndicator(c).rsi().iloc[-1])
    sma50 = float(c.rolling(50).mean().iloc[-1])
    m1 = float(price / c.iloc[-22] - 1)
    low10 = float(l.iloc[-10:].min())
    t = f"{sym}.NS"
    if rsi >= 75 or (price < sma50 and m1 < -0.08):
        sig, why = "Sell", ("Price rose very fast (overbought); a pullback is common." if rsi >= 75
                            else "Price is in a downtrend (below its 50-day average).")
    elif price > sma50 and 45 <= rsi < 68 and m1 > 0:
        sig, why = "Buy", "Price is trending up, not overheated."
    else:
        sig, why = "Wait", "No clear trend signal."
    return {"Stock": names.get(sym, sym), "Ticker": t, "Sector": SECTORS.get(t, "-"), "Price": price,
            "Day change": float(price / c.iloc[-2] - 1), "Week change": float(price / c.iloc[-6] - 1),
            "Month change": m1, "RSI": rsi, "ATR": atr, "Buy from": max(low10, price - atr), "Buy up to": price,
            "Sell target": price + 3 * atr, "Stop-loss": price - 2 * atr,
            "52w low": float(c.iloc[-252:].min()), "52w high": float(c.iloc[-252:].max()),
            "Signal": sig, "Why": why, "As of": df.index[-1], "Value traded (Cr/day)": float((c * v).iloc[-20:].mean() / 1e7)}


def _chunk(syms, names):
    try:
        data = yf.download([f"{s}.NS" for s in syms], period="1y", auto_adjust=True, progress=False,
                           group_by="ticker", threads=True)
    except Exception:
        return []
    if not isinstance(data.columns, pd.MultiIndex):
        return []
    top, out = set(data.columns.get_level_values(0)), []
    for s in syms:
        t = f"{s}.NS"
        if t in top:
            try:
                r = _one(s, data[t], names)
                if r:
                    out.append(r)
            except Exception:
                pass
    return out


def scan_all(force=False, progress=None, workers=3):
    """Return the last saved scan straight away. Scan every NSE equity only if forced or none exists."""
    saved = latest("scan")
    if saved and not force:
        return pd.read_pickle(saved)
    f = CACHE / f"scan_{date.today()}.pkl"
    u = universe()
    names = dict(zip(u["SYMBOL"], u["NAME OF COMPANY"].str.title()))
    names.update({t.replace(".NS", ""): n for t, n in NAMES.items()})
    syms = list(u["SYMBOL"])
    chunks = [syms[i:i + CHUNK] for i in range(0, len(syms), CHUNK)]
    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda c: _chunk(c, names), chunks):
            rows += res
            done += 1
            if progress:
                progress(done / len(chunks))
    # a scan with many stocks missing (offline, or Yahoo blocking us) must not replace a good one
    if not rows or (saved and len(rows) < 0.8 * len(pd.read_pickle(saved))):
        raise RuntimeError("Market scan incomplete: could not download enough stocks.")
    df = pd.DataFrame(rows).sort_values("Value traded (Cr/day)", ascending=False).reset_index(drop=True)
    save_atomic(f, df.to_pickle)
    keep_only(f, "scan")
    return df


def live_quotes(tickers):
    """Latest 1-minute prices (Yahoo, delayed up to ~15 min). Returns {ticker: (price, prev_close)}."""
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    out = {}
    try:
        d = yf.download(tickers, period="5d", interval="1m", auto_adjust=False, progress=False,
                        group_by="ticker", threads=True, prepost=False)
    except Exception:
        return out
    multi = isinstance(d.columns, pd.MultiIndex)
    for t in tickers:
        try:
            x = (d[t] if multi else d)["Close"].dropna()
            days = x.index.normalize()
            last_day = days[-1]
            prev = x[days < last_day]
            out[t] = (float(x.iloc[-1]), float(prev.iloc[-1]) if len(prev) else float(x.iloc[0]), x.index[-1])
        except Exception:
            continue
    return out


def scan_exists():
    """True if any saved scan (today's or older) can be shown."""
    return latest("scan") is not None


_job, _started = None, 0.0
_lock = threading.Lock()


def _due():
    """Is it time for another refresh?"""
    now = time.time()
    saved = [f.stat().st_mtime for f in (latest("scan"), latest("rank")) if f]
    if not saved or now - _started < REFRESH_SECONDS:
        return False
    if market_open():  # every 10 minutes, counted from the start of the previous refresh
        return bool(_started) or now - min(saved) >= REFRESH_SECONDS
    return min(saved) < last_close()  # closed: only until the closing prices are saved


def _refresh():
    for name, build in (("scan", partial(scan_all, workers=1)),  # one batch at a time: app stays responsive
                        ("rank", partial(rank_all, force=True))):
        try:
            build(force=True) if name == "scan" else build()
        except Exception:
            log.exception("Background refresh of %s failed; keeping the old data", name)


def refresh_in_background():
    """Start a refresh if one is due, without blocking the app. Returns True while one is running."""
    global _job, _started
    with _lock:
        running = _job is not None and _job.is_alive()
        if not running and _due():
            _job, _started = threading.Thread(target=_refresh, daemon=True), time.time()
            _job.start()
            running = True
        return running


def data_version():
    """Changes whenever new results are saved (used as the app's cache key)."""
    return tuple((f.name, f.stat().st_mtime) for f in (latest("scan"), latest("rank")) if f)


def updated_at():
    """When the saved market scan was made (India time), or None."""
    f = latest("scan")
    return datetime.fromtimestamp(f.stat().st_mtime, IST) if f else None
