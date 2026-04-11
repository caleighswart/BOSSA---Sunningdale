"""
Bossa Sunningdale — Prep Engine
================================
Reads PilotLive stock rows and generates a prioritised prep list
for the head chef.

Items are classified as:
  URGENT   — stock < urgent_pct of par  (do before anything else)
  TODAY    — stock < low_pct of par     (must prep today)
  STOCKED  — at or above low par        (no action needed)
"""

from prep_config import PREP_ITEMS, EXCLUDE


def _total_soh(rows, cats):
    """Sum stock on hand across all items in the given categories."""
    return sum(
        r["soh"]
        for r in rows
        if r["cat"] in cats and r["cat"] not in EXCLUDE and r["soh"] > 0
    )


def analyse_prep(rows):
    """
    Evaluate each prep item against current stock.

    Returns:
        urgent  — list of dicts: items needing immediate action
        today   — list of dicts: items to prep today
        stocked — list of str:  item labels that are fine
    """
    urgent, today, stocked = [], [], []

    for item in PREP_ITEMS:
        soh = _total_soh(rows, item["cats"])
        par = item["par"]
        pct = soh / par if par else 0

        entry = {
            "label":  item["label"],
            "action": item["action"],
            "unit":   item["unit"],
            "soh":    soh,
            "par":    par,
            "pct":    pct,
            "note":   item.get("note"),
        }

        if pct < item["urgent_pct"]:
            urgent.append(entry)
        elif pct < item["low_pct"]:
            today.append(entry)
        else:
            stocked.append(item["label"])

    # Sort urgent and today by % of par ascending (worst first)
    urgent.sort(key=lambda x: x["pct"])
    today.sort(key=lambda x: x["pct"])

    return urgent, today, stocked


def _fmt(val, unit):
    if unit == "kg":
        return f"{val:.1f} kg"
    v = int(val) if val == int(val) else round(val, 1)
    return f"{v} {unit}"


def _b(text):
    return f"<b>{text}</b>"


def _it(text):
    return f"<i>{text}</i>"


def build_prep_brief(urgent, today, stocked, report_date, brief_date, service_start, prep_deadline):
    from datetime import datetime
    day = datetime.strptime(brief_date, "%Y-%m-%d").strftime("%a %-d %b %Y")

    lines = [
        f"👨‍🍳 {_b('BOSSA SUNNINGDALE — DAILY PREP')}",
        f"📅 {day}  |  PilotLive: {report_date}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── URGENT ────────────────────────────────────────────────────────────────
    lines.append(f"\n🔴 {_b('URGENT — Do first')}\n")
    if urgent:
        for e in urgent:
            needed = max(0, e["par"] - e["soh"])
            action_line = (
                f"{_b(e['label'])}: {e['action']} {_fmt(needed, e['unit'])} "
                f"(only {_fmt(e['soh'], e['unit'])} left, par {_fmt(e['par'], e['unit'])})"
            )
            lines.append(action_line)
            if e["note"]:
                lines.append(f"  {_it(e['note'])}")
    else:
        lines.append("  None — all proteins & sauces well stocked ✅")

    # ── TODAY'S PREP ──────────────────────────────────────────────────────────
    lines.append(f"\n🟡 {_b(\"TODAY'S PREP\")}\n")
    if today:
        for e in today:
            needed = max(0, e["par"] - e["soh"])
            action_line = (
                f"{_b(e['label'])}: {e['action']} {_fmt(needed, e['unit'])} "
                f"({_fmt(e['soh'], e['unit'])} in stock)"
            )
            lines.append(action_line)
            if e["note"]:
                lines.append(f"  {_it(e['note'])}")
    else:
        lines.append("  Nothing extra — kitchen is well set up ✅")

    # ── STOCKED ───────────────────────────────────────────────────────────────
    if stocked:
        lines.append(f"\n✅ {_b('STOCKED — No action needed')}")
        lines.append(f"  {', '.join(stocked)}")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ Prep target: ready by {prep_deadline}  |  Service: {service_start}",
        _it("Bossa Prep Bot"),
    ]

    return "\n".join(lines)
