"""Per-user holdings ("Your buys"), stored in SQLite next to the user accounts."""
import sqlite3
from datetime import date

import pandas as pd

from auth import DB


def _conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ticker TEXT, qty REAL,
        buy_price REAL, buy_date TEXT)""")
    return c


def add(username, ticker, qty, buy_price, buy_date=None):
    with _conn() as c:
        c.execute("INSERT INTO holdings (username, ticker, qty, buy_price, buy_date) VALUES (?,?,?,?,?)",
                  (username, ticker, float(qty), float(buy_price), str(buy_date or date.today())))


def remove(username, holding_id):
    with _conn() as c:
        c.execute("DELETE FROM holdings WHERE id=? AND username=?", (int(holding_id), username))


def listing(username):
    with _conn() as c:
        return pd.read_sql_query("SELECT id, ticker, qty, buy_price, buy_date FROM holdings "
                                 "WHERE username=? ORDER BY id DESC", c, params=(username,))
