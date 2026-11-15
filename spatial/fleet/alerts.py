"""Alerts from the hub's recommendations: edge-triggered (a condition alerts once when it appears and
once when it clears), optional webhook. Nothing leaves this machine unless a webhook URL is given."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

RANK = {"low": 0, "medium": 1, "high": 2}


def key_of(r: dict) -> str:
    return f"{r['kind']}:{r.get('node') or ','.join(r.get('nodes_to_free', []))}"


class AlertEngine:
    def __init__(self, min_severity: str = "high", clock=time.time):
        if min_severity not in RANK:
            raise ValueError("min_severity must be low, medium or high")
        self.min_rank, self.clock = RANK[min_severity], clock
        self.firing: dict[str, dict] = {}
        self.history: list[dict] = []                       # newest last, capped

    def update(self, recommendations: list[dict]) -> list[dict]:
        """Feed the current recommendations; returns the events produced by this update."""
        now, events = self.clock(), []
        current = {key_of(r): r for r in recommendations if RANK.get(r.get("severity"), 0) >= self.min_rank}
        for k, r in current.items():
            if k not in self.firing:
                self.firing[k] = {"since": now, **r}
                events.append({"event": "firing", "key": k, "ts": now, "severity": r["severity"], "text": r["text"]})
        for k in [k for k in self.firing if k not in current]:
            old = self.firing.pop(k)
            events.append({"event": "resolved", "key": k, "ts": now, "severity": old["severity"], "text": old["text"],
                           "lasted_s": now - old["since"]})
        self.history = (self.history + events)[-200:]
        return events


def post_webhook(url: str, event: dict, timeout: float = 5.0) -> None:
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError("webhook must be an http(s) URL")
    req = urllib.request.Request(url, data=json.dumps(event).encode(), headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=timeout).read()
