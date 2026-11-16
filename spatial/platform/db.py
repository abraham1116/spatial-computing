"""SQLite store. One connection guarded by a lock: enough for one service process; swap for Postgres behind
the same functions when you need several."""
from __future__ import annotations

import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL,
  created REAL NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
  email_verified INTEGER NOT NULL DEFAULT 0, totp_secret TEXT, totp_enabled INTEGER NOT NULL DEFAULT 0, totp_last_step INTEGER NOT NULL DEFAULT 0,
  recovery TEXT NOT NULL DEFAULT '[]', personal_org INTEGER);
CREATE TABLE IF NOT EXISTS orgs(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL, personal INTEGER NOT NULL DEFAULT 0,
  billing_name TEXT NOT NULL DEFAULT '', billing_address TEXT NOT NULL DEFAULT '', billing_country TEXT NOT NULL DEFAULT '', vat_id TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS members(org_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(org_id, user_id));
CREATE TABLE IF NOT EXISTS invites(
  id INTEGER PRIMARY KEY, org_id INTEGER NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, invited_by INTEGER NOT NULL,
  created REAL NOT NULL, expires REAL NOT NULL, accepted REAL);
CREATE TABLE IF NOT EXISTS verifications(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS challenges(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, ip TEXT, ua TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS counters(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, ip TEXT, ua TEXT);
CREATE TABLE IF NOT EXISTS apps(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  budget_usd REAL, created REAL NOT NULL, deleted REAL, org_id INTEGER);
CREATE TABLE IF NOT EXISTS api_keys(
  id INTEGER PRIMARY KEY, app_id INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, cred_name TEXT NOT NULL,
  hint TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, revoked REAL);
CREATE TABLE IF NOT EXISTS usage(
  id INTEGER PRIMARY KEY, app_id INTEGER NOT NULL, ts REAL NOT NULL, workload TEXT, node TEXT, ok INTEGER, seconds REAL NOT NULL);
CREATE INDEX IF NOT EXISTS usage_app_ts ON usage(app_id, ts);
CREATE TABLE IF NOT EXISTS offsets(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, period TEXT NOT NULL, amount_usd REAL NOT NULL, status TEXT NOT NULL,
  lines TEXT NOT NULL, created REAL NOT NULL, paid REAL, provider_ref TEXT, org_id INTEGER, number TEXT, subtotal_usd REAL, tax_rate REAL, tax_usd REAL,
  billing TEXT, seller TEXT);
CREATE TABLE IF NOT EXISTS resets(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, to_addr TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL, sent REAL,
  attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0, last_error TEXT);
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
            self._migrate()

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

    # ------------------------------------------------------------------ migration of databases created by older versions
    ADD = {"users": [("email_verified", "INTEGER NOT NULL DEFAULT 0"), ("totp_secret", "TEXT"), ("totp_enabled", "INTEGER NOT NULL DEFAULT 0"),
                     ("totp_last_step", "INTEGER NOT NULL DEFAULT 0"), ("recovery", "TEXT NOT NULL DEFAULT '[]'"), ("personal_org", "INTEGER")],
           "apps": [("org_id", "INTEGER")],
           "invoices": [("org_id", "INTEGER"), ("number", "TEXT"), ("subtotal_usd", "REAL"), ("tax_rate", "REAL"), ("tax_usd", "REAL"), ("billing", "TEXT"), ("seller", "TEXT")],
           "outbox": [("attempts", "INTEGER NOT NULL DEFAULT 0"), ("next_try", "REAL NOT NULL DEFAULT 0"), ("last_error", "TEXT")]}

    def _migrate(self) -> None:
        for table, cols in self.ADD.items():
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        # the unique (user_id, period) constraint of the first version is replaced by (org_id, period)
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS invoices_org_period ON invoices(org_id, period)")
        now = time.time()
        for u in self.conn.execute("SELECT id, name FROM users WHERE personal_org IS NULL").fetchall():       # one personal organisation per user
            oid = self.conn.execute("INSERT INTO orgs(name,created,personal) VALUES(?,?,1)", (u["name"] + "'s workspace", now)).lastrowid
            self.conn.execute("INSERT INTO members(org_id,user_id,role,created) VALUES(?,?,?,?)", (oid, u["id"], "owner", now))
            self.conn.execute("UPDATE users SET personal_org=? WHERE id=?", (oid, u["id"]))
        self.conn.execute("UPDATE apps SET org_id=(SELECT personal_org FROM users WHERE users.id=apps.user_id) WHERE org_id IS NULL")
        self.conn.execute("UPDATE invoices SET org_id=(SELECT personal_org FROM users WHERE users.id=invoices.user_id) WHERE org_id IS NULL")
