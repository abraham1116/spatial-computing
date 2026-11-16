"""Pricing, usage rating and payment.

PRICING IS A CONFIGURATION, NOT A FACT: the defaults below are an example price list so the dashboard has
something to show. Set your real prices with --pricing-file (JSON) before charging anybody.

Payment goes through Stripe Checkout when STRIPE_SECRET_KEY is set. Without it, the "Pay" action is
refused with a clear message: nothing is ever marked paid without a payment provider confirming it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

DEFAULT_PRICING = {
    "currency": "usd",
    "note": "Example price list: the operator has not set real prices yet.",
    "free_compute_hours_per_month": 1.0,
    "compute_usd_per_hour": 0.10,                  # per hour of task wall time on the fleet
    "min_invoice_usd": 0.50,                       # below this the period is waived (no tiny charges)
    "tax_label": "VAT",
    "tax_rate_percent": 0.0,                       # default rate added to every invoice
    "tax_by_country": {},                          # {"FR": 20, "DE": 19}: overrides the default rate by the customer's billing country
    "no_tax_with_vat_id_abroad": False,            # simplified B2B reverse charge: a customer with a VAT id outside the seller's country pays no tax
}

PRICING_KEYS = {"currency": str, "note": str, "free_compute_hours_per_month": (int, float), "compute_usd_per_hour": (int, float), "min_invoice_usd": (int, float),
                "tax_label": str, "tax_rate_percent": (int, float), "tax_by_country": dict, "no_tax_with_vat_id_abroad": bool}


def validate_pricing(d: dict) -> dict:
    """Return a clean pricing dict or raise ValueError. Bounds keep a typo from charging 1000x."""
    out = dict(DEFAULT_PRICING)
    for k, v in d.items():
        if k not in PRICING_KEYS:
            raise ValueError(f"unknown pricing field '{k}'")
        if isinstance(v, bool) != (PRICING_KEYS[k] is bool) or not isinstance(v, PRICING_KEYS[k]):
            raise ValueError(f"'{k}' has the wrong type")
        out[k] = v
    if not (isinstance(out["currency"], str) and len(out["currency"]) == 3 and out["currency"].isalpha()):
        raise ValueError("currency must be a 3-letter code")
    for k, lo, hi in (("free_compute_hours_per_month", 0, 100000), ("compute_usd_per_hour", 0, 1000), ("min_invoice_usd", 0, 1000), ("tax_rate_percent", 0, 50)):
        if not lo <= out[k] <= hi:
            raise ValueError(f"'{k}' must be between {lo} and {hi}")
    for c, r in out["tax_by_country"].items():
        if not (isinstance(c, str) and len(c) == 2 and c.isalpha() and isinstance(r, (int, float)) and not isinstance(r, bool) and 0 <= r <= 50):
            raise ValueError("tax_by_country must map 2-letter country codes to rates between 0 and 50")
    out["tax_by_country"] = {c.upper(): r for c, r in out["tax_by_country"].items()}
    out["currency"] = out["currency"].lower()
    return out


@dataclass
class Pricing:
    data: dict = field(default_factory=lambda: dict(DEFAULT_PRICING))

    def __post_init__(self):
        self.data = {**DEFAULT_PRICING, **self.data}          # fields added in later versions keep their defaults

    @classmethod
    def load(cls, path: str | None) -> "Pricing":
        d = dict(DEFAULT_PRICING)
        if path:
            d.update(json.load(open(path)))
        return cls(d)

    def rate(self, seconds_by_app: dict[int, float]) -> dict:
        """Cost of one period. The free allowance is shared by the whole account, applied app by app in id order."""
        free = self.data["free_compute_hours_per_month"] * 3600
        lines, total = [], 0.0
        for app_id in sorted(seconds_by_app):
            sec = seconds_by_app[app_id]
            billable = max(0.0, sec - free)
            free = max(0.0, free - sec)
            cost = round(billable / 3600 * self.data["compute_usd_per_hour"], 4)
            lines.append({"app_id": app_id, "seconds": round(sec, 3), "billable_seconds": round(billable, 3), "usd": cost})
            total += cost
        return {"lines": lines, "total_usd": round(total, 4)}


class PaymentError(Exception):
    pass


class Stripe:
    """Stripe Checkout over plain HTTPS (no SDK). `api_base` is overridable for tests."""

    def __init__(self, secret_key: str | None, webhook_secret: str | None, api_base: str = "https://api.stripe.com"):
        self.key, self.whsec, self.base = secret_key, webhook_secret, api_base

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def checkout_url(self, invoice_id: int, amount_usd: float, email: str, success_url: str, cancel_url: str, currency: str = "usd") -> tuple[str, str]:
        if not self.key:
            raise PaymentError("payments are not configured on this server (no STRIPE_SECRET_KEY)")
        cents = int(round(amount_usd * 100))
        if cents < 50:
            raise PaymentError("amount is below the payment provider's minimum")
        form = urllib.parse.urlencode({
            "mode": "payment", "success_url": success_url, "cancel_url": cancel_url, "customer_email": email,
            "client_reference_id": str(invoice_id), "metadata[invoice_id]": str(invoice_id),
            "line_items[0][quantity]": "1", "line_items[0][price_data][currency]": currency,
            "line_items[0][price_data][unit_amount]": str(cents),
            "line_items[0][price_data][product_data][name]": f"Spatial Computing usage, invoice {invoice_id}"}).encode()
        req = urllib.request.Request(self.base + "/v1/checkout/sessions", data=form, method="POST",
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=15))
        except Exception as e:
            raise PaymentError(f"payment provider error: {type(e).__name__}") from e
        return r["url"], r["id"]

    def verify_webhook(self, payload: bytes, header: str, tolerance_s: int = 300, now: float | None = None) -> dict:
        """Check the Stripe-Signature header (t=..,v1=hmac_sha256(secret, 't.payload')) and return the event."""
        if not self.whsec:
            raise PaymentError("webhook secret not configured")
        try:
            parts = dict(p.split("=", 1) for p in header.split(","))
            t, sig = int(parts["t"]), parts["v1"]
        except Exception:
            raise PaymentError("malformed signature header")
        expected = hmac.new(self.whsec.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise PaymentError("bad signature")
        if abs((now or time.time()) - t) > tolerance_s:
            raise PaymentError("signature too old")
        return json.loads(payload)
