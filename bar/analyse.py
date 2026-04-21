"""
Bossa Sunningdale — Bar Stock Analysis Engine
==============================================
Matches PilotLive products to Sava's bar count par levels and generates
the daily bar brief shown on Telegram.

Matching strategy:
  - Normalize both sides: lowercase, collapse whitespace, strip stray
    apostrophe/accent differences.
  - PilotLive product names and Sava's bar count use identical
    "xx - name" formatting, so the match rate should be very high.
  - Any PilotLive product in a bar category that doesn't match the
    par sheet is reported under "Unmatched products".
  - Any par-sheet product without a par value is reported under
    "Par missing".

Data source:
  Live SSRS pull ONLY. No Excel fallback — the bar bot never sends a
  stale brief. If SSRS is unreachable the run fails loudly so Caleigh
  sees the failure in the GitHub Actions log.
"""

import os
import re
import sys
from datetime import datetime

from config import (
    BAR_CATEGORIES, CATEGORY_LABELS, CATEGORY_ORDER,
    CRITICAL_PCT, LOW_PCT, VARIANCE_CUTOFF,
    IGNORE_MISSING_PAR, load_pars,
)


# ── NAME NORMALISATION ────────────────────────────────────────────────────────
def _norm(name: str) -> str:
    """Lowercase, collapse whitespace, drop the 'zz ' sort-prefix."""
    if not name:
        return ""
    s = name.lower().strip()
    # Some PilotLive rows are prefixed "zz " for sort ordering
    if s.startswith("zz "):
        s = s[3:].strip()
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def load_data() -> tuple[list[dict], str]:
    """
    Pull live stock from PilotLive SSRS. This is the ONLY data source —
    we intentionally do not fall back to any cached Excel snapshot so the
    bar team never receives a stale brief.

    Raises SystemExit if credentials are missing or SSRS is unreachable.
    """
    username = os.getenv("PILOTLIVE_USERNAME")
    password = os.getenv("PILOTLIVE_PASSWORD")

    if not (username and password):
        print("❌ PILOTLIVE_USERNAME / PILOTLIVE_PASSWORD not set.")
        print("   The bar bot only uses live SSRS data. Aborting.")
        sys.exit(1)

    from pilotfetch import fetch_bar_rows
    print("Fetching live data from SSRS...")
    rows, title = fetch_bar_rows(username, password)
    print(f"  Loaded {len(rows)} items — {title}")
    return rows, title


# ── CORE ANALYSIS ─────────────────────────────────────────────────────────────
def analyse(rows: list[dict]) -> dict:
    """
    Match PilotLive rows against par sheet and classify each product.

    Returns a dict with keys:
        by_cat       — {cat: {"critical": [...], "low": [...], "healthy": [...],
                               "variance": [...]}}
        unmatched    — list of (cat, name, soh) in categories Sava tracks where
                       the PilotLive product doesn't appear on her par sheet
        missing_par  — list of par-sheet products that have no par value set
        total_value  — sum of stock value for tracked categories only
        tracked_cats — set of categories Sava tracks (>=1 par entry on sheet)
    """
    pars = load_pars()           # {name: par_or_None}
    pars_norm = { _norm(k): (k, v) for k, v in pars.items() }

    # Build list of categories Sava actually tracks by infering from the
    # prefix of each par-sheet product name.
    PREFIX_TO_CAT = {
        "dr": "DRAUGHT", "be": "BEER", "ci": "CIDER", "cb": "CBEV",
        "lq": "LIQUEUR", "px": "PREMIX", "ps": "PORTSHERRY",
        "br": "BRANDY", "ru": "RUM", "wh": "WHISKEY", "ws": "WHITE SPIR",
        "sw": "SWINE", "ww": "WWINE", "rw": "RWINE",
        "pa": "PACKAGING", "waka": "VAPES", "puff": "VAPES",
        "hb": "HBEV", "so": "LIQUEUR", "sj": "HBEV",
    }
    cat_counts: dict[str, int] = {}
    for name in pars:
        m = re.match(r"^([a-z]+)\s*-", name.lower())
        if m and m.group(1) in PREFIX_TO_CAT:
            c = PREFIX_TO_CAT[m.group(1)]
            cat_counts[c] = cat_counts.get(c, 0) + 1
    tracked_cats: set[str] = set(cat_counts.keys()) & BAR_CATEGORIES
    # Only flag unmatched ("new products") for categories Sava tracks extensively
    # (>=3 par items) — avoids spam for categories where she only tracks one item
    # like PACKAGING (straws only).
    unmatched_report_cats = {c for c, n in cat_counts.items() if n >= 3} & BAR_CATEGORIES

    by_cat: dict[str, dict] = {}
    unmatched: list[tuple[str, str, float]] = []
    total_value = 0.0

    for r in rows:
        if r["cat"] not in tracked_cats:
            continue
        total_value += r["value"]
        n = _norm(r["name"])
        entry = pars_norm.get(n)
        if entry is None:
            # Only surface unmatched in categories Sava tracks extensively
            if r["cat"] in unmatched_report_cats:
                unmatched.append((r["cat"], r["name"], r["soh"]))
            continue

        par_key, par = entry
        if par is None or par == 0:
            # Par missing — handled separately below
            continue

        soh = r["soh"]
        pct = soh / par if par else 0

        bucket = by_cat.setdefault(r["cat"], {
            "critical": [], "low": [], "healthy": [], "variance": [],
        })
        item = {"name": r["name"], "soh": soh, "par": par, "pct": pct}

        if soh < VARIANCE_CUTOFF:
            bucket["variance"].append(item)
        elif 0 <= soh < par * CRITICAL_PCT:
            bucket["critical"].append(item)
        elif par * CRITICAL_PCT <= soh < par * LOW_PCT:
            bucket["low"].append(item)
        else:
            bucket["healthy"].append(item)

    # Sort each bucket by worst pct first
    for cat, b in by_cat.items():
        b["critical"].sort(key=lambda x: x["pct"])
        b["low"].sort(key=lambda x: x["pct"])

    # Par missing = items on the sheet without a par, minus any the user has chosen to ignore
    missing_par = sorted([
        name for name, par in pars.items()
        if par is None and name not in IGNORE_MISSING_PAR
    ])

    return {
        "by_cat":       by_cat,
        "unmatched":    unmatched,
        "missing_par":  missing_par,
        "total_value":  total_value,
        "tracked_cats": tracked_cats,
    }


# ── BRIEF BUILDING ────────────────────────────────────────────────────────────
def _nice(name: str) -> str:
    """Strip the 'xx - ' prefix and Title Case the remainder."""
    parts = name.split(" - ", 1)
    n = parts[-1].strip() if len(parts) > 1 else name
    n = n.strip()
    return (n[0].upper() + n[1:]) if n else n


def _b(text):
    return f"<b>{text}</b>"


def _it(text):
    return f"<i>{text}</i>"


def _fmt(val: float) -> str:
    if val == int(val):
        return str(int(val))
    return f"{val:.1f}"


def build_brief(result: dict, report_date: str, brief_date: str) -> str:
    by_cat      = result["by_cat"]
    unmatched   = result["unmatched"]
    missing_par = result["missing_par"]
    total_value = result["total_value"]

    day = datetime.strptime(brief_date, "%Y-%m-%d").strftime("%a %-d %b %Y")
    lines = [
        f"🍾 {_b('BOSSA SUNNINGDALE — BAR STOCK BRIEF')}",
        f"📅 {day}  |  PilotLive: {report_date}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── CRITICAL ─────────────────────────────────────────────────────────────
    lines += [f"\n🔴 {_b('CRITICAL — Order today')} {_it('(&lt; 30% par)')}\n"]
    any_crit = False
    for cat in CATEGORY_ORDER:
        b = by_cat.get(cat)
        if not b or not b["critical"]:
            continue
        any_crit = True
        label = CATEGORY_LABELS.get(cat, cat)
        items = b["critical"]
        if len(items) == 1:
            it = items[0]
            lines.append(
                f"{_b(label)}: {_nice(it['name'])} — "
                f"{_fmt(it['soh'])} / {_fmt(it['par'])}"
            )
        elif len(items) <= 4:
            lines.append(f"{_b(label)} ({len(items)} items):")
            for it in items:
                lines.append(f"  • {_nice(it['name'])}: {_fmt(it['soh'])} / {_fmt(it['par'])}")
        else:
            lines.append(f"{_b(label)} — {len(items)} items critical:")
            for it in items[:3]:
                lines.append(f"  • {_nice(it['name'])}: {_fmt(it['soh'])} / {_fmt(it['par'])}")
            lines.append(f"  {_it(f'+ {len(items) - 3} more')}")
    if not any_crit:
        lines.append("  None ✅")

    # ── LOW ──────────────────────────────────────────────────────────────────
    lines += [f"\n🟡 {_b('LOW — Watch closely')} {_it('(30–70% par)')}\n"]
    any_low = False
    for cat in CATEGORY_ORDER:
        b = by_cat.get(cat)
        if not b or not b["low"]:
            continue
        any_low = True
        label = CATEGORY_LABELS.get(cat, cat)
        items = b["low"]
        if len(items) == 1:
            it = items[0]
            lines.append(
                f"{_b(label)}: {_nice(it['name'])} — "
                f"{_fmt(it['soh'])} / {_fmt(it['par'])}"
            )
        elif len(items) <= 3:
            lines.append(f"{_b(label)} ({len(items)} items):")
            for it in items:
                lines.append(f"  • {_nice(it['name'])}: {_fmt(it['soh'])} / {_fmt(it['par'])}")
        else:
            worst = items[0]
            lines.append(
                f"{_b(label)} — {len(items)} items low "
                f"(worst: {_nice(worst['name'])} at {_fmt(worst['soh'])}/{_fmt(worst['par'])})"
            )
    if not any_low:
        lines.append("  None ✅")

    # ── HEALTHY ──────────────────────────────────────────────────────────────
    healthy_cats = [
        CATEGORY_LABELS.get(cat, cat)
        for cat in CATEGORY_ORDER
        if (b := by_cat.get(cat)) and not b["critical"] and not b["low"] and b["healthy"]
    ]
    if healthy_cats:
        lines += [f"\n✅ {_b('ALL GOOD')}\n  {', '.join(healthy_cats)}"]

    # ── VARIANCES ────────────────────────────────────────────────────────────
    all_var = [
        (CATEGORY_LABELS.get(cat, cat), it)
        for cat, b in by_cat.items() for it in b["variance"]
    ]
    if all_var:
        lines += [f"\n⚠️ {_b('VARIANCES — Investigate')}\n"]
        for label, it in sorted(all_var, key=lambda x: x[1]["soh"]):
            lines.append(f"  • {_nice(it['name'])} ({label}): {it['soh']:.0f}")

    # ── PAR MISSING ──────────────────────────────────────────────────────────
    if missing_par:
        lines += [
            f"\n❓ {_b('PAR MISSING — Set par levels')} "
            f"{_it(f'({len(missing_par)} items)')}\n"
        ]
        # Show up to 15, group the rest
        show = missing_par[:15]
        for name in show:
            lines.append(f"  • {name}")
        if len(missing_par) > 15:
            lines.append(f"  {_it(f'+ {len(missing_par) - 15} more')}")

    # ── UNMATCHED (new products in PilotLive, not on Sava's sheet) ──────────
    if unmatched:
        lines += [
            f"\n🆕 {_b('NEW PRODUCTS — Add to bar count sheet')} "
            f"{_it(f'({len(unmatched)} items)')}\n"
        ]
        for cat, name, soh in unmatched[:10]:
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"  • {name} ({label}): {_fmt(soh)} soh")
        if len(unmatched) > 10:
            lines.append(f"  {_it(f'+ {len(unmatched) - 10} more')}")

    # ── FOOTER ───────────────────────────────────────────────────────────────
    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 {_b(f'Bar stock value: R{total_value:,.0f}')}",
        _it("Bossa Bar Stock Agent"),
    ]

    return "\n".join(lines)
