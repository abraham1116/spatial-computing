"""Outgoing e-mail: a queue in the database, delivered by SMTP with retries. Nothing is sent without SMTP settings;
messages then stay in the outbox (visible to the operator) instead of being lost."""
from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage

MAX_ATTEMPTS = 6


class Mailer:
    def __init__(self, db, smtp: dict | None, clock=time.time):
        self.db, self.smtp, self.clock = db, smtp, clock

    def queue(self, to: str, subject: str, body: str) -> int:
        mid = self.db.x("INSERT INTO outbox(to_addr,subject,body,created,next_try) VALUES(?,?,?,?,?)", (to, subject, body, self.clock(), 0))
        self.deliver(mid)
        return mid

    def _send(self, to: str, subject: str, body: str) -> None:
        c = self.smtp
        m = EmailMessage(); m["From"], m["To"], m["Subject"] = c["from"], to, subject; m.set_content(body)
        if c.get("ssl"):
            s = smtplib.SMTP_SSL(c["host"], c.get("port", 465), timeout=15, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(c["host"], c.get("port", 587), timeout=15)
        with s:
            if c.get("starttls", True) and not c.get("ssl"):
                s.starttls(context=ssl.create_default_context())
            if c.get("user"):
                s.login(c["user"], c["password"])
            s.send_message(m)

    def deliver(self, mid: int) -> bool:
        r = self.db.one("SELECT * FROM outbox WHERE id=?", (mid,))
        if not r or r["sent"] is not None or not self.smtp:
            return False
        try:
            self._send(r["to_addr"], r["subject"], r["body"])
        except Exception as e:
            n = r["attempts"] + 1
            self.db.x("UPDATE outbox SET attempts=?, last_error=?, next_try=? WHERE id=?",
                      (n, f"{type(e).__name__}: {e}"[:200], self.clock() + min(3600, 30 * 2 ** n), mid))
            return False
        self.db.x("UPDATE outbox SET sent=?, attempts=attempts+1, last_error=NULL WHERE id=?", (self.clock(), mid))
        return True

    def flush(self) -> int:
        """Retry unsent messages that are due (called every minute by the service). Returns how many were sent."""
        if not self.smtp:
            return 0
        n = 0
        for r in self.db.q("SELECT id FROM outbox WHERE sent IS NULL AND attempts<? AND next_try<=? ORDER BY id LIMIT 50", (MAX_ATTEMPTS, self.clock())):
            n += self.deliver(r["id"])
        return n
