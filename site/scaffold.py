"""Shared scaffolding for the bilingual static site (English at the root, French under /fr/).
Language modules (content_en.py, content_fr.py) call into this one; build.py drives them.
Command outputs shown on the site come from data/outputs.txt, captured from real runs."""
from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).parent
REPO = "https://github.com/abraham1116/spatial-computing"
E = html.escape

OUT: dict[str, str] = {}
_cur = None
for _line in (ROOT / "data/outputs.txt").read_text().splitlines():
    if _line.startswith("### "):
        _cur = _line[4:].strip()
        OUT[_cur] = []
    elif _cur:
        OUT[_cur].append(_line)
OUT = {k: "\n".join(v).strip("\n") for k, v in OUT.items()}

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">')

# Set by build.py before calling a language module.
CFG: dict = {}


def alt_url(is_doc: bool, key: str) -> str:
    """URL of the same page in the other language, relative to the current page."""
    if CFG["lang"] == "en":
        return f"../fr/docs/{key}.html" if is_doc else "fr/index.html"
    return f"../../docs/{key}.html" if is_doc else "../index.html"


def head(title, desc, base, alt):
    p = CFG["prefix"] + base
    other = "fr" if CFG["lang"] == "en" else "en"
    return (f'<!doctype html><html lang="{CFG["lang"]}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{E(title)}</title><meta name="description" content="{E(desc)}">'
            f'<link rel="alternate" hreflang="{other}" href="{alt}">'
            f'<link rel="icon" href="{p}assets/logo.svg" type="image/svg+xml">{FONTS}<link rel="stylesheet" href="{p}assets/style.css"></head>')


def nav(base, active, alt):
    ui, p = CFG["ui"], CFG["prefix"] + base

    def a(href, label, key, cls=""):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a href="{base}{href}"{cur} class="{cls}">{label}</a>'
    other = "FR" if CFG["lang"] == "en" else "EN"
    other_name = "Français" if CFG["lang"] == "en" else "English"
    return (f'<header class="nav"><div class="wrap"><a class="brand" href="{base}index.html"><img src="{p}assets/logo.svg" alt="">Spatial Computing</a>'
            f'<nav aria-label="{ui["nav_label"]}">{a("docs/index.html", "Docs", "docs")}{a("index.html#proof", ui["proof"], "p", "hide-sm")}'
            f'<a class="hide-sm" href="{REPO}" rel="noopener">GitHub</a>'
            f'<a class="lang" href="{alt}" hreflang="{other.lower()}" lang="{other.lower()}" title="{other_name}">{other}</a>'
            f'<a class="btn" href="{base}docs/quickstart.html">{ui["install"]}</a></nav></div></header>')


def out_block(key, n=None):
    t = OUT[key]
    if n:
        t = "\n".join(t.splitlines()[:n])
    return E(t)


def rail(items):
    return "".join(f'<h5>{E(t)}</h5><pre>{c}</pre>' for t, c in items)


def doc(key, title, lead, body, panels):
    order, titles, groups = CFG["order"], CFG["titles"], CFG["nav_groups"]
    i = order.index(key)
    prev = f'<a href="{order[i-1]}.html">← {titles[order[i-1]]}</a>' if i > 0 else "<span></span>"
    nxt = f'<a href="{order[i+1]}.html">{titles[order[i+1]]} →</a>' if i < len(order) - 1 else "<span></span>"
    side = "".join(f'<h4>{g}</h4>' + "".join(
        f'<a href="{k}.html"' + (' aria-current="page"' if k == key else "") + f'>{t}</a>' for k, t in items) for g, items in groups)
    alt = alt_url(True, key)
    page = head(f"{title} — Spatial Computing docs", lead, "../", alt) + "<body>" + nav("../", "docs", alt)
    page += (f'<div class="docs"><aside class="side" aria-label="{CFG["ui"]["docs_label"]}">{side}</aside>'
             f'<main class="main"><h1>{title}</h1><p class="lead" style="margin-bottom:8px">{lead}</p>{body}<div class="pager">{prev}{nxt}</div></main>'
             f'<aside class="rail" aria-label="{CFG["ui"]["examples_label"]}">{rail(panels)}</aside></div>'
             f'<script src="{CFG["prefix"]}../assets/app.js"></script></body></html>')
    out = CFG["out"] / "docs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{key}.html").write_text(page)
