"""
Bossa Sunningdale — Prep Variance Engine
=========================================
Analyses PilotLive variance data for prep categories and builds
the chef's daily variance report.

Variance = (Opening + Purchases − TheoreticalUsage) − ClosingStock
  Negative → used MORE than theory  (wastage / over-portioning / theft)
  Positive → used LESS than theory  (under-portioning / sales not rung in)
"""

from datetime import datetime
from prep_config import PREP_CATEGORIES, MIN_VARIANCE, HIGH_VARIANCE_PCT, WATCH_VARIANCE_PCT


def analyse_variances(rows):
    """
    Filter rows to prep categories and classify by variance severity.

    Returns:
        high   — list of dicts: variance > HIGH_VARIANCE_PCT of theoretical usage
        watch  — list of dicts: variance between WATCH and HIGH pct
        clean  — list of str:  item names with no significant variance
    """
    high, watch, clean = [], [], []

    for r in rows:
        if r["cat"] not in PREP_CATEGORIES:
            continue
        if r["theoretical_usage"] <= 0:
            continue

        v   = r["variance"]
        pct = abs(v) / r["theoretical_usage"] if r["theoretical_usage"] else 0

        if abs(v) < MIN_VARIANCE:
            clean.append(_nice(r["name"]))
            continue

        entry = {
            "name":    _nice(r["name"]),
            "cat":     r["cat"],
            "theory":  r["theoretical_usage"],
            "soh":     r["soh"],
            "variance": v,
            "pct":     pct,
        }

        if pct >= HIGH_VARIANCE_PCT:
            high.append(entry)
        elif pct >= WATCH_VARIANCE_PCT:
            watch.append(entry)
        else:
            clean.append(_nice(r["name"]))

    # Sort worst variance first (most negative = most over-used)
    high.sort(key=lambda x: x["variance"])
    watch.sort(key=lambda x: x["variance"])

    return high, watch, clean


def _nice(name):
    parts = name.split(" - ", 1)
    n = parts[-1].strip() if len(parts) > 1 else name
    n = n.lstrip("zz ").strip()
    return (n[0].upper() + n[1:]) if n else n


def _b(text):
    return f"<b>{text}</b>"


def _it(text):
    return f"<i>{text}</i>"


def _sign(v):
    return f"+{v:.1f}" if v > 0 else f"{v:.1f}"


def build_variance_brief(high, watch, clean, report_date, brief_date):
    day = datetime.strptime(brief_date, "%Y-%m-%d").strftime("%a %-d %b %Y")

    lines = [
        f"👨‍🍳 {_b('BOSSA SUNNINGDALE — PREP VARIANCES')}",
        f"📅 {day}  |  PilotLive: {report_date}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # HIGH
    lines.append(f"\n🔴 {_b('HIGH VARIANCE — Investigate')}\n")
    if high:
        for e in high:
            direction = "over-used" if e["variance"] < 0 else "under-used"
            detail = _it("{}, {:.0f}% off".format(direction, abs(e["pct"]) * 100))
            lines.append(
                f"{_b(_nice(e['name']))} ({e['cat']}): "
                f"{_sign(e['variance'])} vs theory "
                f"({detail})"
            )
    else:
        lines.append("  None ✅")

    # WATCH
    lines.append(f"\n🟡 {_b('WATCH')}\n")
    if watch:
        for e in watch:
            direction = "over-used" if e["variance"] < 0 else "under-used"
            detail = _it("{}, {:.0f}% off".format(direction, abs(e["pct"]) * 100))
            lines.append(
                f"{_b(_nice(e['name']))} ({e['cat']}): "
                f"{_sign(e['variance'])} "
                f"({detail})"
            )
    else:
        lines.append("  None ✅")

    # CLEAN
    if clean:
        lines.append(f"\n✅ {_b('ON TARGET')}")
        lines.append(f"  {', '.join(clean)}")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━",
        _it("Bossa Prep Bot"),
    ]

    return "\n".join(lines)
