"""Design-system brief + frontend detection.

Lives in its own module (only depends on models) so both the executor — which
injects the brief into the first-pass worker prompt — and the quality gate —
which re-injects it on refine — can share it without a circular import.
"""

from __future__ import annotations

from .models import Job

WEB_HINTS = ("website", "webseite", "landing", "html", "homepage", "shop", "webshop", "seite")


def wants_web(job: Job, filenames: tuple[str, ...] = ()) -> bool:
    """Cheap pre-execution guess (used to inject the brief into the prompt)."""
    if any(n.lower().endswith((".html", ".htm")) for n in filenames):
        return True
    return any(h in job.body.lower() for h in WEB_HINTS)


def is_frontend(job: Job, files: dict[str, str]) -> bool:
    """Post-execution check: did we actually produce a web frontend?"""
    if any(name.lower().endswith((".html", ".htm")) for name in files):
        return True
    return any(h in job.body.lower() for h in WEB_HINTS)


def design_system_prompt() -> str:
    """A strong, opinionated brief injected for web jobs. Topic-agnostic but
    forces modern, production-grade output instead of a bare template."""
    return (
        "\n## Design system (MANDATORY for any web output)\n"
        "Build a modern, polished, production-grade site — never a bare template.\n"
        "- LAYOUT: mobile-first, responsive with CSS grid/flexbox; a centred "
        "max-width container (~1100px); generous whitespace on an 8px spacing scale.\n"
        "- COLOR: define a cohesive palette in :root CSS variables that FITS THE "
        "TOPIC (e.g. an organic farm → warm earthy greens, cream, a ripe accent). "
        "Never default to plain Arial on white.\n"
        "- TYPOGRAPHY: load a tasteful Google-Fonts pairing via <link> (a display "
        "font for headings + a readable sans for body), line-height >=1.5, a clear "
        "type scale.\n"
        "- POLISH: soft shadows, rounded corners, smooth 150-250ms hover/focus "
        "transitions, visible :focus-visible outlines.\n"
        "- IMAGERY (STRICT): NEVER use an <img> tag or any external/file image URL "
        "— they break. Represent ALL visuals with INLINE SVG (icons, simple "
        "illustrations) or CSS (gradients, shapes, background patterns) only. A card "
        "'photo' = a tasteful CSS gradient block or an inline SVG, never <img>.\n"
        "- LANGUAGE: write EVERY piece of visible text (headings, nav, buttons, "
        "labels, product names, footer) in the SAME language as the task. Do not mix "
        "languages.\n"
        "- COMPLETENESS: implement EVERY concrete item the task names (e.g. each "
        "listed product/section). If the task lists products, create a card for each "
        "one with a realistic name, short description and a price.\n"
        "- FUNCTIONALITY: if the task implies ordering/booking/cart, build it for "
        "REAL in script.js — a product grid with per-item prices, add-to-cart using "
        "localStorage, a live cart count AND line items, a running total that updates, "
        "and a working order/checkout form with validation. No dead buttons.\n"
        "- ACCESSIBILITY: semantic HTML5 landmarks, labelled form controls, >=4.5:1 "
        "contrast; inline SVGs need role=img + an aria-label or <title>.\n"
        "Split code into index.html + styles.css + script.js."
    )
