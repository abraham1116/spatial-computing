"""Builds the bilingual static site. Run: python3 build.py
English is the default language (site root); French is generated under fr/."""
from __future__ import annotations

import scaffold
import content_en
import content_fr

ROOT = scaffold.ROOT


def build(lang: str, mod, out, prefix: str):
    nav_groups = mod.NAV_GROUPS
    scaffold.CFG.clear()
    scaffold.CFG.update(
        lang=lang, prefix=prefix, out=out, ui=mod.UI, nav_groups=nav_groups,
        order=[k for _, items in nav_groups for k, _ in items],
        titles={k: t for _, items in nav_groups for k, t in items},
    )
    mod.landing()
    mod.docs()


if __name__ == "__main__":
    build("en", content_en, ROOT, "")
    build("fr", content_fr, ROOT / "fr", "../")
    pages = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*.html"))
    print(len(pages), "pages:", *pages[:3], "…")
