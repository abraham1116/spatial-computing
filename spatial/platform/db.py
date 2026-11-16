"""SQLite store. One connection guarded by a lock: enough for one service process; swap for Postgres behind
the same functions when you need several."""
from __future__ import annotations

import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL,
  created REAL NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, ip TEXT, ua TEXT);
CREATE TABLE IF NOT EXISTS apps(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  budget_usd REAL, created REAL NOT NULL, deleted REAL);
CREATE TABLE IF NOT EXISTS api_keys(
  id INTEGER PRIMARY KEY, app_id INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, cred_name TEXT NOT NULL,
  hint TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, revoked REAL);
CREATE TABLE IF NOT EXISTS usage(
  id INTEGER PRIMARY KEY, app_id INTEGER NOT NULL, ts REAL NOT NULL, workload TEXT, node TEXT, ok INTEGER, seconds REAL NOT NULL);
CREATE INDEX IF NOT EXISTS usage_app_ts ON usage(app_id, ts);
CREATE TABLE IF NOT EXISTS offsets(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, period TEXT NOT NULL, amount_usd REAL NOT NULL, status TEXT NOT NULL,
  lines TEXT NOT NULL, created REAL NOT NULL, paid REAL, provider_ref TEXT, UNIQUE(user_id, period));
CREATE TABLE IF NOT EXISTS resets(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, to_addr TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL, sent REAL);
CREATE TABLE IF NOT EXISTS tokens(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, hint TEXT NOT NULL,
  scope TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, last_used REAL, revoked REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL NOT NULL, user_id INTEGER, kind TEXT NOT NULL, detail TEXT);
"""


class DB:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)

    def q(self, sql: str, args=()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, args=()):
        r = self.q(sql, args)
        return r[0] if r else None

    def x(self, sql: str, args=()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            return cur.lastrowid

    def event(self, user_id, kind: str, detail: str = "") -> None:
        self.x("INSERT INTO events(ts,user_id,kind,detail) VALUES(?,?,?,?)", (time.time(), user_id, kind, detail[:500]))
