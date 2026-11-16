"""VAT identification numbers: format for the EU, UK, Switzerland and Norway; the check digit where the algorithm is public and
simple (AT, BE, DE, DK, FR, IT, PL, PT); and an optional online check against the European Commission's VIES service.
A passing offline check means "well formed", not "registered": only VIES (or the tax authority) says that."""
from __future__ import annotations

import json
import re
import urllib.request

FORMATS = {
    "AT": r"U\d{8}", "BE": r"[01]\d{9}", "BG": r"\d{9,10}", "CY": r"\d{8}[A-Z]", "CZ": r"\d{8,10}", "DE": r"\d{9}", "DK": r"\d{8}",
    "EE": r"\d{9}", "EL": r"\d{9}", "GR": r"\d{9}", "ES": r"[A-Z0-9]\d{7}[A-Z0-9]", "FI": r"\d{8}", "FR": r"[A-HJ-NP-Z0-9]{2}\d{9}", "HR": r"\d{11}",
    "HU": r"\d{8}", "IE": r"\d{7}[A-Z]{1,2}|\d[A-Z+*]\d{5}[A-Z]", "IT": r"\d{11}", "LT": r"\d{9}|\d{12}", "LU": r"\d{8}", "LV": r"\d{11}",
    "MT": r"\d{8}", "NL": r"\d{9}B\d{2}", "PL": r"\d{10}", "PT": r"\d{9}", "RO": r"\d{2,10}", "SE": r"\d{12}", "SI": r"\d{8}", "SK": r"\d{10}",
    "XI": r"\d{9}|\d{12}|GD\d{3}|HA\d{3}", "GB": r"\d{9}|\d{12}|GD\d{3}|HA\d{3}", "CH": r"E\d{9}(MWST|TVA|IVA)", "NO": r"\d{9}MVA",
}


def _luhn_ok(digits: str) -> bool:
    s = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            d = d - 9 if d > 9 else d
        s += d
    return s % 10 == 0


def _checksum(cc: str, n: str) -> bool | None:
    """True/False when the algorithm is implemented for this country, None when it is not."""
    try:
        if cc == "FR" and n[:2].isdigit():
            return int(n[:2]) == (12 + 3 * (int(n[2:]) % 97)) % 97
        if cc == "DE":
            p = 10
            for ch in n[:8]:
                s = (int(ch) + p) % 10 or 10
                p = (2 * s) % 11
            return (11 - p) % 10 == int(n[8]) if (11 - p) != 10 else int(n[8]) == 0
        if cc == "IT":
            return _luhn_ok(n)
        if cc == "BE":
            return 97 - int(n[:8]) % 97 == int(n[8:])
        if cc == "DK":
            return sum(int(c) * w for c, w in zip(n, (2, 7, 6, 5, 4, 3, 2, 1))) % 11 == 0
        if cc == "PL":
            s = sum(int(c) * w for c, w in zip(n[:9], (6, 5, 7, 2, 3, 4, 5, 6, 7))) % 11
            return s != 10 and s == int(n[9])
        if cc == "PT":
            s = sum(int(c) * w for c, w in zip(n[:8], (9, 8, 7, 6, 5, 4, 3, 2)))
            r = 11 - s % 11
            return (0 if r > 9 else r) == int(n[8])
        if cc == "AT":
            d = n[1:]
            s = sum((int(c) * (1 if i % 2 == 0 else 2) // 10 + int(c) * (1 if i % 2 == 0 else 2) % 10) for i, c in enumerate(d[:7]))
            return (96 - s) % 10 == int(d[7])
    except (ValueError, IndexError):
        return False
    return None


def parse(raw: str) -> tuple[str, str]:
    s = re.sub(r"[\s.\-]", "", (raw or "")).upper()
    return s[:2], s[2:]


def check(raw: str) -> dict:
    cc, n = parse(raw)
    if cc not in FORMATS:
        return {"ok": False, "reason": "unknown country prefix (use two letters, e.g. FR123456789)", "country": cc, "number": n, "checksum": "not checked"}
    if not re.fullmatch(FORMATS[cc], n):
        return {"ok": False, "reason": f"not a valid {cc} VAT number format", "country": cc, "number": n, "checksum": "not checked"}
    c = _checksum(cc, n)
    if c is False:
        return {"ok": False, "reason": f"the check digit of this {cc} number is wrong", "country": cc, "number": n, "checksum": "bad"}
    return {"ok": True, "reason": "", "country": cc, "number": n, "checksum": "ok" if c else "not checked for this country"}


VIES = "https://ec.europa.eu/taxation_customs/vies/rest-api"


def vies(raw: str, base: str = VIES, timeout: float = 8.0) -> bool | None:
    """True/False from the Commission's VIES service, None when it cannot answer (unreachable, member-state service down)."""
    cc, n = parse(raw)
    if cc not in FORMATS or cc in ("GB", "CH", "NO", "XI"):
        return None                                                    # VIES covers EU members only
    try:
        d = json.load(urllib.request.urlopen(f"{base}/ms/{'EL' if cc == 'GR' else cc}/vat/{n}", timeout=timeout))
    except Exception:
        return None
    v = d.get("isValid", d.get("valid"))
    return bool(v) if v is not None else None
