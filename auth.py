"""Simple user accounts: SQLite + salted PBKDF2 password hashes."""
import hashlib
import hmac
import os
import re
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "users.db"


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt BLOB, hash BLOB)")
    return c


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


def register(username, password):
    """Returns (ok, message)."""
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,20}", username):
        return False, "Username: 3-20 letters, digits or underscore."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    salt = os.urandom(16)
    try:
        with _conn() as c:
            c.execute("INSERT INTO users VALUES (?,?,?)", (username, salt, _hash(password, salt)))
    except sqlite3.IntegrityError:
        return False, "Username already taken."
    return True, "Account created. You can log in now."


def login(username, password):
    with _conn() as c:
        row = c.execute("SELECT salt, hash FROM users WHERE username=?",
                        (username.strip().lower(),)).fetchone()
    return bool(row) and hmac.compare_digest(row[1], _hash(password, row[0]))
