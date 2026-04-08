"""
Bossa Sunningdale — Stock Analysis Engine
Reads PilotLive data (API or Excel fallback) and generates the morning brief.
"""

import pandas as pd
import os
from datetime import datetime
from config import GROUPS, EXCLUDE


def load_from_excel(path):
    df = pd.read_excel(path, sheet_name="Theoretical Stock On Hand", header=None)
    rows, current_cat = [], None
    for i, row in df.iterrows():
        vals = list(row)
        if i < 7:
            continue
        c1, c2, c3, c9, c10 = vals[1], vals[2], vals[3], vals[9], vals[10]
        if str(c1) != "nan" and str(c2) == "nan" and str(c3) == "nan":
            current_cat = str(c1).strip()
            continue
        if str(c1) == "nan" and str(c2) != "nan":
            try:
                rows.append({
                    "cat":   current_cat,
                    "name":  str(c2).strip(),
                    "cost":  float(c3)  if str(c3)  != "nan" else 0,
                    "soh":   float(c9)  if str(c9)  != "nan" else 0,
                    "value": float(c10) if str(c10) != "nan" else 0,
                })
            except Exception:
                pass
    return rows


def load_data():
    """
    Load stock data from Pilot Cloud (if credentials available) or fall back to
    the most recent Excel file in inventory/data/.
    """
    username = os.getenv("PILOTLIVE_USERNAME")
    password = os.getenv("PILOTLIVE_PASSWORD")

    if username and password:
        from pilotcloud import download_stock_report
        print("Logging into Pilot Cloud...")
        path = download_stock_report(username, password)
        print(f"Downloaded: {os.path.basename(path)}")
        return load_from_excel(path)

    # Excel fallback — looks for most recent file in data/
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    xlsx_files = sorted(
        [f for f in os.listdir(data_dir) if f.endswith(".xlsx")],
        reverse=True
    )
    if not xlsx_files:
        raise FileNotFoundError(
            "No Excel file found in inventory/data/ and PILOTLIVE_USERNAME/PASSWORD not set."
        )
    path = os.path.join(data_dir, xlsx_files[0])
    print(f"Using Excel file: {xlsx_files[0]}")
    return load_from_excel(path)


def nice(name):
    parts = name.split(" - ", 1)
    n = parts[-1].strip() if len(parts) > 1 else name
    n = n.lstrip("zz ").strip()
    return (n[0].upper() + n[1:]) if n else n


def fmt(val, unit):
    if unit == "kg":
        return f"{val:.1f}kg"
    if unit == "bottles":
        v = int(val) if val == int(val) else round(val, 1)
        return f"{v} btl"
    v = int(val) if val == int(val) else round(val, 1)
    return str(v)


def b(text):
    return f"<b>{text}</b>"


def it(text):
    return f"<i>{text}</i>"


def analyse(rows):
    """Run stock analysis and return group results + total value."""
    group_results = {}
    total_value = 0

    for group, (cats, par, unit) in GROUPS.items():
        items = [r for r in rows if r["cat"] in cats and r["cat"] not in EXCLUDE and r["cost"] > 0]
        if not items:
            continue
        total_value += sum(r["value"] for r in items if r["soh"] >= 0)
        critical = sorted(
            [(r["name"], r["soh"]) for r in items if 0 <= r["soh"] < par * 0.30],
            key=lambda x: x[1] / par
        )
        low = sorted(
            [(r["name"], r["soh"]) for r in items if par * 0.30 <= r["soh"] < par * 0.70],
            key=lambda x: x[1] / par
        )
        variance = [(r["name"], r["soh"]) for r in items if r["soh"] < -5]
        healthy = len(items) - len(critical) - len(low) - len(variance)
        group_results[group] = {
            "critical": critical, "low": low, "variance": variance,
            "healthy": healthy, "par": par, "unit": unit,
        }

    return group_results, total_value


def build_brief(group_results, total_value, report_date, brief_date):
    lines = []
    day = datetime.strptime(brief_date, "%Y-%m-%d").strftime("%a %-d %b %Y")
    lines += [
        f"🏪 {b('BOSSA SUNNINGDALE — STOCK BRIEF')}",
        f"📅 {day}  |  PilotLive: {report_date}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # CRITICAL
    lines += [f"\n🔴 {b('CRITICAL — Order today')} {it('(&lt; 30% par)')}\n"]
    any_crit = False
    for g, d in group_results.items():
        if not d["critical"]:
            continue
        any_crit = True
        n, par, unit = len(d["critical"]), d["par"], d["unit"]
        if n == 1:
            name, soh = d["critical"][0]
            lines.append(f"{b(g)}: {nice(name)} — {fmt(soh, unit)} remaining (par {fmt(par, unit)})")
        elif n <= 4:
            lines.append(f"{b(g)} ({n} items):")
            for name, soh in d["critical"]:
                lines.append(f"  • {nice(name)}: {fmt(soh, unit)}")
        else:
            lines.append(f"{b(g)} — {n} items critical:")
            for name, soh in d["critical"][:3]:
                lines.append(f"  • {nice(name)}: {fmt(soh, unit)}")
            lines.append(f"  {it(f'+ {n - 3} more')}")
    if not any_crit:
        lines.append("  None ✅")

    # LOW
    lines += [f"\n🟡 {b('LOW — Watch closely')} {it('(30–70% par)')}\n"]
    any_low = False
    for g, d in group_results.items():
        if not d["low"]:
            continue
        any_low = True
        n, par, unit = len(d["low"]), d["par"], d["unit"]
        if n == 1:
            name, soh = d["low"][0]
            lines.append(f"{b(g)}: {nice(name)} — {fmt(soh, unit)} (par {fmt(par, unit)})")
        elif n <= 3:
            lines.append(f"{b(g)} ({n} items):")
            for name, soh in d["low"]:
                lines.append(f"  • {nice(name)}: {fmt(soh, unit)}")
        else:
            worst = d["low"][0]
            lines.append(f"{b(g)} — {n} items low (worst: {nice(worst[0])} at {fmt(worst[1], unit)})")
    if not any_low:
        lines.append("  None ✅")

    # HEALTHY
    healthy_groups = [g for g, d in group_results.items() if not d["critical"] and not d["low"] and d["healthy"] > 0]
    if healthy_groups:
        lines += [f"\n✅ {b('ALL GOOD')}\n  {', '.join(healthy_groups)}"]

    # VARIANCES
    all_var = [(g, name, soh) for g, d in group_results.items() for name, soh in d["variance"]]
    if all_var:
        lines += [f"\n⚠️ {b('VARIANCES — Investigate')}\n"]
        for g, name, soh in sorted(all_var, key=lambda x: x[2]):
            lines.append(f"  • {nice(name)} ({g}): {soh:.0f}")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 {b(f'Stock value: R{total_value:,.0f}')}",
        it("Bossa Predictive Inventory Agent"),
    ]

    return "\n".join(lines)
